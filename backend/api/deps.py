"""Shared FastAPI dependencies: database session, current user, rate limiting, ownership scoping."""

from __future__ import annotations

from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from backend.config import BackendSettings, get_settings
from backend.db import get_db
from backend.models import User
from backend.security import decode_access_token, rate_limiter

DbSession = Annotated[Session, Depends(get_db)]
SettingsDep = Annotated[BackendSettings, Depends(get_settings)]
_bearer = HTTPBearer(auto_error=False)
T = TypeVar("T")


def get_current_user(
    db: DbSession,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise unauthorized
    user_id = decode_access_token(settings, credentials.credentials)
    if user_id is None:
        raise unauthorized
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def scoped(model: type[T], user: User) -> Select:
    """SELECT restricted to rows owned by `user`. All user-data queries start here."""
    return select(model).where(model.user_id == user.id)  # type: ignore[attr-defined]


def get_owned(db: Session, model: type[T], object_id: int, user: User) -> T:
    """Fetch one row owned by the user, or 404 (never 403, to avoid leaking existence)."""
    obj = db.execute(scoped(model, user).where(model.id == object_id)).unique().scalar_one_or_none()  # type: ignore[attr-defined]
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


def client_ip(request: Request, settings: BackendSettings) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def auth_rate_limit(request: Request, settings: SettingsDep) -> None:
    key = f"auth:{request.url.path}:{client_ip(request, settings)}"
    retry = rate_limiter.check(key, settings.auth_rate_limit_per_minute, 60)
    if retry is not None:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again shortly.",
                            headers={"Retry-After": str(int(retry) + 1)})
