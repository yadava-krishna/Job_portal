"""Linking a portal account (LinkedIn, Indeed) to a JobPilot user through the portal's official sign-in.

Flow (authorization code; the app uses bearer tokens, not cookies):
  1. start     the signed-in user asks to connect. JobPilot stores a pending sign-in bound to that user (SHA-256 of a
               random state, a nonce, an encrypted PKCE verifier, the exact redirect URI; 10 minutes; single use) and
               returns the provider's authorization URL. The browser goes there in the same tab.
  2. provider  the user signs in on the provider's own site (JobPilot never sees a portal password or OTP) and consents.
  3. callback  the provider redirects to <app>/oauth-callback.html, a static page that keeps code + state in this tab's
               sessionStorage and returns to Settings. Nothing is exchanged there.
  4. complete  the signed-in app posts code + state. JobPilot rejects a state that is unknown, used, expired, or was
               started by a different JobPilot user (an attacker can't get their sign-in completed in your session, or
               yours in theirs), checks the RFC 9207 issuer where the provider sends it, exchanges the code, verifies the
               ID token, and links the provider's stable subject id. The same portal account can't be linked to two
               JobPilot users.
Disconnect deletes the tokens. Neither provider publishes a revocation endpoint, so the user is told where to remove
JobPilot on the portal itself.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import AuditLog, ExternalIdentity, OAuthState, User, utcnow
from backend.security import CredentialCipher
from backend.services import identity_providers as idp
from backend.services.identity_providers import Provider, ProviderError

STATE_TTL = timedelta(minutes=10)
CANCELLED = {"user_cancelled_login", "user_cancelled_authorize", "access_denied", "consent_required", "login_required"}
# The provider refused JobPilot's app itself (not the user): wrong credentials, an unapproved app or scope.
APP_REFUSED = {"unauthorized_client", "invalid_client", "invalid_scope", "unsupported_response_type"}


def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _hash(state: str) -> str:
    return hashlib.sha256(state.encode()).hexdigest()


def _audit(db: Session, user: User, action: str, provider: str, **details: Any) -> None:
    # Never tokens, codes, e-mail addresses or subject ids.
    db.add(AuditLog(actor_id=user.id, action=action, target_type="portal", target_id=provider, details=details))


def provider_or_404(settings: BackendSettings, key: str, db: Session | None = None) -> Provider:
    p = idp.get(settings, key, db)
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This portal has no account sign-in in JobPilot.")
    return p


def identity(db: Session, user: User, provider: str) -> ExternalIdentity | None:
    return db.execute(select(ExternalIdentity).where(ExternalIdentity.user_id == user.id, ExternalIdentity.provider == provider)).scalar_one_or_none()


def effective_status(row: ExternalIdentity, p: Provider | None, now: datetime | None = None) -> tuple[str, str | None]:
    """linked | reconnect_required, with the reason shown to the user."""
    now = now or utcnow()
    if row.status == "reconnect_required":
        return "reconnect_required", row.status_detail
    exp = _aware(row.access_expires_at)
    if exp and exp <= now:
        rexp = _aware(row.refresh_expires_at)
        can_refresh = bool(row.refresh_token_encrypted) and (rexp is None or rexp > now) and bool(p and p.issues_refresh)
        if not can_refresh:
            return "reconnect_required", "JobPilot's access has expired. Reconnect to link it again."
    return "linked", None


# ---- 1. start ---------------------------------------------------------------------------------------------------

def start(db: Session, settings: BackendSettings, user: User, provider: str, *, purpose: str = "link") -> dict[str, Any]:
    """purpose "test": an admin testing the server's setup with a real sign-in. It completes like a link, but nothing
    is linked and no token is kept; only the result is recorded (portal_setup_service)."""
    p = provider_or_404(settings, provider, db)
    if not p.configured:
        raise HTTPException(status.HTTP_409_CONFLICT, p.problem)
    now = utcnow()
    # Old pending sign-ins for this user and portal are dropped: only the newest can complete.
    db.execute(delete(OAuthState).where(OAuthState.user_id == user.id, OAuthState.provider == p.key))
    db.execute(delete(OAuthState).where(OAuthState.expires_at < now - timedelta(days=1)))
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(24) if p.oidc else None
    verifier = secrets.token_urlsafe(64) if p.pkce else None
    db.add(OAuthState(user_id=user.id, provider=p.key, state_hash=_hash(state), nonce=nonce, redirect_uri=p.redirect_uri,
                      code_verifier_encrypted=CredentialCipher(settings).encrypt(verifier) if verifier else None,
                      scopes=list(p.scopes), created_at=now, expires_at=now + STATE_TTL, purpose=purpose))
    _audit(db, user, "portal.setup_test_started" if purpose == "test" else "portal.connect_started", p.key)
    db.commit()
    return {"provider": p.key, "authorization_url": idp.authorization_url(p, state, nonce=nonce, verifier=verifier),
            "expires_in": int(STATE_TTL.total_seconds())}


# ---- 4. complete ------------------------------------------------------------------------------------------------

def _safe_code(v: str | None) -> str:
    return re.sub(r"[^a-z0-9_.-]", "", (v or "").lower())[:40]


def complete(db: Session, settings: BackendSettings, user: User, *, state: str, code: str | None, error: str | None,
             iss: str | None) -> ExternalIdentity | dict[str, Any]:
    """Returns the linked identity, or for an admin's setup test (purpose "test") the recorded test result."""
    row = db.execute(select(OAuthState).where(OAuthState.state_hash == _hash(state or ""))).scalar_one_or_none() if state else None
    if row is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This sign-in isn't one JobPilot started. Start again from Portal Connections.")
    p = provider_or_404(settings, row.provider, db)
    if row.user_id != user.id:
        # Started by a different JobPilot user: never link, and burn it so it can't be retried.
        row.used_at = row.used_at or utcnow()
        _audit(db, user, "portal.link_rejected", p.key, reason="state_of_another_user")
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This sign-in was started from a different JobPilot account. Nothing was linked.")
    if row.purpose != "test":
        return _complete(db, settings, user, row, p, code=code, error=error, iss=iss)
    from backend.services import portal_setup_service

    if getattr(user, "role", "user") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only an admin can test the portal sign-in setup.")
    seen: dict[str, str] = {}
    try:
        out = _complete(db, settings, user, row, p, code=code, error=error, iss=iss, test=True, seen=seen)
    except HTTPException as exc:
        err = _safe_code(error)
        verdict = ("cancelled" if err in CANCELLED else
                   "authorization_required" if err in APP_REFUSED or seen.get("kind") == "client" else "failed")
        if seen.get("claimed"):  # this attempt got as far as the provider (not a stale or reused sign-in)
            portal_setup_service.record_test(db, p, verdict, str(exc.detail))
        raise
    return out


