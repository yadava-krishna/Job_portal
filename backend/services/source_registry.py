"""Health of each discovery source, recorded in job_sources (admin views in Phase 5)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import JobSource, utcnow

log = logging.getLogger(__name__)
SOURCES = {
    "greenhouse": ("ats", "Greenhouse job boards (official API)"),
    "lever": ("ats", "Lever job boards (official API)"),
    "ashby": ("ats", "Ashby job boards (official API)"),
    "smartrecruiters": ("ats", "SmartRecruiters job boards (official Posting API)"),
    "recruitee": ("ats", "Recruitee careers sites (official Careers Site API)"),
    "adzuna_api": ("api", "Adzuna Jobs API"),
    "alert_email": ("email", "Job-alert emails (user mailbox)"),
    "browser_clipper": ("clip", "Browser clipper"),
}


def _row(db: Session, key: str) -> JobSource:
    pending = next((o for o in db.new if isinstance(o, JobSource) and o.key == key), None)
    row = pending or db.execute(select(JobSource).where(JobSource.key == key)).scalar_one_or_none()
    if row is None:
        kind, name = SOURCES.get(key, ("other", key))
        row = JobSource(key=key, kind=kind, name=name, enabled=True, config={}, health="unknown")
        db.add(row)
        try:
            with db.begin_nested():
                db.flush([row])
        except IntegrityError:  # another worker created it first
            row = db.execute(select(JobSource).where(JobSource.key == key)).scalar_one()
    return row


def record(db: Session, key: str, *, ok: bool, error: str | None = None) -> JobSource | None:
    """Health bookkeeping must never break a discovery run."""
    try:
        row = _row(db, key)
    except Exception:  # noqa: BLE001
        log.warning("Could not record health for source %s", key, exc_info=True)
        return None
    now = utcnow()
    row.last_run_at = now
    if ok:
        row.health, row.last_ok_at, row.last_error = "ok", now, None
    else:
        row.health, row.last_error = "degraded", (error or "")[:2000]
    return row
