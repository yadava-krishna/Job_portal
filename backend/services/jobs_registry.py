"""Named background jobs (spec 02 §19). Every run is recorded in job_runs with status, attempts and details, so the
admin page shows what ran, when, and what failed. Jobs are idempotent and guarded so two copies never run at once.

Jobs whose external dependency isn't configured (e-mail delivery without SMTP, IMAP alert ingestion without any
connected mailbox) record status `blocked` with the reason instead of pretending to succeed.
"""

from __future__ import annotations

import logging
import shutil
import threading
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.db import session_factory
from backend.models import (AnalyticsDaily, AnalyticsEvent, Application, EmailIntegration, Interview, JobRun, MentorAction,
                            Notification, RefreshToken, User, utcnow)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class JobSpec:
    name: str
    schedule: str          # human-readable; the scheduler wiring is in scheduler_service
    owner: str
    description: str
    fn: Callable[[Session, BackendSettings], dict[str, Any]]
    retries: int = 2


class Blocked(Exception):
    """The job can't run because something only the owner can provide is missing."""


_locks: dict[str, threading.Lock] = {}


def run(name: str, settings: BackendSettings, trigger: str = "schedule") -> JobRun:
    spec = REGISTRY[name]
    lock = _locks.setdefault(name, threading.Lock())
    with session_factory()() as db:
        if not lock.acquire(blocking=False):
            row = JobRun(name=name, trigger=trigger, status="skipped", finished_at=utcnow(), details={"reason": "already running"})
            db.add(row)
            db.commit()
            return row
        row = JobRun(name=name, trigger=trigger, status="running")
        db.add(row)
        db.commit()
        try:
            for attempt in range(1, spec.retries + 2):
                row.attempts = attempt
                try:
                    row.details = spec.fn(db, settings) or {}
                    row.status = "ok"
                    break
                except Blocked as b:
                    db.rollback()
                    row.status, row.error = "blocked", str(b)
                    break
                except Exception as exc:  # retry with backoff, then record the failure
                    db.rollback()
                    row.error = f"{type(exc).__name__}: {exc}"[:2000]
                    log.warning("job %s attempt %s failed: %s", name, attempt, row.error)
                    if attempt <= spec.retries:
                        time.sleep(min(30, 2 ** attempt))
                    else:
                        row.status = "failed"
        finally:
            row.finished_at = utcnow()
            db.add(row)
            db.commit()
            db.refresh(row)
            lock.release()
        return row


def _users(db: Session) -> list[User]:
    return list(db.execute(select(User).where(User.is_active.is_(True), User.onboarding_completed_at.is_not(None))).scalars())


# ---------------- job bodies ----------------

def _daily_discovery(db, settings):
    from backend.services.scheduler_service import get_scheduler
    get_scheduler(settings).run_all(trigger="scheduled")
    return {"note": "per-user discovery runs are recorded in discovery_runs"}


def _source_refresh(db, settings):
    from backend.services import source_registry
    from backend.services.connectors.registry import registry
    health = registry.list_health()
    try:
        source_registry.refresh(db) if hasattr(source_registry, "refresh") else None
    except Exception as exc:
        log.info("source registry refresh failed: %s", exc)
    return {"connectors": len(health), "unhealthy": sum(1 for h in health if getattr(h, "status", "") not in ("ok", "healthy", "unknown"))}


def _normalise_and_dedupe(db, settings):
    """Deduplication runs inline in every discovery run; this back-fills derived signals on jobs stored before they
    existed (visa sponsorship from the description, seniority from the title or stated experience)."""
    from sqlalchemy import or_, select

    from backend.models import Job
    from backend.services.career_service import infer_seniority, sponsorship_signal
    out = {"sponsorship": 0, "seniority": 0}
    rows = db.execute(select(Job).where(or_(Job.seniority.is_(None), Job.sponsorship_signal.is_(None),
                                            Job.sponsorship_signal == "unknown"))).scalars().all()
    for job in rows:
        sig, ev = sponsorship_signal(job.description)
        if sig != (job.sponsorship_signal or "unknown"):
            job.sponsorship_signal, job.sponsorship_evidence = sig, (ev or None) and ev[:300]
            out["sponsorship"] += 1
        if not job.seniority and (lvl := infer_seniority(job.title, job.experience_min)):
            job.seniority = lvl
            out["seniority"] += 1
    db.commit()
    return out