def _complete(db: Session, settings: BackendSettings, user: User, row: OAuthState, p: Provider, *, code: str | None,
              error: str | None, iss: str | None, test: bool = False, seen: dict[str, str] | None = None) -> ExternalIdentity | dict[str, Any]:
    nothing = "Nothing was linked." if not test else "The test didn't pass."
    if row.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This sign-in was already used. Start again from Portal Connections.")
    if _aware(row.expires_at) <= utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This sign-in took longer than 10 minutes and expired. Start again.")
    # Single use, even if the rest fails: claimed atomically, so two requests with the same state can't both pass.
    claimed = db.execute(update(OAuthState).where(OAuthState.id == row.id, OAuthState.used_at.is_(None)).values(used_at=utcnow()))
    db.commit()
    if claimed.rowcount != 1:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "This sign-in was already used. Start again from Portal Connections.")
    if seen is not None:
        seen["claimed"] = "1"
    if not p.configured:
        raise HTTPException(status.HTTP_409_CONFLICT, p.problem)
    if p.redirect_uri != row.redirect_uri:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The server's sign-in settings changed while you were away. Start again.")

    if error:
        _audit(db, user, "portal.link_failed", p.key, reason=_safe_code(error))
        db.commit()
        if _safe_code(error) in CANCELLED:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"You cancelled on {p.name}. {nothing}")
        if _safe_code(error) in APP_REFUSED:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{p.name} refused JobPilot's app ({_safe_code(error)}): the app's "
                                                             f"credentials, redirect URL or approval need an admin's attention. {nothing}")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{p.name} didn't complete the sign-in ({_safe_code(error) or 'error'}). {nothing}")
    if p.iss_param and iss not in p.issuers:
        _audit(db, user, "portal.link_rejected", p.key, reason="issuer_mismatch")
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"The sign-in response didn't come from {p.name}. {nothing}")
    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{p.name} didn't send a sign-in code. Start again.")

    cipher = CredentialCipher(settings)
    verifier = cipher.decrypt(row.code_verifier_encrypted) if row.code_verifier_encrypted else None
    try:
        tokens = idp.exchange_code(p, code, verifier)
        claims, checks = ({}, {"id_token": "not_issued"})
        if tokens.get("id_token"):
            claims, checks = idp.verify_id_token(p, tokens["id_token"], row.nonce)
        elif p.oidc:
            raise ProviderError("invalid_token", f"{p.name} didn't send an ID token. Nothing was linked.")
        info: dict[str, Any] = {}
        try:
            info = idp.userinfo(p, tokens["access_token"])
        except ProviderError:
            if not claims:  # no ID token: the userinfo answer is the only proof of who this is
                raise
        subject = claims.get("sub") or info.get("sub")
        if claims.get("sub") and info.get("sub") and claims["sub"] != info["sub"]:
            raise ProviderError("invalid_token", f"{p.name} described two different accounts. Nothing was linked.")
        if not subject:
            raise ProviderError("provider_error", f"{p.name} didn't say which account this is.")
    except ProviderError as exc:
        if seen is not None:
            seen["kind"] = exc.kind
        _audit(db, user, "portal.link_failed", p.key, reason=exc.kind)
        db.commit()
        code_ = status.HTTP_400_BAD_REQUEST if exc.kind in ("invalid_grant", "invalid_token") else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(code_, exc.message) from None

    if test:  # the admin's setup test: the real sign-in worked end to end. Link nothing, keep no token.
        from backend.services import portal_setup_service

        shared = [k for k in ("name", "email") if (claims.get(k) or info.get(k))]
        detail = (f"Signed in with {p.name}, verified the {'ID token and ' if claims else ''}account, and read "
                  f"{', '.join(shared) if shared else 'the account ID'}. Nothing was linked or kept.")
        _audit(db, user, "portal.setup_tested", p.key, result="verified", simulated=p.simulated)
        return portal_setup_service.record_test(db, p, "verified", detail)

    other = db.execute(select(ExternalIdentity).where(ExternalIdentity.provider == p.key, ExternalIdentity.subject == subject,
                                                      ExternalIdentity.user_id != user.id)).scalar_one_or_none()
    if other is not None:
        _audit(db, user, "portal.link_rejected", p.key, reason="linked_to_another_user")
        db.commit()
        raise HTTPException(status.HTTP_409_CONFLICT, f"This {p.name} account is already linked to another JobPilot account. "
                                                      "Disconnect it there first.")
    merged = {**claims, **{k: v for k, v in info.items() if v not in (None, "")}}
    granted = _granted(tokens.get("scope"), row.scopes)
    ident = identity(db, user, p.key)
    replaced = bool(ident and ident.subject != subject)
    if ident is None:
        ident = ExternalIdentity(user_id=user.id, provider=p.key, subject=subject)
        db.add(ident)
    now = utcnow()
    ident.subject = subject
    _fill(ident, merged, granted)
    ident.access_token_encrypted = cipher.encrypt(tokens["access_token"])
    ident.refresh_token_encrypted = cipher.encrypt(tokens["refresh_token"]) if tokens.get("refresh_token") else None
    ident.access_expires_at = _expiry(now, tokens.get("expires_in"))
    ident.refresh_expires_at = _expiry(now, tokens.get("refresh_token_expires_in")) if tokens.get("refresh_token") else None
    ident.status, ident.status_detail = "linked", None
    ident.checks = {**checks, "userinfo": bool(info), "pkce": bool(verifier), "state": "bound_to_user", "simulated": p.simulated}
    ident.linked_at = now if (replaced or ident.linked_at is None or ident.id is None) else ident.linked_at
    ident.last_validated_at = now
    _audit(db, user, "portal.linked", p.key, replaced_other_account=replaced, scopes=granted)
    try:
        db.commit()
    except IntegrityError:  # the same account was linked elsewhere a moment ago
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, f"This {p.name} account is already linked to another JobPilot account.") from None
    db.refresh(ident)
    return ident


