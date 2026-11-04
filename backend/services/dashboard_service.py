"""Dashboard statistics, activity feed and analytics for one user."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import Application, ApplicationEvent, DiscoveryRun, User, UserJob
from core import timeutil

PENDING = ("PREPARED", "OPENED", "CONFIRMATION_PENDING")


def _local_date(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timeutil.tz()).date()


def summary(db: Session, user: User) -> dict[str, Any]:
    ujs = db.execute(select(UserJob).where(UserJob.user_id == user.id)).unique().scalars().all()
    apps = db.execute(select(Application).where(Application.user_id == user.id)).unique().scalars().all()
    today = timeutil.today()
    scores = [u.match_score for u in ujs if u.match_score is not None and u.status != "dismissed"]
    by_platform: dict[str, dict[str, Any]] = defaultdict(lambda: {"discovered": 0, "shortlisted": 0, "applied": 0, "scores": []})
    for u in ujs:
        p = by_platform[u.job.platform]
        p["discovered"] += 1
        p["shortlisted"] += u.status == "shortlisted"
        if u.match_score is not None:
            p["scores"].append(u.match_score)
    for a in apps:
        if a.status == "SUBMITTED":
            by_platform[a.job.platform]["applied"] += 1
    platforms = [{"platform": k, "discovered": v["discovered"], "shortlisted": v["shortlisted"], "applied": v["applied"],
                  "average_score": round(sum(v["scores"]) / len(v["scores"]), 1) if v["scores"] else None}
                 for k, v in sorted(by_platform.items())]
    last_run = db.execute(select(DiscoveryRun).where(DiscoveryRun.user_id == user.id).order_by(DiscoveryRun.id.desc()).limit(1)).scalar_one_or_none()
    return {
        "total_discovered": len(ujs),
        "total_shortlisted": sum(u.status == "shortlisted" for u in ujs),
        "total_applied": sum(a.status == "SUBMITTED" for a in apps),
        "total_saved": sum(u.is_saved for u in ujs),
        "pending_applications": sum(a.status in PENDING for a in apps),
        "average_match_score": round(sum(scores) / len(scores), 1) if scores else None,
        "discovered_today": sum(_local_date(u.discovered_at) == today for u in ujs),
        "applied_today": sum(a.status == "SUBMITTED" and _local_date(a.submitted_at) == today for a in apps),
        "posted_today_verified": sum(u.job.posted_at == today and u.job.posted_at_source in ("platform_api", "platform_page", "user_provided") for u in ujs),
        "interviews": sum(a.stage == "interview" for a in apps),
        "offers": sum(a.stage == "offer" for a in apps),
        "platforms": platforms,
        "last_discovery_run": None if last_run is None else {
            "id": last_run.id, "status": last_run.status, "started_at": last_run.started_at, "completed_at": last_run.completed_at,
            "jobs_found": last_run.jobs_found, "jobs_new": last_run.jobs_new, "jobs_matched": last_run.jobs_matched,
            "errors": len(last_run.error_details or []),
        },
    }


def activity(db: Session, user: User, limit: int = 30) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for e in db.execute(select(ApplicationEvent, Application).join(Application, Application.id == ApplicationEvent.application_id)
                        .where(ApplicationEvent.user_id == user.id).order_by(ApplicationEvent.id.desc()).limit(limit)).unique().all():
        ev, app = e
        items.append({"kind": "application", "event_type": ev.event_type, "at": ev.created_at, "application_id": app.id,
                      "title": app.job.title, "company": app.job.company, "to_status": ev.to_status, "details": ev.details})
    for r in db.execute(select(DiscoveryRun).where(DiscoveryRun.user_id == user.id).order_by(DiscoveryRun.id.desc()).limit(10)).scalars():
        items.append({"kind": "discovery", "event_type": f"DISCOVERY_{r.status.upper()}", "at": r.started_at, "run_id": r.id,
                      "details": f"{r.jobs_found} found, {r.jobs_new} new, {r.jobs_matched} shortlisted, {r.duplicates} duplicates",
                      "sources": r.sources})
    items.sort(key=lambda x: x["at"], reverse=True)
    return items[:limit]


def analytics(db: Session, user: User, days: int = 30) -> dict[str, Any]:
    today = timeutil.today()
    start = today - timedelta(days=days - 1)
    start_dt = datetime.combine(start, time.min, tzinfo=timeutil.tz()).astimezone(timezone.utc)
    apps = db.execute(select(Application).where(Application.user_id == user.id)).unique().scalars().all()
    ujs = db.execute(select(UserJob.discovered_at, UserJob.status).where(UserJob.user_id == user.id, UserJob.discovered_at >= start_dt)).all()
    per_day_applied = Counter(_local_date(a.submitted_at) for a in apps if a.status == "SUBMITTED" and a.submitted_at)
    per_day_found = Counter(_local_date(d) for d, _ in ujs)
    series = [{"date": (start + timedelta(days=i)).isoformat(), "discovered": per_day_found.get(start + timedelta(days=i), 0),
               "applied": per_day_applied.get(start + timedelta(days=i), 0)} for i in range(days)]
    total_jobs = db.execute(select(func.count()).select_from(UserJob).where(UserJob.user_id == user.id)).scalar_one()
    shortlisted = db.execute(select(func.count()).select_from(UserJob).where(UserJob.user_id == user.id, UserJob.status.in_(["shortlisted", "applied"]))).scalar_one()
    submitted = [a for a in apps if a.status == "SUBMITTED"]
    funnel = [
        {"stage": "Discovered", "count": total_jobs},
        {"stage": "Shortlisted", "count": shortlisted},
        {"stage": "Prepared", "count": len(apps)},
        {"stage": "Applied", "count": len(submitted)},
        {"stage": "Interview", "count": sum(a.stage in ("interview", "offer") for a in submitted)},
        {"stage": "Offer", "count": sum(a.stage == "offer" for a in submitted)},
    ]
    by_platform: dict[str, Counter] = defaultdict(Counter)
    for a in submitted:
        by_platform[a.job.platform]["applied"] += 1
        if a.stage in ("screening", "interview", "offer"):
            by_platform[a.job.platform]["responses"] += 1
        if a.stage == "rejected":
            by_platform[a.job.platform]["rejected"] += 1
    platform_rates = [{"platform": p, "applied": c["applied"], "responses": c["responses"], "rejected": c["rejected"],
                       "response_rate": round(100 * c["responses"] / c["applied"], 1) if c["applied"] else 0.0}
                      for p, c in sorted(by_platform.items())]
    status_counts = Counter(a.status for a in apps)
    return {"days": days, "series": series, "funnel": funnel, "platforms": platform_rates, "status_counts": dict(status_counts)}
