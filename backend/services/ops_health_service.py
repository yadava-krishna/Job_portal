"""Operational health for the admin console (GET /admin/ops-health): disk space on the data and backup volumes,
database size and largest tables, backup inventory, failed background jobs and discovery runs, per-source health and
freshness, aggregate user activity and browser-extension diagnostics.

Every check degrades to {"available": false, "note": ...} instead of raising, because a path may not be mounted in the
container or a query may not exist on SQLite. Nothing here returns secrets, environment values, file contents or
anything about an individual user: activity is counts only, and error texts are scrubbed of credentials and e-mail
addresses.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from backend.config import PROJECT_ROOT, BackendSettings
from backend.models import (AnalyticsEvent, Application, DiscoveryRun, ExtensionToken, Job, JobRun, JobSource, RunError, User,
                            utcnow)

log = logging.getLogger(__name__)

BACKUP_DIR = Path("/backups")          # mounted read-only into the backend container (docker-compose.yml)
BACKUP_STALE_HOURS = 26                # the backup service runs daily; it catches up at start-up past 26 hours
SOURCE_STALE_HOURS = 48
WINDOW = timedelta(days=7)
EXTENSION_MANIFEST = PROJECT_ROOT / "extension" / "manifest.json"

_SCRUB = [
    (re.compile(r"(?i)\b(app_key|app_id|api_key|apikey|key|token|access_token|password|passwd|pwd|secret|signature)=[^&\s'\"]+"), r"\1=[redacted]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1[redacted]"),
    (re.compile(r"://[^/\s:@]+:[^@\s/]+@"), "://[redacted]@"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[email]"),
]


def scrub(value: str | None, limit: int = 300) -> str | None:
    """Error text safe to show: no credentials, connection strings or e-mail addresses."""
    if not value:
        return None
    out = value
    for pattern, repl in _SCRUB:
        out = pattern.sub(repl, out)
    return out if len(out) <= limit else out[:limit].rstrip() + "…"


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _hours_since(dt: datetime | None, now: datetime) -> float | None:
    dt = _aware(dt)
    return None if dt is None else round(max(0.0, (now - dt).total_seconds()) / 3600, 1)


def _level(used_percent: float) -> str:
    return "critical" if used_percent >= 90 else "high" if used_percent >= 80 else "warning" if used_percent >= 70 else "ok"


# ---------------- disks ----------------

def _disk(label: str, path: Path) -> dict[str, Any]:
    base = {"label": label, "path": str(path)}
    try:
        if not path.exists():
            return {**base, "available": False, "note": "Not available: this folder isn't mounted here."}
        u = shutil.disk_usage(path)
        dev = os.stat(path).st_dev
    except OSError:
        return {**base, "available": False, "note": "Not available: the backend can't read this folder."}
    used = round(100 * u.used / u.total, 1) if u.total else 0.0
    return {**base, "available": True, "total_gb": round(u.total / 1e9, 1), "used_gb": round(u.used / 1e9, 1),
            "free_gb": round(u.free / 1e9, 1), "used_percent": used, "level": _level(used), "_dev": dev}


def disks(settings: BackendSettings) -> list[dict[str, Any]]:
    out = [_disk("Data (resumes, exports, reports, logs)", settings.storage_dir), _disk("Backups", BACKUP_DIR)]
    devs = [d.get("_dev") for d in out]
    if devs[0] is not None and devs[0] == devs[1]:
        out[1]["note"] = "Same disk as the data folder: a disk failure would lose both. Keep an off-machine copy."
    for d in out:
        d.pop("_dev", None)
    return out


# ---------------- database ----------------

def database(db: Session) -> dict[str, Any]:
    dialect = db.get_bind().dialect.name
    out: dict[str, Any] = {"available": True, "dialect": dialect}
    try:
        t0 = time.perf_counter()
        db.execute(text("SELECT 1"))
        out["latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    except Exception:  # noqa: BLE001  report, never raise
        db.rollback()
        return {"available": False, "dialect": dialect, "note": "Not available: the database did not answer."}
    try:
        out["migration"] = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception:  # noqa: BLE001  e.g. a test database created without Alembic
        db.rollback()
        out["migration"] = None
    if dialect == "postgresql":
        try:
            out["size_bytes"] = int(db.execute(text("SELECT pg_database_size(current_database())")).scalar() or 0)
            out["connections"] = int(db.execute(text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")).scalar() or 0)
            out["server_version"] = db.execute(text("SHOW server_version")).scalar()
            rows = db.execute(text(
                "SELECT c.relname, pg_total_relation_size(c.oid) AS bytes, GREATEST(c.reltuples, 0)::bigint AS est_rows "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relkind = 'r' AND n.nspname = current_schema() ORDER BY bytes DESC LIMIT 8")).all()
            out["largest_tables"] = [{"table": r[0], "bytes": int(r[1]), "rows_estimate": int(r[2])} for r in rows]
        except Exception:  # noqa: BLE001  e.g. missing privileges on pg_stat_activity
            db.rollback()
            out.setdefault("note", "Some database statistics are not available.")
    elif dialect == "sqlite":
        path = db.get_bind().url.database
        try:
            out["size_bytes"] = os.path.getsize(path) if path and path != ":memory:" else None
        except OSError:
            out["size_bytes"] = None
        out["largest_tables"] = []
        out["note"] = "Development database (SQLite): table sizes are not available."
    return out


# ---------------- backups ----------------

def _folder_size(path: str) -> int:
    total = 0
    with os.scandir(path) as it:
        for e in it:
            if e.is_file(follow_symlinks=False):
                total += e.stat(follow_symlinks=False).st_size
    return total


def backups(now: datetime) -> dict[str, Any]:
    """Backup folders written by deploy/backup/backup.sh: /backups/<label>-<UTC timestamp>/ (daily-*, manual-*, ...)."""
    try:
        with os.scandir(BACKUP_DIR) as it:
            folders = [(e.name, e.stat(follow_symlinks=False).st_mtime, e.path) for e in it
                       if e.is_dir(follow_symlinks=False) and e.name != "offhost"]
    except FileNotFoundError:
        return {"available": False, "level": "unknown", "note": "Not available: the backups folder isn't mounted in the backend."}
    except OSError:
        return {"available": False, "level": "unknown",
                "note": "Not available: the backend can't read the backups folder (folder permissions). "
                        "Check backups with deploy/backup.sh or the backup container's logs."}
    out: dict[str, Any] = {"available": True, "count": len(folders), "daily_count": sum(1 for n, *_ in folders if n.startswith("daily-")),
                           "stale_after_hours": BACKUP_STALE_HOURS}
    status = BACKUP_DIR / "last_backup.json"
    try:
        last = json.loads(status.read_text()) if status.is_file() else None
        out["last_status"] = last.get("status") if isinstance(last, dict) else None
    except (OSError, ValueError):
        out["last_status"] = None
    if not folders:
        return {**out, "level": "critical", "newest": None, "note": "No backups yet: there is nothing to restore from."}
    name, mtime, path = max(folders, key=lambda f: f[1])
    age = round((now.timestamp() - mtime) / 3600, 1)
    try:
        size = _folder_size(path)
    except OSError:
        size = None
    out["newest"] = {"name": name, "at": datetime.fromtimestamp(mtime, timezone.utc), "age_hours": age, "size_bytes": size}
    out["level"] = "warning" if age > BACKUP_STALE_HOURS else "ok"
    if out["last_status"] == "failed":
        out["level"] = "critical"
        out["note"] = "The last backup attempt failed. See the backup container's logs."
    elif age > BACKUP_STALE_HOURS:
        out["note"] = f"The newest backup is more than {BACKUP_STALE_HOURS} hours old. Check that the backup service is running."
    return out


# ---------------- failures: background jobs, discovery runs, workflow errors ----------------

def background_jobs(db: Session, now: datetime) -> dict[str, Any]:
    since = now - WINDOW
    bad = ("failed", "interrupted")
    rows = db.execute(select(JobRun).where(JobRun.status.in_(bad), JobRun.started_at >= since)
                      .order_by(JobRun.started_at.desc()).limit(20)).scalars().all()
    by_name = db.execute(select(JobRun.name, func.count(), func.max(JobRun.started_at))
                         .where(JobRun.status.in_(bad), JobRun.started_at >= since).group_by(JobRun.name)
                         .order_by(func.count().desc())).all()
    stuck = db.execute(select(JobRun).where(JobRun.status == "running", JobRun.started_at < now - timedelta(hours=2))).scalars().all()
    return {
        "failed_count": sum(n for _, n, _ in by_name),
        "by_name": [{"name": name, "failures": n, "last_failed_at": _aware(at)} for name, n, at in by_name],
        "recent": [{"name": r.name, "status": r.status, "trigger": r.trigger, "started_at": _aware(r.started_at),
                    "attempts": r.attempts, "error": scrub(r.error)} for r in rows],
        "stuck": [{"name": r.name, "started_at": _aware(r.started_at), "hours": _hours_since(r.started_at, now)} for r in stuck],
    }


def discovery_runs(db: Session, now: datetime) -> dict[str, Any]:
    since = now - WINDOW
    counts = {k: v for k, v in db.execute(select(DiscoveryRun.status, func.count()).where(DiscoveryRun.started_at >= since)
                             .group_by(DiscoveryRun.status))}
    stuck = db.execute(select(func.count()).select_from(DiscoveryRun).where(DiscoveryRun.status == "running",
                                                                            DiscoveryRun.started_at < now - timedelta(hours=1))).scalar() or 0
    reasons: dict[str, int] = {}
    for details in db.execute(select(DiscoveryRun.error_details).where(DiscoveryRun.status == "failed", DiscoveryRun.started_at >= since)
                              .limit(500)).scalars():
        for e in details or []:
            if isinstance(e, dict) and e.get("type"):
                reasons[e["type"]] = reasons.get(e["type"], 0) + 1
    return {"by_status": counts, "failed": counts.get("failed", 0), "stuck_running": stuck,
            "failure_types": [{"type": k, "count": v} for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])[:10]]}


def workflow_errors(db: Session, now: datetime) -> dict[str, Any]:
    """Per-user run errors and Smart Apply failures, as counts by type (never the users or jobs involved)."""
    since = now - WINDOW
    errs = db.execute(select(RunError.error_type, RunError.platform, func.count()).where(RunError.created_at >= since)
                      .group_by(RunError.error_type, RunError.platform).order_by(func.count().desc()).limit(15)).all()
    apply = {k: v for k, v in db.execute(select(Application.apply_state, func.count()).where(
        Application.apply_state.in_(("failed", "submission_uncertain", "needs_information")), Application.apply_state_at >= since)
        .group_by(Application.apply_state))}
    return {"run_errors": [{"type": t, "platform": p, "count": n} for t, p, n in errs],
            "apply_failed": apply.get("failed", 0), "apply_uncertain": apply.get("submission_uncertain", 0),
            "apply_needs_information": apply.get("needs_information", 0)}


# ---------------- sources ----------------

def sources(db: Session, now: datetime) -> list[dict[str, Any]]:
    """Per source: registry health (job_sources) plus failures seen in the last 7 days of discovery runs."""
    seen: dict[str, dict[str, Any]] = {}
    for run in db.execute(select(DiscoveryRun.started_at, DiscoveryRun.source_results).where(DiscoveryRun.started_at >= now - WINDOW)
                          .order_by(DiscoveryRun.started_at.desc()).limit(2000)).all():
        for key, e in (run.source_results or {}).items():
            if not isinstance(e, dict):
                continue
            s = seen.setdefault(key, {"label": e.get("label") or key, "runs": 0, "failed": 0, "last_success_at": None,
                                      "last_failed_at": None, "last_failure": None})
            s["runs"] += 1
            started = _aware(run.started_at)
            if e.get("status") in ("ok", "empty", "partial") and s["last_success_at"] is None:
                s["last_success_at"] = started
            if e.get("status") == "failed":
                s["failed"] += 1
                if s["last_failed_at"] is None:
                    s["last_failed_at"], s["last_failure"] = started, scrub(e.get("message"))
    out: dict[str, dict[str, Any]] = {}
    for js in db.execute(select(JobSource).order_by(JobSource.key)).scalars():
        out[js.key] = {"key": js.key, "name": js.name, "kind": js.kind, "enabled": js.enabled, "health": js.health,
                       "last_run_at": _aware(js.last_run_at), "last_success_at": _aware(js.last_ok_at), "last_error": scrub(js.last_error)}
    for key, s in seen.items():
        row = out.setdefault(key, {"key": key, "name": s["label"], "kind": None, "enabled": True, "health": "unknown",
                                   "last_run_at": None, "last_success_at": None, "last_error": None})
        row["runs_7d"], row["failures_7d"] = s["runs"], s["failed"]
        row["last_failed_at"], row["last_failure"] = s["last_failed_at"], s["last_failure"]
        if s["last_success_at"] and (row["last_success_at"] is None or s["last_success_at"] > row["last_success_at"]):
            row["last_success_at"] = s["last_success_at"]
    for row in out.values():
        row.setdefault("runs_7d", 0)
        row.setdefault("failures_7d", 0)
        row.setdefault("last_failed_at", None)
        row.setdefault("last_failure", None)
        row["hours_since_success"] = _hours_since(row["last_success_at"], now)
        ran = row["last_run_at"] is not None or row["runs_7d"] > 0
        stale = ran and (row["hours_since_success"] is None or row["hours_since_success"] > SOURCE_STALE_HOURS)
        row["state"] = ("disabled" if not row["enabled"] else "failing" if stale and row["failures_7d"] else "stale" if stale
                        else "degraded" if row["health"] in ("degraded", "failing") else "ok" if ran else "idle")
    order = {"failing": 0, "stale": 1, "degraded": 2, "ok": 3, "idle": 4, "disabled": 5}
    return sorted(out.values(), key=lambda r: (order[r["state"]], r["key"]))


def source_freshness(db: Session, now: datetime) -> list[dict[str, Any]]:
    """How current each source's jobs are: open jobs, newest discovered and newest confirmed-still-listed."""
    open_ = (Job.closed_at.is_(None)) & (Job.is_expired.is_(False))
    rows = db.execute(select(Job.source, func.count(), func.max(Job.discovered_at), func.max(Job.last_verified_at))
                      .where(open_).group_by(Job.source).order_by(func.count().desc()).limit(30)).all()
    return [{"source": s, "open_jobs": n, "newest_discovered_at": _aware(d), "last_verified_at": _aware(v),
             "hours_since_verified": _hours_since(v, now)} for s, n, d, v in rows]


