"""JPSE Phase 1: the background crawler, the posting catalogue, and saved searches served from it.

Acceptance (JOBPILOT_JPSE_BLUEPRINT.md §13, Phase 1): Discover no longer waits on the network, and the matches it finds
are exactly the ones the live path finds. Plus the correctness rules: identity by source key, outbox events in the same
transaction, closing only after a complete valid snapshot, back-off, politeness limits.
"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import timedelta

import httpx
import pytest
from api_helpers import onboard
from ats_fixtures import Boards, greenhouse_board

API = "/api/v1"
BOARD_URLS = {"Acme Fintech": "https://job-boards.greenhouse.io/acmefintech", "Beta Pay": "https://jobs.lever.co/betapay",
              "Gamma Co": "https://jobs.ashbyhq.com/gammaco"}
SEARCH = {"name": "AR roles", "schedule": "daily", "min_match_score": 0,
          "criteria": {"keywords": ["Accounts Receivable"], "locations": ["Bengaluru", "Hyderabad"], "remote_ok": True,
                       "include_suggested": False}}
BOARD_HOSTS = ("boards-api.greenhouse.io", "api.lever.co", "api.ashbyhq.com")


class EtagBoards(Boards):
    """The mocked APIs, answering with an ETag and 304 Not Modified like the real Greenhouse/Lever/Ashby APIs do."""

    def handler(self, request: httpx.Request) -> httpx.Response:
        resp = super().handler(request)
        if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
            tag = '"' + hashlib.md5(resp.content).hexdigest() + '"'
            if request.headers.get("if-none-match") == tag:
                return httpx.Response(304, headers={"etag": tag})
            resp.headers["etag"] = tag
        return resp


@pytest.fixture
def boards(app_env, monkeypatch):
    from backend.services.ats import base
    from backend.services.crawler import service as crawler

    b = EtagBoards()
    monkeypatch.setattr(base, "transport_override", b.transport())
    monkeypatch.setattr(crawler, "FEEDS", ())  # feeds are tested with their own reader below, never the network
    return b


def _db():
    from backend.db import session_factory

    return session_factory()()


def _setup(client, resume_bytes, email="cat@example.com"):
    h = onboard(client, email, resume_bytes)
    for name, url in BOARD_URLS.items():
        assert client.post(f"{API}/companies/watchlist", headers=h, json={"url": url, "name": name}).status_code == 201
    r = client.post(f"{API}/saved-searches", headers=h, json=SEARCH)
    assert r.status_code == 201, r.text
    from backend.services.ats import board_cache

    board_cache.clear()  # adding companies fetched and cached their boards
    return h, r.json()["id"]


def _crawl(db, **kw):
    from backend.models import CrawlState
    from backend.services.crawler import service as crawler

    db.query(CrawlState).update({CrawlState.next_due_at: crawler.utcnow() - timedelta(minutes=1), CrawlState.cooldown_until: None})
    db.commit()
    return crawler.crawl(db, **kw)


def _feed_titles(client, h) -> set[tuple[str, str]]:
    items = client.get(f"{API}/jobs", headers=h, params={"page_size": 100, "group_similar": False}).json()["items"]
    return {(i["job"]["company"], i["job"]["title"] + " @ " + (i["job"]["location"] or "")) for i in items}


def test_crawl_catalogues_every_posting_and_unchanged_boards_answer_304(client, boards, resume_bytes):
    from backend.models import CataloguePosting, CrawlState, IndexOutbox

    _setup(client, resume_bytes)
    db = _db()
    try:
        first = _crawl(db)
        assert first["ok"] == 3 and first["errors"] == 0 and first["new"] > 0
        posts = db.query(CataloguePosting).all()
        titles = {p.title for p in posts}
        assert "Senior Software Engineer" in titles  # every posting, not only the ones some search matches
        assert len({p.source_key for p in posts}) == len(posts)
        assert db.query(IndexOutbox).count() == len(posts)  # one upsert event per new posting, same transaction
        gh = db.query(CataloguePosting).filter(CataloguePosting.source_key == "greenhouse:acmefintech:101").one()
        assert gh.location_normalized and gh.description and "remittance" in gh.description and gh.revision == 1
        events_before, calls_before = db.query(IndexOutbox).count(), len(boards.calls)

        second = _crawl(db)
        assert second["not_modified"] == 3 and second["new"] == 0  # ETag sent, 304 back, nothing re-parsed
        assert db.query(IndexOutbox).count() == events_before
        assert len(boards.calls) - calls_before == 3
        st = db.query(CrawlState).filter(CrawlState.target_key == "ats:greenhouse:acmefintech").one()
        assert st.last_status == "not_modified" and st.etag and st.interval_s == 3600  # quiet board, but watched: capped at 1 h
    finally:
        db.close()


def test_saved_search_from_catalogue_matches_live_results_without_network(client, boards, resume_bytes):
    # Live path (no crawl yet): the result every catalogue run must reproduce.
    h_live, sid_live = _setup(client, resume_bytes, "live@example.com")
    assert client.post(f"{API}/saved-searches/{sid_live}/run", headers=h_live).status_code == 202
    live = _feed_titles(client, h_live)
    assert len(live) == 4

    h, sid = _setup(client, resume_bytes, "cat2@example.com")
    db = _db()
    try:
        _crawl(db)
    finally:
        db.close()
    from backend.services.ats import board_cache

    board_cache.clear()
    calls = len(boards.calls)
    r = client.post(f"{API}/saved-searches/{sid}/run", headers=h)
    run = client.get(f"{API}/jobs/runs/{r.json()['id']}", headers=h).json()
    assert run["status"] in ("completed", "partial"), run
    assert not [c for c in boards.calls[calls:] if any(host in c for host in BOARD_HOSTS)]  # no board was fetched
    assert _feed_titles(client, h) == live  # exactly the same matches
    assert run["source_results"]["greenhouse"]["boards_ok"] == 1


def test_closing_needs_a_complete_valid_snapshot(client, boards, resume_bytes):
    from backend.models import CataloguePosting, CrawlState, IndexOutbox, Job, JobSourceLink

    h, sid = _setup(client, resume_bytes)
    client.post(f"{API}/saved-searches/{sid}/run", headers=h)  # 101 becomes a user-facing job
    db = _db()
    try:
        _crawl(db)
        key = ("greenhouse", "acmefintech")
        # A failed fetch closes nothing and backs off.
        boards.status[key] = 503
        rep = _crawl(db)
        assert rep["errors"] >= 1
        st = db.query(CrawlState).filter(CrawlState.target_key == "ats:greenhouse:acmefintech").one()
        assert st.cooldown_until is not None and st.consecutive_failures == 1
        assert db.query(CataloguePosting).filter(CataloguePosting.closed_at.is_not(None)).count() == 0
        del boards.status[key]
        # A complete snapshot without 101 closes exactly 101, in the catalogue and in the user's jobs.
        boards.payloads[key] = greenhouse_board(include_101=False)
        _crawl(db)
        db.expire_all()
        p101 = db.query(CataloguePosting).filter(CataloguePosting.source_key == "greenhouse:acmefintech:101").one()
        assert p101.closed_at is not None and p101.revision == 2
        assert db.query(IndexOutbox).filter(IndexOutbox.posting_id == p101.id, IndexOutbox.event == "close").count() == 1
        assert db.query(CataloguePosting).filter(CataloguePosting.target_key == "ats:greenhouse:acmefintech",
                                                 CataloguePosting.closed_at.is_(None)).count() == 3
        link = db.query(JobSourceLink).filter(JobSourceLink.source_key == "greenhouse:acmefintech:101").one()
        assert db.get(Job, link.job_id).closed_at is not None
        # It comes back: reopened, same identity, new revision.
        boards.payloads[key] = greenhouse_board()
        _crawl(db)
        db.expire_all()
        p101 = db.query(CataloguePosting).filter(CataloguePosting.source_key == "greenhouse:acmefintech:101").one()
        assert p101.closed_at is None and p101.revision == 3
    finally:
        db.close()


def test_a_board_that_suddenly_lists_nothing_is_not_trusted(client, boards, resume_bytes):
    from backend.models import CataloguePosting, CrawlState

    _setup(client, resume_bytes)
    key = ("greenhouse", "acmefintech")
    big = greenhouse_board()
    for i in range(4):  # 8 open postings
        extra = dict(big["jobs"][1], id=200 + i, absolute_url=f"https://job-boards.greenhouse.io/acmefintech/jobs/{200 + i}")
        big["jobs"].append(extra)
    boards.payloads[key] = big
    db = _db()
    try:
        _crawl(db)
        boards.payloads[key] = {"jobs": [], "meta": {"total": 0}}
        rep = _crawl(db)
        assert rep["suspicious"] == 1
        st = db.query(CrawlState).filter(CrawlState.target_key == "ats:greenhouse:acmefintech").one()
        assert st.last_status == "suspicious_empty" and st.etag is None
        assert db.query(CataloguePosting).filter(CataloguePosting.closed_at.is_not(None)).count() == 0
    finally:
        db.close()


def test_intervals_adapt_and_failures_back_off():
    from datetime import datetime, timezone

    from backend.models import CrawlState
    from backend.services.crawler import service as c

    assert c.next_interval(3600, True, False) == 1800
    assert c.next_interval(c.MIN_INTERVAL, True, False) == c.MIN_INTERVAL
    assert c.next_interval(3600, False, False) == 5400
    assert c.next_interval(c.MAX_INTERVAL, False, False) == c.MAX_INTERVAL
    assert c.next_interval(3600 * 8, False, True) == c.WATCHED_CAP
    now = datetime(2026, 11, 17, tzinfo=timezone.utc)
    s = CrawlState(target_key="ats:x:y", kind="board", consecutive_failures=0, interval_s=3600, priority=1)
    waits = []
    for _ in range(12):
        c._fail(s, now, "error", "HTTP 503")
        waits.append((s.cooldown_until - now).total_seconds())
        assert s.next_due_at == s.cooldown_until and s.priority == 0
    assert waits[0] == c.BACKOFF_BASE and waits[1] == 2 * c.BACKOFF_BASE and max(waits) == c.BACKOFF_MAX


def test_politeness_limits_per_host_and_never_denied_hosts():
    from backend.services.crawler.politeness import HostLimiter

    lim = HostLimiter(global_in_flight=8, per_host=2, rps={"a.example": 1000.0}, sleep=lambda s: None)
    active, peak, lock = [0], [0], threading.Lock()

    def work():
        with lim.slot("a.example"):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.02)
            with lock:
                active[0] -= 1

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 2
    for host in ("www.linkedin.com", "naukri.com", "in.indeed.com", "www.glassdoor.co.in"):
        with pytest.raises(PermissionError):
            lim.slot(host)
    waits = []
    slow = HostLimiter(rps={"b.example": 2.0}, sleep=waits.append)
    for _ in range(3):
        with slow.slot("b.example"):
            pass
    assert [round(w, 2) for w in waits] == [0.5, 1.0]  # 2 per second: the 2nd waits 0.5 s, the 3rd 1.0 s


def test_percolation_brings_new_postings_to_feeds_without_discover(client, boards, resume_bytes):
    from backend.models import DiscoveryRun, SavedSearch
    from backend.services.crawler import service as crawler

    from backend.config import get_settings
    from backend.models import User

    h, sid = _setup(client, resume_bytes)
    db = _db()
    try:
        db.query(User).update({User.onboarding_completed_at: crawler.utcnow()})  # percolation, like the scheduler, serves onboarded users
        db.commit()
        _crawl(db)
        assert crawler.percolate(db, get_settings()) == 1  # the search never ran and its boards are new: it runs once
        assert crawler.percolate(db, get_settings()) == 0  # nothing changed since
        db.query(SavedSearch).update({SavedSearch.last_run_at: crawler.utcnow() - timedelta(hours=2)})
        db.commit()
        key = ("greenhouse", "acmefintech")
        board = greenhouse_board()
        new = dict(board["jobs"][0], id=999, absolute_url="https://job-boards.greenhouse.io/acmefintech/jobs/999",
                   title="Accounts Receivable Lead")
        board["jobs"].append(new)
        boards.payloads[key] = board
        rep = _crawl(db)
        assert rep["new"] == 1 and rep["changed"] == 1
        assert crawler.percolate(db, get_settings()) == 1
        assert any("Accounts Receivable Lead" in t for _, t in _feed_titles(client, h))
        assert db.query(DiscoveryRun).filter(DiscoveryRun.trigger == "background").count() == 2
        assert crawler.percolate(db, get_settings()) == 0  # at most once per 30 minutes per search
    finally:
        db.close()


def test_discover_answers_from_catalogue_then_refreshes_in_background(client, boards, resume_bytes):
    h, _ = _setup(client, resume_bytes)
    db = _db()
    try:
        _crawl(db)
    finally:
        db.close()
    r = client.post(f"{API}/jobs/discover", headers=h, json={})
    assert r.status_code == 202
    run = client.get(f"{API}/jobs/runs/{r.json()['id']}", headers=h).json()
    assert run["status"] in ("completed", "partial") and run["jobs_found"] >= 4


def test_feeds_are_catalogued_without_closing_what_drops_out(client, boards, resume_bytes, monkeypatch):
    from backend.models import CataloguePosting
    from backend.services.crawler import service as crawler
    from backend.services.normalization import NormalizedJob

    monkeypatch.setattr(crawler, "FEEDS", ("himalayas",))
    batch = [[NormalizedJob(source="himalayas", source_key=f"himalayas:{i}", platform="Himalayas", company="Remote Co",
                            title=f"Collections Analyst {i}", location="Remote - India", work_mode="Remote") for i in range(3)]]

    def reader(task):
        return crawler.Outcome(task["state_id"], "ok", jobs=batch[0])

    db = _db()
    try:
        assert _crawl(db, feed_reader=reader)["new"] == 3
        batch[0] = batch[0][:1]
        _crawl(db, feed_reader=reader)
        assert db.query(CataloguePosting).filter(CataloguePosting.closed_at.is_not(None)).count() == 0
        from backend.models import CrawlState
        from backend.services.crawler import catalogue

        st = db.query(CrawlState).filter(CrawlState.target_key == "feed:himalayas").one()
        assert [nj.source_key for nj in catalogue.feed_jobs(db, st)] == ["himalayas:0"]  # latest snapshot only
    finally:
        db.close()


def test_payload_round_trip_keeps_every_field():
    from datetime import date

    from backend.services.crawler.catalogue import from_payload, to_payload
    from backend.services.normalization import NormalizedJob

    nj = NormalizedJob(source="lever", source_key="lever:x:1", platform="Lever", company="X", title="AR Analyst",
                       locations=["Pune", "Remote"], posted_at=date(2026, 11, 1), expires_at=date(2026, 12, 1),
                       required_skills=["Excel"], description="Full text", salary_min_lpa=8.0)
    back = from_payload(to_payload(nj), nj.description)
    assert back == nj


def test_a_slow_host_never_delays_other_hosts(client, boards, resume_bytes):
    """Each host has its own queue and workers: Greenhouse and Ashby finish while Lever is still hanging."""
    from backend.services.ats.base import fetch_board
    from backend.services.crawler import service as crawler
    from backend.services.crawler.politeness import HostLimiter

    _setup(client, resume_bytes)
    finished: dict[str, float] = {}
    t0 = time.monotonic()

    def fetch(ats, token, **kw):
        if ats == "lever":
            time.sleep(1.5)
        res = fetch_board(ats, token, **kw)
        finished[ats] = time.monotonic() - t0
        return res

    db = _db()
    try:
        rep = _crawl(db, fetch=fetch, limiter=HostLimiter(global_in_flight=2, sleep=lambda s: None))
        assert rep["ok"] == 3
        assert finished["greenhouse"] < 1.0 and finished["ashby"] < 1.0 and finished["lever"] >= 1.5
    finally:
        db.close()


def test_titles_typed_as_one_field_are_split_and_tolerate_cut_off_words():
    """A user typed several roles into one title (with a typo); a copy-pasted title carried an invisible character."""
    from backend.schemas.discovery import SearchCriteria
    from backend.services.saved_search_service import Criteria, split_titles

    assert split_titles(["Associat/ Sr Associate/ Investment Specialist"]) == ["Associat", "Sr Associate", "Investment Specialist"]
    assert split_titles(["FP&A", "Order to Cash, Billing", "Analyst | Associate", "Analyst or Associate"]) == \
        ["FP&A", "Order to Cash, Billing", "Analyst", "Associate"]
    c = Criteria(SearchCriteria(related_titles=False), ["Associat/ Sr Associate/ Investment Specialist"], [])
    assert c.title_ok("Senior Associate, Investments") and c.title_ok("Investment Specialist - Wealth")
    assert not c.title_ok("Software Engineer")
    assert not Criteria(SearchCriteria(related_titles=False), ["Payroll Specialist"], []).title_ok("Pay Specialist")  # short words stay exact
    d = Criteria(SearchCriteria(related_titles=False), ["Devops Engineer​"], [])
    assert d.title_ok("Senior DevOps Engineer") and not d.title_ok("DevOps Lead")


def test_catalogue_search_api_with_postgres_fallback(client, boards, resume_bytes, monkeypatch):
    """The engine is not running in tests: the endpoint answers from the database with the same exact filters."""
    monkeypatch.setenv("JPSE_SEARCH", "on")  # asks the engine first, then falls back
    monkeypatch.setenv("JPSE_SEARCH_SOCKET", "/nonexistent/searchd.sock")
    from backend.services import search_engine

    monkeypatch.setattr(search_engine, "SOCKET", "/nonexistent/searchd.sock")
    h, _ = _setup(client, resume_bytes)
    db = _db()
    try:
        _crawl(db)
    finally:
        db.close()
    r = client.get(f"{API}/catalogue/search", headers=h, params={"q": "receivable", "limit": 20})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine"] == "postgres" and body["items"]
    assert all("receivable" in i["title"].lower() for i in body["items"])
    everything = client.get(f"{API}/catalogue/search", headers=h, params={"limit": 100}).json()["items"]
    assert any(i["title"] == "Senior Software Engineer" for i in everything)  # every posting, not only matches
    assert client.get(f"{API}/catalogue/search", headers=h, params={"country": "ZZ"}).json()["items"] == []  # exact, never loosened
    assert client.get(f"{API}/catalogue/search", params={"q": "x"}).status_code == 401


def test_search_engine_query_building():
    from backend.services.search_engine import Query

    q = Query(terms=["AR analyst"], countries=["IN"], remote_open_to=["IN", "*"], work_modes=["Remote"], posted_within_days=7,
              salary_currency="INR", salary_min=500000, limit=5000)
    req = q.to_request()
    assert req["filters"] == [["country:IN", "remote:IN", "remote:*"], ["mode:Remote"]]
    assert req["limit"] == 2000 and req["salary"] == {"currency": "INR", "min": 500000, "unknown_ok": False}
    assert isinstance(req["posted_after_day"], int)
    assert Query().to_request() == {"method": "search", "limit": 50}