def _granted(scope: Any, requested: list[str]) -> list[str]:
    if isinstance(scope, str) and scope.strip():
        return sorted(set(re.split(r"[\s,]+", scope.strip())))
    return sorted(set(requested))  # the provider didn't say: what was asked for and consented to


def _expiry(now: datetime, seconds: Any) -> datetime | None:
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return None
    return now + timedelta(seconds=s) if s > 0 else None


def _fill(ident: ExternalIdentity, data: dict[str, Any], granted: list[str]) -> None:
    """Only what the provider shared under a granted scope. Never copied into the JobPilot profile."""
    name = data.get("name") or " ".join(x for x in (data.get("given_name"), data.get("family_name")) if x) or None
    ident.name = str(name)[:200] if name else None
    email = data.get("email")
    ident.email = str(email)[:320] if isinstance(email, str) and "@" in email else None
    ev = data.get("email_verified")
    ident.email_verified = (ev if isinstance(ev, bool) else str(ev).lower() == "true") if ident.email and ev is not None else None
    pic = data.get("picture")
    ident.picture_url = pic if isinstance(pic, str) and pic.startswith("https://") else None
    ident.scopes = granted


# ---- check, refresh -----------------------------------------------------------------------------------------------

def check(db: Session, settings: BackendSettings, user: User, provider: str) -> ExternalIdentity:
    """Ask the provider whether JobPilot's access still works (refreshing it first where the provider allows)."""
    p = provider_or_404(settings, provider, db)
    # Locked for the whole check: two checks at once (a double click, two tabs) must not both spend the same rotating
    # refresh token, or the second would see it refused and wrongly drop a healthy link.
    ident = db.execute(select(ExternalIdentity).where(ExternalIdentity.user_id == user.id, ExternalIdentity.provider == p.key)
                       .with_for_update()).scalar_one_or_none()
    if ident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No {p.name} account is linked.")
    if not p.configured:
        raise HTTPException(status.HTTP_409_CONFLICT, p.problem)
    cipher = CredentialCipher(settings)
    now = utcnow()

    def needs_reconnect(detail: str) -> ExternalIdentity:
        ident.status, ident.status_detail = "reconnect_required", detail[:300]
        ident.access_token_encrypted = None
        _audit(db, user, "portal.reconnect_required", p.key)
        db.commit()
        return ident

    st, detail = effective_status(ident, p, now)
    if st == "reconnect_required":
        return needs_reconnect(detail or "Reconnect to link it again.")
    access = cipher.decrypt(ident.access_token_encrypted) if ident.access_token_encrypted else None
    exp = _aware(ident.access_expires_at)
    if (access is None or (exp and exp <= now)) and ident.refresh_token_encrypted:
        spent = ident.refresh_token_encrypted
        rt = cipher.decrypt(spent)
        try:
            tokens = idp.refresh(p, rt or "")
        except ProviderError as exc:
            if exc.kind != "invalid_grant":  # the provider is down or answered oddly: keep the link, try again later
                db.rollback()
                raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from None
            db.refresh(ident)
            if ident.refresh_token_encrypted != spent:  # another check refreshed it meanwhile (SQLite has no row lock)
                return ident
            return needs_reconnect(f"{p.name} no longer accepts JobPilot's access. Reconnect to link it again.")
        access = tokens["access_token"]
        ident.access_token_encrypted = cipher.encrypt(access)
        ident.access_expires_at = _expiry(now, tokens.get("expires_in"))
        if tokens.get("refresh_token"):  # rotated
            ident.refresh_token_encrypted = cipher.encrypt(tokens["refresh_token"])
            ident.refresh_expires_at = _expiry(now, tokens.get("refresh_token_expires_in"))
        if tokens.get("scope"):
            ident.scopes = _granted(tokens["scope"], ident.scopes)
    if access is None:
        return needs_reconnect("JobPilot's access has expired. Reconnect to link it again.")
    try:
        info = idp.userinfo(p, access)
    except ProviderError as exc:
        if exc.kind == "unauthorized":
            return needs_reconnect(exc.message)
        db.commit()
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from None
    if info.get("sub") != ident.subject:
        return needs_reconnect(f"{p.name} now reports a different account. Reconnect to choose the right one.")
    _fill(ident, info, ident.scopes)
    ident.status, ident.status_detail = "linked", None
    ident.last_validated_at = now
    db.commit()
    return ident


