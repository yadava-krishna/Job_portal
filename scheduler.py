"""Daily scheduler (APScheduler) with retries, catch-up after downtime and graceful shutdown."""

from __future__ import annotations

import logging
import signal
import threading
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from core import timeutil
from core.settings import Settings
from database.db import Database
from runner import DailyRunner, RunAlreadyInProgress, RunResult

log = logging.getLogger(__name__)


def should_catch_up(db: Database, settings: Settings, now: datetime) -> bool:
    """True when today's scheduled time has passed and no scheduled/catch-up run completed today."""
    if not settings.scheduler.run_missed_on_startup:
        return False
    scheduled = now.replace(hour=settings.scheduler.hour, minute=settings.scheduler.minute, second=0, microsecond=0)
    if now < scheduled:
        return False
    return not db.completed_run_exists(now.date(), ("scheduled", "catchup"))


def run_with_retries(settings: Settings, trigger: str, stop_event: threading.Event) -> RunResult | None:
    attempts = settings.scheduler.retry_attempts
    for attempt in range(1, attempts + 1):
        if stop_event.is_set():
            return None
        try:
            result = DailyRunner(settings, stop_event=stop_event).run(trigger=trigger, attempt=attempt)
            print(result.summary_text, flush=True)
            return result
        except RunAlreadyInProgress as exc:
            log.warning("%s", exc)
            return None
        except Exception as exc:
            if attempt == attempts:
                log.error("Daily run failed after %d attempt(s): %s", attempts, exc)
                return None
            delay = settings.scheduler.retry_backoff_seconds * attempt
            log.warning("Daily run attempt %d failed (%s); retrying in %.0f s.", attempt, exc, delay)
            if stop_event.wait(delay):
                return None
    return None


def start_scheduler(settings: Settings) -> None:
    timeutil.set_timezone(settings.timezone)
    stop_event = threading.Event()
    scheduler = BlockingScheduler(timezone=settings.timezone)

    scheduler.add_job(
        run_with_retries,
        CronTrigger(hour=settings.scheduler.hour, minute=settings.scheduler.minute, timezone=settings.timezone),
        args=[settings, "scheduled", stop_event],
        id="daily_job_run",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=int(settings.scheduler.misfire_grace_hours * 3600) or None,
        replace_existing=True,
    )

    db = Database(settings.db_path)
    try:
        catch_up = should_catch_up(db, settings, timeutil.now())
    finally:
        db.close()
    if catch_up:
        log.info("Today's %s run was missed; running it now.", settings.scheduler.run_time)
        scheduler.add_job(run_with_retries, args=[settings, "catchup", stop_event], id="catch_up_run", max_instances=1)

    def shutdown(signum, _frame):
        log.info("Received %s; finishing the current step and shutting down.", signal.Signals(signum).name)
        stop_event.set()
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    log.info("Scheduler started: daily run at %s %s. Press Ctrl+C to stop.", settings.scheduler.run_time, settings.timezone)
    try:
        # Returns after shutdown(); the job thread (if any) sees stop_event, records the run
        # as interrupted at its next checkpoint, and is joined before the process exits.
        scheduler.start()
    finally:
        stop_event.set()
        log.info("Scheduler stopped.")
