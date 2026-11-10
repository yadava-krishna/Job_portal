from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.api.deps import CurrentUser, DbSession, SettingsDep, auth_rate_limit, check_account_lock, login_failure_key
from backend.schemas.auth import (
    AuthConfig,
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UserOut,
)
from sqlalchemy import select

from backend.models import User
from backend.security import rate_limiter
from backend.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
PASSWORD_RULES = ["At least 10 characters", "Upper- and lower-case letters", "At least one number", "Not a common password"]


@router.get("/config", response_model=AuthConfig)
def auth_config(settings: SettingsDep) -> AuthConfig:
    return AuthConfig(registration_requires_invite=bool(settings.registration_invite_code), password_rules=PASSWORD_RULES)


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(auth_rate_limit)])
def register(req: RegisterRequest, request: Request, db: DbSession, settings: SettingsDep) -> AuthResponse:
    user = auth_service.register(db, settings, req)
    return auth_service.issue_tokens(db, settings, user, request.headers.get("user-agent"))


@router.post("/login", response_model=AuthResponse, dependencies=[Depends(auth_rate_limit)])
def login(req: LoginRequest, request: Request, db: DbSession, settings: SettingsDep) -> AuthResponse:
    check_account_lock(req.email, settings)
    try:
        user = auth_service.authenticate(db, req)
    except HTTPException as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            rate_limiter.record(login_failure_key(req.email))
        raise
    rate_limiter.clear(login_failure_key(req.email))
    return auth_service.issue_tokens(db, settings, user, request.headers.get("user-agent"))


@router.post("/refresh", response_model=AuthResponse, dependencies=[Depends(auth_rate_limit)])
def refresh(req: RefreshRequest, request: Request, db: DbSession, settings: SettingsDep) -> AuthResponse:
    return auth_service.rotate_refresh(db, settings, req.refresh_token, request.headers.get("user-agent"))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(user: CurrentUser, db: DbSession, req: RefreshRequest | None = None) -> None:
    auth_service.logout(db, req.refresh_token if req else None, user)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/forgot-password", dependencies=[Depends(auth_rate_limit)])
def forgot_password(body: ForgotPasswordRequest, db: DbSession, settings: SettingsDep) -> dict:
    """E-mail a single-use reset link. Says honestly when e-mail is not set up on this server."""
    from backend.services import email_service

    if not email_service.is_smtp_configured() and email_service.test_outbox is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "Password reset by e-mail is not set up on this server. Ask the JobPilot owner to reset your password.")
    user = db.execute(select(User).where(User.email == body.email.strip().lower())).scalar_one_or_none()
    if user is not None and user.is_active:  # same response either way, so this can't be used to find accounts
        token = auth_service.create_reset_token(settings, user)
        base = (settings.public_app_url or "").rstrip("/")
        reset_link = f"{base}/#/reset-password?token={token}"
        html = f"""<p>You asked to reset your JobPilot password.</p>
<p><a href="{reset_link}">Set a new password</a>. The link works once and expires in 1 hour.</p>
<p>If you did not ask for this, ignore this e-mail; your password has not changed.</p>"""
        email_service.send_email(user.email, "JobPilot: reset your password", html, f"Reset link (valid 1 hour, single use): {reset_link}")
    return {"message": "If an account exists for that e-mail address, a reset link has been sent."}


@router.post("/reset-password", dependencies=[Depends(auth_rate_limit)])
def reset_password(body: ResetPasswordRequest, db: DbSession, settings: SettingsDep) -> dict:
    """Apply a new password using a verified reset token."""
    auth_service.reset_password(db, settings, body.token, body.new_password)
    return {"message": "Password updated successfully. You may now log in."}

