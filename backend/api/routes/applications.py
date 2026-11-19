from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from backend.api import serializers
from backend.api.deps import CurrentUser, DbSession, SettingsDep
from backend.models import Application, UserJob, utcnow
from backend.schemas.applications import (
    ApplicationDetail,
    ApplicationOut,
    ApplyOptions,
    ConfirmRequest,
    DestinationConfirm,
    HandoffOut,
    PackageOut,
    ResumeChoice,
    WorkspaceAnswers,
    EmailDraftRequest,
    EmailDraftResponse,
    OpenResponse,
    PrepareRequest,
    StageRequest,
    StatusChangeRequest,
    TrackingUpdate,
)
from backend.services import application_service as svc
from backend.services import apply_prep_service as prep
from backend.services import apply_state_service, platform_service

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("/prepare", response_model=ApplicationDetail, status_code=status.HTTP_201_CREATED)
def prepare(body: PrepareRequest, user: CurrentUser, db: DbSession, settings: SettingsDep) -> ApplicationDetail:
    """Prepare (or return the existing) application package for a job in your feed."""
    app = svc.prepare(db, settings, user, body.user_job_id, body.include_cover_letter)
    return serializers.application_detail(db, user, app)


@router.post("/{application_id}/open", response_model=OpenResponse)
def open_listing(application_id: int, user: CurrentUser, db: DbSession) -> OpenResponse:
    """Record that the original listing is being opened. This never marks the job as applied."""
    app = svc.owned_application(db, user, application_id)
    url = svc.open_listing(db, user, app)
    return OpenResponse(application=serializers.application_detail(db, user, app), url=url)


@router.get("/{application_id}/apply-options", response_model=ApplyOptions)
def apply_options(application_id: int, user: CurrentUser, db: DbSession) -> ApplyOptions:
    """Where this job can be applied to, and whether Fill with JobPilot supports that page."""
    app = svc.owned_application(db, user, application_id)
    return ApplyOptions(**svc.apply_options(db, app))


@router.post("/{application_id}/confirm", response_model=ApplicationDetail)
def confirm(application_id: int, body: ConfirmRequest, user: CurrentUser, db: DbSession) -> ApplicationDetail:
    app = svc.owned_application(db, user, application_id)
    svc.confirm(db, user, app, body.submitted, body.reference_id, body.confirmation_text, body.notes)
    apply_state_service.after_user_confirm(db, app, body.submitted)
    return serializers.application_detail(db, user, app)


@router.post("/{application_id}/pending", response_model=ApplicationDetail)
def confirmation_pending(application_id: int, user: CurrentUser, db: DbSession) -> ApplicationDetail:
    """Returned to the portal but not sure yet whether the submission went through."""
    app = svc.owned_application(db, user, application_id)
    svc.confirm(db, user, app, None, None, None, None)
    return serializers.application_detail(db, user, app)


@router.post("/{application_id}/fail", response_model=ApplicationDetail)
def fail(application_id: int, body: StatusChangeRequest, user: CurrentUser, db: DbSession) -> ApplicationDetail:
    app = svc.owned_application(db, user, application_id)
    svc.set_failed(db, user, app, body.reason)
    return serializers.application_detail(db, user, app)


@router.post("/{application_id}/withdraw", response_model=ApplicationDetail)
def withdraw(application_id: int, body: StatusChangeRequest, user: CurrentUser, db: DbSession) -> ApplicationDetail:
    app = svc.owned_application(db, user, application_id)
    svc.withdraw(db, user, app, body.reason)
    return serializers.application_detail(db, user, app)


@router.post("/{application_id}/stage", response_model=ApplicationDetail)
def stage(application_id: int, body: StageRequest, user: CurrentUser, db: DbSession) -> ApplicationDetail:
    app = svc.owned_application(db, user, application_id)
    svc.set_stage(db, user, app, body.stage, body.note)
    return serializers.application_detail(db, user, app)


@router.put("/{application_id}/tracking", response_model=ApplicationDetail)
def tracking(application_id: int, body: TrackingUpdate, user: CurrentUser, db: DbSession) -> ApplicationDetail:
    """Your notes and follow-up date for this application."""
    app = svc.owned_application(db, user, application_id)
    svc.update_tracking(db, user, app, body.model_dump(exclude_unset=True))
    return serializers.application_detail(db, user, app)


# ---- Apply Workspace: the prepared package, resume choice, answers, destination, native hand-off ----------------

def _pkg_out(db, user, app, package, **extra) -> PackageOut:
    return PackageOut(application=serializers.application_detail(db, user, app), package=package, **extra)


@router.get("/{application_id}/package", response_model=PackageOut)
def package(application_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep, refresh: bool = False) -> PackageOut:
    """Everything prepared for this application: destination, resume, answers, missing information, readiness, next step.

    Rebuilt on every call from your current profile and remembered answers (the employer's published questions are
    cached for a day; `refresh=true` re-reads them)."""
    app = svc.owned_application(db, user, application_id)
    return _pkg_out(db, user, app, prep.build(db, settings, user, app, refresh_questions=refresh))


@router.put("/{application_id}/resume", response_model=PackageOut)
def choose_resume(application_id: int, body: ResumeChoice, user: CurrentUser, db: DbSession, settings: SettingsDep) -> PackageOut:
    """Use this resume (an upload or a Resume Studio version) for this application. Smart Apply attaches exactly this one."""
    app = svc.owned_application(db, user, application_id)
    prep.select_resume(db, settings, user, app, body.kind, body.id, body.format)
    return _pkg_out(db, user, app, prep.build(db, settings, user, app))


