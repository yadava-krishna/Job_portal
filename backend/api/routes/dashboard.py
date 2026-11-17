"""Dashboard action centre (Phase 4)."""

from __future__ import annotations

from fastapi import APIRouter

from backend.api.deps import CurrentUser, DbSession
from backend.schemas.dashboard import OverviewOut
from backend.services import overview_service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/overview", response_model=OverviewOut)
def overview(user: CurrentUser, db: DbSession) -> OverviewOut:
    """New matching jobs, what needs attention, what's coming up, saved and recent applications, resume and discovery status."""
    return OverviewOut(**overview_service.overview(db, user))
