"""JPSE Phase 3 acceptance: jp-searchd (C) agrees exactly with PostgreSQL on filters and follows changes within seconds.

Runs only with PostgreSQL (TEST_POSTGRES_URL) and the built image (JPS_IMAGE, e.g. jobpilot-searchd:dev).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid

import pytest

IMAGE = os.environ.get("JPS_IMAGE", "")
pytestmark = pytest.mark.skipif(not (os.environ.get("TEST_POSTGRES_URL") and IMAGE and shutil.which("docker")),
                                reason="needs TEST_POSTGRES_URL, JPS_IMAGE and docker")


def test_searchd_matches_postgres_and_follows_changes(client, tmp_path, monkeypatch):
    from test_catalogue_crawler import EtagBoards

    from backend.db import session_factory
    from backend.models import CataloguePosting, Company, IndexOutbox
    from backend.services import search_engine as se
    from backend.services.ats import base
    from backend.services.crawler import service as crawler

    boards = EtagBoards()
    monkeypatch.setattr(base, "transport_override", boards.transport())
    monkeypatch.setattr(crawler, "FEEDS", ())
    db = session_factory()()
    name = f"jps-test-{uuid.uuid4().hex[:8]}"
    sockdir = tmp_path / "run"
    sockdir.mkdir()
    sockdir.chmod(0o777)
    try:
        for ats, token, cname in (("greenhouse", "acmefintech", "Acme"), ("lever", "betapay", "Beta"), ("ashby", "gammaco", "Gamma"),
                                  ("smartrecruiters", "DeltaWorks", "Delta"), ("recruitee", "epsilonpay", "Epsilon")):
            db.add(Company(name=cname, ats=ats, board_token=token, origin="curated", enabled=True))
        db.commit()
        crawler.crawl(db)
        url = os.environ["TEST_POSTGRES_URL"].replace("postgresql+psycopg://", "postgresql://")
        subprocess.run(["docker", "run", "-d", "--name", name, "--network", "host", "-v", f"{sockdir}:/run/jpse",
                        "-e", f"JPS_DATABASE_URL={url}", "-e", "JPS_REFRESH_S=1", IMAGE], check=True, capture_output=True)
        monkeypatch.setattr(se, "SOCKET", str(sockdir / "searchd.sock"))
        for _ in range(100):
            if se.engine_health().get("ready"):
                break
            time.sleep(0.2)
        assert se.engine_health().get("ready"), subprocess.run(["docker", "logs", name], capture_output=True, text=True).stderr
        total = db.query(CataloguePosting).filter(CataloguePosting.closed_at.is_(None)).count()
        assert se.engine_health()["docs"] == total
        for f in (dict(), dict(countries=["IN"]), dict(work_modes=["Remote"]), dict(sources=["lever", "ashby"]),
                  dict(countries=["IN"], remote_open_to=["IN", "*"]), dict(countries=["ZZ"])):
            q = se.Query(limit=500, **f)
            assert se.engine_search(q).ids == se.postgres_search(db, q).ids, f
        hits = se.engine_search(se.Query(terms=["accounts receivable"], limit=50)).ids
        assert hits and all("receivable" in db.get(CataloguePosting, i).title.lower() for i in hits[:3])
        # a change and a close reach the engine through index_outbox within seconds
        p = db.query(CataloguePosting).filter(CataloguePosting.closed_at.is_(None)).first()
        p.title, p.revision = "Zyxquant Ledger Lead", p.revision + 1
        db.add(IndexOutbox(posting_id=p.id, revision=p.revision, event="upsert"))
        gone = db.query(CataloguePosting).filter(CataloguePosting.closed_at.is_(None), CataloguePosting.id != p.id).first()
        gone.closed_at, gone.revision = crawler.utcnow(), gone.revision + 1
        db.add(IndexOutbox(posting_id=gone.id, revision=gone.revision, event="close"))
        db.commit()
        deadline = time.time() + 10
        while time.time() < deadline:
            if se.engine_search(se.Query(terms=["zyxquant"], limit=3)).ids[:1] == [p.id] and \
                    gone.id not in se.engine_search(se.Query(limit=500)).ids:
                break
            time.sleep(0.2)
        else:
            pytest.fail("the engine did not follow the change and the close within 10 s")
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)
        db.close()
