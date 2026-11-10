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


# ---------------- operations: background jobs, product analytics, backups, disk ----------------

@router.get("/jobs")
def admin_jobs(admin: CurrentAdmin, db: DbSession) -> list[dict[str, Any]]:
    """Every named background job with its schedule, last status and last error."""
    from backend.services import jobs_registry

    return jobs_registry.overview(db)


@router.post("/jobs/{name}/run")
def admin_run_job(name: str, admin: CurrentAdmin, db: DbSession, settings: SettingsDep, request: Request) -> dict[str, Any]:
    """Controlled replay: run one job now (guarded against concurrent runs) and return the recorded result."""
    from fastapi import HTTPException

    from backend.services import jobs_registry

    if name not in jobs_registry.REGISTRY:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown job")
    admin_service.record_audit(db, admin.id, "JOB_REPLAYED", "job", name, client_ip(request, settings), {})
    db.commit()
    row = jobs_registry.run(name, settings, trigger="replay")
    return {"id": row.id, "name": row.name, "status": row.status, "attempts": row.attempts, "details": row.details, "error": row.error}


@router.get("/product-metrics")
def admin_product_metrics(admin: CurrentAdmin, db: DbSession, days: int = Query(30, ge=1, le=365)) -> dict[str, Any]:
    """The 16 PRD events and north-star metrics, aggregated (no individual candidate data)."""
    from datetime import timedelta

    from sqlalchemy import func, select

    from backend.models import AICall, AnalyticsEvent, Application, Gap, Interview, Reflection, User, utcnow
    from backend.services import platform_service

    since = utcnow() - timedelta(days=days)
    apps = db.execute(select(Application).where(Application.status == "SUBMITTED", Application.submitted_at >= since)).unique().scalars().all()
    with_iv = sum(1 for a in apps if a.stage in ("interview", "offer") or db.execute(select(Interview.id).where(Interview.application_id == a.id)).first())
    offers = sum(1 for a in apps if a.stage == "offer")
    weekly = db.execute(select(func.count(func.distinct(AnalyticsEvent.user_id))).where(AnalyticsEvent.created_at >= utcnow() - timedelta(days=7))).scalar() or 0
    candidates = db.execute(select(func.count()).select_from(User).where(User.role == "user", User.is_active.is_(True))).scalar() or 0
    onboarded = db.execute(select(func.count()).select_from(User).where(User.onboarding_completed_at.is_not(None))).scalar() or 0
    reused = sum(1 for a in apps if a.resume_version_id)
    closed = db.execute(select(func.count()).select_from(Gap).where(Gap.status == "closed")).scalar() or 0
    gaps = db.execute(select(func.count()).select_from(Gap)).scalar() or 0
    refl = db.execute(select(func.count()).select_from(Reflection).where(Reflection.created_at >= since)).scalar() or 0
    ai = db.execute(select(AICall.purpose, func.count(), func.coalesce(func.sum(AICall.cost_usd), 0)).where(AICall.created_at >= since)
                    .group_by(AICall.purpose)).all()
    pct = lambda a, b: round(100 * a / b, 1) if b else None  # noqa: E731
    return {
        "days": days, "events": platform_service.event_counts(db, days),
        "north_star": {"applications_submitted": len(apps), "application_to_interview_pct": pct(with_iv, len(apps)),
                       "interview_to_offer_pct": pct(offers, with_iv), "offers": offers, "gap_closure_pct": pct(closed, gaps),
                       "resume_reuse_pct": pct(reused, len(apps)), "weekly_active_candidates": weekly,
                       "reflections_completed": refl, "onboarding_activation_pct": pct(onboarded, candidates)},
        "ai_costs": [{"purpose": p, "calls": n, "cost_usd": float(c)} for p, n, c in ai],
        "feedback": platform_service.feedback_summary(db),
        "note": "Raw application count is not a success measure on its own; look at conversions and outcomes.",
    }


@router.get("/system")
def admin_system(admin: CurrentAdmin, settings: SettingsDep) -> dict[str, Any]:
    """Disk usage (warnings at 70/80/90%) and the last backup's status, as written by the backup service."""
    import json
    import shutil
    from pathlib import Path

    root = settings.storage_dir if settings.storage_dir.exists() else Path("/")
    u = shutil.disk_usage(root)
    used = round(100 * u.used / u.total, 1)
    level = "critical" if used >= 90 else "high" if used >= 80 else "warning" if used >= 70 else "ok"
    backup = None
    p = Path("/backups/last_backup.json")
    if p.is_file():
        try:
            backup = json.loads(p.read_text())
        except ValueError:
            backup = {"status": "unreadable"}
    return {"disk": {"used_percent": used, "free_gb": round(u.free / 1e9, 1), "level": level},
            "backup": backup or {"status": "unknown", "note": "No backup status file. Start the backup service (docker compose up -d backup)."}}