def _job_matching(db, settings):
    from backend.services import matching_service
    _normalise_and_dedupe(db, settings)  # signals the scorer and filters rely on
    n = 0
    for u in _users(db):
        try:
            n += matching_service.rescore_user(db, settings, u)
        except Exception as exc:  # one user's profile problem must not stop the others
            log.info("rescore skipped for user %s: %s", u.id, exc)
    return {"rescored": n}


def _gap_generation(db, settings):
    from backend.services import career_service
    done = 0
    for u in _users(db):
        try:
            career_service.generate_gaps(db, settings, u)
            done += 1
        except Exception as exc:
            log.info("gaps skipped for user %s: %s", u.id, exc)
    return {"users": done}


def _resume_feedback(db, settings):
    from backend.models import ResumeFeedback, ResumeVersion
    from backend.services import studio_service
    n = 0
    for v in db.execute(select(ResumeVersion).where(ResumeVersion.status == "draft")).unique().scalars().all():
        latest = db.execute(select(ResumeFeedback.checksum).where(ResumeFeedback.resume_version_id == v.id)
                            .order_by(ResumeFeedback.generated_at.desc())).scalars().first()
        if latest != v.content_checksum:
            studio_service.feedback(db, settings, db.get(User, v.user_id), v, None)
            n += 1
    return {"versions_checked": n}


def _resource_refresh(db, settings):
    from backend.services import learning_service
    return learning_service.refresh_links(db)


def _notification_dispatch(db, settings):
    """Reminders (follow-ups, interviews within 24h, actions due) as in-app notifications, deduplicated per item/day;
    e-mail copies only when SMTP is configured and the user opted in."""
    from backend.services import email_service, platform_service
    now = utcnow()
    today = now.date().isoformat()
    created = 0

    def notify(uid, kind, title, body, link, key):
        nonlocal created
        if db.execute(select(Notification.id).where(Notification.user_id == uid, Notification.dedupe_key == key)).first():
            return
        db.add(Notification(user_id=uid, kind=kind, title=title, body=body, link=link, dedupe_key=key))
        created += 1

    for a in db.execute(select(Application).where(Application.follow_up_at.is_not(None), Application.follow_up_at <= now,
                                                  Application.stage.notin_(("rejected", "withdrawn", "archived")))).unique().scalars():
        notify(a.user_id, "follow_up_due", f"Follow up: {a.job.title} at {a.job.company}", "Your follow-up date has arrived.",
               "/applied", f"followup:{a.id}:{a.follow_up_at.date().isoformat()}")
    for iv in db.execute(select(Interview).where(Interview.scheduled_at >= now, Interview.scheduled_at <= now + timedelta(hours=24),
                                                 Interview.outcome == "scheduled")).scalars():
        notify(iv.user_id, "interview_upcoming", f"Interview soon: {iv.round_name or 'Interview'}",
               f"Scheduled for {iv.scheduled_at:%d %b %H:%M} (UTC). Practise in Interview prep.", "/interview-prep", f"interview:{iv.id}")
    for act in db.execute(select(MentorAction).where(MentorAction.completed_at.is_(None), MentorAction.dismissed_at.is_(None),
                                                     MentorAction.due_on.is_not(None), MentorAction.due_on <= now.date())).scalars():
        notify(act.user_id, "action_due", f"Action due: {act.title[:80]}", act.reason[:300], "/mentor", f"action:{act.id}:{today}")
    db.commit()
    emailed = 0
    if email_service.is_smtp_configured():
        for u in _users(db):
            if not platform_service.has_consent(db, u.id, "email_notifications"):
                continue
            unsent = db.execute(select(Notification).where(Notification.user_id == u.id, Notification.read_at.is_(None),
                                                           Notification.created_at >= now - timedelta(hours=24))).scalars().all()
            if unsent and email_service.send_email(u.email, f"JobPilot: {len(unsent)} update(s)",
                                                   "<br>".join(f"<b>{n.title}</b> {n.body or ''}" for n in unsent[:20])):
                emailed += 1
    return {"in_app_created": created, "emails_sent": emailed, "email_channel": "on" if email_service.is_smtp_configured() else "not configured"}


def _alert_email_ingestion(db, settings):
    if not db.execute(select(EmailIntegration.id).where(EmailIntegration.enabled.is_(True))).first():
        raise Blocked("No user has connected a job-alert mailbox (Settings > Email). Nothing to ingest.")
    return {"note": "mailbox alerts are ingested inside each user's daily discovery run"}


def _report_generation(db, settings):
    from backend.services import report_service
    n = 0
    for u in _users(db):
        try:
            report_service.generate(db, settings, u, "daily")
            n += 1
        except Exception as exc:
            log.info("report skipped for user %s: %s", u.id, exc)
    return {"reports": n}