@router.post("/{application_id}/answers", response_model=PackageOut)
def save_answers(application_id: int, body: WorkspaceAnswers, user: CurrentUser, db: DbSession, settings: SettingsDep) -> PackageOut:
    """Answers for this application. Each one is remembered for later applications only if `remember` is true."""
    app = svc.owned_application(db, user, application_id)
    res = prep.save_answers(db, settings, user, app, [i.model_dump() for i in body.items])
    db.commit()
    return _pkg_out(db, user, app, res["package"], saved=res["saved"], errors=res["errors"])


@router.post("/{application_id}/destination", response_model=PackageOut)
def confirm_destination(application_id: int, body: DestinationConfirm, user: CurrentUser, db: DbSession, settings: SettingsDep) -> PackageOut:
    """You confirmed that a suggested employer posting is the same job: apply there instead of the original listing."""
    app = svc.owned_application(db, user, application_id)
    pkg = prep.confirm_destination(db, settings, user, app, body.url)
    db.commit()
    return _pkg_out(db, user, app, pkg)


@router.delete("/{application_id}/destination", response_model=PackageOut)
def clear_destination(application_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep) -> PackageOut:
    app = svc.owned_application(db, user, application_id)
    pkg = prep.clear_destination(db, settings, user, app)
    db.commit()
    return _pkg_out(db, user, app, pkg)


@router.post("/{application_id}/handoff", response_model=HandoffOut)
def handoff(application_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep, smart: bool = False) -> HandoffOut:
    """You are opening the employer's (or the platform's own) application page. Recorded as 'employer page opened',
    never as applied. `smart=true` when Smart Apply opens and fills it."""
    app = svc.owned_application(db, user, application_id)
    if app.status == "SUBMITTED":
        raise HTTPException(status.HTTP_409_CONFLICT, "This application was already submitted. JobPilot will not submit it again.")
    pkg = app.package or prep.build(db, settings, user, app, commit=False)
    url = (pkg.get("destination") or {}).get("url") or app.job.job_url
    if not url:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "This job has no application page to open.")
    if not platform_service.has_consent(db, user.id, "apply_assist"):
        platform_service.set_consent_nocommit(db, user, "apply_assist", True)
    mode = "assisted_submit" if smart and (pkg.get("capabilities") or {}).get("assisted_submit") else ("autofill_review" if smart else "manual_handoff")
    if app.apply_state not in ("filling", "needs_information", "ready_for_review", "reviewed", "submission_authorized", "submission_pending",
                               "submission_uncertain", "user_reported", "submitted_confirmed"):
        apply_state_service.record(db, user, app, "form_opened", mode=mode, session={"page": url})
    else:
        svc.mark_in_progress(db, user, app, "apply_workspace")
    app.opened_at = app.opened_at or utcnow()
    db.commit()
    pkg = prep.build(db, settings, user, app)
    return HandoffOut(application=serializers.application_detail(db, user, app), package=pkg, url=url)


@router.get("", response_model=list[ApplicationOut])
def list_applications(user: CurrentUser, db: DbSession,
                      status_filter: list[Literal["PREPARED", "OPENED", "CONFIRMATION_PENDING", "SUBMITTED", "FAILED", "WITHDRAWN"]] | None = Query(None, alias="status")
                      ) -> list[ApplicationOut]:
    stmt = select(Application).where(Application.user_id == user.id)
    if status_filter:
        stmt = stmt.where(Application.status.in_(status_filter))
    apps = db.execute(stmt.order_by(Application.updated_at.desc())).unique().scalars().all()
    ujs = {u.id: u for u in db.execute(select(UserJob).where(UserJob.user_id == user.id, UserJob.id.in_([a.user_job_id for a in apps if a.user_job_id]))).unique().scalars()}
    return [serializers.application(a, ujs.get(a.user_job_id)) for a in apps]


@router.get("/{application_id}", response_model=ApplicationDetail)
def get_application(application_id: int, user: CurrentUser, db: DbSession) -> ApplicationDetail:
    return serializers.application_detail(db, user, svc.owned_application(db, user, application_id))


# --- Phase 12: Apply Orchestrator & Recruiter Email Endpoints ---

@router.post("/jobs/{job_id}/orchestrate", response_model=ApplicationDetail)
def orchestrate_application(job_id: int, user: CurrentUser, db: DbSession) -> ApplicationDetail:
    """Orchestrates candidate application route (A, B, C, or D) with tailored resume and screening Q&A."""
    from backend.services.apply_orchestrator import ApplyOrchestrator
    app = ApplyOrchestrator.orchestrate_job(db, user, job_id)
    return serializers.application_detail(db, user, app)


@router.post("/{application_id}/email-draft", response_model=EmailDraftResponse)
def get_recruiter_email_draft(application_id: int, body: EmailDraftRequest, user: CurrentUser, db: DbSession) -> EmailDraftResponse:
    """Generates professional, verified recruiter email draft with explicit consent gate."""
    from backend.services.recruiter_email_service import RecruiterEmailService
    app = svc.owned_application(db, user, application_id)
    draft = RecruiterEmailService.generate_draft(db, user, app, target_email=body.target_email)
    return EmailDraftResponse(
        recipient_email=draft.recipient_email,
        subject=draft.subject,
        body_text=draft.body_text,
        attachment_name=draft.attachment_name,
        candidate_consent_required=draft.candidate_consent_required,
    )

