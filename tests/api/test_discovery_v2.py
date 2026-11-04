"""Phase 2 discovery end to end: official boards (mocked) → saved searches → dedup → scored feed → notifications."""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from api_helpers import AR_JD, auth, onboard, register
from ats_fixtures import Boards, greenhouse_board

API = "/api/v1"
BOARD_URLS = {"Acme Fintech": "https://job-boards.greenhouse.io/acmefintech", "Beta Pay": "https://jobs.lever.co/betapay",
              "Gamma Co": "https://jobs.ashbyhq.com/gammaco"}
SEARCH = {"name": "AR roles", "schedule": "daily", "min_match_score": 0,
          "criteria": {"keywords": ["Accounts Receivable"], "locations": ["Bengaluru", "Hyderabad"], "remote_ok": True}}


@pytest.fixture
def boards(app_env, monkeypatch):
    from backend.services.ats import base

    b = Boards()
    monkeypatch.setattr(base, "transport_override", b.transport())
    return b


def _watch_all(client, h) -> dict[str, int]:
    ids = {}
    for name, url in BOARD_URLS.items():
        r = client.post(f"{API}/companies/watchlist", headers=h, json={"url": url, "name": name})
        assert r.status_code == 201, r.text
        ids[name] = r.json()["id"]
    return ids


def _run(client, h, search_id: int, expect=("completed", "partial")) -> dict:
    r = client.post(f"{API}/saved-searches/{search_id}/run", headers=h)
    assert r.status_code == 202, r.text
    run = client.get(f"{API}/jobs/runs/{r.json()['id']}", headers=h).json()
    assert run["status"] in expect, run
    return run


def _feed(client, h, **params) -> list[dict]:
    r = client.get(f"{API}/jobs", headers=h, params={"page_size": 100, **params})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _setup(client, resume_bytes, email="d@example.com", search=SEARCH) -> tuple[dict, int, dict]:
    h = onboard(client, email, resume_bytes)
    ids = _watch_all(client, h)
    r = client.post(f"{API}/saved-searches", headers=h, json=search)
    assert r.status_code == 201, r.text
    return h, r.json()["id"], ids


# ---- discovery ------------------------------------------------------------------------------------

def test_saved_search_discovers_scores_and_filters_board_jobs(client, boards, resume_bytes):
    from core import timeutil

    h, sid, _ = _setup(client, resume_bytes)
    run = _run(client, h, sid)
    items = {(i["job"]["platform"], i["job"]["company"], i["job"]["title"]): i for i in _feed(client, h)}
    assert set(items) == {
        ("Greenhouse", "Acme Fintech", "Accounts Receivable Analyst"),           # Bengaluru
        ("Lever", "Beta Pay", "Accounts Receivable Analyst"),                    # Bangalore
        ("Lever", "Beta Pay", "Accounts Receivable Executive"),                  # Remote - India
        ("Ashby", "Gamma Co", "Accounts Receivable Analyst - Collections"),      # Hyderabad
    }  # not: the software engineer (title), Mumbai (location), Remote - US (location), unlisted Ashby posting
    assert run["jobs_new"] == 4 and run["saved_search_id"] == sid and run["trigger"] == "manual"
    gh = items[("Greenhouse", "Acme Fintech", "Accounts Receivable Analyst")]
    job = gh["job"]
    assert job["posted_at"] == (timeutil.today() - timedelta(days=1)).isoformat()
    assert job["posted_at_confidence"] == "verified" and job["posted_label"] == "Yesterday"
    assert job["has_full_description"] and job["industry"] is None and job["first_seen_at"]
    assert [s["source"] for s in job["sources"]] == ["greenhouse"] and job["sources"][0]["url"].endswith("/jobs/101")
    assert job["experience_required"] and gh["match_score"] is not None and gh["scoring_method"].startswith("rule")
    assert any("receivable" in s.lower() for s in gh["matching_skills"])
    stats = run["platform_stats"]
    assert stats["Greenhouse"]["boards_checked"] == 1 and stats["Ashby"]["new"] == 1


def test_repeat_runs_add_no_duplicate_jobs_or_notifications(client, boards, resume_bytes):
    from sqlalchemy import func, select

    from backend.db import session_factory
    from backend.models import Job, JobSourceLink, Notification

    h, sid, _ = _setup(client, resume_bytes)
    first = _run(client, h, sid)
    notes1 = client.get(f"{API}/notifications", headers=h).json()
    assert notes1["unread"] == first["jobs_new"] == 4 and len(notes1["items"]) == 4
    from backend.services.ats import board_cache

    for _ in range(2):
        board_cache.clear()  # force real re-fetches, as the scheduler would a day later
        again = _run(client, h, sid)
        assert again["jobs_new"] == 0 and again["duplicates"] == 4
    assert len(_feed(client, h)) == 4
    assert client.get(f"{API}/notifications", headers=h).json()["unread"] == 4
    db = session_factory()()
    try:
        assert db.execute(select(func.count()).select_from(Job)).scalar_one() == 4
        assert db.execute(select(func.count()).select_from(JobSourceLink)).scalar_one() == 4
        assert db.execute(select(func.count()).select_from(Notification)).scalar_one() == 4
    finally:
        db.close()


