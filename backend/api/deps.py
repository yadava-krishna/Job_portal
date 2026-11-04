"""Shared FastAPI dependencies: database session, current user, rate limiting, ownership scoping."""

from __future__ import annotations

import ipaddress
from functools import lru_cache
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


@lru_cache(maxsize=16)
def _networks(cidrs: tuple[str, ...]) -> tuple[ipaddress._BaseNetwork, ...]:
    return tuple(ipaddress.ip_network(c, strict=False) for c in cidrs)


def _parse_ip(value: str | None) -> ipaddress._BaseAddress | None:
    if not value:
        return None
    value = value.strip().strip('"')
    if value.startswith("[") and "]" in value:  # [IPv6]:port
        value = value[1:value.index("]")]
    elif value.count(":") == 1:  # IPv4:port
        value = value.split(":")[0]
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def resolve_client_ip(peer: str | None, forwarded_for: str | None, trusted_cidrs: list[str], trust_headers: bool = True) -> str:
    """Return the real client address.

    X-Forwarded-For is honoured only when the direct peer is a trusted proxy, and then the chain is
    read right to left, skipping trusted proxies: the first untrusted address is the client. Entries
    a client prepends itself can never be selected, because each trusted proxy appends the address
    it actually received the connection from.
    """
    nets = _networks(tuple(trusted_cidrs))
    peer_ip = _parse_ip(peer)
    is_trusted = lambda ip: any(ip in n for n in nets)  # noqa: E731
    if not trust_headers or peer_ip is None or not is_trusted(peer_ip) or not forwarded_for:
        return str(peer_ip) if peer_ip else (peer or "unknown")
    chain = [_parse_ip(part) for part in forwarded_for.split(",")]
    for ip in reversed(chain):
        if ip is None:
            # A malformed hop: nothing to its left can be trusted, so attribute the request to the peer.
            return str(peer_ip)
        if not is_trusted(ip):
            return str(ip)
    # Every hop is a trusted proxy (e.g. a request from this machine): use the left-most, all are ours.
    return str(chain[0])


def client_ip(request: Request, settings: BackendSettings) -> str:
    # Proxies may append a separate header line rather than extending the first (ngrok does): read all of
    # them, in order. headers.get() would return only the first line, which the client controls.
    forwarded = ", ".join(request.headers.getlist("x-forwarded-for")) or None
    return resolve_client_ip(request.client.host if request.client else None, forwarded,
                             settings.trusted_proxy_cidrs, settings.trust_proxy_headers)


def is_local_request(request: Request, settings: BackendSettings) -> bool:
    """True when the resolved client is this machine or a container on its Docker networks."""
    ip = _parse_ip(client_ip(request, settings))
    return ip is not None and any(ip in n for n in _networks(tuple(settings.trusted_proxy_cidrs)))


def _too_many(retry: float) -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many attempts. Try again shortly.",
                         headers={"Retry-After": str(int(retry) + 1)})


def auth_rate_limit(request: Request, settings: SettingsDep) -> None:
    key = f"auth:{request.url.path}:{client_ip(request, settings)}"
    retry = rate_limiter.check(key, settings.auth_rate_limit_per_minute, 60)
    if retry is not None:
        raise _too_many(retry)


def login_failure_key(email: str) -> str:
    return f"login-fail:{email.strip().lower()}"


def check_account_lock(email: str, settings: BackendSettings) -> None:
    """Per-account brute-force protection, independent of the client address."""
    window = settings.login_failure_window_minutes * 60
    if rate_limiter.count(login_failure_key(email), window) >= settings.login_failures_per_account:
        raise _too_many(window)