def _visa_check(db, settings):
    from backend.services import international_service
    return international_service.check_sources(db)


def _analytics_rollup(db, settings):
    day = (utcnow() - timedelta(days=1)).date()
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    end = start + timedelta(days=1)
    rows = db.execute(select(AnalyticsEvent.name, func.count()).where(AnalyticsEvent.created_at >= start, AnalyticsEvent.created_at < end,
                                                                      AnalyticsEvent.success.is_(True)).group_by(AnalyticsEvent.name)).all()
    metrics = {f"event:{n}": c for n, c in rows}
    metrics["active_candidates"] = db.execute(select(func.count(func.distinct(AnalyticsEvent.user_id)))
                                              .where(AnalyticsEvent.created_at >= start, AnalyticsEvent.created_at < end)).scalar() or 0
    for k, v in metrics.items():
        row = db.execute(select(AnalyticsDaily).where(AnalyticsDaily.day == day, AnalyticsDaily.metric == k)).scalar_one_or_none()
        if row is None:
            db.add(AnalyticsDaily(day=day, metric=k, value=float(v)))
        else:
            row.value = float(v)
    db.commit()
    return {"day": day.isoformat(), "metrics": len(metrics)}


RETENTION = {"refresh_tokens_days_after_expiry": 7, "read_notifications_days": 90, "job_runs_days": 90,
             "analytics_events_days": 400, "app_log_files_days": 30}


def _cleanup(db, settings):
    now = utcnow()
    out = {}
    out["refresh_tokens"] = db.execute(delete(RefreshToken).where(RefreshToken.expires_at < now - timedelta(days=RETENTION["refresh_tokens_days_after_expiry"]))).rowcount
    out["notifications"] = db.execute(delete(Notification).where(Notification.read_at.is_not(None),
                                                                 Notification.read_at < now - timedelta(days=RETENTION["read_notifications_days"]))).rowcount
    out["job_runs"] = db.execute(delete(JobRun).where(JobRun.started_at < now - timedelta(days=RETENTION["job_runs_days"]))).rowcount
    out["analytics_events"] = db.execute(delete(AnalyticsEvent).where(AnalyticsEvent.created_at < now - timedelta(days=RETENTION["analytics_events_days"]))).rowcount
    db.commit()
    from backend.services import discovery_service
    out["expired_jobs"] = discovery_service.reap_expired_jobs(db, max_age_days=45)
    logs = settings.storage_dir / "logs"
    removed = 0
    if logs.is_dir():
        cutoff = time.time() - RETENTION["app_log_files_days"] * 86400
        for f in logs.glob("*.log"):
            if f.stat().st_mtime < cutoff:
                f.unlink(missing_ok=True)
                removed += 1
    out["log_files"] = removed
    usage = shutil.disk_usage(settings.storage_dir if settings.storage_dir.exists() else "/")
    out["disk_used_percent"] = round(100 * usage.used / usage.total, 1)
    return out


REGISTRY: dict[str, JobSpec] = {s.name: s for s in [
    JobSpec("daily_discovery", "daily at SCHEDULER_RUN_TIME (+ catch-up after downtime)", "discovery",
            "Discover jobs for every onboarded user from their saved searches and connected sources.", _daily_discovery, retries=0),
    JobSpec("source_refresh", "daily 05:00", "discovery", "Refresh connector health/telemetry.", _source_refresh),
    JobSpec("job_normalisation", "inline with discovery", "discovery", "Normalise raw postings into canonical jobs.", _normalise_and_dedupe, retries=0),
    JobSpec("job_deduplication", "inline with discovery", "discovery", "Merge duplicate postings across sources.", _normalise_and_dedupe, retries=0),
    JobSpec("job_matching", "daily 06:00", "matching", "Re-score every user's feed with the current scoring version.", _job_matching),
    JobSpec("gap_generation", "daily 06:30", "career", "Recompute each user's gaps from their relevant jobs and rejections.", _gap_generation),
    JobSpec("resume_feedback_generation", "daily 07:00", "resume studio", "Refresh ATS/readiness feedback for changed drafts.", _resume_feedback),
    JobSpec("resource_refresh", "weekly, Sunday 04:00", "learning", "Re-check learning resource links; hide broken ones.", _resource_refresh),
    JobSpec("notification_dispatch", "every 30 minutes", "notifications", "Follow-up, interview and action reminders; optional e-mail.", _notification_dispatch),
    JobSpec("alert_email_ingestion", "with daily discovery", "discovery", "Read job-alert e-mails from connected mailboxes.", _alert_email_ingestion, retries=0),
    JobSpec("report_generation", "daily 21:00", "reports", "Daily Excel application reports per user.", _report_generation),
    JobSpec("visa_source_check", "daily 03:00", "international", "Fetch official visa pages and record a fingerprint.", _visa_check),
    JobSpec("visa_change_detection", "with visa_source_check", "international", "Flag changed official pages to watchers.", _visa_check, retries=0),
    JobSpec("analytics_rollup", "daily 00:30", "analytics", "Roll up yesterday's events into daily metrics.", _analytics_rollup),
    JobSpec("cleanup_and_retention", "daily 01:30", "platform", "Apply retention rules, expire stale jobs, prune logs, check disk.", _cleanup),
]}