def test_same_title_in_two_cities_on_one_board_stays_two_jobs(client, boards, resume_bytes):
    search = {**SEARCH, "criteria": {**SEARCH["criteria"], "locations": ["Bengaluru", "Mumbai"]}}
    h, sid, _ = _setup(client, resume_bytes, search=search)
    _run(client, h, sid)
    acme = [i["job"] for i in _feed(client, h) if i["job"]["company"] == "Acme Fintech"]
    assert sorted(j["location"] for j in acme) == ["Bengaluru", "Mumbai"]


def test_clipped_linkedin_job_and_board_job_merge_into_one(client, boards, resume_bytes):
    h, sid, _ = _setup(client, resume_bytes)
    clip = {"url": "https://www.linkedin.com/jobs/view/5550001/", "platform": "LinkedIn", "title": "Sr Accounts Receivable Analyst",
            "company": "Acme Fintech Pvt Ltd", "location": "Bengaluru, Karnataka, India", "description": AR_JD[:120],
            "captured_via": "clipper"}
    assert client.post(f"{API}/jobs/import", headers=h, json=clip).status_code == 201
    # The board calls it "Accounts Receivable Analyst"; make the titles comparable like the clip.
    from backend.services.ats import board_cache

    boards.payloads[("greenhouse", "acmefintech")]["jobs"][0]["title"] = "Senior Accounts Receivable Analyst"
    board_cache.clear()  # adding the company cached the board
    _run(client, h, sid)
    acme = [i for i in _feed(client, h) if "Acme" in i["job"]["company"]]
    assert len(acme) == 1, [i["job"]["title"] for i in acme]
    job = acme[0]["job"]
    assert sorted(s["platform"] for s in job["sources"]) == ["Greenhouse", "LinkedIn"]
    assert job["posted_at_confidence"] == "verified" and job["has_full_description"]
    assert job["platform"] == "LinkedIn"  # first seen there; the board listing is linked, not a second feed item
    # Filtering by either platform finds it.
    assert [i["job"]["id"] for i in _feed(client, h, platform="Greenhouse") if "Acme" in i["job"]["company"]] == [job["id"]]
    assert [i["job"]["id"] for i in _feed(client, h, platform="LinkedIn")] == [job["id"]]


def test_jobs_removed_from_a_board_are_marked_closed(client, boards, resume_bytes):
    from backend.services.ats import board_cache

    h, sid, _ = _setup(client, resume_bytes)
    _run(client, h, sid)
    boards.payloads[("greenhouse", "acmefintech")] = greenhouse_board(include_101=False)
    board_cache.clear()
    _run(client, h, sid)
    assert not [i for i in _feed(client, h) if i["job"]["company"] == "Acme Fintech"]
    closed = [i["job"] for i in _feed(client, h, include_closed=True) if i["job"]["company"] == "Acme Fintech"]
    assert len(closed) == 1 and closed[0]["closed_at"]
    # It comes back if the employer re-lists it.
    boards.payloads[("greenhouse", "acmefintech")] = greenhouse_board()
    board_cache.clear()
    _run(client, h, sid)
    assert [i["job"]["closed_at"] for i in _feed(client, h) if i["job"]["company"] == "Acme Fintech"] == [None]


def test_unknown_posting_dates_are_never_presented_as_recent(client, boards, resume_bytes):
    search = {**SEARCH, "criteria": {**SEARCH["criteria"], "locations": ["Mumbai"]}}
    h, sid, _ = _setup(client, resume_bytes, search=search)
    _run(client, h, sid)
    mumbai = [i["job"] for i in _feed(client, h) if i["job"]["location"] == "Mumbai"]
    assert len(mumbai) == 1
    assert mumbai[0]["posted_at"] is None and mumbai[0]["posted_label"] == "Unknown" and mumbai[0]["posted_at_confidence"] == "unknown"
    for window in ("today", "24h", "3d", "7d", "30d"):
        assert not [i for i in _feed(client, h, posted=window, include_estimated=True) if i["job"]["location"] == "Mumbai"], window
    assert [i["job"]["location"] for i in _feed(client, h, confidence="unknown")] == ["Mumbai"]
    assert "Mumbai" not in [i["job"]["location"] for i in _feed(client, h, confidence="verified")]


def test_posted_windows_use_verified_dates(client, boards, resume_bytes):
    h, sid, _ = _setup(client, resume_bytes)
    _run(client, h, sid)
    titles = lambda **p: sorted(i["job"]["platform"] + ":" + i["job"]["title"] for i in _feed(client, h, **p))  # noqa: E731
    assert titles(posted="today") == []
    assert titles(posted="3d") == ["Ashby:Accounts Receivable Analyst - Collections", "Greenhouse:Accounts Receivable Analyst"]
    assert len(titles(posted="7d")) == 3 and len(titles(posted="30d")) == 4


def test_feed_filters_industry_company_employment_and_search(client, boards, resume_bytes):
    from backend.db import session_factory
    from backend.models import Company

    h, sid, ids = _setup(client, resume_bytes)
    db = session_factory()()
    db.get(Company, ids["Beta Pay"]).industry = "Fintech"
    db.commit()
    db.close()
    _run(client, h, sid)
    assert {i["job"]["company"] for i in _feed(client, h, industry="fintech")} == {"Beta Pay"}
    assert {i["job"]["company"] for i in _feed(client, h, company="gamma")} == {"Gamma Co"}
    assert {i["job"]["title"] for i in _feed(client, h, employment_type="Contract")} == {"Accounts Receivable Executive"}
    assert len(_feed(client, h, saved_search_id=sid)) == 4 and _feed(client, h, saved_search_id=sid + 999) == []


