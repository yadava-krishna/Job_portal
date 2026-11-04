from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from backend.api.deps import CurrentUser, DbSession, SettingsDep, auth_rate_limit
from backend.schemas.auth import AuthConfig, AuthResponse, LoginRequest, RefreshRequest, RegisterRequest, UserOut
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
    user = auth_service.authenticate(db, req)
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
