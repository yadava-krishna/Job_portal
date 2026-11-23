"""Admin setup of portal sign-in (LinkedIn OpenID Connect, Indeed OAuth) and its connection readiness.

An admin either sets the server's environment settings (LINKEDIN_CLIENT_ID, ...), which always win, or saves the
developer app's client ID and secret in Settings -> Portal Connections -> Set up. Saved secrets are encrypted with the
dedicated ENCRYPTION_KEY only (security.ConnectorSecretCipher: never a key derived from JWT_SECRET, never a generated
one). Without a valid ENCRYPTION_KEY, saving secrets is off and the admin is told why; nothing else in JobPilot changes.
Secrets are write-only: no API returns them, even to an admin.

Readiness (what the backend allows, and the reason) is one state per provider:
  missing_configuration   no credentials, or saved ones that can't be read                      blocks Connect
  invalid_callback        no usable callback URL, or the portal rejected it in a test           blocks Connect
  invalid_credentials     the portal rejected the client ID/secret in a test                     blocks Connect
  authorization_required  the portal hasn't approved the app/product/scopes (test)               blocks Connect
  provider_unavailable    the portal was down or answered oddly in the last test (temporary)     allows Connect
  consent_declined        the admin cancelled the last test on the portal                       allows Connect
  verified                a real sign-in test passed for exactly this configuration             allows Connect
  unverified              configured, never tested (or the test was for other settings)         allows Connect
  simulated               the server signs in with the local simulator (OAUTH_DEV_ENDPOINTS)    allows Connect (labelled)
Only an admin's test changes it, never a candidate's sign-in, since a browser can send any `error` it likes. A test
against the simulator is stored apart (simulated_test) and never changes the real result. A result recorded for a
different configuration (client ID, callback, scopes, source) is ignored.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import AuditLog, PortalProviderConfig, User, utcnow
from backend.security import ConnectorKeyError, ConnectorSecretCipher
from backend.services import identity_providers as idp

NAMES = {"linkedin": "LinkedIn", "indeed": "Indeed"}
LINKS = {
    "linkedin": {"console": "https://www.linkedin.com/developers/apps",
                 "docs": "https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2"},
    "indeed": {"console": "https://docs.indeed.com/getstarted/partner-console"},
}
PRODUCT = {"linkedin": "Sign In with LinkedIn using OpenID Connect", "indeed": "3-legged OAuth (Indeed Partner Console)"}
CLIENT_ID_RE = re.compile(r"^[A-Za-z0-9._~-]{4,200}$")
BLOCKING = {"missing_configuration", "invalid_callback", "invalid_credentials", "authorization_required"}
# Test verdicts that describe the configuration (and so set readiness); the others are about that one attempt.
VERDICT_STATE = {"verified": "verified", "invalid_credentials": "invalid_credentials", "invalid_callback": "invalid_callback",
                 "authorization_required": "authorization_required", "provider_unavailable": "provider_unavailable",
                 "cancelled": "consent_declined"}


def _row(db: Session, provider: str) -> PortalProviderConfig | None:
    return db.execute(select(PortalProviderConfig).where(PortalProviderConfig.provider == provider)).scalar_one_or_none()


def _provider_or_404(provider: str) -> str:
    if provider not in idp.PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Only LinkedIn and Indeed have a sign-in to set up. Naukri has none.")
    return provider


def _audit(db: Session, admin: User, action: str, provider: str, **details: Any) -> None:
    db.add(AuditLog(actor_id=admin.id, action=action, target_type="portal_setup", target_id=provider, details=details))


def config_fingerprint(p: idp.Provider) -> str:
    """What a test result is valid for. Never includes the secret (a new secret is saved through save(), which clears
    the result anyway)."""
    return hashlib.sha256("|".join([p.key, p.source, p.client_id, p.redirect_uri, " ".join(p.scopes)]).encode()).hexdigest()[:64]


def last_test(row: PortalProviderConfig | None, p: idp.Provider | None = None) -> dict[str, Any] | None:
    """The last REAL test, if it was for this configuration."""
    if row is None or not row.last_test_status:
        return None
    if p is not None and row.last_test_config and row.last_test_config != config_fingerprint(p):
        return None
    return {"status": row.last_test_status, "detail": row.last_test_detail, "simulated": False,
            "at": row.last_test_at.isoformat() if row.last_test_at else None}


def readiness(p: idp.Provider, test: dict[str, Any] | None) -> dict[str, Any]:
    """{state, blocks_connect, detail}: see the module docstring."""
    name = p.name
    if not p.configured:
        state = "invalid_callback" if p.client_id and p.client_secret and _callback_problem(p) else "missing_configuration"
        return {"state": state, "blocks_connect": True, "detail": p.problem}
    if p.simulated:
        return {"state": "simulated", "blocks_connect": False,
                "detail": f"Signs in with the local simulator (OAUTH_DEV_ENDPOINTS), not the real {name}."}
    if test is None:
        return {"state": "unverified", "blocks_connect": False, "detail": f"Set up, but no real {name} sign-in test has passed yet."}
    state = VERDICT_STATE.get(test["status"], "unverified")
    detail = test["detail"] or ""
    if state == "unverified":  # a failure that says nothing definite about the setup
        detail = f"The last test didn't pass ({detail}). Connecting is still allowed; test again to confirm the setup."
    return {"state": state, "blocks_connect": state in BLOCKING, "detail": detail}


def _callback_problem(p: idp.Provider) -> bool:
    return bool(p.problem) and ("redirect URI" in p.problem or "PUBLIC_APP_URL" in p.problem)


def secret_storage(settings: BackendSettings) -> dict[str, Any]:
    state, detail, key_id = ConnectorSecretCipher.status(settings)
    return {"state": state, "detail": detail, "key_id": key_id, "can_save": state == "ok"}


def provider_readiness(db: Session | None, settings: BackendSettings, p: idp.Provider) -> dict[str, Any]:
    return readiness(p, last_test(_row(db, p.key), p) if db is not None else None)


def overview(db: Session, settings: BackendSettings) -> list[dict[str, Any]]:
    storage = secret_storage(settings)
    out = []
    for key in idp.PROVIDERS:
        p = idp.get(settings, key, db)
        row = _row(db, key)
        env = key.upper()
        explicit = getattr(settings, f"{key}_redirect_uri", None)
        test = last_test(row, p)
        ready = readiness(p, test)
        saved = bool(row and row.client_id and row.client_secret_encrypted)
        if not saved:
            secret_status = None
        elif p.source != "admin":
            secret_status = "overridden"  # environment settings win
        elif p.client_secret:
            secret_status = "ok" if not storage["key_id"] or row.client_secret_key_id in (None, storage["key_id"]) else "needs_rotation"
        else:
            secret_status = "unreadable"
        out.append({
            "provider": key, "name": NAMES[key], "product": PRODUCT[key], "links": LINKS[key],
            "state": ready["state"], "readiness": ready, "configured": p.configured, "problem": p.problem,
            "source": p.source or None, "editable": p.source != "env",
            "client_id": p.client_id or (row.client_id if row else None) or None, "has_secret": bool(p.client_secret) or saved,
            "secret_status": secret_status, "secret_storage": storage,
            "redirect_uri": p.redirect_uri or None,
            "redirect_from": f"{env}_REDIRECT_URI" if explicit else ("PUBLIC_APP_URL" if p.redirect_uri else None),
            "redirect_problem": idp._redirect_problem(p.redirect_uri, settings) if p.redirect_uri else
                                f"The server doesn't know its public address: set PUBLIC_APP_URL (or {env}_REDIRECT_URI).",
            "scopes": list(p.scopes), "simulated": p.simulated, "pkce": p.pkce,
            "env_names": [f"{env}_CLIENT_ID", f"{env}_CLIENT_SECRET"],
            "last_test": test, "simulated_test": (row.simulated_test if row else None) or None,
            "updated_at": row.updated_at.isoformat() if row and row.client_id and row.updated_at else None,
        })
    return out


def one(db: Session, settings: BackendSettings, provider: str) -> dict[str, Any]:
    return next(r for r in overview(db, settings) if r["provider"] == _provider_or_404(provider))


def _reset_test(row: PortalProviderConfig) -> None:
    row.last_test_at = row.last_test_status = row.last_test_detail = row.last_test_config = None
    row.last_test_simulated = False


def save(db: Session, settings: BackendSettings, admin: User, provider: str, client_id: str, client_secret: str | None) -> dict[str, Any]:
    _provider_or_404(provider)
    if idp.get(settings, provider, db).source == "env":
        raise HTTPException(status.HTTP_409_CONFLICT, f"{NAMES[provider]} is set in the server's environment settings, which take "
                                                      "precedence. Change it there.")
    try:
        cipher = ConnectorSecretCipher(settings)
    except ConnectorKeyError as exc:
        # Never fall back to JWT_SECRET and never invent a key: saving is off until the server has a dedicated key.
        raise HTTPException(status.HTTP_409_CONFLICT, f"Saving connector secrets is off. {exc.message} Set it on the backend and "
                                                      "restart; or use the LINKEDIN_/INDEED_ environment settings instead.") from None
    client_id = (client_id or "").strip()
    if not CLIENT_ID_RE.match(client_id):
        raise HTTPException(422, "Paste the Client ID exactly as the developer portal shows it (letters, digits, - . _ ~).")
    row = _row(db, provider)
    secret = (client_secret or "").strip()
    if secret and (len(secret) > 500 or re.search(r"\s", secret)):
        raise HTTPException(422, "Paste the Client Secret exactly as the developer portal shows it.")
    if not secret:
        if not (row and row.client_secret_encrypted):
            raise HTTPException(422, "Add the Client Secret too.")
        if cipher.decrypt(row.client_secret_encrypted)[0] is None:
            raise HTTPException(409, "The saved secret can't be read with this server's ENCRYPTION_KEY, so it can't be kept. "
                                     "Restore the original key, or enter the secret again.")
    if row is None:
        row = PortalProviderConfig(provider=provider)
        db.add(row)
    changed = row.client_id != client_id or bool(secret)
    row.client_id = client_id
    if secret:
        row.client_secret_encrypted = cipher.encrypt(secret)
        row.client_secret_key_id = cipher.key_id
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
        row.client_id = row.client_secret_encrypted = row.client_secret_key_id = None
        row.updated_by = admin.id
        _reset_test(row)
        row.simulated_test = None
        _audit(db, admin, "portal.setup_removed", provider)
        db.commit()
    return one(db, settings, provider)


def start_test(db: Session, settings: BackendSettings, admin: User, provider: str) -> dict[str, Any]:
    from backend.services import connection_service

    _provider_or_404(provider)
    return connection_service.start(db, settings, admin, provider, purpose="test")


def record_test(db: Session, p: idp.Provider, verdict: str, detail: str) -> dict[str, Any]:
    """Store an admin's test result. A simulated test goes to simulated_test only and never touches the real result."""
    row = _row(db, p.key)
    if row is None:
        row = PortalProviderConfig(provider=p.key)
        db.add(row)
    at = utcnow()
    if p.simulated:
        row.simulated_test = {"status": verdict, "detail": (detail or "")[:300], "at": at.isoformat(), "simulated": True}
        db.commit()
        return {"provider": p.key, **row.simulated_test}
    row.last_test_at = at
    row.last_test_status = verdict
    row.last_test_detail = (detail or "")[:300]
    row.last_test_simulated = False
    row.last_test_config = config_fingerprint(p)
    db.commit()
    return {"provider": p.key, **(last_test(row) or {})}