def test_criteria_work_mode_employment_experience_and_exclusions(client, boards, resume_bytes):
    search = {**SEARCH, "criteria": {**SEARCH["criteria"], "work_modes": ["On-site", "Hybrid"], "employment_types": ["Full-time"],
                                     "exclude_keywords": ["Collections"], "experience_years": 4}}
    h, sid, _ = _setup(client, resume_bytes, search=search)
    _run(client, h, sid)
    assert sorted(i["job"]["platform"] for i in _feed(client, h)) == ["Greenhouse", "Lever"]


def test_search_without_keywords_falls_back_to_preferred_titles(client, boards, resume_bytes):
    search = {"name": "From my preferences", "criteria": {"related_titles": False}}
    h, sid, _ = _setup(client, resume_bytes, search=search)  # preferences: "Accounts Receivable Analyst" in Bengaluru
    _run(client, h, sid)
    assert sorted((i["job"]["platform"], i["job"]["location"]) for i in _feed(client, h)) == [
        ("Greenhouse", "Bengaluru"), ("Lever", "Bangalore, Karnataka")]


def test_related_titles_widen_the_search_within_the_role_family(client, boards, resume_bytes):
    h, sid, _ = _setup(client, resume_bytes, search={"name": "Related", "criteria": {}})
    _run(client, h, sid)
    # "Accounts Receivable Executive" (Remote - India) is in the receivables family of "Accounts Receivable Analyst".
    assert sorted((i["job"]["platform"], i["job"]["title"]) for i in _feed(client, h)) == [
        ("Greenhouse", "Accounts Receivable Analyst"), ("Lever", "Accounts Receivable Analyst"), ("Lever", "Accounts Receivable Executive")]
    # ...but never the software engineer on the same board.
    assert all("Engineer" not in i["job"]["title"] for i in _feed(client, h))


def test_board_failures_are_reported_not_fatal(client, boards, resume_bytes):
    h, sid, _ = _setup(client, resume_bytes)
    from backend.services.ats import board_cache

    boards.status[("lever", "betapay")] = 503
    del boards.payloads[("ashby", "gammaco")]
    board_cache.clear()  # adding the companies cached the healthy boards
    run = _run(client, h, sid)
    kinds = {e["type"] for e in run["error_details"]}
    assert run["status"] == "partial" and kinds == {"BOARD_FETCH_FAILED", "BOARD_NOT_FOUND"}
    assert {i["job"]["platform"] for i in _feed(client, h)} == {"Greenhouse"}
    status = {c["name"]: c["last_status"] for c in client.get(f"{API}/companies/watchlist", headers=h).json()}
    assert status == {"Acme Fintech": "ok", "Beta Pay": "error", "Gamma Co": "not_found"}


def test_search_with_no_companies_explains_what_to_do(client, boards, resume_bytes):
    h = onboard(client, "nocos@example.com", resume_bytes)
    sid = client.post(f"{API}/saved-searches", headers=h, json=SEARCH).json()["id"]
    run = _run(client, h, sid, expect=("failed",))
    assert [e["type"] for e in run["error_details"]] == ["NO_COMPANIES"] and run["jobs_found"] == 0
    assert run["source_results"]["company_boards"]["status"] == "not_configured"
    assert run["summary"].startswith("Discovery could not run.") and "No companies to search" in run["summary"]


# ---- Adzuna -------------------------------------------------------------------------------------------

def test_adzuna_source_without_credentials_reports_not_configured(client, boards, resume_bytes):
    search = {**SEARCH, "criteria": {**SEARCH["criteria"], "sources": ["adzuna_api"]}}
    h, sid, _ = _setup(client, resume_bytes, search=search)
    run = _run(client, h, sid, expect=("failed",))  # never "completed" when the only source is unconfigured
    assert [e["type"] for e in run["error_details"]] == ["ADZUNA_NOT_CONFIGURED"] and run["jobs_found"] == 0
    assert run["source_results"]["adzuna_api"]["status"] == "not_configured"
    assert "ADZUNA_APP_ID" in run["summary"]


def test_adzuna_results_merge_with_board_listing(client, boards, resume_bytes):
    from backend.config import get_settings
    from backend.db import session_factory
    from backend.models import SavedSearch, User
    from backend.services import saved_search_service
    from backend.services.adzuna import AdzunaClient
    from core import timeutil

    search = {**SEARCH, "criteria": {**SEARCH["criteria"], "sources": ["greenhouse", "adzuna_api"]}}
    h, sid, _ = _setup(client, resume_bytes, search=search)
    payload = {"results": [{"id": 9001, "title": "Accounts Receivable Analyst", "company": {"display_name": "Acme Fintech Pvt. Ltd."},
                            "location": {"display_name": "Bangalore, Karnataka"}, "description": AR_JD[:250],
                            "redirect_url": "https://www.adzuna.in/land/ad/9001?se=x", "created": f"{timeutil.today().isoformat()}T03:00:00Z"}]}
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, json=payload)

    db = session_factory()()
    try:
        user, row = db.query(User).filter_by(email="d@example.com").one(), db.get(SavedSearch, sid)
        run, _ = saved_search_service.start(db, user, row)
        run = saved_search_service.execute(db, get_settings(), user, row, run,
                                           adzuna_client=AdzunaClient("id", "key", transport=httpx.MockTransport(handler)))
    finally:
        db.close()
    assert run.status == "completed", run.error_details
    assert calls and "what=Accounts+Receivable" in str(calls[0])
    acme = [i["job"] for i in _feed(client, h) if "Acme" in i["job"]["company"]]
    assert len(acme) == 1 and sorted(s["source"] for s in acme[0]["sources"]) == ["adzuna_api", "greenhouse"]
    # The board's full description wins over Adzuna's snippet.
    assert acme[0]["has_full_description"]


