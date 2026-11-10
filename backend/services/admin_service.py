"""backend/services/admin_service.py

Admin operations: user management, invite codes, system telemetry, and audit logging.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (
    Application,
    AuditLog,
    Interview,
    Invite,
    Job,
    Offer,
    SourceConnector,
    User,
    UserJob,
)
from backend.schemas.admin import AdminUserOut, AuditLogEntry, InviteOut, SystemMetrics


def list_users(db: Session, limit: int = 50, offset: int = 0) -> list[AdminUserOut]:
    """List all registered users with activity metrics."""
    users = db.execute(select(User).order_by(User.id.desc()).limit(limit).offset(offset)).scalars().all()
    results: list[AdminUserOut] = []
    for u in users:
        apps_count = db.scalar(select(func.count(Application.id)).where(Application.user_id == u.id)) or 0
        jobs_count = db.scalar(select(func.count(UserJob.id)).where(UserJob.user_id == u.id)) or 0
        results.append(
            AdminUserOut(
                id=u.id,
                email=u.email,
                full_name=u.full_name or "",
                is_active=u.is_active,
                role=getattr(u, "role", "user") or "user",
                created_at=u.created_at,
                last_login_at=getattr(u, "last_login_at", None),
                applications_count=apps_count,
                jobs_count=jobs_count,
            )
        )
    return results


def set_user_active(db: Session, user_id: int, is_active: bool, actor: User, ip: str | None) -> User:
    """Activate or deactivate a user account."""
    if user_id == actor.id and not is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admins cannot deactivate their own account.")
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    u.is_active = is_active
    record_audit(db, actor.id, "USER_STATUS_CHANGE", "User", str(u.id), ip, {"is_active": is_active})
    db.commit()
    db.refresh(u)
    return u


def set_user_role(db: Session, user_id: int, role: str, actor: User, ip: str | None) -> User:
    """Change a user's role (user | admin)."""
    if user_id == actor.id and role != "admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Admins cannot demote their own account.")
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found.")
    u.role = role
    record_audit(db, actor.id, "USER_ROLE_CHANGE", "User", str(u.id), ip, {"role": role})
    db.commit()
    db.refresh(u)
    return u


def generate_invite(
    db: Session,
    email: str | None,
    role: str,
    max_uses: int,
    expires_days: int,
    actor: User,
    ip: str | None,
) -> InviteOut:
    """Generate a single-use or multi-use registration invite code."""
    raw_code = f"JP-{secrets.token_hex(4).upper()}"
    token_hash = hashlib.sha256(raw_code.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

    inv = Invite(
        token_hash=token_hash,
        email=email.strip().lower() if email else None,
        role=role,
        max_uses=max_uses,
        used_count=0,
        expires_at=expires_at,
        created_by_id=actor.id,
    )
    db.add(inv)
    record_audit(db, actor.id, "INVITE_GENERATED", "Invite", None, ip, {"email": email, "role": role, "max_uses": max_uses})
    db.commit()
    db.refresh(inv)

    return InviteOut(
        id=inv.id,
        code=raw_code,
        email=inv.email,
        role=inv.role,
        max_uses=inv.max_uses,
        used_count=inv.used_count,
        expires_at=inv.expires_at,
        created_at=inv.created_at,
    )


def list_invites(db: Session) -> list[InviteOut]:
    """List active and historical invites."""
    rows = db.execute(select(Invite).order_by(Invite.id.desc()).limit(100)).scalars().all()
    return [
        InviteOut(
            id=r.id,
            code="[REDACTED]",
            email=r.email,
            role=r.role,
            max_uses=r.max_uses,
            used_count=r.used_count,
            expires_at=r.expires_at or datetime.now(timezone.utc),
            created_at=r.created_at,
        )
        for r in rows
    ]


def revoke_invite(db: Session, invite_id: int, actor: User, ip: str | None) -> None:
    """Revoke an unused or active invite."""
    inv = db.get(Invite, invite_id)
    if not inv:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invite not found.")
    inv.revoked_at = datetime.now(timezone.utc)
    record_audit(db, actor.id, "INVITE_REVOKED", "Invite", str(inv.id), ip, {})
    db.commit()


def system_metrics(db: Session) -> SystemMetrics:
    """Calculate platform-wide usage metrics."""
    total_users = db.scalar(select(func.count(User.id))) or 0
    active_users = db.scalar(select(func.count(User.id)).where(User.is_active.is_(True))) or 0
    total_jobs = db.scalar(select(func.count(Job.id))) or 0
    total_apps = db.scalar(select(func.count(Application.id))) or 0
    total_interviews = db.scalar(select(func.count(Interview.id))) or 0
    total_offers = db.scalar(select(func.count(Offer.id))) or 0
    active_sources = db.scalar(select(func.count(SourceConnector.id)).where(SourceConnector.enabled.is_(True))) or 0

    return SystemMetrics(
        total_users=total_users,
        active_users=active_users,
        total_jobs=total_jobs,
        total_applications=total_apps,
        total_interviews=total_interviews,
        total_offers=total_offers,
        active_sources=active_sources,
        server_time=datetime.now(timezone.utc),
    )


def audit_logs(db: Session, limit: int = 50, offset: int = 0) -> list[AuditLogEntry]:
    """Retrieve security audit log entries."""
    rows = db.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset)).scalars().all()
    return [
        AuditLogEntry(
            id=r.id,
            actor_id=r.actor_id,
            action=r.action,
            target_type=r.target_type,
            target_id=r.target_id,
            ip=r.ip,
            details=r.details or {},
            created_at=r.created_at,
        )
        for r in rows
    ]


def record_audit(
    db: Session,
    actor_id: int | None,
    action: str,
    target_type: str | None,
    target_id: str | None,
    ip: str | None,
    details: dict[str, Any] | None = None,
) -> None:
    """Append a security event to the audit log."""
    log_entry = AuditLog(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id else None,
        ip=ip,
        details=details or {},
    )
    db.add(log_entry)
