"""Password hashing, JWT access tokens, refresh-token helpers, credential encryption, rate limiting."""

from __future__ import annotations

import base64
import hashlib
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from backend.config import BackendSettings

_hasher = PasswordHasher()  # Argon2id with library defaults
JWT_ALGORITHM = "HS256"
COMMON_PASSWORDS = {"password", "password1", "password123", "12345678", "123456789", "qwerty123", "letmein1", "welcome1", "admin123"}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def password_problems(password: str, email: str | None = None) -> list[str]:
    problems = []
    if len(password) < 10:
        problems.append("at least 10 characters")
    if len(password) > 128:
        problems.append("at most 128 characters")
    if not re.search(r"[a-z]", password) or not re.search(r"[A-Z]", password):
        problems.append("both upper- and lower-case letters")
    if not re.search(r"\d", password):
        problems.append("at least one number")
    if password.lower() in COMMON_PASSWORDS:
        problems.append("not a common password")
    if email and email.split("@")[0].lower() in password.lower() and len(email.split("@")[0]) >= 4:
        problems.append("must not contain your email name")
    return problems


def create_access_token(settings: BackendSettings, user_id: int) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    ttl = settings.access_token_minutes * 60
    payload = {"sub": str(user_id), "type": "access", "iat": now, "exp": now + timedelta(seconds=ttl), "jti": secrets.token_hex(8)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM), ttl


def decode_access_token(settings: BackendSettings, token: str) -> int | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM], options={"require": ["exp", "sub", "type"]})
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    try:
        return int(payload["sub"])
    except (TypeError, ValueError):
        return None


def new_refresh_token() -> tuple[str, str]:
    """Return (opaque token for the client, SHA-256 hash for storage)."""
    token = secrets.token_urlsafe(48)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class CredentialCipher:
    """Encrypts third-party credentials (e.g. IMAP app passwords) at rest."""

    def __init__(self, settings: BackendSettings):
        key = settings.encryption_key
        if not key:
            digest = hashlib.sha256(("credential-key:" + settings.jwt_secret).encode()).digest()
            key = base64.urlsafe_b64encode(digest).decode()
        self._fernet = Fernet(key.encode() if isinstance(key, str) else key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str | None:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken:
            return None


class RateLimiter:
    """Sliding-window limiter keyed by (bucket, client). In-process: one backend worker."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: float = 60.0) -> float | None:
        """Record a hit. Returns None if allowed, else seconds until a slot frees up."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            if len(hits) >= limit:
                return max(0.0, window_seconds - (now - hits[0]))
            hits.append(now)
            return None

    def count(self, key: str, window_seconds: float) -> int:
        """Hits recorded for `key` inside the window, without recording a new one."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits.get(key)
            if not hits:
                return 0
            while hits and now - hits[0] > window_seconds:
                hits.popleft()
            return len(hits)

    def record(self, key: str) -> None:
        with self._lock:
            self._hits[key].append(time.monotonic())

    def clear(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


rate_limiter = RateLimiter()