# ---- companies, watchlist, directory ------------------------------------------------------------------

def test_add_company_by_url_validates_the_board(client, boards, resume_bytes):
    h = onboard(client, "co@example.com", resume_bytes)
    bad = client.post(f"{API}/companies/watchlist", headers=h, json={"url": "https://jobs.lever.co/doesnotexist"})
    assert bad.status_code == 422 and "No Lever job board" in bad.json()["detail"]
    other = client.post(f"{API}/companies/watchlist", headers=h, json={"url": "https://www.linkedin.com/company/acme"})
    assert other.status_code == 422
    boards.status[("ashby", "gammaco")] = 503
    assert client.post(f"{API}/companies/watchlist", headers=h, json={"url": BOARD_URLS["Gamma Co"]}).status_code == 503
    ok = client.post(f"{API}/companies/watchlist", headers=h, json={"url": BOARD_URLS["Acme Fintech"] + "/jobs/101"})
    assert ok.status_code == 201
    c = ok.json()
    assert (c["ats"], c["board_token"], c["origin"], c["last_status"], c["job_count"]) == ("greenhouse", "acmefintech", "user", "ok", 4)
    assert c["name"] == "Acme Fintech Private Limited" and c["board_url"] == "https://job-boards.greenhouse.io/acmefintech"
    # Watching twice is idempotent; removing works; removing again is 404.
    assert client.post(f"{API}/companies/watchlist", headers=h, json={"ats": "greenhouse", "token": "AcmeFintech"}).json()["id"] == c["id"]
    assert len(client.get(f"{API}/companies/watchlist", headers=h).json()) == 1
    assert client.delete(f"{API}/companies/watchlist/{c['id']}", headers=h).status_code == 204
    assert client.delete(f"{API}/companies/watchlist/{c['id']}", headers=h).status_code == 404


def test_directory_suggested_and_bulk_watch(client, boards, resume_bytes):
    h = onboard(client, "dir@example.com", resume_bytes)
    suggested = client.get(f"{API}/companies/suggested", headers=h).json()
    assert len(suggested) >= 20 and all(s["curated"] and s["industry"] for s in suggested)
    found = client.get(f"{API}/companies/directory", headers=h, params={"q": "razorpay"}).json()
    assert found[0]["name"] == "Razorpay" and found[0]["curated"] and found[0]["ats"] == "greenhouse"
    jobsync = client.get(f"{API}/companies/directory", headers=h, params={"q": "1password", "ats": "ashby"}).json()
    assert jobsync and not jobsync[0]["curated"]
    picks = [{"ats": s["ats"], "token": s["token"]} for s in suggested[:3]]
    r = client.post(f"{API}/companies/watchlist/bulk", headers=h, json={"companies": picks})
    assert r.status_code == 201 and all(c["origin"] == "curated" for c in r.json())
    assert all(s["watched"] for s in client.get(f"{API}/companies/suggested", headers=h).json()[:3])
    # Curated boards were verified when the list was built, so adding them makes no network calls.
    assert boards.calls == []


def test_jobsync_attribution_ships_with_the_data():
    from backend.services.company_service import DATA_DIR

    notice = (DATA_DIR / "NOTICE.md").read_text()
    assert "JobSync" in notice and "MIT" in notice and "8c20325c35dbf203334a270cef5aef446f06a774" in notice
    assert "Permission is hereby granted" in (DATA_DIR / "JOBSYNC_LICENSE").read_text()


# ---- saved searches: CRUD, validation, isolation ------------------------------------------------------

def test_saved_search_crud_and_validation(client, boards, resume_bytes):
    h = onboard(client, "crud@example.com", resume_bytes)
    r = client.post(f"{API}/saved-searches", headers=h, json={**SEARCH, "criteria": {"company_ids": [424242]}})
    assert r.status_code == 422 and "Unknown company" in r.json()["detail"]
    assert client.post(f"{API}/saved-searches", headers=h, json={"name": "x", "criteria": {"sources": []}}).status_code == 422
    assert client.post(f"{API}/saved-searches", headers=h, json={"name": "x", "schedule": "hourly"}).status_code == 422
    created = client.post(f"{API}/saved-searches", headers=h, json=SEARCH).json()
    assert created["next_run_at"] and created["last_run"] is None and created["criteria"]["sources"] == ["greenhouse", "lever", "ashby"]
    upd = client.put(f"{API}/saved-searches/{created['id']}", headers=h, json={**SEARCH, "schedule": "manual", "name": "Renamed"}).json()
    assert upd["name"] == "Renamed" and upd["next_run_at"] is None
    assert [s["name"] for s in client.get(f"{API}/saved-searches", headers=h).json()] == ["Renamed"]
    assert client.delete(f"{API}/saved-searches/{created['id']}", headers=h).status_code == 204
    assert client.get(f"{API}/saved-searches/{created['id']}", headers=h).status_code == 404


