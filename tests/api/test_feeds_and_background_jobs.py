"""Remote-job feeds in saved searches, background-job catch-up after downtime, and the admin jobs overview."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api_helpers import AR_JD, onboard

API = "/api/v1"


def _feed_job(sid: str, n: int, title: str, location: str):
    from backend.services.normalization import NormalizedJob

    return NormalizedJob(source=sid, source_key=f"{sid}:{n}", platform=sid.title(), company=f"Remote Co {n}", title=title,
                         external_job_id=str(n), location=location, locations=[location], work_mode="Remote",
                         description=AR_JD, job_url=f"https://example.com/{sid}/{n}", application_url=f"https://example.com/{sid}/{n}")


def test_remote_feeds_are_filtered_by_the_search_and_report_failures(client, resume_bytes, monkeypatch):
    from backend.services import saved_search_service as sss

    feeds = {
        "remotive": ([_feed_job("remotive", 1, "Accounts Receivable Analyst", "Worldwide"),     # kept: remote, open to India
                      _feed_job("remotive", 2, "Accounts Receivable Analyst", "USA only"),      # dropped: not open to India
                      _feed_job("remotive", 3, "Customer Service Representative", "Worldwide")], None),  # dropped: title
        "himalayas": ([], "HTTP 503 from himalayas.app"),
    }
    calls: list[str] = []
    monkeypatch.setattr(sss, "FEED_SOURCES", ("remotive", "himalayas"))
    monkeypatch.setattr(sss, "_fetch_feed", lambda sid: (calls.append(sid), feeds[sid])[1])

    h = onboard(client, "feeds@example.com", resume_bytes)
    search = {"name": "AR remote", "schedule": "daily", "min_match_score": 0,
              "criteria": {"keywords": ["Accounts Receivable"], "locations": ["Bengaluru"], "remote_ok": True, "sources": ["remote_feeds"]}}
    r = client.post(f"{API}/saved-searches", headers=h, json=search)
    assert r.status_code == 201, r.text
    run = client.post(f"{API}/saved-searches/{r.json()['id']}/run", headers=h).json()
    run = client.get(f"{API}/jobs/runs/{run['id']}", headers=h).json()

    assert calls == ["remotive", "himalayas"]  # each feed fetched once
    res = run["source_results"]
    assert res["remotive"]["status"] == "ok" and res["remotive"]["listings_checked"] == 3 and res["remotive"]["found"] == 1
    assert res["himalayas"]["status"] == "failed" and "503" in res["himalayas"]["message"]
    assert run["status"] == "partial"  # one feed failed, and the run says so
    titles = [(j["job"]["title"], j["job"]["company"]) for j in client.get(f"{API}/jobs", headers=h, params={"page_size": 50}).json()["items"]]
    assert titles == [("Accounts Receivable Analyst", "Remote Co 1")]


def test_new_searches_include_remote_feeds_and_legacy_board_sets_still_expand():
    from backend.schemas.discovery import SearchCriteria

    assert "remote_feeds" in SearchCriteria().sources
    legacy = SearchCriteria(sources=["greenhouse", "lever", "ashby", "remote_feeds"]).sources
    assert legacy == ["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "remote_feeds"]


def test_previous_fire_time_handles_daily_and_weekly_jobs():
    from apscheduler.triggers.cron import CronTrigger

    from backend.services.scheduler_service import previous_fire_time

    tz = "Asia/Kolkata"
    now = datetime(2026, 11, 13, 4, 0, tzinfo=timezone.utc)  # Friday 09:30 IST
    daily = previous_fire_time(CronTrigger(timezone=tz, hour=5, minute=0), now)
    assert daily.isoformat() == "2026-11-13T05:00:00+05:30"
    early = previous_fire_time(CronTrigger(timezone=tz, hour=21, minute=0), now)
    assert early.isoformat() == "2026-11-12T21:00:00+05:30"  # today's 21:00 hasn't come yet
    weekly = previous_fire_time(CronTrigger(timezone=tz, day_of_week="sun", hour=4, minute=0), now)
    assert weekly.isoformat() == "2026-11-08T04:00:00+05:30"


def test_jobs_missed_while_offline_are_caught_up_once(app_env):
    from backend.config import get_settings
    from backend.db import Base, get_engine, init_engine, session_factory
    from backend.models import JobRun
    from backend.services import jobs_registry
    from backend.services.scheduler_service import PortalScheduler

    settings = get_settings()
    init_engine(settings.database_url)
    Base.metadata.create_all(get_engine())
    with session_factory()() as db:  # source_refresh already ran just now; nothing else has
        db.add(JobRun(name="source_refresh", trigger="schedule", status="ok", started_at=datetime.now(timezone.utc)))
        db.commit()

    class FakeScheduler:
        def __init__(self):
            self.jobs = []

        def add_job(self, fn, trigger, args=None, id=None, **kw):
            self.jobs.append((id, args))

    s = PortalScheduler(settings)
    s.scheduler = FakeScheduler()
    s._catch_up_registry_jobs()
    ids = [i for i, _ in s.scheduler.jobs]
    expected = {f"catch_up:{n}" for n in jobs_registry.SCHEDULES} - {"catch_up:source_refresh", "catch_up:notification_dispatch",
                                                                      "catch_up:report_generation"}
    assert set(ids) == expected and len(ids) == len(expected)
    assert all(args[2] == "catch_up" for _, args in s.scheduler.jobs)

    # Once they have run, a restart schedules nothing.
    with session_factory()() as db:
        for i in ids:
            db.add(JobRun(name=i.split(":", 1)[1], trigger="catch_up", status="ok", started_at=datetime.now(timezone.utc)))
        db.commit()
    s.scheduler = FakeScheduler()
    s._catch_up_registry_jobs()
    assert s.scheduler.jobs == []


def test_admin_overview_shows_daily_discovery_and_inline_steps(app_env):
    from backend.config import get_settings
    from backend.db import Base, get_engine, init_engine, session_factory
    from backend.models import DiscoveryRun, User
    from backend.services import jobs_registry

    init_engine(get_settings().database_url)
    Base.metadata.create_all(get_engine())
    with session_factory()() as db:
        u = User(email="o@example.com", password_hash="x", full_name="O")
        db.add(u)
        db.flush()
        db.add(DiscoveryRun(user_id=u.id, trigger="catch_up", sources=["all"], status="partial",
                            started_at=datetime.now(timezone.utc) - timedelta(hours=1), completed_at=datetime.now(timezone.utc),
                            jobs_found=12, jobs_new=3, error_details=[{"type": "BOARD_FETCH_FAILED", "message": "Bjak (ashby): timed out."}]))
        db.commit()
        rows = {r["name"]: r for r in jobs_registry.overview(db)}
    d = rows["daily_discovery"]
    assert d["last_status"] == "partial" and d["last_trigger"] == "catch_up" and "Bjak" in d["last_error"] and d["last_ok_at"]
    assert rows["job_deduplication"]["last_status"] == "partial" and rows["job_deduplication"]["runs_with"] == "daily_discovery"


def test_board_fetch_retries_transient_failures_then_gives_up(app_env, monkeypatch):
    import httpx
    import pytest

    from backend.services.ats import base

    calls = []

    def flaky(request):
        calls.append(1)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"jobs": []})

    monkeypatch.setattr(base, "transport_override", httpx.MockTransport(flaky))
    assert base.get_json("https://boards-api.greenhouse.io/v1/boards/x/jobs") == {"jobs": []} and len(calls) == 3

    calls.clear()
    monkeypatch.setattr(base, "transport_override", httpx.MockTransport(lambda r: (calls.append(1), httpx.Response(503))[1]))
    with pytest.raises(base.AtsError) as e:
        base.get_json("https://boards-api.greenhouse.io/v1/boards/x/jobs")
    assert e.value.kind == "transient" and len(calls) == 3  # first try + two retries

    calls.clear()
    monkeypatch.setattr(base, "transport_override", httpx.MockTransport(lambda r: (calls.append(1), httpx.Response(404))[1]))
    with pytest.raises(base.AtsError):
        base.get_json("https://boards-api.greenhouse.io/v1/boards/x/jobs")
    assert len(calls) == 1  # a missing board is not retried


def test_skill_sync_skips_resume_lines_that_are_not_skills(client, resume_bytes):
    from backend.config import get_settings
    from backend.db import session_factory
    from backend.models import CandidateProfile, CandidateSkill, User
    from backend.services import career_service

    onboard(client, "longskill@example.com", resume_bytes)
    line = "Certified Solutions Architect Currently pursuing Amazon Web Services Certified Kubernetes Administrator Dec - 2023 " * 2
    with session_factory()() as db:
        user = db.query(User).filter_by(email="longskill@example.com").one()
        prof = db.query(CandidateProfile).filter_by(user_id=user.id).one()
        prof.confirmed_profile = {**(prof.confirmed_profile or {}), "skills": ["SQL", line, "  Power   BI "]}
        db.commit()
        career_service.sync_skills_from_profile(db, get_settings(), user)  # must not raise on the over-long line
        names = {s.name for s in db.query(CandidateSkill).filter_by(user_id=user.id)}
    assert "SQL" in names and "Power BI" in names and not any(len(n) > career_service.MAX_SKILL_NAME for n in names)


def test_runs_cut_off_by_a_restart_are_closed_and_caught_up(app_env):
    from backend.config import get_settings
    from backend.db import Base, get_engine, init_engine, session_factory
    from backend.models import JobRun
    from backend.services.scheduler_service import PortalScheduler

    settings = get_settings()
    init_engine(settings.database_url)
    Base.metadata.create_all(get_engine())
    with session_factory()() as db:
        db.add(JobRun(name="analytics_rollup", trigger="catch_up", status="running", started_at=datetime.now(timezone.utc)))
        db.commit()
    s = PortalScheduler(settings)
    s._close_interrupted_runs()
    with session_factory()() as db:
        row = db.query(JobRun).filter_by(name="analytics_rollup").one()
        assert row.status == "interrupted" and row.finished_at is not None and "restarted" in row.error

    class FakeScheduler:
        def __init__(self):
            self.ids = []

        def add_job(self, fn, trigger, args=None, id=None, **kw):
            self.ids.append(id)

    s.scheduler = FakeScheduler()
    s._catch_up_registry_jobs()
    assert "catch_up:analytics_rollup" in s.scheduler.ids  # an interrupted run doesn't count as having run
