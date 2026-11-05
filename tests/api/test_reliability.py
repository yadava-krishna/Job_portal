"""Stage H: the daily discovery run is caught up once after downtime, never duplicated."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api_helpers import onboard


def _scheduler(monkeypatch, run_time: str):
    from backend.config import get_settings
    from backend.services.scheduler_service import PortalScheduler

    settings = get_settings().model_copy(update={"scheduler_enabled": True, "scheduler_run_time": run_time})
    s = PortalScheduler(settings)
    calls: list[str] = []
    monkeypatch.setattr(s, "run_all", lambda trigger="scheduled": calls.append(trigger))
    return s, calls


def _past_run_time() -> str:
    from zoneinfo import ZoneInfo

    local = datetime.now(ZoneInfo("Asia/Kolkata")) - timedelta(minutes=30)
    return local.strftime("%H:%M") if local.date() == datetime.now(ZoneInfo("Asia/Kolkata")).date() else "00:00"


def test_missed_daily_run_is_scheduled_once_after_start(client, monkeypatch):
    s, _ = _scheduler(monkeypatch, _past_run_time())
    s.start()
    try:
        assert s.scheduler.get_job("daily_catch_up") is not None
    finally:
        s.shutdown()


def test_no_catch_up_when_todays_run_already_happened(client, resume_bytes, monkeypatch):
    from backend.db import session_factory
    from backend.models import DiscoveryRun, User

    onboard(client, "rel@example.com", resume_bytes)
    with session_factory()() as db:
        user = db.query(User).one()
        db.add(DiscoveryRun(user_id=user.id, trigger="scheduled", sources=["all"], status="completed", error_details=[], platform_stats={},
                            started_at=datetime.now(timezone.utc)))
        db.commit()
    s, _ = _scheduler(monkeypatch, _past_run_time())
    s.start()
    try:
        assert s.scheduler.get_job("daily_catch_up") is None
    finally:
        s.shutdown()


def test_catch_up_run_is_recorded_honestly_and_not_repeated(client, resume_bytes, monkeypatch):
    from backend.config import get_settings
    from backend.db import session_factory
    from backend.models import DiscoveryRun
    from backend.services import saved_search_service
    from backend.services.scheduler_service import PortalScheduler

    h = onboard(client, "rel2@example.com", resume_bytes)
    assert client.get("/api/v1/onboarding", headers=h).json()["completed"]  # completion is recorded lazily
    monkeypatch.setattr(saved_search_service, "run_all", lambda db, settings, user, run, scheduled=True: None)
    s = PortalScheduler(get_settings())
    s.run_all(trigger="catch_up")
    s.run_all(trigger="catch_up")  # a second start-up shortly after: nothing new
    with session_factory()() as db:
        triggers = [r.trigger for r in db.query(DiscoveryRun).all()]
    assert triggers == ["catch_up"]
