"""Phase 4: interviews, offers, contacts, the Today view, active-time tracking, data export and account deletion.

Everything is scoped to the requesting user; other users' rows are always 404.
"""

from __future__ import annotations

import shutil
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import (
    Application,
    ApplicationContact,
    ApplicationEvent,
    AuditLog,
    CandidateProfile,
    Company,
    DiscoveryRun,
    ExtensionToken,
    Interview,
    JobPreference,
    JobView,
    Notification,
    Offer,
    Resume,
    SavedSearch,
    User,
    UserActivitySession,
    UserCompany,
    UserJob,
    utcnow,
)
from backend.services.application_service import owned_application
from core import timeutil

SESSION_GAP = timedelta(minutes=5)
HEARTBEAT_SECONDS = 30
# Days without any news before an application counts as "waiting on them", per stage.
QUIET_DAYS = {"applied": 14, "screening": 10, "assessment": 10, "interview": 7, "offer": 5}


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def _owned(db: Session, model, user: User, obj_id: int):
    row = db.execute(select(model).where(model.id == obj_id, model.user_id == user.id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return row


def _event(db: Session, app: Application, user: User, kind: str, details: str) -> None:
    db.add(ApplicationEvent(application_id=app.id, user_id=user.id, event_type=kind, from_status=None, to_status=None, details=details[:500]))


# ---- interviews, offers, contacts -----------------------------------------------------------

def add_interview(db: Session, user: User, app_id: int, data: dict) -> Interview:
    app = owned_application(db, user, app_id)
    if app.status != "SUBMITTED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Interviews can be added once the application is submitted.")
    iv = Interview(user_id=user.id, application_id=app.id, **data)
    db.add(iv)
    if app.stage in (None, "applied", "screening", "assessment", "ghosted"):
        _event(db, app, user, "STAGE_CHANGED", f"{app.stage} → interview (interview added)")
        app.stage = "interview"
    _event(db, app, user, "INTERVIEW_ADDED", data.get("round_name") or "Interview")
    db.commit()
    db.refresh(iv)
    return iv


def update_interview(db: Session, user: User, iv_id: int, data: dict) -> Interview:
    iv = _owned(db, Interview, user, iv_id)
    for k, v in data.items():
        setattr(iv, k, v)
    db.commit()
    db.refresh(iv)
    return iv


def delete_row(db: Session, user: User, model, obj_id: int) -> None:
    db.delete(_owned(db, model, user, obj_id))
    db.commit()


def interviews(db: Session, user: User, *, upcoming: bool = False) -> list[Interview]:
    stmt = select(Interview).where(Interview.user_id == user.id)
    if upcoming:
        stmt = stmt.where(Interview.scheduled_at >= utcnow() - timedelta(hours=2), Interview.outcome == "scheduled")
    return list(db.execute(stmt.order_by(Interview.scheduled_at.is_(None), Interview.scheduled_at)).scalars())


def upsert_offer(db: Session, user: User, app_id: int, data: dict) -> Offer:
    app = owned_application(db, user, app_id)
    if app.status != "SUBMITTED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Offers can be recorded once the application is submitted.")
    offer = db.execute(select(Offer).where(Offer.application_id == app.id, Offer.user_id == user.id)).scalar_one_or_none()
    if offer is None:
        offer = Offer(user_id=user.id, application_id=app.id)
        db.add(offer)
        _event(db, app, user, "OFFER_RECORDED", data.get("status", "received"))
        if app.stage != "offer":
            _event(db, app, user, "STAGE_CHANGED", f"{app.stage} → offer (offer recorded)")
            app.stage = "offer"
    for k, v in data.items():
        setattr(offer, k, v)
    db.commit()
    db.refresh(offer)
    return offer


def offers(db: Session, user: User) -> list[Offer]:
    return list(db.execute(select(Offer).where(Offer.user_id == user.id).order_by(Offer.decision_deadline.is_(None), Offer.decision_deadline)).scalars())


