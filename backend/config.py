"""Backend configuration from environment variables (see .env.example)."""

from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VERSION = "1.0.0"


class BackendSettings(BaseModel):
    environment: str = "development"
    database_url: str = "sqlite:///./storage/jobpilot-dev.db"
    storage_dir: Path = PROJECT_ROOT / "storage"
    jwt_secret: str = Field(min_length=32)
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    # Fernet key for encrypting third-party credentials (IMAP passwords). Derived from jwt_secret if unset.
    encryption_key: str | None = None
    encryption_key_previous: str | None = None  # read-only during a key rotation (connector secrets)
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173", "http://localhost:3000"])
    registration_invite_code: str | None = None
    trust_proxy_headers: bool = True
    # Only these peers may set X-Forwarded-For (ngrok/nginx containers on Docker networks, loopback).
    trusted_proxy_cidrs: list[str] = Field(default_factory=lambda: ["127.0.0.0/8", "::1/128", "172.16.0.0/12"])
    # API docs: "public" (dev), "local" (only from this machine / Docker networks), "off".
    docs_mode: str = "public"
    login_failures_per_account: int = 10
    login_failure_window_minutes: int = 15
    max_upload_mb: int = 5
    auth_rate_limit_per_minute: int = 10
    timezone: str = "Asia/Kolkata"
    llm_provider: str = "rule_based"
    llm_model: str = "claude-opus-5"
    llm_effort: str = "medium"
    llm_base_url: str | None = None
    llm_api_key_env: str = "ANTHROPIC_API_KEY"
    adzuna_app_id: str | None = None
    adzuna_app_key: str | None = None
    adzuna_country: str = "in"
    scheduler_enabled: bool = True
    scheduler_run_time: str = "09:00"
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str = "JobPilot <no-reply@jobpilot.local>"
    # Where people open JobPilot (used for links in e-mails), e.g. https://<user>.github.io/Job_portal
    public_app_url: str | None = None
    # Extension server-identity proof (POST /extension/prove). The proof names the host it is for, so a server address
    # published by someone else cannot relay the challenge here and pass it on. When set, only these public API hosts
    # (e.g. "your-name.ngrok-free.dev") are ever signed; otherwise the Host the request arrived on is signed.
    extension_api_hosts: list[str] = Field(default_factory=list)
    # Answer the old host-less proof (extension 2.2.0 and earlier). Off: that proof can be relayed (see SECURITY.md).
    extension_prove_legacy: bool = False
    # Portal account linking (Settings -> Portal Connections). A provider is offered only when its client id, secret and
    # an exact registered redirect URI are all set. The redirect URI defaults to <PUBLIC_APP_URL>/oauth-callback.html.
    linkedin_client_id: str | None = None
    linkedin_client_secret: str | None = None
    linkedin_redirect_uri: str | None = None
    linkedin_pkce: bool = False          # LinkedIn's discovery document doesn't advertise PKCE for web apps
    linkedin_require_nonce: bool = False  # LinkedIn's discovery document doesn't list a nonce claim; a nonce present is always checked
    indeed_client_id: str | None = None
    indeed_client_secret: str | None = None
    indeed_redirect_uri: str | None = None
    indeed_scopes: str = "email offline_access"
    # Local simulated providers only (tests and demos): {"linkedin": {"authorize": ..., "token": ..., ...}}. Refused in production.
    oauth_dev_endpoints: dict = Field(default_factory=dict)

    @field_validator("oauth_dev_endpoints", mode="before")
    @classmethod
    def _dev_endpoints(cls, v):
        if isinstance(v, str):
            import json
            return json.loads(v) if v.strip() else {}
        return v or {}

    @field_validator("extension_api_hosts", mode="before")
    @classmethod
    def _split_hosts(cls, v):
        if isinstance(v, str):
            return [h.strip().lower() for h in v.split(",") if h.strip()]
        return [str(h).strip().lower() for h in (v or [])]

    @field_validator("trusted_proxy_cidrs", mode="before")
    @classmethod
    def _split_cidrs(cls, v):
        if isinstance(v, str):
            return [c.strip() for c in v.split(",") if c.strip()]
        return v

    @field_validator("docs_mode")
    @classmethod
    def _docs_mode(cls, v: str) -> str:
        if v not in {"public", "local", "off"}:
            raise ValueError("DOCS_MODE must be public, local or off")
        return v

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split(cls, v):
        if isinstance(v, str):
            return [o.strip().rstrip("/") for o in v.split(",") if o.strip()]
        return v

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def users_dir(self) -> Path:
        return self.storage_dir / "users"

    def user_dir(self, user_id: int, *parts: str) -> Path:
        # user_id is always an integer from the database, never client input.
        base = self.users_dir / str(int(user_id))
        return base.joinpath(*parts) if parts else base

    @property
    def adzuna_enabled(self) -> bool:
        return bool(self.adzuna_app_id and self.adzuna_app_key)


