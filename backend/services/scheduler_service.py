"""Daily background discovery for every onboarded user (alert emails + Adzuna), then a daily report."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from backend.config import BackendSettings
from backend.db import session_factory
from backend.models import User

log = logging.getLogger(__name__)
SEARCH_TICK_MINUTES = 15


class PortalScheduler:
    def __init__(self, settings: BackendSettings):
        self.settings = settings
        self.scheduler: BackgroundScheduler | None = None
        self.last_run: dict[str, Any] | None = None
        self.last_search_tick: dict[str, Any] | None = None
        self._lock = threading.Lock()
        self._search_lock = threading.Lock()

    def start(self) -> None:
        if not self.settings.scheduler_enabled or self.scheduler is not None:
            return
        hour, minute = (int(x) for x in self.settings.scheduler_run_time.split(":"))
        self.scheduler = BackgroundScheduler(timezone=self.settings.timezone)
        self.scheduler.add_job(self.run_all, CronTrigger(hour=hour, minute=minute, timezone=self.settings.timezone),
                               id="daily_discovery", max_instances=1, coalesce=True, misfire_grace_time=6 * 3600)
        self.scheduler.add_job(self.run_due_searches, IntervalTrigger(minutes=SEARCH_TICK_MINUTES, timezone=self.settings.timezone),
                               id="saved_searches", max_instances=1, coalesce=True)
        self._close_interrupted_runs()
        self.scheduler.start()
        self._catch_up_missed_daily_run(hour, minute)
        log.info("Portal scheduler started: daily discovery at %s %s", self.settings.scheduler_run_time, self.settings.timezone)

    def shutdown(self) -> None:
        if self.scheduler is not None:
            self.scheduler.shutdown(wait=False)
            self.scheduler = None

    def status(self) -> dict[str, Any]:
        job = self.scheduler.get_job("daily_discovery") if self.scheduler else None
        return {
            "enabled": self.settings.scheduler_enabled,
            "running": bool(self.scheduler and self.scheduler.running),
            "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
            "last_run": self.last_run,
        }

    def _close_interrupted_runs(self) -> None:
        from backend.services import saved_search_service

        db = session_factory()()
        try:
            n = saved_search_service.mark_interrupted(db)
            if n:
                log.warning("Marked %d discovery run(s) interrupted by the last restart.", n)
        except Exception:
            log.exception("Could not close interrupted discovery runs")
        finally:
            db.close()

    def _scheduled_run_since(self, since: datetime) -> bool:
        from backend.models import DiscoveryRun

        db = session_factory()()
        try:
            return db.execute(select(DiscoveryRun.id).where(DiscoveryRun.trigger.in_(("scheduled", "catch_up")),
                                                            DiscoveryRun.started_at >= since).limit(1)).first() is not None
        finally:
            db.close()

    def _catch_up_missed_daily_run(self, hour: int, minute: int) -> None:
        """If JobPilot was offline at today's scheduled time, run the daily discovery once shortly after start-up.

        The run is recorded with trigger "catch_up" so the history shows it was late. It is skipped if today's run
        (or an earlier catch-up) already happened, so restarts never cause duplicate daily runs.
        """
        from datetime import timedelta, timezone as tz
        from zoneinfo import ZoneInfo

        local = datetime.now(ZoneInfo(self.settings.timezone))
        due = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if local < due:
            return
        try:
            if self._scheduled_run_since(due.astimezone(tz.utc)):
                return
        except Exception:
            log.exception("Could not check for a missed daily run")
            return
        from apscheduler.triggers.date import DateTrigger

        log.warning("Today's %s discovery run was missed (JobPilot was offline); catching up in 2 minutes.", self.settings.scheduler_run_time)
        self.scheduler.add_job(self.run_all, DateTrigger(run_date=local + timedelta(minutes=2)), kwargs={"trigger": "catch_up"},
                               id="daily_catch_up", replace_existing=True, max_instances=1)

    def run_due_searches(self) -> None:
        """Saved searches whose schedule is due (daily/weekly), one at a time."""
        from backend.services import saved_search_service

        if not self._search_lock.acquire(blocking=False):
            return
        started = datetime.now().isoformat(timespec="seconds")
        done = 0
        try:
            db = session_factory()()
            try:
                done = saved_search_service.run_due(db, self.settings)
            except Exception:
                db.rollback()
                log.exception("Saved-search tick failed")
            finally:
                db.close()
        finally:
            self.last_search_tick = {"at": started, "searches_run": done}
            self._search_lock.release()

    def run_all(self, trigger: str = "scheduled") -> None:
        from backend.services import discovery_service, report_service, saved_search_service

        if not self._lock.acquire(blocking=False):
            log.warning("Scheduled discovery already running; skipped.")
            return
        if trigger == "catch_up":
            from datetime import timedelta, timezone as tz

            try:
                if self._scheduled_run_since(datetime.now(tz.utc) - timedelta(hours=12)):
                    log.info("Daily discovery already ran; catch-up skipped.")
                    self._lock.release()
                    return
            except Exception:
                log.exception("Could not check for an earlier run")
        started = datetime.now().isoformat(timespec="seconds")
        done, failed = 0, 0
        try:
            db = session_factory()()
            try:
                users = db.execute(select(User).where(User.is_active.is_(True), User.onboarding_completed_at.is_not(None))).scalars().all()
                for user in users:
                    try:
                        run = discovery_service.start_run(db, user, trigger, ["all"])
                        saved_search_service.run_all(db, self.settings, user, run, scheduled=True)
                        report_service.generate(db, self.settings, user, "daily")
                        done += 1
                    except Exception:
                        db.rollback()
                        failed += 1
                        log.exception("Scheduled discovery failed for user %s", user.id)
            finally:
                db.close()
        finally:
            self.last_run = {"started_at": started, "users_processed": done, "users_failed": failed}
            self._lock.release()


_scheduler: PortalScheduler | None = None


def get_scheduler(settings: BackendSettings) -> PortalScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = PortalScheduler(settings)
    return _scheduler
