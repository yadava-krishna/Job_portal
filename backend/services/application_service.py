"""Application workflow: prepare → open (external) → confirm. The user always submits on the platform.

Status rules
  PREPARED              package ready (screening answers, checklist, optional cover letter)
  OPENED                the original listing was opened. This is NOT an application.
  CONFIRMATION_PENDING  user returned but has not yet said whether they submitted
  SUBMITTED             user explicitly confirmed, or a platform confirmation email matched
  FAILED / WITHDRAWN    terminal unless reopened
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from applications.screening_answers import ScreeningAnswerer
from backend.config import BackendSettings
from backend.models import Application, ApplicationEvent, Job, User, UserJob, utcnow
from backend.services import resume_service
from backend.services.matching_service import UserMatcher, job_to_posting
from core import timeutil
from core.models import NEEDS_CANDIDATE_INPUT, MatchResult
from intelligence.cover_letter import generate_cover_letter
from platforms import detect_platform, get_adapter

ALLOWED: dict[str, set[str]] = {
    "PREPARED": {"OPENED", "CONFIRMATION_PENDING", "SUBMITTED", "FAILED", "WITHDRAWN"},
    "OPENED": {"OPENED", "CONFIRMATION_PENDING", "SUBMITTED", "PREPARED", "FAILED", "WITHDRAWN"},
    "CONFIRMATION_PENDING": {"OPENED", "SUBMITTED", "PREPARED", "FAILED", "WITHDRAWN"},
    "FAILED": {"PREPARED", "OPENED", "SUBMITTED", "WITHDRAWN"},
    "SUBMITTED": {"WITHDRAWN"},
    "WITHDRAWN": set(),
}
ACTIVE = ("PREPARED", "OPENED", "CONFIRMATION_PENDING", "SUBMITTED")
STAGES = ("applied", "screening", "assessment", "interview", "offer", "rejected", "withdrawn", "ghosted", "archived")
# How the user applied, from the confirmation source (shown in the tracker).
SUBMISSION_METHODS = {"user_confirmed": "Employer website, confirmed in JobPilot",
                      "extension_user_confirmed": "Employer website, confirmed in the extension"}


def _event(db: Session, app: Application, user: User, event_type: str, frm: str | None, to: str | None, details: str | None = None) -> None:
    db.add(ApplicationEvent(application_id=app.id, user_id=user.id, event_type=event_type, from_status=frm, to_status=to, details=details))


def _transition(db: Session, user: User, app: Application, to: str, event_type: str, details: str | None = None) -> None:
    if to not in ALLOWED.get(app.status, set()):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Application is {app.status}; it cannot move to {to}.")
    frm = app.status
    app.status = to
    _event(db, app, user, event_type, frm, to, details)


def owned_user_job(db: Session, user: User, user_job_id: int) -> UserJob:
    uj = db.execute(select(UserJob).where(UserJob.id == user_job_id, UserJob.user_id == user.id)).unique().scalar_one_or_none()
    if uj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found in your feed.")
    return uj


def owned_application(db: Session, user: User, app_id: int) -> Application:
    app = db.execute(select(Application).where(Application.id == app_id, Application.user_id == user.id)).unique().scalar_one_or_none()
    if app is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Application not found.")
    return app


def checklist_for(job: Job, uj: UserJob, screening: list[dict[str, str]]) -> list[dict[str, str]]:
    detected = detect_platform(job.job_url) if job.job_url else None
    official = bool(detected and job.platform == detected.value) if job.platform != "Adzuna" else bool(job.job_url and job.job_url.startswith("https://"))
    items = [
        {"check": "Listing URL is on the official platform domain (https)", "status": "PASS" if official else "CHECK",
         "detail": job.job_url or "No URL"},
        {"check": "Employer name present", "status": "PASS" if job.company else "CHECK", "detail": job.company or "Missing"},
        {"check": "Posting is still open", "status": "CHECK",
         "detail": "Confirm on the platform page. JobPilot never fetches job pages automatically."},
        {"check": "Employer looks genuine (no fees or deposits requested)", "status": "CHECK", "detail": ""},
    ]
    today = timeutil.today()
    if job.posted_at and (today - job.posted_at).days > 30:
        items.append({"check": "Posting age", "status": "WARN", "detail": f"Posted {(today - job.posted_at).days} days ago; it may be closed."})
    if uj.eligibility_status and uj.eligibility_status != "ELIGIBLE":
        items.append({"check": f"Eligibility: {uj.eligibility_status}", "status": "WARN", "detail": "; ".join(uj.eligibility_reasons or [])})
    for flag in job.verification_flags or []:
        items.append({"check": "Verification flag", "status": "WARN", "detail": flag})
    missing = [s["question"] for s in screening if s["status"] == NEEDS_CANDIDATE_INPUT]
    if missing:
        items.append({"check": "Screening answers that need your input", "status": "ACTION", "detail": "; ".join(missing)})
    return items


def prepare(db: Session, settings: BackendSettings, user: User, user_job_id: int, include_cover_letter: bool | None) -> Application:
    uj = owned_user_job(db, user, user_job_id)
    existing = db.execute(select(Application).where(Application.user_id == user.id, Application.job_id == uj.job_id)).unique().scalar_one_or_none()
    if existing is not None:
        if existing.status in ("FAILED",):
            _transition(db, user, existing, "PREPARED", "REPREPARED")
            db.commit()
        return existing  # one application per job per user, ever

    job = uj.job
    if job.fingerprint:
        dup = db.execute(
            select(Application).join(Job, Job.id == Application.job_id)
            .where(Application.user_id == user.id, Job.fingerprint == job.fingerprint, Job.id != job.id, Application.status.in_(ACTIVE))
        ).unique().scalars().first()
        if dup is not None:
            raise HTTPException(status.HTTP_409_CONFLICT,
                                f"You already have an application for {job.title} at {job.company} on {dup.job.platform} (#{dup.id}).")

    matcher = UserMatcher(db, settings, user)
    answerer = ScreeningAnswerer(matcher.profile, matcher.verified_facts, matcher.taxonomy)
    screening = answerer.answer_all(job.screening_questions or [])
    prefs_app = (matcher.prefs.application_settings if matcher.prefs else {}) or {}
    mode = prefs_app.get("cover_letter", "when_required")
    want_cl = include_cover_letter if include_cover_letter is not None else (
        mode == "always" or (mode == "when_required" and "cover letter" in (job.description or "").lower()))
    cover_letter = None
    if want_cl:
        match = MatchResult.model_validate(uj.match) if uj.match else None
        cover_letter, _method = generate_cover_letter(job_to_posting(job), matcher.profile, match, matcher.llm)

    resume = resume_service.active_resume(db, user)
    app = Application(user_id=user.id, job_id=job.id, user_job_id=uj.id, status="PREPARED", resume_id=resume.id if resume else None,
                      resume_used=resume.original_filename if resume else None, cover_letter=cover_letter, screening_answers=screening,
                      checklist=checklist_for(job, uj, screening))
    db.add(app)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return db.execute(select(Application).where(Application.user_id == user.id, Application.job_id == uj.job_id)).unique().scalar_one()
    _event(db, app, user, "PREPARED", None, "PREPARED",
           f"{len(screening)} screening answers; cover letter: {'yes' if cover_letter else 'no'}")
    db.commit()
    db.refresh(app)
    return app


def open_listing(db: Session, user: User, app: Application) -> str:
    if not app.job.job_url:
        raise HTTPException(422, "This job has no original URL to open.")
    if app.status == "SUBMITTED":
        _event(db, app, user, "REOPENED_LISTING", app.status, app.status, "Listing opened after submission")
    else:
        _transition(db, user, app, "OPENED", "OPENED_EXTERNAL", "Original listing opened; this is not a submission.")
        app.opened_at = utcnow()
    db.commit()
    return app.job.job_url


def apply_options(db: Session, app: Application) -> dict:
    from backend.models import JobSourceLink
    from backend.services import extension_service

    job = app.job
    url = job.job_url
    ref = extension_service.job_ref(url) if url else None
    hosted = None
    if ref is None and job.platform == "Greenhouse":
        links = list(db.execute(select(JobSourceLink).where(JobSourceLink.job_id == job.id)).scalars())
        hosted = extension_service.greenhouse_hosted_form(job, links)
    if ref:
        msg = f"Fill with JobPilot supports this {job.platform} application page."
    elif hosted:
        msg = ("This listing is on the employer's own careers site, which Fill with JobPilot cannot fill. "
               "Greenhouse also hosts the application form for this job; you can apply there instead.")
    elif job.platform in ("Greenhouse", "Lever", "Ashby"):
        msg = "This listing is on the employer's own careers site, which Fill with JobPilot cannot fill. Apply there manually."
    else:
        msg = f"Apply on {job.platform or 'the original site'} yourself; JobPilot keeps track once you confirm."
    return {"original_url": url, "original_supported": ref is not None, "platform": job.platform, "hosted_form_url": hosted,
            "direct_apply": False, "message": msg}


def mark_submitted(db: Session, user: User, app: Application, *, reference_id: str | None, confirmation_text: str | None,
                   source: str, notes: str | None = None) -> None:
    if app.status == "SUBMITTED":
        return
    _transition(db, user, app, "SUBMITTED", "SUBMISSION_CONFIRMED",
                f"source={source}" + (f"; reference={reference_id}" if reference_id else ""))
    app.submitted_at = utcnow()
    app.reference_id = (reference_id or "").strip() or None
    app.confirmation_text = (confirmation_text or "").strip() or None
    app.confirmation_source = source
    app.stage = "applied"
    if notes:
        app.notes = notes
    if app.user_job_id:
        uj = db.get(UserJob, app.user_job_id)
        if uj is not None and uj.user_id == user.id:
            uj.status = "applied"


def confirm(db: Session, user: User, app: Application, submitted: bool | None, reference_id: str | None,
            confirmation_text: str | None, notes: str | None, *, source: str = "user_confirmed") -> Application:
    if submitted is None:
        if app.status != "CONFIRMATION_PENDING":
            _transition(db, user, app, "CONFIRMATION_PENDING", "RETURNED_UNDECIDED", "User returned without confirming yet.")
    elif submitted:
        mark_submitted(db, user, app, reference_id=reference_id, confirmation_text=confirmation_text, source=source, notes=notes)
    else:
        # Closed the page without applying: leave it where it was before opening.
        if app.status in ("OPENED", "CONFIRMATION_PENDING"):
            _transition(db, user, app, "PREPARED", "NOT_SUBMITTED", "User reported the application was not submitted.")
    db.commit()
    db.refresh(app)
    return app


def mark_in_progress(db: Session, user: User, app: Application, source: str) -> Application:
    """The user is working on the employer's form (e.g. clicked Fill with JobPilot). Never a submission."""
    if app.status in ("PREPARED", "FAILED", "CONFIRMATION_PENDING"):
        _transition(db, user, app, "OPENED", "OPENED_EXTERNAL", f"Application form opened ({source}); this is not a submission.")
        app.opened_at = app.opened_at or utcnow()
        db.commit()
    return app