# (name, cron fields) wired by scheduler_service; jobs marked "inline" run as part of daily_discovery.
SCHEDULES: dict[str, dict[str, Any]] = {
    "source_refresh": {"hour": 5, "minute": 0}, "job_matching": {"hour": 6, "minute": 0}, "gap_generation": {"hour": 6, "minute": 30},
    "resume_feedback_generation": {"hour": 7, "minute": 0}, "resource_refresh": {"day_of_week": "sun", "hour": 4, "minute": 0},
    "notification_dispatch": {"minute": "*/30"}, "report_generation": {"hour": 21, "minute": 0}, "visa_source_check": {"hour": 3, "minute": 0},
    "analytics_rollup": {"hour": 0, "minute": 30}, "cleanup_and_retention": {"hour": 1, "minute": 30},
}


# Jobs that run as a step of another job. Until they have a run of their own, they show the parent's latest run.
RUNS_WITH = {"job_normalisation": "daily_discovery", "job_deduplication": "daily_discovery", "visa_change_detection": "visa_source_check"}
_DISCOVERY_STATUS = {"completed": "ok", "partial": "partial", "failed": "failed", "running": "running"}


def _discovery_overview(db: Session) -> dict[str, Any]:
    """The daily discovery is recorded as discovery runs (one per user), not job runs: report its latest scheduled run."""
    from backend.models import DiscoveryRun

    auto = DiscoveryRun.trigger.in_(("scheduled", "catch_up"))
    last = db.execute(select(DiscoveryRun).where(auto).order_by(DiscoveryRun.started_at.desc())).scalars().first()
    ok = db.execute(select(DiscoveryRun).where(auto, DiscoveryRun.status.in_(("completed", "partial")))
                    .order_by(DiscoveryRun.started_at.desc())).scalars().first()
    error = None
    if last and last.error_details:
        msgs = [e.get("message") for e in last.error_details if isinstance(e, dict) and e.get("message")]
        error = "; ".join(msgs[:3]) or None
    return {"last_status": _DISCOVERY_STATUS.get(last.status, last.status) if last else None,
            "last_started_at": last.started_at if last else None, "last_error": error,
            "last_ok_at": (ok.completed_at or ok.started_at) if ok else None,
            "last_details": {"trigger": last.trigger, "jobs_found": last.jobs_found, "jobs_new": last.jobs_new} if last else None,
            "last_trigger": last.trigger if last else None}


def overview(db: Session) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for name, spec in REGISTRY.items():
        base = {"name": name, "schedule": spec.schedule, "owner": spec.owner, "description": spec.description, "retries": spec.retries,
                "runs_with": RUNS_WITH.get(name)}
        if name == "daily_discovery":
            out[name] = {**base, **_discovery_overview(db)}
            continue
        last = db.execute(select(JobRun).where(JobRun.name == name).order_by(JobRun.started_at.desc())).scalars().first()
        ok = db.execute(select(JobRun).where(JobRun.name == name, JobRun.status == "ok").order_by(JobRun.started_at.desc())).scalars().first()
        out[name] = {**base, "last_status": last.status if last else None, "last_started_at": last.started_at if last else None,
                     "last_error": last.error if last else None, "last_ok_at": ok.finished_at if ok else None,
                     "last_details": last.details if last else None, "last_trigger": last.trigger if last else None}
    for name, parent in RUNS_WITH.items():
        if name in out and out[name]["last_status"] is None and parent in out:
            p = out[parent]
            out[name].update({k: p[k] for k in ("last_status", "last_started_at", "last_error", "last_ok_at", "last_trigger")})
    return list(out.values())
