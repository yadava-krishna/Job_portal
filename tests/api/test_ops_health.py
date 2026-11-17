"""Admin console operational health (GET /admin/ops-health): admin only, degrades to "not available", never leaks
secrets or individual users' data."""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from api_helpers import auth, register

API = "/api/v1"


def _admin(client, email="health-admin@example.com"):
    from backend.db import session_factory
    from backend.models import User

    h = auth(register(client, email))
    with session_factory()() as db:
        db.execute(update(User).where(User.email == email).values(role="admin"))
        db.commit()
    return h


def test_ops_health_is_admin_only(client):
    h = auth(register(client, "not-admin@example.com"))
    assert client.get(f"{API}/admin/ops-health", headers=h).status_code == 403
    assert client.get(f"{API}/admin/ops-health").status_code in (401, 403)


def test_ops_health_reports_backups_failures_and_sources(client, tmp_path, monkeypatch):
    from backend.db import session_factory
    from backend.models import DiscoveryRun, JobRun, JobSource, RunError, User
    from backend.services import ops_health_service

    backups = tmp_path / "backups"
    old = backups / "daily-20261101T023000Z"
    old.mkdir(parents=True)
    (old / "jobpilot.dump").write_bytes(b"x" * 2048)
    (backups / "manual-20261031T090000Z").mkdir()
    stamp = time.time() - 30 * 3600
    os.utime(old, (stamp, stamp))
    os.utime(backups / "manual-20261031T090000Z", (stamp - 3600, stamp - 3600))
    monkeypatch.setattr(ops_health_service, "BACKUP_DIR", backups)

    a = _admin(client)
    now = datetime.now(timezone.utc)
    with session_factory()() as db:
        uid = db.query(User.id).filter(User.email == "health-admin@example.com").scalar()
        db.add(JobRun(name="job_matching", status="failed", started_at=now - timedelta(hours=3), finished_at=now,
                      error="OperationalError: could not connect to postgresql://jobpilot:hunter2@postgres/jobpilot "
                            "for owner@example.com app_key=abc123"))
        db.add(JobRun(name="report_generation", status="ok", started_at=now - timedelta(hours=1)))
        db.add(JobSource(key="lever", kind="ats", name="Lever", health="degraded", last_run_at=now - timedelta(hours=1),
                         last_ok_at=now - timedelta(days=4), last_error="HTTP 503 from https://api.lever.co?token=zzz"))
        db.add(DiscoveryRun(user_id=uid, trigger="scheduled", status="failed", started_at=now - timedelta(hours=2),
                            error_details=[{"type": "INTERRUPTED", "message": "restart"}],
                            source_results={"lever": {"label": "Lever", "status": "failed", "message": "HTTP 503"},
                                            "greenhouse": {"label": "Greenhouse", "status": "ok", "found": 3}}))
        db.add(RunError(user_id=uid, error_type="BOARD_FETCH", platform="lever", description="private detail", recovery_status="skipped"))
        db.commit()

    r = client.get(f"{API}/admin/ops-health", headers=a)
    assert r.status_code == 200, r.text
    d = r.json()
    for key in ("disks", "database", "backups", "background_jobs", "discovery", "workflows", "sources", "source_freshness",
                "user_activity", "extension", "attention"):
        assert key in d, key

    # Disks: the data folder exists in tests; the backups folder is the patched one.
    assert d["disks"][0]["available"] is True and d["disks"][0]["level"] in ("ok", "warning", "high", "critical")
    assert d["disks"][1]["available"] is True
    # Database: SQLite in tests, so no table sizes but no error either.
    assert d["database"]["available"] is True and d["database"]["dialect"] in ("sqlite", "postgresql")
    # Backups: two folders, newest 30 hours old -> warning.
    b = d["backups"]
    assert b["available"] and b["count"] == 2 and b["daily_count"] == 1
    assert b["newest"]["name"] == "daily-20261101T023000Z" and b["newest"]["size_bytes"] == 2048
    assert b["newest"]["age_hours"] > 26 and b["level"] == "warning"
    assert any("backup" in x["text"].lower() for x in d["attention"])
    # Failed background jobs, scrubbed.
    jobs = d["background_jobs"]
    assert jobs["failed_count"] == 1 and jobs["by_name"][0]["name"] == "job_matching"
    err = jobs["recent"][0]["error"]
    assert "hunter2" not in err and "abc123" not in err and "owner@example.com" not in err and "[redacted]" in err
    # Discovery and workflow failures are counts only.
    assert d["discovery"]["failed"] == 1 and d["discovery"]["failure_types"][0]["type"] == "INTERRUPTED"
    assert d["workflows"]["run_errors"] == [{"type": "BOARD_FETCH", "platform": "lever", "count": 1}]
    assert "private detail" not in r.text
    # Sources: Lever failing (no success for 4 days, a failure this week); Greenhouse ok from the run.
    src = {s["key"]: s for s in d["sources"]}
    assert src["lever"]["state"] == "failing" and src["lever"]["failures_7d"] == 1 and "zzz" not in (src["lever"]["last_error"] or "")
    assert src["greenhouse"]["state"] == "ok" and src["greenhouse"]["last_success_at"]
    # Activity is aggregate only.
    assert d["user_activity"]["accounts"] >= 1 and "email" not in str(d["user_activity"])
    assert d["extension"]["connected_devices"] == 0 and d["extension"]["version_reporting"] is False
    # Never secrets from the environment.
    assert "test-secret-" not in r.text


def test_ops_health_degrades_when_paths_are_missing(client, tmp_path, monkeypatch):
    from backend.services import ops_health_service

    monkeypatch.setattr(ops_health_service, "BACKUP_DIR", tmp_path / "not-mounted")
    a = _admin(client, "health-admin2@example.com")
    d = client.get(f"{API}/admin/ops-health", headers=a).json()
    assert d["backups"]["available"] is False and "not available" in d["backups"]["note"].lower()
    assert d["disks"][1]["available"] is False and "not available" in d["disks"][1]["note"].lower()


def test_ops_health_empty_backup_folder_is_critical(client, tmp_path, monkeypatch):
    from backend.services import ops_health_service

    (tmp_path / "b").mkdir()
    monkeypatch.setattr(ops_health_service, "BACKUP_DIR", tmp_path / "b")
    a = _admin(client, "health-admin3@example.com")
    d = client.get(f"{API}/admin/ops-health", headers=a).json()
    assert d["backups"]["count"] == 0 and d["backups"]["level"] == "critical"


def test_scrub_removes_credentials_and_emails():
    from backend.services.ops_health_service import scrub

    s = scrub("GET https://x/api?app_id=1&app_key=SECRET Bearer abc.def postgresql://u:p@h/db a.b@c.io")
    assert "SECRET" not in s and "abc.def" not in s and "u:p@" not in s and "a.b@c.io" not in s
    assert scrub(None) is None and scrub("x" * 400).endswith("…")
