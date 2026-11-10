"""Registration, login, refresh-token rotation and logout."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import AuditLog, RefreshToken, User, utcnow
from backend.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserOut
from backend.security import (
    create_access_token,
    hash_password,
    hash_token,
    needs_rehash,
    new_refresh_token,
    password_problems,
    verify_password,
)

# Verifying against a dummy hash for unknown emails keeps response time uniform (no user enumeration).
_DUMMY_HASH = hash_password("dummy-password-for-timing-1A")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def register(db: Session, settings: BackendSettings, req: RegisterRequest) -> User:
    email = req.email.lower().strip()
    code = (req.invite_code or "").strip()
    invite = _usable_invite(db, code, email) if code else None
    owner_code = bool(settings.registration_invite_code and code and hmac.compare_digest(code, settings.registration_invite_code))
    if settings.registration_invite_code and not (owner_code or invite):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "A valid invite code is required to register.")
    problems = password_problems(req.password, email)
    if problems:
        raise HTTPException(422, {"message": "Password does not meet the policy.", "requirements": problems})
    user = User(email=email, password_hash=hash_password(req.password), full_name=(req.full_name or "").strip() or None,
                role=invite.role if invite and invite.role in ("user", "mentor") else "user")  # invites never grant admin
    db.add(user)
    if invite is not None:
        invite.used_count += 1
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.") from None
    db.refresh(user)
    return user


def _usable_invite(db: Session, code: str, email: str):
    """An admin-created invite (stored hashed) that is unrevoked, unexpired, has uses left and, if it names an
    e-mail address, matches it."""
    from backend.models import Invite

    inv = db.execute(select(Invite).where(Invite.token_hash == hashlib.sha256(code.encode()).hexdigest())).scalar_one_or_none()
    if inv is None or inv.revoked_at is not None or inv.used_count >= inv.max_uses:
        return None
    if inv.expires_at is not None and _aware(inv.expires_at) < utcnow():
        return None
    if inv.email and inv.email != email:
        return None
    return inv


def authenticate(db: Session, req: LoginRequest) -> User:
    user = db.execute(select(User).where(User.email == req.email.lower().strip())).scalar_one_or_none()
    if user is None:
        verify_password(_DUMMY_HASH, req.password)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    if not verify_password(user.password_hash, req.password) or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password.")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(req.password)
    user.last_login_at = utcnow()
    db.commit()
    return user


def issue_tokens(db: Session, settings: BackendSettings, user: User, user_agent: str | None, family_id: str | None = None) -> AuthResponse:
    access, ttl = create_access_token(settings, user.id)
    refresh, refresh_hash = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=refresh_hash, family_id=family_id or str(uuid.uuid4()),
                        expires_at=utcnow() + timedelta(days=settings.refresh_token_days), user_agent=(user_agent or "")[:300]))
    db.commit()
    return AuthResponse(access_token=access, refresh_token=refresh, expires_in=ttl, user=UserOut.model_validate(user))


def rotate_refresh(db: Session, settings: BackendSettings, token: str, user_agent: str | None) -> AuthResponse:
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired. Please sign in again.")
    row = db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(token))).scalar_one_or_none()
    if row is None:
        raise invalid
    if row.revoked_at is not None:
        # A rotated token was replayed: assume theft and end the whole session family.
        revoke_family(db, row.family_id)
        raise invalid
    if _aware(row.expires_at) <= utcnow():
        raise invalid
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise invalid
    row.revoked_at = utcnow()
    db.commit()
    return issue_tokens(db, settings, user, user_agent, family_id=row.family_id)


def revoke_family(db: Session, family_id: str) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None)).values(revoked_at=utcnow()))
    db.commit()


def logout(db: Session, token: str | None, user: User) -> None:
    if not token:
        return
    row = db.execute(select(RefreshToken).where(RefreshToken.token_hash == hash_token(token), RefreshToken.user_id == user.id)).scalar_one_or_none()
    if row is not None:
        revoke_family(db, row.family_id)


def _password_fingerprint(password_hash: str) -> str:
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def create_reset_token(settings: BackendSettings, user: User) -> str:
    """One-hour reset token bound to the current password hash: it stops working once the password changes,
    so each link can be used only once."""
    import jwt
    payload = {"sub": user.email, "type": "reset", "pwd": _password_fingerprint(user.password_hash),
               "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_reset_token(settings: BackendSettings, token: str) -> tuple[str, str] | None:
    import jwt
    try:
        data = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except Exception:
        return None
    if data.get("type") != "reset" or not data.get("sub") or not data.get("pwd"):
        return None
    return data["sub"], data["pwd"]


def reset_password(db: Session, settings: BackendSettings, token: str, new_password: str) -> bool:
    claims = verify_reset_token(settings, token)
    invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired password reset link.")
    if not claims:
        raise invalid
    user = db.execute(select(User).where(User.email == claims[0])).scalar_one_or_none()
    if not user or not user.is_active or _password_fingerprint(user.password_hash) != claims[1]:
        raise invalid
    problems = password_problems(new_password, user.email)
    if problems:
        raise HTTPException(422, {"message": "Password does not meet the policy.", "requirements": problems})
    user.password_hash = hash_password(new_password)
    # Sign out every existing session: whoever had the old password must not stay logged in.
    for rt in db.execute(select(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))).scalars():
        rt.revoked_at = utcnow()
    db.add(AuditLog(actor_id=user.id, action="PASSWORD_RESET", target_type="user", target_id=str(user.id)))
    db.commit()
    return True