def test_saved_searches_watchlists_and_notifications_are_private(client, boards, resume_bytes):
    h, sid, ids = _setup(client, resume_bytes)
    _run(client, h, sid)
    other = auth(register(client, "intruder@example.com"))
    for method, path in [("get", f"/saved-searches/{sid}"), ("put", f"/saved-searches/{sid}"), ("delete", f"/saved-searches/{sid}"),
                         ("post", f"/saved-searches/{sid}/run"), ("get", f"/saved-searches/{sid}/runs")]:
        kwargs = {"json": SEARCH} if method == "put" else {}
        assert getattr(client, method)(API + path, headers=other, **kwargs).status_code == 404, path
    assert client.get(f"{API}/saved-searches", headers=other).json() == []
    assert client.get(f"{API}/companies/watchlist", headers=other).json() == []
    assert client.delete(f"{API}/companies/watchlist/{ids['Acme Fintech']}", headers=other).status_code == 404
    assert client.get(f"{API}/notifications", headers=other).json() == {"items": [], "unread": 0}
    mine = client.get(f"{API}/notifications", headers=h).json()["items"][0]["id"]
    client.post(f"{API}/notifications/{mine}/read", headers=other)
    assert client.get(f"{API}/notifications", headers=h).json()["unread"] == 4  # the intruder could not mark it read
    assert client.get(f"{API}/jobs", headers=other).json()["total"] == 0


def test_notifications_read_flow(client, boards, resume_bytes):
    h, sid, _ = _setup(client, resume_bytes)
    _run(client, h, sid)
    items = client.get(f"{API}/notifications", headers=h).json()["items"]
    assert all(i["kind"] == "new_match" and "%" in i["title"] and i["link"].startswith("/discover?job=") for i in items)
    assert client.post(f"{API}/notifications/{items[0]['id']}/read", headers=h).status_code == 204
    assert client.get(f"{API}/notifications", headers=h).json()["unread"] == 3
    assert len(client.get(f"{API}/notifications", headers=h, params={"unread_only": True}).json()["items"]) == 3
    client.post(f"{API}/notifications/read-all", headers=h)
    assert client.get(f"{API}/notifications", headers=h).json()["unread"] == 0


def test_notification_threshold_uses_the_search_score(client, boards, resume_bytes):
    h, sid, _ = _setup(client, resume_bytes, search={**SEARCH, "min_match_score": 100})
    run = _run(client, h, sid)
    assert run["jobs_new"] == 4 and client.get(f"{API}/notifications", headers=h).json()["unread"] == 0


# ---- scheduling ------------------------------------------------------------------------------------------

def test_scheduler_runs_only_due_enabled_searches(client, boards, resume_bytes):
    from backend.config import get_settings
    from backend.db import session_factory
    from backend.models import DiscoveryRun, SavedSearch, utcnow
    from backend.services import saved_search_service

    h, due_id, _ = _setup(client, resume_bytes)
    assert client.get(f"{API}/onboarding", headers=h).json()["completed"]  # what the app does on load
    later = client.post(f"{API}/saved-searches", headers=h, json={**SEARCH, "name": "later"}).json()["id"]
    manual = client.post(f"{API}/saved-searches", headers=h, json={**SEARCH, "name": "manual", "schedule": "manual"}).json()["id"]
    off = client.post(f"{API}/saved-searches", headers=h, json={**SEARCH, "name": "off", "enabled": False}).json()["id"]
    db = session_factory()()
    try:
        db.get(SavedSearch, due_id).next_run_at = utcnow() - timedelta(minutes=1)
        db.commit()
        assert [s.id for s in saved_search_service.due(db)] == [due_id]
        assert saved_search_service.run_due(db, get_settings()) == 1
        row = db.get(SavedSearch, due_id)
        db.refresh(row)
        assert row.last_run_at and row.next_run_at - row.last_run_at == timedelta(days=1)
        runs = db.query(DiscoveryRun).filter(DiscoveryRun.saved_search_id.is_not(None)).all()
        assert [(r.saved_search_id, r.trigger, r.status) for r in runs] == [(due_id, "scheduled", "completed")]
        assert saved_search_service.due(db) == []  # not due again until tomorrow
        assert {later, manual, off}.isdisjoint({r.saved_search_id for r in runs})
    finally:
        db.close()


def test_interrupted_runs_are_closed(client, resume_bytes):
    from backend.db import session_factory
    from backend.models import DiscoveryRun, User, utcnow
    from backend.services import saved_search_service

    onboard(client, "intr@example.com", resume_bytes)
    db = session_factory()()
    try:
        user = db.query(User).filter_by(email="intr@example.com").one()
        stale = DiscoveryRun(user_id=user.id, trigger="manual", sources=[], status="running", error_details=[], platform_stats={},
                             started_at=utcnow() - timedelta(hours=2))
        fresh = DiscoveryRun(user_id=user.id, trigger="manual", sources=[], status="running", error_details=[], platform_stats={})
        db.add_all([stale, fresh])
        db.commit()
        assert saved_search_service.mark_interrupted(db) == 1
        db.refresh(stale)
        db.refresh(fresh)
        assert stale.status == "failed" and stale.error_details[-1]["type"] == "INTERRUPTED" and fresh.status == "running"
    finally:
        db.close()