def set_failed(db: Session, user: User, app: Application, reason: str | None) -> Application:
    _transition(db, user, app, "FAILED", "FAILED", reason)
    db.commit()
    return app


def withdraw(db: Session, user: User, app: Application, reason: str | None) -> Application:
    _transition(db, user, app, "WITHDRAWN", "WITHDRAWN", reason)
    if app.stage:
        app.stage = "withdrawn"
    db.commit()
    return app


def set_stage(db: Session, user: User, app: Application, stage: str, note: str | None) -> Application:
    if app.status != "SUBMITTED":
        raise HTTPException(status.HTTP_409_CONFLICT, "Pipeline stages apply only after the application is submitted.")
    old = app.stage
    app.stage = stage
    _event(db, app, user, "STAGE_CHANGED", old, stage, note)
    db.commit()
    return app


def update_tracking(db: Session, user: User, app: Application, fields: dict) -> Application:
    """Notes and follow-up date: the user's own bookkeeping, at any status."""
    if "notes" in fields:
        app.notes = (fields["notes"] or "").strip() or None
    if "follow_up_at" in fields:
        app.follow_up_at = fields["follow_up_at"]
        _event(db, app, user, "FOLLOW_UP_SET", None, None, fields["follow_up_at"].isoformat() if fields["follow_up_at"] else "cleared")
    db.commit()
    db.refresh(app)
    return app


def submission_method(app: Application) -> str | None:
    src = app.confirmation_source
    if not src:
        return None
    if src.startswith("email"):
        return "Employer website, confirmed by the platform's e-mail"
    return SUBMISSION_METHODS.get(src, src.replace("_", " "))


def needs_input(app: Application) -> list[str]:
    return [s["question"] for s in (app.screening_answers or []) if s.get("status") == NEEDS_CANDIDATE_INPUT]


def events(db: Session, user: User, app: Application) -> list[ApplicationEvent]:
    return list(db.execute(select(ApplicationEvent).where(ApplicationEvent.application_id == app.id, ApplicationEvent.user_id == user.id)
                           .order_by(ApplicationEvent.id)).scalars())


def platform_method(job: Job) -> str:
    platform = detect_platform(job.job_url) if job.job_url else None
    return get_adapter(platform).capabilities.application_method if platform else (job.application_method or "Apply on the original listing")

