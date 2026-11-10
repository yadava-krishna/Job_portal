"""backend/api/routes/admin.py

Endpoints for system administration, access management, invites, metrics, and audit log.
All routes require the CurrentAdmin dependency (role == 'admin').
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request, status

from backend.api.deps import CurrentAdmin, DbSession, SettingsDep, client_ip
from backend.schemas.admin import (
    AdminUserOut,
    AuditLogEntry,
    InviteCreate,
    InviteOut,
    SystemMetrics,
    UserRoleUpdate,
    UserStatusUpdate,
)
from backend.schemas.discovery import SourceConnectorOut
from backend.services import admin_service
from backend.services.connectors import registry

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserOut])
def get_users(
    admin: CurrentAdmin,
    db: DbSession,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[AdminUserOut]:
    """List all registered users with usage stats."""
    return admin_service.list_users(db, limit=limit, offset=offset)


@router.put("/users/{user_id}/status", response_model=dict)
def update_user_status(
    user_id: int,
    body: UserStatusUpdate,
    admin: CurrentAdmin,
    db: DbSession,
    request: Request,
    settings: SettingsDep,
) -> dict:
    """Activate or deactivate a user."""
    ip = client_ip(request, settings)
    u = admin_service.set_user_active(db, user_id, body.is_active, actor=admin, ip=ip)
    return {"id": u.id, "email": u.email, "is_active": u.is_active}


@router.put("/users/{user_id}/role", response_model=dict)
def update_user_role(
    user_id: int,
    body: UserRoleUpdate,
    admin: CurrentAdmin,
    db: DbSession,
    request: Request,
    settings: SettingsDep,
) -> dict:
    """Promote or demote a user role."""
    ip = client_ip(request, settings)
    u = admin_service.set_user_role(db, user_id, body.role, actor=admin, ip=ip)
    return {"id": u.id, "email": u.email, "role": u.role}


@router.get("/invites", response_model=list[InviteOut])
def get_invites(admin: CurrentAdmin, db: DbSession) -> list[InviteOut]:
    """List created invite codes."""
    return admin_service.list_invites(db)


@router.post("/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def create_invite(
    body: InviteCreate,
    admin: CurrentAdmin,
    db: DbSession,
    request: Request,
    settings: SettingsDep,
) -> InviteOut:
    """Generate a registration invite code."""
    ip = client_ip(request, settings)
    return admin_service.generate_invite(
        db,
        email=body.email,
        role=body.role,
        max_uses=body.max_uses,
        expires_days=body.expires_days,
        actor=admin,
        ip=ip,
    )


@router.delete("/invites/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invite(
    invite_id: int,
    admin: CurrentAdmin,
    db: DbSession,
    request: Request,
    settings: SettingsDep,
) -> None:
    """Revoke an invite code."""
    ip = client_ip(request, settings)
    admin_service.revoke_invite(db, invite_id, actor=admin, ip=ip)


@router.get("/metrics", response_model=SystemMetrics)
def get_metrics(admin: CurrentAdmin, db: DbSession) -> SystemMetrics:
    """Retrieve platform aggregate usage metrics."""
    return admin_service.system_metrics(db)


@router.get("/audit-log", response_model=list[AuditLogEntry])
def get_audit_log(
    admin: CurrentAdmin,
    db: DbSession,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> list[AuditLogEntry]:
    """Paginated security audit log."""
    return admin_service.audit_logs(db, limit=limit, offset=offset)


@router.get("/sources", response_model=list[SourceConnectorOut])
def get_admin_sources(admin: CurrentAdmin) -> list[SourceConnectorOut]:
    """View all registered discovery connectors and telemetry."""
    out = []
    for c in registry.list_all():
        pol = c.policy
        h = c.get_source_health()
        out.append(
            SourceConnectorOut(
                source_id=c.source_id,
                name=c.name,
                domain=c.domain,
                category=c.category.value,
                access_method=c.access_method.value,
                permission_status=pol.permission_status.value if pol else "unknown",
                is_discoverable=pol.is_discoverable if pol else False,
                status=h.status,
                rate_limit_rpm=pol.rate_limit_rpm if pol else 10,
                last_success_at=h.last_success_at,
                last_error=h.last_error,
                jobs_discovered=h.jobs_discovered,
            )
        )
    return out
