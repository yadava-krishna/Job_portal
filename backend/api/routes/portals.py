"""Portal Connections (Settings): what JobPilot can do with LinkedIn, Naukri and Indeed, and a profile checklist for
LinkedIn and Naukri built from your confirmed profile. No portal account is ever connected or read."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.api.deps import CurrentUser, DbSession
from backend.services import portal_service

router = APIRouter(prefix="/portals", tags=["portals"])


class ItemDone(BaseModel):
    done: bool


@router.get("")
def list_portals(user: CurrentUser) -> list[dict[str, Any]]:
    return portal_service.connections()


@router.get("/{portal}/review")
def portal_review(portal: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return portal_service.review(db, user, portal)


@router.put("/{portal}/review/{key}")
def mark_item(portal: str, key: str, body: ItemDone, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Tick (or untick) a checklist item you've done on the portal yourself."""
    return portal_service.mark(db, user, portal, key, body.done)
