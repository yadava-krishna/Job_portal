"""Dashboard action centre: what needs the user's attention, in one request.

Every section is built from real rows. Nothing is estimated, and an empty section means there is nothing to do.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.models import Application, CandidateProfile, DiscoveryRun, Job, JobPreference, JobView, Resume, User, UserJob, utcnow
from backend.models.career import ResumeExport, ResumeVersion
from backend.services import freshness, tracker_service
from backend.services import discovery_service
from backend.services.discovery_service import RAN
from backend.services.normalization import salary_label

NEW_JOB_DAYS = 7
DEFAULT_MIN_SCORE = 70.0
TOP = 5


def _job_row(uj: UserJob, now) -> dict[str, Any]:
    j = uj.job
    return {"user_job_id": uj.id, "title": j.title, "company": j.company, "match_score": uj.match_score,
            "location": j.location_normalized or j.location, "salary": salary_label(j), "discovered_at": uj.discovered_at,
            "freshness": freshness.status(j, now)["state"], "eligibility_status": uj.eligibility_status}


def _open(job: Job) -> bool:
    return job.closed_at is None and not job.is_expired


def new_jobs(db: Session, user: User, now) -> dict[str, Any]:
    pref = db.execute(select(JobPreference).where(JobPreference.user_id == user.id)).scalar_one_or_none()
    min_score = float(pref.min_match_score) if pref and pref.min_match_score is not None else DEFAULT_MIN_SCORE
    since = now - timedelta(days=NEW_JOB_DAYS)
    viewed = select(JobView.job_id).where(JobView.user_id == user.id)
    rows = db.execute(select(UserJob).join(Job, Job.id == UserJob.job_id)
                      .where(UserJob.user_id == user.id, UserJob.status.in_(["new", "shortlisted"]), UserJob.discovered_at >= since,
                             UserJob.match_score >= min_score, Job.closed_at.is_(None), Job.is_expired.is_(False),
                             or_(UserJob.eligibility.is_(None), UserJob.eligibility != "fail"),
                             UserJob.job_id.not_in(viewed))
                      .order_by(UserJob.match_score.desc(), UserJob.discovered_at.desc())).unique().scalars().all()
    return {"count": len(rows), "min_score": min_score, "days": NEW_JOB_DAYS, "top": [_job_row(u, now) for u in rows[:TOP]]}


def saved_jobs(db: Session, user: User, now) -> dict[str, Any]:
    applied = select(Application.job_id).where(Application.user_id == user.id)
    rows = db.execute(select(UserJob).where(UserJob.user_id == user.id, UserJob.is_saved.is_(True),
                                            UserJob.status.in_(["new", "shortlisted"]), UserJob.job_id.not_in(applied))
                      .order_by(UserJob.saved_at.desc().nulls_last())).unique().scalars().all()
    closed = [u for u in rows if not _open(u.job)]
    return {"count": len(rows), "no_longer_open": len(closed), "top": [_job_row(u, now) for u in rows[:TOP]]}


def recent_submitted(db: Session, user: User) -> list[dict[str, Any]]:
    apps = db.execute(select(Application).where(Application.user_id == user.id, Application.status == "SUBMITTED")
                      .order_by(Application.submitted_at.desc().nulls_last()).limit(TOP)).unique().scalars().all()
    return [{"application_id": a.id, "title": a.job.title, "company": a.job.company, "submitted_at": a.submitted_at,
             "stage": a.stage or "applied"} for a in apps]


def resume_status(db: Session, user: User) -> dict[str, Any]:
    active = db.execute(select(Resume).where(Resume.user_id == user.id, Resume.is_active.is_(True))
                        .order_by(Resume.uploaded_at.desc()).limit(1)).scalar_one_or_none()
    profile = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    versions = db.execute(select(ResumeVersion).where(ResumeVersion.user_id == user.id, ResumeVersion.status != "archived")
                          .order_by(ResumeVersion.updated_at.desc())).scalars().all()
    last_export = db.execute(select(func.max(ResumeExport.created_at)).where(ResumeExport.user_id == user.id)).scalar_one_or_none()
    latest = versions[0] if versions else None
    if latest is None:
        state, message = "missing", "You haven't built a resume in Resume Studio yet."
    elif last_export is None:
        state, message = "not_exported", "Your resume has never been exported to PDF or Word."
    else:
        state, message = "ready", None
    return {
        "state": state, "message": message,
        "uploaded": None if active is None else {"filename": active.original_filename, "uploaded_at": active.uploaded_at},
        "profile_confirmed": bool(profile and profile.confirmed_at),
        "versions": len(versions),
        "latest": None if latest is None else {"id": latest.id, "name": latest.name, "updated_at": latest.updated_at, "status": latest.status},
        "last_export_at": last_export,
    }


def discovery_health(db: Session, user: User) -> dict[str, Any]:
    run = db.execute(select(DiscoveryRun).where(DiscoveryRun.user_id == user.id).order_by(DiscoveryRun.id.desc()).limit(1)).scalar_one_or_none()
    if run is None:
        return {"last_run": None, "problems": [], "state": "never_run"}
    problems = []
    for key, entry in (run.source_results or {}).items():
        st = entry.get("status")
        if st in RAN and st != "partial":
            continue
        if st in ("failed", "partial", "error"):
            problems.append({"source": key, "label": entry.get("label") or key, "status": st, "message": entry.get("message")})
    if run.status == "failed" and discovery_service.nothing_configured(run):
        state = "not_configured"
    elif run.status == "failed":
        state = "failed"
    elif run.status in ("running", "queued", "pending"):
        state = "running"
    elif problems:
        state = "partial"
    else:
        state = "ok"
    return {"state": state, "problems": problems,
            "last_run": {"id": run.id, "status": run.status, "started_at": run.started_at, "completed_at": run.completed_at,
                         "jobs_found": run.jobs_found, "jobs_new": run.jobs_new}}


def overview(db: Session, user: User) -> dict[str, Any]:
    now = utcnow()
    today = tracker_service.today_view(db, user)
    return {
        "new_jobs": new_jobs(db, user, now),
        "attention": today["your_move"],
        "upcoming": today["coming_up"],
        "waiting": today["waiting_on_them"],
        "saved": saved_jobs(db, user, now),
        "recent_submitted": recent_submitted(db, user),
        "resume": resume_status(db, user),
        "discovery": discovery_health(db, user),
    }
