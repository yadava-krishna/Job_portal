"""Named background jobs, admin operations views, health alias, stage-move rules (JOB-*, ADM-*, DEP-05)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api_helpers import auth, import_job, onboard, register

API = "/api/v1"


def _admin(client, email="ops-admin@example.com"):
    from backend.db import session_factory
    from backend.models import User

    h = auth(register(client, email))
    with session_factory()() as db:
        db.query(User).filter(User.email == email).one().role = "admin"
        db.commit()
    return h


def test_all_fifteen_named_jobs_are_registered():
    from backend.services import jobs_registry

    assert set(jobs_registry.REGISTRY) == {
        "daily_discovery", "source_refresh", "job_normalisation", "job_deduplication", "job_matching", "gap_generation",
        "resume_feedback_generation", "resource_refresh", "notification_dispatch", "alert_email_ingestion", "report_generation",
        "visa_source_check", "visa_change_detection", "analytics_rollup", "cleanup_and_retention"}
    assert all(n in jobs_registry.REGISTRY for n in jobs_registry.SCHEDULES)


def test_jobs_run_record_results_and_blocked_dependencies(client, resume_bytes, monkeypatch):
    from backend.services import international_service, learning_service

    h = onboard(client, "jobs@example.com", resume_bytes)
    uj = import_job(client, h)["user_job_ids"][0]
    a = _admin(client)
    assert client.get(f"{API}/admin/jobs", headers=h).status_code == 403
    # Reminders: a due follow-up becomes one notification, and running twice doesn't duplicate it.
    app_id = client.post(f"{API}/applications/prepare", headers=h, json={"user_job_id": uj}).json()["id"]
    client.post(f"{API}/applications/{app_id}/confirm", headers=h, json={"submitted": True})
    client.put(f"{API}/applications/{app_id}/tracking", headers=h,
               json={"follow_up_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()})
    r1 = client.post(f"{API}/admin/jobs/notification_dispatch/run", headers=a).json()
    r2 = client.post(f"{API}/admin/jobs/notification_dispatch/run", headers=a).json()
    assert r1["status"] == "ok" and r1["details"]["in_app_created"] == 1 and r2["details"]["in_app_created"] == 0
    assert r1["details"]["email_channel"] == "not configured"
    # No connected mailbox: honestly blocked, not "ok".
    assert client.post(f"{API}/admin/jobs/alert_email_ingestion/run", headers=a).json()["status"] == "blocked"
    for name in ("gap_generation", "analytics_rollup", "cleanup_and_retention", "job_matching", "resume_feedback_generation"):
        assert client.post(f"{API}/admin/jobs/{name}/run", headers=a).json()["status"] == "ok", name
    monkeypatch.setattr(learning_service, "refresh_links", lambda db, limit=200: {"ok": 1, "broken": 0, "unverifiable": 0})
    monkeypatch.setattr(international_service, "check_sources", lambda db: {"checked": 0, "changed": 0, "failed": 0, "stale": 0})
    assert client.post(f"{API}/admin/jobs/resource_refresh/run", headers=a).json()["status"] == "ok"
    jobs = {j["name"]: j for j in client.get(f"{API}/admin/jobs", headers=a).json()}
    assert jobs["notification_dispatch"]["last_status"] == "ok" and jobs["alert_email_ingestion"]["last_status"] == "blocked"
    assert client.post(f"{API}/admin/jobs/nope/run", headers=a).status_code == 404


def test_product_metrics_system_and_health(client, resume_bytes):
    h = onboard(client, "pm@example.com", resume_bytes)
    a = _admin(client, "pm-admin@example.com")
    m = client.get(f"{API}/admin/product-metrics", headers=a).json()
    assert len([e for e in m["events"] if not e.endswith("_failed") and e not in ("application_aborted",)]) >= 16
    assert "application_to_interview_pct" in m["north_star"]
    assert client.get(f"{API}/admin/product-metrics", headers=h).status_code == 403
    sysinfo = client.get(f"{API}/admin/system", headers=a).json()
    assert sysinfo["disk"]["level"] in ("ok", "warning", "high", "critical") and "backup" in sysinfo
    hl = client.get("/api/health")
    assert hl.status_code == 200 and hl.json()["database"]["connected"] is True and "password" not in hl.text.lower()


def test_mentor_role_can_be_assigned_by_admin(client):
    a = _admin(client, "role-admin@example.com")
    register(client, "future-mentor@example.com")
    users = client.get(f"{API}/admin/users", headers=a).json()
    uid = next(u["id"] for u in users if u["email"] == "future-mentor@example.com")
    assert client.put(f"{API}/admin/users/{uid}/role", headers=a, json={"role": "mentor"}).status_code == 200
    assert client.put(f"{API}/admin/users/{uid}/role", headers=a, json={"role": "superuser"}).status_code == 422


def test_admin_invites_work_at_registration_and_are_consumed(client, monkeypatch):
    from backend.config import get_settings

    a = _admin(client, "inv-admin@example.com")
    monkeypatch.setattr(get_settings(), "registration_invite_code", "owner-code-for-tests-only")
    inv = client.post(f"{API}/admin/invites", headers=a, json={"role": "mentor", "max_uses": 1, "expires_days": 7}).json()
    code = inv.get("code") or inv.get("invite_code") or inv.get("raw_code")
    assert code, inv
    body = {"email": "invited@example.com", "password": "Str0ngPassw0rd", "full_name": "Invited", "invite_code": code}
    r = client.post(f"{API}/auth/register", json=body)
    assert r.status_code == 201, r.text
    assert client.get(f"{API}/auth/me", headers=auth(r.json())).json()["role"] == "mentor"
    again = client.post(f"{API}/auth/register", json={**body, "email": "second@example.com"})
    assert again.status_code == 403  # single-use invite already consumed
    assert client.post(f"{API}/auth/register", json={**body, "email": "x@example.com", "invite_code": "JP-WRONG"}).status_code == 403
    admin_inv = client.post(f"{API}/admin/invites", headers=a, json={"role": "admin", "max_uses": 1, "expires_days": 7}).json()
    code2 = admin_inv.get("code") or admin_inv.get("invite_code") or admin_inv.get("raw_code")
    r2 = client.post(f"{API}/auth/register", json={**body, "email": "noadmin@example.com", "invite_code": code2})
    assert r2.status_code == 201 and client.get(f"{API}/auth/me", headers=auth(r2.json())).json()["role"] == "user"


def test_audit_log_lists_job_runs_and_server_errors_keep_cors_headers(client, monkeypatch):
    a = _admin(client, "audit-admin@example.com")
    assert client.post(f"{API}/admin/jobs/analytics_rollup/run", headers=a).json()["status"] == "ok"
    r = client.get(f"{API}/admin/audit-log", headers=a)  # an entry whose target is a job name, not a number
    assert r.status_code == 200, r.text
    assert any(e["target_id"] == "analytics_rollup" for e in r.json())

    # An unexpected server error still carries CORS headers, so the browser shows the error instead of "blocked by CORS".
    from backend.config import get_settings
    from backend.services import jobs_registry

    origin = get_settings().cors_origins[0]
    monkeypatch.setattr(jobs_registry, "overview", lambda db: 1 / 0)
    from fastapi.testclient import TestClient

    from backend.main import create_app

    with TestClient(create_app(start_scheduler=False), raise_server_exceptions=False) as c:
        r = c.get(f"{API}/admin/jobs", headers={**a, "Origin": origin})
    assert r.status_code == 500 and r.headers.get("access-control-allow-origin") == origin
