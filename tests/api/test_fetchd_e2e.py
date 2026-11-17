"""JPSE Phase 2 acceptance: jp-fetchd (C) produces exactly the catalogue the Python crawler produces.

Runs only with PostgreSQL (TEST_POSTGRES_URL) and the built image (JPF_IMAGE, e.g. jobpilot-fetchd:dev). The fake job
boards are the same fixtures the Python tests use, served on 127.0.0.1 with ETags; jp-fetchd is run in test mode
(JPF_TEST_ORIGIN), the only mode in which it will talk to a loopback address.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from ats_fixtures import Boards, greenhouse_board

IMAGE = os.environ.get("JPF_IMAGE", "")
pytestmark = pytest.mark.skipif(not (os.environ.get("TEST_POSTGRES_URL") and IMAGE and shutil.which("docker")),
                                reason="needs TEST_POSTGRES_URL, JPF_IMAGE and docker")
COMPANIES = [("greenhouse", "acmefintech", "Acme Fintech"), ("lever", "betapay", "Beta Pay"), ("ashby", "gammaco", "Gamma Co"),
             ("smartrecruiters", "DeltaWorks", "Delta Works"), ("recruitee", "epsilonpay", "Epsilon Pay")]


class EtagBoards(Boards):
    def handler(self, request: httpx.Request) -> httpx.Response:
        resp = super().handler(request)
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
            tag = '"' + hashlib.md5(resp.content).hexdigest() + '"'
            if request.headers.get("if-none-match") == tag:
                return httpx.Response(304, headers={"etag": tag})
            resp.headers["etag"] = tag
        return resp


def _serve(boards: EtagBoards):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802  /<host>/<path>  ->  https://<host>/<path>
            req = httpx.Request("GET", "https:/" + self.path, headers=dict(self.headers))
            resp = boards.handler(req)
            self.send_response(resp.status_code)
            for k, v in resp.headers.items():
                if k.lower() not in ("content-length", "transfer-encoding", "connection", "content-encoding"):
                    self.send_header(k, v)
            body = resp.content
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _run_fetchd(port: int) -> str:
    url = os.environ["TEST_POSTGRES_URL"].replace("postgresql+psycopg://", "postgresql://")
    p = subprocess.run(["docker", "run", "--rm", "--network", "host", "-e", f"JPF_DATABASE_URL={url}", "-e", "JPF_ONCE=1",
                        "-e", f"JPF_TEST_ORIGIN=http://127.0.0.1:{port}", "-e", "JPF_BUDGET_S=60", IMAGE],
                       capture_output=True, text=True, timeout=180)
    assert p.returncode == 0, p.stderr
    return p.stderr


def _catalogue(db):
    from backend.models import CataloguePosting

    return {p.source_key: (p.content_hash, p.title, p.location_normalized, p.closed_at is None)
            for p in db.query(CataloguePosting).all()}


def _due_now(db):
    from backend.models import CrawlState
    from backend.services.crawler import service as crawler

    db.query(CrawlState).update({CrawlState.next_due_at: crawler.utcnow() - timedelta(minutes=1), CrawlState.cooldown_until: None})
    db.commit()


def test_fetchd_produces_the_same_catalogue_as_the_python_crawler(client, monkeypatch):
    from backend.db import session_factory
    from backend.models import CataloguePosting, Company, CrawlRawItem, CrawlResult, CrawlState, IndexOutbox
    from backend.services.ats import base
    from backend.services.crawler import fetchd
    from backend.services.crawler import service as crawler

    boards = EtagBoards()
    monkeypatch.setattr(crawler, "FEEDS", ())
    db = session_factory()()
    try:
        for ats, token, name in COMPANIES:
            db.add(Company(name=name, ats=ats, board_token=token, origin="curated", enabled=True))
        db.commit()
        # 1. The reference: the Python crawler over the mocked APIs.
        monkeypatch.setattr(base, "transport_override", boards.transport())
        assert crawler.crawl(db)["ok"] == len(COMPANIES)
        reference = _catalogue(db)
        assert len(reference) >= 8
        for model in (IndexOutbox, CataloguePosting, CrawlRawItem, CrawlResult):
            db.query(model).delete()
        db.query(CrawlState).delete()
        db.commit()

        # 2. The same boards through jp-fetchd (C), applied by the Python applier.
        monkeypatch.setenv("JPSE_FETCHD", "1")
        crawler.sync_targets(db)
        srv = _serve(boards)
        try:
            log = _run_fetchd(srv.server_port)
            assert "status=ok" in log
            rep = fetchd.apply_pending(db)
            assert rep["applied"] == len(COMPANIES) and rep["failed"] == 0, rep
            db.expire_all()
            assert _catalogue(db) == reference  # same keys, same content hashes, same normalised facts

            # 3. Again, immediately: ETags answer 304 (SmartRecruiters is paginated, so it is fetched in full and found
            #    byte-identical). Nothing changes, no outbox event.
            events = db.query(IndexOutbox).count()
            _due_now(db)
            log = _run_fetchd(srv.server_port)
            assert log.count("status=not_modified") == len(COMPANIES) - 1 and "status=unchanged" in log
            assert fetchd.apply_pending(db)["applied"] == len(COMPANIES)
            assert db.query(IndexOutbox).count() == events

            # 4. A posting leaves a board: only it is sent as changed (the rest as unchanged ids) and only it closes.
            boards.payloads[("greenhouse", "acmefintech")] = greenhouse_board(include_101=False)
            _due_now(db)
            _run_fetchd(srv.server_port)
            assert db.query(CrawlResult).filter(CrawlResult.state == "pending").count() == len(COMPANIES)
            fetchd.apply_pending(db)
            db.expire_all()
            closed = {p.source_key for p in db.query(CataloguePosting).filter(CataloguePosting.closed_at.is_not(None))}
            assert closed == {"greenhouse:acmefintech:101"}
        finally:
            srv.shutdown()
    finally:
        db.close()
