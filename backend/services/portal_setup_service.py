"""Admin setup of portal sign-in (LinkedIn OpenID Connect, Indeed OAuth): Settings -> Portal Connections -> Set up.

An admin either sets the server's environment settings (LINKEDIN_CLIENT_ID, ...), which always win, or saves the
developer app's client ID and secret here. The secret is encrypted with CredentialCipher (the mechanism JobPilot already
uses for portal tokens and mailbox passwords), is write-only, and no API ever returns it, even to an admin.

"Test connection" runs the real sign-in for the admin (connection_service, purpose "test"): it goes to the portal's own
page and back, verifies the ID token and account, then links nothing and keeps no token. The result is recorded here and
shown in the setup panel. A test against OAUTH_DEV_ENDPOINTS is recorded as simulated and never counts as verified.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import AuditLog, PortalProviderConfig, User, utcnow
from backend.security import CredentialCipher
from backend.services import identity_providers as idp

NAMES = {"linkedin": "LinkedIn", "indeed": "Indeed"}
LINKS = {
    "linkedin": {"console": "https://www.linkedin.com/developers/apps",
                 "docs": "https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2"},
    "indeed": {"console": "https://docs.indeed.com/getstarted/partner-console"},
}
PRODUCT = {"linkedin": "Sign In with LinkedIn using OpenID Connect", "indeed": "3-legged OAuth (Indeed Partner Console)"}
CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9._~-]{4,200}$")


def _row(db: Session, provider: str) -> PortalProviderConfig | None:
    return db.execute(select(PortalProviderConfig).where(PortalProviderConfig.provider == provider)).scalar_one_or_none()


def _provider_or_404(provider: str) -> str:
    if provider not in idp.PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Only LinkedIn and Indeed have a sign-in to set up. Naukri has none.")
    return provider


def _audit(db: Session, admin: User, action: str, provider: str, **details: Any) -> None:
    db.add(AuditLog(actor_id=admin.id, action=action, target_type="portal_setup", target_id=provider, details=details))


def last_test(row: PortalProviderConfig | None) -> dict[str, Any] | None:
    if row is None or not row.last_test_status:
        return None
    return {"status": row.last_test_status, "detail": row.last_test_detail, "simulated": bool(row.last_test_simulated),
            "at": row.last_test_at.isoformat() if row.last_test_at else None}


def setup_state(p: idp.Provider, test: dict[str, Any] | None) -> str:
    """not_configured | simulated | ready_to_test | verified | authorization_required | failed (the admin's view)."""
    if not p.configured:
        return "not_configured"
    if p.simulated:
        return "simulated"
    if test is None or test["simulated"] or test["status"] == "cancelled":
        return "ready_to_test"
    return {"verified": "verified", "authorization_required": "authorization_required"}.get(test["status"], "failed")


def overview(db: Session, settings: BackendSettings) -> list[dict[str, Any]]:
    out = []
    for key in idp.PROVIDERS:
        p = idp.get(settings, key, db)
        row = _row(db, key)
        env = key.upper()
        explicit = getattr(settings, f"{key}_redirect_uri", None)
        test = last_test(row)
        out.append({
            "provider": key, "name": NAMES[key], "product": PRODUCT[key], "links": LINKS[key],
            "state": setup_state(p, test), "configured": p.configured, "problem": p.problem,
            "source": p.source or None, "editable": p.source != "env",
            "client_id": p.client_id or None, "has_secret": bool(p.client_secret),
            "redirect_uri": p.redirect_uri or None,
            "redirect_from": f"{env}_REDIRECT_URI" if explicit else ("PUBLIC_APP_URL" if p.redirect_uri else None),
            "redirect_problem": idp._redirect_problem(p.redirect_uri, settings) if p.redirect_uri else
                                f"The server doesn't know its public address: set PUBLIC_APP_URL (or {env}_REDIRECT_URI).",
            "scopes": list(p.scopes), "simulated": p.simulated, "pkce": p.pkce,
            "env_names": [f"{env}_CLIENT_ID", f"{env}_CLIENT_SECRET"],
            "last_test": test,
            "updated_at": row.updated_at.isoformat() if row and row.client_id and row.updated_at else None,
        })
    return out


def one(db: Session, settings: BackendSettings, provider: str) -> dict[str, Any]:
    return next(r for r in overview(db, settings) if r["provider"] == _provider_or_404(provider))


def _reset_test(row: PortalProviderConfig) -> None:
    row.last_test_at = row.last_test_status = row.last_test_detail = None
    row.last_test_simulated = False


def save(db: Session, settings: BackendSettings, admin: User, provider: str, client_id: str, client_secret: str | None) -> dict[str, Any]:
    _provider_or_404(provider)
    if idp.get(settings, provider, db).source == "env":
        raise HTTPException(status.HTTP_409_CONFLICT, f"{NAMES[provider]} is set in the server's environment settings, which take "
                                                      "precedence. Change it there.")
    client_id = (client_id or "").strip()
    if not CLIENT_ID_RE.match(client_id):
        raise HTTPException(422, "Paste the Client ID exactly as the developer portal shows it (letters, digits, - . _ ~).")
    row = _row(db, provider)
    secret = (client_secret or "").strip()
    if secret and (len(secret) > 500 or re.search(r"\s", secret)):
        raise HTTPException(422, "Paste the Client Secret exactly as the developer portal shows it.")
    if not secret and not (row and row.client_secret_encrypted):
        raise HTTPException(422, "Add the Client Secret too.")
    if row is None:
        row = PortalProviderConfig(provider=provider)
        db.add(row)
    changed = row.client_id != client_id or bool(secret)
    row.client_id = client_id
    if secret:
        row.client_secret_encrypted = CredentialCipher(settings).encrypt(secret)
    row.updated_by = admin.id
    row.updated_at = utcnow()
    if changed:
        _reset_test(row)  # a test of the old credentials says nothing about these
    _audit(db, admin, "portal.setup_saved", provider, secret_replaced=bool(secret))  # never the values
    db.commit()
    return one(db, settings, provider)


def clear(db: Session, settings: BackendSettings, admin: User, provider: str) -> dict[str, Any]:
    _provider_or_404(provider)
    row = _row(db, provider)
    if row is not None:
        row.client_id = row.client_secret_encrypted = None
        row.updated_by = admin.id
        _reset_test(row)
        _audit(db, admin, "portal.setup_removed", provider)
        db.commit()
    return one(db, settings, provider)


def start_test(db: Session, settings: BackendSettings, admin: User, provider: str) -> dict[str, Any]:
    from backend.services import connection_service

    _provider_or_404(provider)
    return connection_service.start(db, settings, admin, provider, purpose="test")


def record_test(db: Session, p: idp.Provider, verdict: str, detail: str) -> dict[str, Any]:
    row = _row(db, p.key)
    if row is None:
        row = PortalProviderConfig(provider=p.key)
        db.add(row)
    row.last_test_at = utcnow()
    row.last_test_status = verdict
    row.last_test_detail = (detail or "")[:300]
    row.last_test_simulated = p.simulated
    db.commit()
    return {"provider": p.key, **(last_test(row) or {})}
