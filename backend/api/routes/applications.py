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
    ConfirmRequest,
    OpenResponse,
    PrepareRequest,
    StageRequest,
    StatusChangeRequest,
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