# ---------------- users and extension ----------------

def user_activity(db: Session, now: datetime) -> dict[str, Any]:
    def count(stmt) -> int:
        return int(db.execute(stmt).scalar() or 0)

    users = select(func.count()).select_from(User)
    return {
        "accounts": count(users), "active_accounts": count(users.where(User.is_active.is_(True))),
        "signups_7d": count(users.where(User.created_at >= now - WINDOW)),
        "logins_24h": count(users.where(User.last_login_at >= now - timedelta(hours=24))),
        "logins_7d": count(users.where(User.last_login_at >= now - WINDOW)),
        "logins_30d": count(users.where(User.last_login_at >= now - timedelta(days=30))),
        "active_users_7d": count(select(func.count(func.distinct(AnalyticsEvent.user_id))).where(AnalyticsEvent.created_at >= now - WINDOW)),
        "discovery_runs_7d": count(select(func.count()).select_from(DiscoveryRun).where(DiscoveryRun.started_at >= now - WINDOW)),
        "applications_submitted_7d": count(select(func.count()).select_from(Application).where(
            Application.status == "SUBMITTED", Application.submitted_at >= now - WINDOW)),
    }


def extension(db: Session, now: datetime) -> dict[str, Any]:
    live = ExtensionToken.revoked_at.is_(None) & (ExtensionToken.expires_at.is_(None) | (ExtensionToken.expires_at > now))

    def count(*where) -> int:
        return int(db.execute(select(func.count()).select_from(ExtensionToken).where(*where)).scalar() or 0)

    bundled = None
    try:
        bundled = json.loads(EXTENSION_MANIFEST.read_text()).get("version")
    except (OSError, ValueError, AttributeError):
        pass
    return {
        "connected_devices": count(live), "used_24h": count(live, ExtensionToken.last_used_at >= now - timedelta(hours=24)),
        "used_7d": count(live, ExtensionToken.last_used_at >= now - WINDOW),
        "unused_30d": count(live, (ExtensionToken.last_used_at.is_(None)) | (ExtensionToken.last_used_at < now - timedelta(days=30))),
        "expired": count(ExtensionToken.revoked_at.is_(None), ExtensionToken.expires_at <= now),
        "bundled_version": bundled,
        "version_reporting": False,
        "note": "The extension doesn't send its version to the server yet, so JobPilot can't list which versions are in use. "
                "Smart Apply problems are counted under failed workflows.",
    }


