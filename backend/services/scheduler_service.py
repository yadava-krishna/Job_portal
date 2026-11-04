"""Daily background discovery for every onboarded user (alert emails + Adzuna), then a daily report."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from backend.config import BackendSettings
from backend.db import session_factory
from backend.models import User

log = logging.getLogger(__name__)


class PortalScheduler:
    def __init__(self, settings: BackendSettings):
        self.settings = settings
        self.scheduler: BackgroundScheduler | None = None
        self.last_run: dict[str, Any] | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        if not self.settings.scheduler_enabled or self.scheduler is not None:
            return
        hour, minute = (int(x) for x in self.settings.scheduler_run_time.split(":"))
        self.scheduler = BackgroundScheduler(timezone=self.settings.timezone)
        self.scheduler.add_job(self.run_all, CronTrigger(hour=hour, minute=minute, timezone=self.settings.timezone),
                               id="daily_discovery", max_instances=1, coalesce=True, misfire_grace_time=6 * 3600)
        self.scheduler.start()
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

    def run_all(self) -> None:
        from backend.services import discovery_service, report_service

        if not self._lock.acquire(blocking=False):
            log.warning("Scheduled discovery already running; skipped.")
            return
        started = datetime.now().isoformat(timespec="seconds")
        done, failed = 0, 0
        try:
            db = session_factory()()
            try:
                users = db.execute(select(User).where(User.is_active.is_(True), User.onboarding_completed_at.is_not(None))).scalars().all()
                for user in users:
                    try:
                        discovery_service.run_discovery(db, self.settings, user, None, trigger="scheduled")
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