def add_contact(db: Session, user: User, app_id: int, data: dict) -> ApplicationContact:
    app = owned_application(db, user, app_id)
    c = ApplicationContact(user_id=user.id, application_id=app.id, **data)
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def contacts(db: Session, user: User, app_id: int) -> list[ApplicationContact]:
    owned_application(db, user, app_id)
    return list(db.execute(select(ApplicationContact).where(ApplicationContact.user_id == user.id,
                                                            ApplicationContact.application_id == app_id)).scalars())


def calendar_ics(db: Session, user: User) -> str:
    """Your scheduled interviews as an iCalendar file (import into Google Calendar, Outlook, Apple Calendar)."""
    def esc(s: str | None) -> str:
        return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")

    stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//JobPilot//Interviews//EN", "CALSCALE:GREGORIAN"]
    for iv in interviews(db, user):
        if iv.scheduled_at is None or iv.outcome == "cancelled":
            continue
        app = db.get(Application, iv.application_id)
        start = _aware(iv.scheduled_at).astimezone(timezone.utc)
        end = start + timedelta(minutes=iv.duration_minutes or 60)
        lines += ["BEGIN:VEVENT", f"UID:jobpilot-interview-{iv.id}@jobpilot", f"DTSTAMP:{stamp}",
                  f"DTSTART:{start:%Y%m%dT%H%M%SZ}", f"DTEND:{end:%Y%m%dT%H%M%SZ}",
                  "SUMMARY:" + esc(f"{iv.round_name or 'Interview'}: {app.job.title} at {app.job.company}"),
                  f"LOCATION:{esc(iv.location)}", f"DESCRIPTION:{esc(iv.notes)}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ---- Today -----------------------------------------------------------------------------------

def today_view(db: Session, user: User) -> dict[str, list[dict[str, Any]]]:
    now = utcnow()
    today = timeutil.today()
    apps = db.execute(select(Application).where(Application.user_id == user.id)).unique().scalars().all()
    last_event = dict(db.execute(select(ApplicationEvent.application_id, func.max(ApplicationEvent.created_at))
                                 .where(ApplicationEvent.user_id == user.id).group_by(ApplicationEvent.application_id)).all())
    your_move, coming_up, waiting = [], [], []
    for a in apps:
        label = f"{a.job.title} at {a.job.company}"
        if a.follow_up_at and timeutil.tz() and _aware(a.follow_up_at).astimezone(timeutil.tz()).date() <= today and a.status != "WITHDRAWN":
            your_move.append({"kind": "follow_up", "title": f"Follow up: {label}", "due": a.follow_up_at, "application_id": a.id,
                              "detail": a.notes[:120] if a.notes else None})
        if a.status in ("PREPARED", "OPENED", "CONFIRMATION_PENDING") and now - _aware(a.updated_at) > timedelta(days=1):
            your_move.append({"kind": "unsent", "title": f"Finish or close: {label}", "application_id": a.id,
                              "detail": "Prepared but not confirmed as sent. Apply, or mark it not applied.",
                              "due": a.updated_at})
        if a.status == "SUBMITTED" and a.stage in QUIET_DAYS:
            last = _aware(last_event.get(a.id) or a.submitted_at or a.updated_at)
            quiet = (now - last).days if last else 0
            if quiet >= QUIET_DAYS[a.stage]:
                waiting.append({"kind": "quiet", "title": label, "application_id": a.id, "due": last,
                                "detail": f"No news for {quiet} days at the {a.stage} stage. Follow up, or mark it ghosted."})
    for iv in interviews(db, user, upcoming=True):
        if iv.scheduled_at and _aware(iv.scheduled_at) <= now + timedelta(days=14):
            app = db.get(Application, iv.application_id)
            coming_up.append({"kind": "interview", "title": f"{iv.round_name or 'Interview'}: {app.job.title} at {app.job.company}",
                              "due": iv.scheduled_at, "application_id": app.id, "interview_id": iv.id,
                              "detail": " · ".join(x for x in (iv.mode, iv.location) if x) or None})
    for o in offers(db, user):
        if o.status in ("received", "negotiating") and o.decision_deadline:
            app = db.get(Application, o.application_id)
            coming_up.append({"kind": "offer_deadline", "title": f"Offer decision: {app.job.company}", "due": o.decision_deadline,
                              "application_id": app.id, "detail": f"Decide by {o.decision_deadline:%d %b}"})
    applied_jobs = {a.job_id for a in apps}
    saved = db.execute(select(UserJob).where(UserJob.user_id == user.id, UserJob.is_saved.is_(True),
                                             UserJob.status.in_(["new", "shortlisted"]))).unique().scalars().all()
    for uj in saved:
        if uj.job_id not in applied_jobs and uj.saved_at and now - _aware(uj.saved_at) > timedelta(days=3) and uj.job.closed_at is None:
            your_move.append({"kind": "decide_saved", "title": f"Decide: {uj.job.title} at {uj.job.company}", "user_job_id": uj.id,
                              "detail": "Saved more than 3 days ago. Apply or dismiss it.", "due": uj.saved_at})
    key = lambda x: (_aware(x["due"]) if isinstance(x.get("due"), datetime) else
                     datetime.combine(x["due"], time.min, tzinfo=timezone.utc) if isinstance(x.get("due"), date) else now)
    return {"your_move": sorted(your_move, key=key), "coming_up": sorted(coming_up, key=key), "waiting_on_them": sorted(waiting, key=key)}


# ---- active time -----------------------------------------------------------------------------

def heartbeat(db: Session, user: User, visible: bool, active: bool) -> None:
    """Counted only while the tab is visible and the user was recently active; a gap over 5 minutes starts a new session."""
    if not (visible and active):
        return
    now = utcnow()
    s = db.execute(select(UserActivitySession).where(UserActivitySession.user_id == user.id)
                   .order_by(UserActivitySession.last_heartbeat_at.desc()).limit(1)).scalar_one_or_none()
    if s is None or now - _aware(s.last_heartbeat_at) > SESSION_GAP:
        db.add(UserActivitySession(user_id=user.id, started_at=now, last_heartbeat_at=now, active_seconds=0, heartbeats=1))
    else:
        gap = (now - _aware(s.last_heartbeat_at)).total_seconds()
        s.active_seconds += int(min(gap, HEARTBEAT_SECONDS * 2))
        s.heartbeats += 1
        s.last_heartbeat_at = now
    user.last_seen_at = now
    db.commit()


def record_view(db: Session, user: User, job_id: int) -> None:
    v = db.execute(select(JobView).where(JobView.user_id == user.id, JobView.job_id == job_id)).scalar_one_or_none()
    if v is None:
        db.add(JobView(user_id=user.id, job_id=job_id))
    else:
        v.view_count += 1
        v.last_viewed_at = utcnow()
    db.commit()


def activity_metrics(db: Session, user: User, days: int = 30) -> dict[str, Any]:
    start = timeutil.today() - timedelta(days=days - 1)
    start_dt = datetime.combine(start, time.min, tzinfo=timeutil.tz()).astimezone(timezone.utc)
    sessions = db.execute(select(UserActivitySession).where(UserActivitySession.user_id == user.id,
                                                            UserActivitySession.started_at >= start_dt)).scalars().all()
    local = lambda dt: _aware(dt).astimezone(timeutil.tz()).date()  # noqa: E731
    per_day_minutes = Counter()
    for s in sessions:
        per_day_minutes[local(s.started_at)] += s.active_seconds / 60
    viewed = db.execute(select(func.count()).select_from(JobView).where(JobView.user_id == user.id, JobView.last_viewed_at >= start_dt)).scalar_one()
    saved = db.execute(select(func.count()).select_from(UserJob).where(UserJob.user_id == user.id, UserJob.saved_at >= start_dt)).scalar_one()
    apps = db.execute(select(Application).where(Application.user_id == user.id)).unique().scalars().all()
    done = [a for a in apps if a.status == "SUBMITTED" and a.submitted_at and _aware(a.submitted_at) >= start_dt]
    per_day_apps = Counter(local(a.submitted_at) for a in done)
    ivs = db.execute(select(func.count()).select_from(Interview).where(Interview.user_id == user.id, Interview.created_at >= start_dt)).scalar_one()
    ofs = db.execute(select(func.count()).select_from(Offer).where(Offer.user_id == user.id, Offer.created_at >= start_dt)).scalar_one()
    total = sum(s.active_seconds for s in sessions) / 60
    return {"days": days, "active_minutes": round(total), "sessions": len(sessions),
            "average_session_minutes": round(total / len(sessions), 1) if sessions else 0.0,
            "jobs_viewed": viewed, "jobs_saved": saved, "applications_completed": len(done), "interviews": ivs, "offers": ofs,
            "per_day": [{"date": (start + timedelta(days=i)).isoformat(), "active_minutes": round(per_day_minutes.get(start + timedelta(days=i), 0)),
                         "applications": per_day_apps.get(start + timedelta(days=i), 0)} for i in range(days)]}


# ---- your data -------------------------------------------------------------------------------

def _row(obj, exclude: set[str] = frozenset()) -> dict[str, Any]:
    out = {}
    for col in obj.__table__.columns:
        if col.key in exclude:
            continue
        v = getattr(obj, col.key)
        out[col.key] = v.isoformat() if isinstance(v, (datetime, date)) else v
    return out


def export(db: Session, user: User) -> dict[str, Any]:
    """Everything JobPilot holds about you, as JSON. Never includes password or credential hashes or server paths."""
    q = lambda m: list(db.execute(select(m).where(m.user_id == user.id)).unique().scalars())  # noqa: E731
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    jobs = []
    for uj in q(UserJob):
        j = uj.job
        jobs.append({**_row(uj, {"user_id", "match"}), "job": {k: (v.isoformat() if isinstance(v, (date, datetime)) else v) for k, v in
                     {"title": j.title, "company": j.company, "location": j.location, "platform": j.platform, "url": j.job_url,
                      "posted_at": j.posted_at}.items()}})
    companies = [{"name": c.name, "ats": c.ats, "board": c.board_token} for c in db.execute(
        select(Company).join(UserCompany, UserCompany.company_id == Company.id).where(UserCompany.user_id == user.id)).scalars()]
    return {
        "exported_at": utcnow().isoformat(), "format": "jobpilot-export-v1",
        "account": _row(user, {"password_hash"}),
        "profile": _row(prof, {"resume_path", "user_id"}) if prof else None,
        "preferences": [_row(p, {"user_id"}) for p in q(JobPreference)],
        "resumes": [_row(r, {"stored_path", "user_id"}) for r in q(Resume)],
        "jobs": jobs,
        "applications": [{**_row(a, {"user_id"}), "job": {"title": a.job.title, "company": a.job.company, "url": a.job.job_url}} for a in q(Application)],
        "application_events": [_row(e, {"user_id"}) for e in q(ApplicationEvent)],
        "interviews": [_row(i, {"user_id"}) for i in q(Interview)],
        "offers": [_row(o, {"user_id"}) for o in q(Offer)],
        "contacts": [_row(c, {"user_id"}) for c in q(ApplicationContact)],
        "saved_searches": [_row(s, {"user_id"}) for s in q(SavedSearch)],
        "watched_companies": companies,
        "notifications": [_row(n, {"user_id"}) for n in q(Notification)],
        "discovery_runs": [_row(r, {"user_id"}) for r in q(DiscoveryRun)],
        "browser_extension_connections": [_row(t, {"user_id", "token_hash"}) for t in q(ExtensionToken)],
        "activity_sessions": [_row(s, {"user_id"}) for s in q(UserActivitySession)],
    }


def delete_account(db: Session, settings: BackendSettings, user: User, password: str, ip: str | None) -> None:
    from backend.security import verify_password

    if not verify_password(user.password_hash, password):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password is incorrect.")
    user_id = user.id
    db.add(AuditLog(actor_id=None, action="account.deleted", target_type="user", target_id=str(user_id), ip=ip, details={}))
    from sqlalchemy import delete

    db.execute(delete(User).where(User.id == user_id))  # every user-owned row goes with it (ON DELETE CASCADE)
    db.commit()
    folder = settings.user_dir(user_id)
    if settings.users_dir.resolve() in folder.resolve().parents:
        shutil.rmtree(folder, ignore_errors=True)
