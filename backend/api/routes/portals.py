"""Portal Connections (Settings): what JobPilot can do with LinkedIn, Naukri and Indeed for you, linking a LinkedIn or
Indeed account through the portal's official sign-in (identity only), and a profile checklist for LinkedIn and Naukri
built from your confirmed profile. Portal passwords, OTPs and cookies are never asked for or read."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from backend.api.deps import CurrentUser, DbSession, SettingsDep
from backend.services import connection_service, portal_service

router = APIRouter(prefix="/portals", tags=["portals"])


class ItemDone(BaseModel):
    done: bool


class OAuthReturn(BaseModel):
    """What the provider put on the redirect, forwarded by the signed-in app (oauth-callback.html → Settings)."""
    state: str = Field(min_length=1, max_length=200)
    code: str | None = Field(default=None, max_length=4096)
    error: str | None = Field(default=None, max_length=200)
    error_description: str | None = Field(default=None, max_length=4096)  # not used; same cap as oauth-callback.js
    iss: str | None = Field(default=None, max_length=300)


def _row(db, settings, user, portal: str) -> dict[str, Any]:
    return next(p for p in portal_service.connections(db, settings, user) if p["portal"] == portal)


@router.get("")
def list_portals(user: CurrentUser, db: DbSession, settings: SettingsDep) -> list[dict[str, Any]]:
    return portal_service.connections(db, settings, user)


@router.post("/oauth/complete")
def oauth_complete(body: OAuthReturn, user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict[str, Any]:
    """Finish a sign-in started from this account. The state must be yours, unused and under 10 minutes old."""
    out = connection_service.complete(db, settings, user, state=body.state, code=body.code, error=body.error, iss=body.iss)
    if isinstance(out, dict):  # an admin's setup test: nothing was linked; the result rides along with the portal row
        return {**_row(db, settings, user, out["provider"]), "setup_test": out}
    return _row(db, settings, user, out.provider)


@router.post("/{portal}/connect")
def connect(portal: str, user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict[str, Any]:
    """Start the portal's official sign-in. Returns the portal's authorization URL to open in this tab."""
    return connection_service.start(db, settings, user, portal)


@router.post("/{portal}/check")
def check(portal: str, user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict[str, Any]:
    """Ask the portal whether JobPilot's access still works (refreshing it where the portal allows)."""
    connection_service.check(db, settings, user, portal)
    return _row(db, settings, user, portal)


@router.delete("/{portal}/connection")
def disconnect(portal: str, user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict[str, Any]:
    out = connection_service.disconnect(db, settings, user, portal)
    return {**out, "portal": _row(db, settings, user, portal)}


@router.get("/{portal}/review")
def portal_review(portal: str, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    return portal_service.review(db, user, portal)


@router.put("/{portal}/review/{key}")
def mark_item(portal: str, key: str, body: ItemDone, user: CurrentUser, db: DbSession) -> dict[str, Any]:
    """Tick (or untick) a checklist item you've done on the portal yourself."""
    return portal_service.mark(db, user, portal, key, body.done)