def _env(name: str, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


@lru_cache
def get_settings() -> BackendSettings:
    jwt_secret = _env("JWT_SECRET")
    environment = _env("ENVIRONMENT", "development")
    if not jwt_secret:
        if environment == "production":
            raise RuntimeError("JWT_SECRET must be set in production (at least 32 characters).")
        jwt_secret = secrets.token_urlsafe(48)  # dev only: tokens reset on restart
    data = {
        "environment": environment,
        "database_url": _env("DATABASE_URL", "sqlite:///" + str(PROJECT_ROOT / "storage" / "jobpilot-dev.db")),
        "storage_dir": Path(_env("STORAGE_DIR", str(PROJECT_ROOT / "storage"))),
        "jwt_secret": jwt_secret,
        "access_token_minutes": int(_env("ACCESS_TOKEN_MINUTES", 15)),
        "refresh_token_days": int(_env("REFRESH_TOKEN_DAYS", 14)),
        "encryption_key": _env("ENCRYPTION_KEY"),
        "encryption_key_previous": _env("ENCRYPTION_KEY_PREVIOUS"),
        "cors_origins": _env("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000"),
        "registration_invite_code": _env("REGISTRATION_INVITE_CODE"),
        "trust_proxy_headers": _env("TRUST_PROXY_HEADERS", "true").lower() == "true",
        "trusted_proxy_cidrs": _env("TRUSTED_PROXY_CIDRS", "127.0.0.0/8,::1/128,172.16.0.0/12"),
        "docs_mode": _env("DOCS_MODE", "local" if environment == "production" else "public"),
        "login_failures_per_account": int(_env("LOGIN_FAILURES_PER_ACCOUNT", 10)),
        "login_failure_window_minutes": int(_env("LOGIN_FAILURE_WINDOW_MINUTES", 15)),
        "max_upload_mb": int(_env("MAX_UPLOAD_MB", 5)),
        "auth_rate_limit_per_minute": int(_env("AUTH_RATE_LIMIT_PER_MINUTE", 10)),
        "timezone": _env("TZ_NAME", "Asia/Kolkata"),
        "llm_provider": _env("LLM_PROVIDER", "rule_based"),
        "llm_model": _env("LLM_MODEL", "claude-opus-5"),
        "llm_effort": _env("LLM_EFFORT", "medium"),
        "llm_base_url": _env("LLM_BASE_URL"),
        "llm_api_key_env": _env("LLM_API_KEY_ENV", "ANTHROPIC_API_KEY"),
        "adzuna_app_id": _env("ADZUNA_APP_ID"),
        "adzuna_app_key": _env("ADZUNA_APP_KEY"),
        "adzuna_country": _env("ADZUNA_COUNTRY", "in"),
        "scheduler_enabled": _env("SCHEDULER_ENABLED", "true").lower() == "true",
        "scheduler_run_time": _env("SCHEDULER_RUN_TIME", "09:00"),
        "extension_api_hosts": _env("EXTENSION_API_HOSTS", ""),
        "extension_prove_legacy": _env("EXTENSION_PROVE_LEGACY", "false").lower() == "true",
        "public_app_url": _env("PUBLIC_APP_URL"),
        "linkedin_client_id": _env("LINKEDIN_CLIENT_ID"),
        "linkedin_client_secret": _env("LINKEDIN_CLIENT_SECRET"),
        "linkedin_redirect_uri": _env("LINKEDIN_REDIRECT_URI"),
        "linkedin_pkce": _env("LINKEDIN_PKCE", "false").lower() == "true",
        "linkedin_require_nonce": _env("LINKEDIN_REQUIRE_NONCE", "false").lower() == "true",
        "indeed_client_id": _env("INDEED_CLIENT_ID"),
        "indeed_client_secret": _env("INDEED_CLIENT_SECRET"),
        "indeed_redirect_uri": _env("INDEED_REDIRECT_URI"),
        "indeed_scopes": _env("INDEED_SCOPES", "email offline_access"),
        "oauth_dev_endpoints": _env("OAUTH_DEV_ENDPOINTS", ""),
    }
    return BackendSettings.model_validate(data)
