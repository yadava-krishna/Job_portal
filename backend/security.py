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


class ConnectorKeyError(Exception):
    """state: missing | invalid. The message is safe to show an admin; it never contains a key."""

    def __init__(self, state: str, message: str):
        super().__init__(message)
        self.state = state
        self.message = message


def connector_key_id(key: str) -> str:
    """A short public identifier of an encryption key (not the key, and not usable to recover it): lets the server say
    which key a saved secret was encrypted with, so a rotation or a lost key is diagnosable."""
    return hashlib.sha256(b"jobpilot-connector-key-id:" + key.encode()).hexdigest()[:16]


def legacy_jwt_derived_key(settings: BackendSettings) -> str:
    """The key CredentialCipher derives from JWT_SECRET when ENCRYPTION_KEY is unset. Used ONLY by the recovery tool
    (backend/scripts/connector_secrets.py) to read connector secrets saved before V3.3 hardening; never to encrypt."""
    return base64.urlsafe_b64encode(hashlib.sha256(("credential-key:" + settings.jwt_secret).encode()).digest()).decode()


class ConnectorSecretCipher:
    """Encrypts portal developer credentials (LinkedIn/Indeed client secrets) with the dedicated ENCRYPTION_KEY only.

    Unlike CredentialCipher it never falls back to a key derived from JWT_SECRET and never generates a key: without a
    valid ENCRYPTION_KEY it refuses (ConnectorKeyError), so connector secrets can't silently depend on the JWT secret
    or become unreadable after a restart. ENCRYPTION_KEY_PREVIOUS, when set, is tried for reading only (rotation)."""

    def __init__(self, settings: BackendSettings, key: str | None = None):
        key = key if key is not None else settings.encryption_key
        if not key:
            raise ConnectorKeyError("missing", "ENCRYPTION_KEY isn't set on the server. Connector secrets need their own "
                                               "encryption key (a Fernet key), separate from JWT_SECRET.")
        try:
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
        except (ValueError, TypeError):
            raise ConnectorKeyError("invalid", "ENCRYPTION_KEY isn't a valid Fernet key (32 url-safe base64-encoded bytes).") from None
        self.key_id = connector_key_id(key)
        prev = getattr(settings, "encryption_key_previous", None) if key == settings.encryption_key else None
        self._previous = None
        if prev:
            try:
                self._previous = (Fernet(prev.encode()), connector_key_id(prev))
            except (ValueError, TypeError):
                self._previous = None

    @staticmethod
    def status(settings: BackendSettings) -> tuple[str, str | None, str | None]:
        """(ok | missing | invalid, admin-facing detail, key id)."""
        try:
            c = ConnectorSecretCipher(settings)
        except ConnectorKeyError as exc:
            return exc.state, exc.message, None
        return "ok", None, c.key_id

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def _fernet_try(self, value: str) -> str | None:
        """This key only (no previous key): the plaintext, or None."""
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken:
            return None

    def decrypt(self, value: str) -> tuple[str | None, str | None]:
        """(plaintext, key id that opened it), or (None, None) when neither the current nor the previous key can."""
        try:
            return self._fernet.decrypt(value.encode()).decode(), self.key_id
        except InvalidToken:
            pass
        if self._previous:
            try:
                return self._previous[0].decrypt(value.encode()).decode(), self._previous[1]
            except InvalidToken:
                pass
        return None, None


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