# ---- disconnect ---------------------------------------------------------------------------------------------------

REMOVE_ON_PORTAL = {
    "linkedin": "To also remove JobPilot on LinkedIn, open LinkedIn Settings → Data privacy and remove JobPilot from the services you've allowed.",
    "indeed": "To also remove JobPilot on Indeed, remove it from the apps allowed in your Indeed account settings.",
}


def disconnect(db: Session, settings: BackendSettings, user: User, provider: str) -> dict[str, Any]:
    p = provider_or_404(settings, provider, db)
    ident = identity(db, user, p.key)
    db.execute(delete(OAuthState).where(OAuthState.user_id == user.id, OAuthState.provider == p.key))
    if ident is None:
        db.commit()
        return {"provider": p.key, "disconnected": False, "detail": f"No {p.name} account was linked."}
    db.delete(ident)  # tokens go with it; nothing else in JobPilot came from the provider
    _audit(db, user, "portal.unlinked", p.key)
    db.commit()
    return {"provider": p.key, "disconnected": True,
            "detail": f"{p.name} is disconnected and JobPilot deleted its access tokens. {p.name} offers no way for apps to revoke "
                      f"access themselves. {REMOVE_ON_PORTAL[p.key]}"}


def public(ident: ExternalIdentity, p: Provider | None) -> dict[str, Any]:
    st, detail = effective_status(ident, p)
    return {"status": st, "status_detail": detail, "simulated": bool((ident.checks or {}).get("simulated")), "name": ident.name, "email": ident.email, "email_verified": ident.email_verified,
            "has_picture": bool(ident.picture_url), "scopes": list(ident.scopes or []),
            "linked_at": ident.linked_at.isoformat() if ident.linked_at else None,
            "last_validated_at": ident.last_validated_at.isoformat() if ident.last_validated_at else None,
            "access_expires_at": ident.access_expires_at.isoformat() if ident.access_expires_at else None,
            "can_refresh": bool(ident.refresh_token_encrypted) and bool(p and p.issues_refresh),
            "checks": dict(ident.checks or {})}
