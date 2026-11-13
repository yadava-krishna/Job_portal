"""backend/schemas/admin.py

Schemas for administrator operations, user lifecycle, invites, and telemetry.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class AdminUserOut(BaseModel):
    id: int
    email: str
    full_name: str
    is_active: bool
    role: str
    created_at: datetime
    last_login_at: datetime | None = None
    applications_count: int = 0
    jobs_count: int = 0


class UserStatusUpdate(BaseModel):
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: Literal["user", "mentor", "admin"]


class InviteCreate(BaseModel):
    email: str | None = Field(default=None, max_length=320)
    role: Literal["user", "mentor", "admin"] = "user"
    max_uses: int = Field(default=1, ge=1, le=100)
    expires_days: int = Field(default=7, ge=1, le=90)


class InviteOut(BaseModel):
    id: int
    code: str
    email: str | None
    role: str
    max_uses: int
    used_count: int
    expires_at: datetime
    created_at: datetime


class SystemMetrics(BaseModel):
    total_users: int
    active_users: int
    total_jobs: int
    total_applications: int
    total_interviews: int
    total_offers: int
    active_sources: int
    server_time: datetime


class AuditLogEntry(BaseModel):
    id: int
    actor_id: int | None
    action: str
    target_type: str | None
    target_id: str | None  # a user id, an invite id or a background job's name ("gap_generation")
    ip: str | None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
