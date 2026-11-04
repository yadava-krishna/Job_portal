"""Registration, login, refresh-token rotation and logout."""

from __future__ import annotations

import hmac
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import RefreshToken, User, utcnow
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
    if settings.registration_invite_code:
        if not req.invite_code or not hmac.compare_digest(req.invite_code.strip(), settings.registration_invite_code):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "A valid invite code is required to register.")
    email = req.email.lower().strip()
    problems = password_problems(req.password, email)
    if problems:
        raise HTTPException(422, {"message": "Password does not meet the policy.", "requirements": problems})
    user = User(email=email, password_hash=hash_password(req.password), full_name=(req.full_name or "").strip() or None)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.") from None
    db.refresh(user)
    return user


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