def test_run_now_does_not_start_a_second_concurrent_run(client, boards, resume_bytes):
    from backend.db import session_factory
    from backend.models import DiscoveryRun, SavedSearch, User
    from backend.services import saved_search_service

    h, sid, _ = _setup(client, resume_bytes)
    db = session_factory()()
    try:
        user, row = db.query(User).filter_by(email="d@example.com").one(), db.get(SavedSearch, sid)
        run, created = saved_search_service.start(db, user, row)
        assert created
        r = client.post(f"{API}/saved-searches/{sid}/run", headers=h)
        assert r.status_code == 202 and r.json()["id"] == run.id and r.json()["status"] == "running"
        assert db.query(DiscoveryRun).filter_by(saved_search_id=sid).count() == 1
    finally:
        db.close()


# ---- existing flows keep working through the unified ingest ----------------------------------------------

def test_clipper_import_still_dedups_against_itself(client, resume_bytes):
    h = onboard(client, "clip@example.com", resume_bytes)
    body = {"url": "https://www.linkedin.com/jobs/view/777/?trk=x", "platform": "LinkedIn", "title": "AR Analyst", "company": "Delta",
            "description": AR_JD, "captured_via": "clipper"}
    first = client.post(f"{API}/jobs/import", headers=h, json=body).json()
    second = client.post(f"{API}/jobs/import", headers=h, json={**body, "captured_via": "form"}).json()
    assert first["user_job_ids"] == second["user_job_ids"] and second["run"]["duplicates"] == 1
    job = _feed(client, h)[0]["job"]
    assert job["platform"] == "LinkedIn" and sorted(s["source"] for s in job["sources"]) == ["browser_clipper", "user_job_url"]


# ---- honest outcomes, starter search, run everything -------------------------------------------------------

def test_run_records_per_source_outcomes_and_summary(client, boards, resume_bytes):
    h, sid, _ = _setup(client, resume_bytes)
    run = _run(client, h, sid)
    res = run["source_results"]
    assert {k: v["status"] for k, v in res.items()} == {"greenhouse": "ok", "lever": "ok", "ashby": "ok"}
    assert res["greenhouse"]["boards_ok"] == 1 and res["greenhouse"]["listings_checked"] == 4 and res["greenhouse"]["found"] == 1
    assert run["status"] == "completed" and run["summary"].startswith("Checked Greenhouse, Lever, Ashby (3 company boards, 7 listings)")
    assert "4 matching jobs: 4 new, 0 already in your feed." in run["summary"]


def test_successful_run_with_zero_matches_is_empty_not_failed(client, boards, resume_bytes):
    search = {**SEARCH, "criteria": {**SEARCH["criteria"], "keywords": ["Astronaut"], "related_titles": False}}
    h, sid, _ = _setup(client, resume_bytes, search=search)
    run = _run(client, h, sid, expect=("completed",))
    assert {v["status"] for v in run["source_results"].values()} == {"empty"}
    assert "No listings matched your titles and locations" in run["summary"] and run["jobs_found"] == 0


def test_all_boards_failing_is_a_failed_run(client, boards, resume_bytes):
    from backend.services.ats import board_cache

    h, sid, _ = _setup(client, resume_bytes)
    for key in list(boards.payloads):
        boards.status[key] = 503
    board_cache.clear()
    run = _run(client, h, sid, expect=("failed",))
    assert {v["status"] for v in run["source_results"].values()} == {"failed"}
    assert "could not be read" in run["source_results"]["lever"]["message"] and run["summary"].startswith("Discovery could not run.")


def test_partial_provider_failure_keeps_the_rest(client, boards, resume_bytes):
    from backend.services.ats import board_cache

    h, sid, _ = _setup(client, resume_bytes)
    boards.status[("lever", "betapay")] = 503
    board_cache.clear()
    run = _run(client, h, sid, expect=("partial",))
    assert run["source_results"]["lever"]["status"] == "failed" and run["source_results"]["greenhouse"]["status"] == "ok"
    assert {i["job"]["platform"] for i in _feed(client, h)} == {"Greenhouse", "Ashby"}


def test_starter_search_is_created_once_from_preferences(client, boards, resume_bytes):
    h = onboard(client, "starter@example.com", resume_bytes)
    assert client.get(f"{API}/onboarding", headers=h).json()["completed"]
    searches = client.get(f"{API}/saved-searches", headers=h).json()
    assert len(searches) == 1
    s = searches[0]
    assert (s["name"], s["origin"], s["schedule"], s["enabled"]) == ("Jobs matching my profile", "starter", "daily", True)
    c = s["criteria"]
    assert c["include_suggested"] and c["related_titles"] and c["keywords"] == [] and c["locations"] == []
    assert c["sources"] == ["greenhouse", "lever", "ashby"]  # Adzuna only once credentials exist
    assert c["experience_years"] and s["next_run_at"]
    client.delete(f"{API}/saved-searches/{s['id']}", headers=h)
    assert client.get(f"{API}/saved-searches", headers=h).json() == []  # deleting it is respected


