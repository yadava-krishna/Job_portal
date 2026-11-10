"""Tests for Phase 5: Admin dashboard, user management, invites, metrics and RBAC."""

from __future__ import annotations

from api_helpers import auth, register


def test_admin_rbac_and_endpoints(client):
    # 1. Register normal user
    user_tokens = register(client, "normal@example.com")
    u_h = auth(user_tokens)

    # Normal user is blocked from admin endpoints
    r = client.get("/api/v1/admin/users", headers=u_h)
    assert r.status_code == 403, r.text

    # 2. Register admin user and set role in DB
    admin_tokens = register(client, "admin@example.com")
    from backend.db import session_factory
    from backend.models import User

    with session_factory()() as db:
        admin_user = db.query(User).filter(User.email == "admin@example.com").one()
        admin_user.role = "admin"
        db.commit()

    a_h = auth(admin_tokens)

    # Admin access allowed
    r = client.get("/api/v1/admin/users", headers=a_h)
    assert r.status_code == 200, r.text
    users = r.json()
    assert len(users) >= 2

    # System metrics
    m = client.get("/api/v1/admin/metrics", headers=a_h).json()
    assert m["total_users"] >= 2

    # Invite lifecycle
    inv = client.post("/api/v1/admin/invites", headers=a_h, json={"role": "user", "max_uses": 2, "expires_days": 14}).json()
    assert inv["code"].startswith("JP-")
    assert inv["max_uses"] == 2

    invs = client.get("/api/v1/admin/invites", headers=a_h).json()
    assert len(invs) >= 1

    # Revoke invite
    client.delete(f"/api/v1/admin/invites/{inv['id']}", headers=a_h)

    # Audit log
    logs = client.get("/api/v1/admin/audit-log", headers=a_h).json()
    assert any(l["action"] == "INVITE_GENERATED" for l in logs)