# ---------------- summary ----------------

def _attention(r: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for d in r["disks"]:
        if d.get("available") and d["level"] != "ok":
            out.append({"level": "critical" if d["level"] == "critical" else "warning",
                        "text": f"{d['label']}: disk {d['used_percent']}% full ({d['free_gb']} GB free)."})
    b = r["backups"]
    if b.get("level") in ("warning", "critical") and b.get("note"):
        out.append({"level": b["level"], "text": b["note"]})
    jobs = r["background_jobs"]
    if jobs["failed_count"]:
        out.append({"level": "warning", "text": f"{jobs['failed_count']} background job run(s) failed or were interrupted in the last 7 days."})
    if jobs["stuck"]:
        out.append({"level": "warning", "text": f"{len(jobs['stuck'])} background job(s) have been running for over 2 hours."})
    if r["discovery"]["failed"]:
        out.append({"level": "warning", "text": f"{r['discovery']['failed']} discovery run(s) failed in the last 7 days."})
    failing = [s["name"] for s in r["sources"] if s["state"] in ("failing", "stale")]
    if failing:
        out.append({"level": "warning", "text": f"Sources not succeeding recently: {', '.join(failing[:6])}{'…' if len(failing) > 6 else ''}."})
    return out


_UNAVAILABLE = {"available": False, "note": "Not available: this check failed. See the backend logs."}
_FALLBACK: dict[str, Any] = {
    "disks": [], "database": {**_UNAVAILABLE}, "backups": {**_UNAVAILABLE, "level": "unknown"},
    "background_jobs": {**_UNAVAILABLE, "failed_count": 0, "by_name": [], "recent": [], "stuck": []},
    "discovery": {**_UNAVAILABLE, "by_status": {}, "failed": 0, "stuck_running": 0, "failure_types": []},
    "workflows": {**_UNAVAILABLE, "run_errors": [], "apply_failed": 0, "apply_uncertain": 0, "apply_needs_information": 0},
    "sources": [], "source_freshness": [], "user_activity": {**_UNAVAILABLE}, "extension": {**_UNAVAILABLE},
}


def overview(db: Session, settings: BackendSettings) -> dict[str, Any]:
    now = utcnow()
    checks = {"disks": lambda: disks(settings), "database": lambda: database(db), "backups": lambda: backups(now),
              "background_jobs": lambda: background_jobs(db, now), "discovery": lambda: discovery_runs(db, now),
              "workflows": lambda: workflow_errors(db, now), "sources": lambda: sources(db, now),
              "source_freshness": lambda: source_freshness(db, now), "user_activity": lambda: user_activity(db, now),
              "extension": lambda: extension(db, now)}
    r: dict[str, Any] = {"generated_at": now}
    for name, check in checks.items():
        try:
            r[name] = check()
        except Exception:  # noqa: BLE001  one failing check must not hide the others
            log.exception("ops health check %s failed", name)
            db.rollback()
            r[name] = _FALLBACK[name]
    r["attention"] = _attention(r)
    return r