def test_starter_search_includes_adzuna_when_configured(client, boards, resume_bytes, monkeypatch):
    from backend.config import get_settings

    monkeypatch.setenv("ADZUNA_APP_ID", "id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "key")
    get_settings.cache_clear()
    h = onboard(client, "adz@example.com", resume_bytes)
    client.get(f"{API}/onboarding", headers=h)
    assert client.get(f"{API}/saved-searches", headers=h).json()[0]["criteria"]["sources"][-1] == "adzuna_api"


def test_run_discovery_now_uses_suggested_boards_without_manual_setup(client, boards, resume_bytes, monkeypatch):
    """A new user presses one button and gets real jobs: no companies, no searches configured by hand."""
    from backend.services import company_service

    fake = ({"name": "Acme Fintech", "ats": "greenhouse", "token": "acmefintech", "industry": "Fintech", "domain": "acme.example"},
            {"name": "Beta Pay", "ats": "lever", "token": "betapay", "industry": "Fintech", "domain": "beta.example"},
            {"name": "Gamma Co", "ats": "ashby", "token": "gammaco", "industry": "SaaS", "domain": "gamma.example"},
            {"name": "Gone Ltd", "ats": "lever", "token": "gone-board", "industry": "SaaS", "domain": "gone.example"})
    monkeypatch.setattr(company_service, "curated", lambda: fake)
    from backend.services import saved_search_service
    monkeypatch.setattr(saved_search_service, "curated", lambda: fake)

    h = onboard(client, "auto@example.com", resume_bytes)
    client.get(f"{API}/onboarding", headers=h)
    r = client.post(f"{API}/jobs/discover", headers=h, json={})
    assert r.status_code == 202
    run = client.get(f"{API}/jobs/runs/{r.json()['id']}", headers=h).json()
    res = run["source_results"]
    assert res["alert_email"]["status"] == "not_configured" and "No mailbox" in res["alert_email"]["message"]
    assert res["adzuna_api"]["status"] == "not_configured"
    assert res["greenhouse"]["status"] == "ok"
    assert res["ashby"]["status"] == "empty"  # reached, but its only listed job is in Hyderabad (preference: Bengaluru)
    assert res["lever"]["status"] == "partial" and "Gone Ltd (board not found)" in res["lever"]["message"]
    assert run["status"] == "partial" and run["jobs_new"] == 3
    feed = _feed(client, h)
    assert {i["job"]["company"] for i in feed} >= {"Acme Fintech", "Beta Pay"}
    assert all(i["match_score"] is not None and i["scoring_method"] for i in feed)
    # Fintech comes from the curated directory entry.
    assert {i["job"]["industry"] for i in feed if i["job"]["company"] == "Beta Pay"} == {"Fintech"}


def test_run_everything_with_nothing_available_fails_with_reasons(client, resume_bytes, monkeypatch):
    from backend.services import saved_search_service

    monkeypatch.setattr(saved_search_service, "curated", lambda: ())
    h = onboard(client, "nothing@example.com", resume_bytes)
    client.get(f"{API}/onboarding", headers=h)
    run_id = client.post(f"{API}/jobs/discover", headers=h, json={}).json()["id"]
    run = client.get(f"{API}/jobs/runs/{run_id}", headers=h).json()
    assert run["status"] == "failed"
    assert {k: v["status"] for k, v in run["source_results"].items()} == {
        "alert_email": "not_configured", "adzuna_api": "not_configured", "company_boards": "not_configured"}
    assert "No mailbox" in run["summary"] and "ADZUNA_APP_ID" in run["summary"] and "No companies to search" in run["summary"]


def test_two_users_get_independent_matches_from_shared_boards(client, boards, resume_bytes):
    h1, s1, _ = _setup(client, resume_bytes, email="one@example.com")
    h2 = onboard(client, "two@example.com", resume_bytes, locations=("Mumbai",))
    _watch_all(client, h2)
    s2 = client.post(f"{API}/saved-searches", headers=h2, json={**SEARCH, "criteria": {**SEARCH["criteria"], "locations": ["Mumbai"]}}).json()["id"]
    _run(client, h1, s1)
    _run(client, h2, s2)
    f1, f2 = _feed(client, h1), _feed(client, h2)
    assert "Mumbai" not in {i["job"]["location"] for i in f1} and {i["job"]["location"] for i in f2} >= {"Mumbai"}
    # One shared job row, two private feed items with their own state.
    shared = [i for i in f1 if i["job"]["location"] == "Remote - India"][0]
    client.post(f"{API}/jobs/{shared['user_job_id']}/dismiss", headers=h1)
    assert client.get(f"{API}/jobs/{shared['user_job_id']}", headers=h2).status_code == 404
    other = [i for i in f2 if i["job"]["id"] == shared["job"]["id"]][0]
    assert other["status"] != "dismissed"
    assert client.get(f"{API}/saved-searches/{s1}", headers=h2).status_code == 404
    assert client.get(f"{API}/jobs/runs/{_run(client, h1, s1)['id']}", headers=h2).status_code == 404


# ---- source health panel ---------------------------------------------------------------------------------

def test_source_health_before_and_after_a_run(client, boards, resume_bytes, monkeypatch):
    from backend.services import company_service, saved_search_service

    fake = ({"name": "Acme Fintech", "ats": "greenhouse", "token": "acmefintech", "industry": "Fintech"},
            {"name": "Gone Ltd", "ats": "lever", "token": "gone-board", "industry": "SaaS"})
    for mod in (company_service, saved_search_service):
        monkeypatch.setattr(mod, "curated", lambda: fake)
    from backend.services import source_health
    monkeypatch.setattr(source_health, "curated", lambda: fake)

    h = onboard(client, "health@example.com", resume_bytes)
    client.get(f"{API}/onboarding", headers=h)
    before = {s["key"]: s for s in client.get(f"{API}/discovery/sources", headers=h).json()["sources"]}
    assert set(before) == {"greenhouse", "lever", "ashby", "adzuna_api", "alert_email", "manual"}
    assert before["greenhouse"]["configured"] and before["greenhouse"]["boards"] == {"total": 1, "ok": 0, "failing": 0, "unchecked": 1}
    assert before["ashby"]["configured"] is False and "No Ashby companies" in before["ashby"]["missing"]
    assert before["adzuna_api"]["connection"] == "not_configured" and "ADZUNA_APP_ID" in before["adzuna_api"]["missing"]
    assert before["alert_email"]["configured"] is False and "No mailbox" in before["alert_email"]["missing"]
    assert before["greenhouse"]["last_attempt_at"] is None

    client.post(f"{API}/jobs/discover", headers=h, json={})
    data = client.get(f"{API}/discovery/sources", headers=h).json()
    after = {s["key"]: s for s in data["sources"]}
    gh, lv = after["greenhouse"], after["lever"]
    assert gh["connection"] == "ok" and gh["last_attempt_at"] and gh["last_success_at"] and gh["jobs_in_feed"] == 1
    assert gh["last_run"]["status"] == "ok" and gh["last_run"]["found"] == 1 and gh["boards"]["ok"] == 1
    assert lv["connection"] == "failing" and lv["boards"]["failing"] == 1 and lv["last_run"]["status"] == "failed"
    assert data["last_run"]["status"] == "partial" and data["saved_searches"] == 1


def test_source_health_is_per_user(client, boards, resume_bytes):
    h1, sid, _ = _setup(client, resume_bytes)
    _run(client, h1, sid)
    h2 = auth(register(client, "fresh@example.com"))
    other = {s["key"]: s for s in client.get(f"{API}/discovery/sources", headers=h2).json()["sources"]}
    assert all(s["jobs_in_feed"] == 0 and s["last_run"] is None for s in other.values())
    assert other["greenhouse"]["configured"] is False


# ---- date filters and unknown dates -----------------------------------------------------------------------

def test_date_range_without_dates_hides_nothing(client, boards, resume_bytes):
    search = {**SEARCH, "criteria": {**SEARCH["criteria"], "locations": ["Bengaluru", "Mumbai"]}}
    h, sid, _ = _setup(client, resume_bytes, search=search)
    _run(client, h, sid)
    everything = client.get(f"{API}/jobs", headers=h).json()
    ranged = client.get(f"{API}/jobs", headers=h, params={"posted": "range"}).json()
    assert ranged["total"] == everything["total"] and ranged["hidden_unknown_dates"] == 0
    assert "Mumbai" in {i["job"]["location"] for i in ranged["items"]}  # its posting date is unknown


def test_date_filters_report_and_optionally_include_unknown_dates(client, boards, resume_bytes):
    from core import timeutil

    search = {**SEARCH, "criteria": {**SEARCH["criteria"], "locations": ["Bengaluru", "Mumbai"]}}
    h, sid, _ = _setup(client, resume_bytes, search=search)
    _run(client, h, sid)
    week = client.get(f"{API}/jobs", headers=h, params={"posted": "7d"}).json()
    assert week["hidden_unknown_dates"] == 1 and "Mumbai" not in {i["job"]["location"] for i in week["items"]}
    shown = client.get(f"{API}/jobs", headers=h, params={"posted": "7d", "include_unknown_dates": True}).json()
    assert shown["total"] == week["total"] + 1 and shown["hidden_unknown_dates"] == 0
    mumbai = [i["job"] for i in shown["items"] if i["job"]["location"] == "Mumbai"][0]
    assert mumbai["posted_at_confidence"] == "unknown" and mumbai["posted_label"] == "Unknown"
    start = (timeutil.today() - timedelta(days=30)).isoformat()
    ranged = client.get(f"{API}/jobs", headers=h, params={"posted": "range", "date_from": start}).json()
    assert ranged["hidden_unknown_dates"] == 1 and ranged["total"] == week["total"] + 1  # +1: the 10-day-old Lever job
    # "today" with include_unknown_dates still never calls an unknown date "today": it is listed and labelled unknown.
    today = client.get(f"{API}/jobs", headers=h, params={"posted": "today", "include_unknown_dates": True}).json()
    assert [i["job"]["posted_label"] for i in today["items"]] == ["Unknown"]


def test_same_role_reposted_on_one_board_is_one_job(client, boards, resume_bytes):
    """Employers sometimes list one role twice (same title, same city); users see one card linked to both postings."""
    from backend.services.ats import board_cache

    payload = boards.payloads[("ashby", "gammaco")]
    twin = {**payload["jobs"][1], "id": "g-3", "jobUrl": "https://jobs.ashbyhq.com/gammaco/g-3"}
    payload["jobs"].append(twin)
    board_cache.clear()
    h, sid, _ = _setup(client, resume_bytes)
    _run(client, h, sid)
    gamma = [i["job"] for i in _feed(client, h) if i["job"]["company"] == "Gamma Co"]
    assert len(gamma) == 1 and sorted(s["url"].rsplit("/", 1)[1] for s in gamma[0]["sources"]) == ["g-2", "g-3"]
    # One posting closing doesn't close the job while the other is still listed.
    payload["jobs"].remove(twin)
    board_cache.clear()
    _run(client, h, sid)
    assert [j["closed_at"] for j in (i["job"] for i in _feed(client, h)) if j["company"] == "Gamma Co"] == [None]
