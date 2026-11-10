from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from backend.api import serializers
from backend.api.deps import CurrentUser, DbSession, SettingsDep
from backend.models import Application, UserJob
from backend.schemas.applications import (
    ApplicationDetail,
    ApplicationOut,
    ApplyOptions,
    ConfirmRequest,
    EmailDraftRequest,
    EmailDraftResponse,
    OpenResponse,
    PrepareRequest,
    StageRequest,
    StatusChangeRequest,
    TrackingUpdate,
)
from backend.services import application_service as svc

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

