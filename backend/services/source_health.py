"""Per-user view of every discovery source: configured or not (and what's missing), connection health, last attempt and
last success, jobs it put in the user's feed, and its outcome in the user's latest run."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import Company, DiscoveryRun, JobSource, JobSourceLink, SavedSearch, User, UserCompany, UserJob
from backend.schemas.discovery import SearchCriteria
from backend.schemas.jobs import DiscoveryRunOut
from backend.services import preference_service
from backend.services.company_service import curated

MANUAL_SOURCES = ("browser_clipper", "user_job_url", "file_import")


class BoardCounts(BaseModel):
    total: int
    ok: int
    failing: int
    unchecked: int


class SourceHealth(BaseModel):
    key: str
    label: str
    kind: str                      # ats | api | email | manual
    enabled: bool                  # used by at least one of your searches / settings
    configured: bool               # everything it needs is in place
    missing: str | None            # what to do when it isn't
    connection: str                # ok | degraded | failing | unknown | not_configured | disabled
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None
    jobs_in_feed: int
    boards: BoardCounts | None = None
    last_run: dict[str, Any] | None = None   # this source's entry in your latest finished run


class SourcesOverview(BaseModel):
    sources: list[SourceHealth]
    last_run: DiscoveryRunOut | None
    saved_searches: int
    enabled_searches: int


def _feed_counts(db: Session, user: User) -> dict[str, int]:
    rows = db.execute(select(JobSourceLink.source, func.count(func.distinct(UserJob.id)))
                      .join(UserJob, UserJob.job_id == JobSourceLink.job_id).where(UserJob.user_id == user.id)
                      .group_by(JobSourceLink.source)).all()
    return {source: n for source, n in rows}


def _boards_for(db: Session, user: User, searches: list[tuple[SavedSearch, SearchCriteria]], ats: str) -> list[Company]:
    ids: set[int] = set()
    tokens: set[str] = set()
    for _, c in searches:
        if ats not in c.sources:
            continue
        ids |= set(c.company_ids)
        if c.use_watchlist:
            ids |= set(db.execute(select(UserCompany.company_id).where(UserCompany.user_id == user.id)).scalars())
        if c.include_suggested:
            tokens |= {e["token"].lower() for e in curated() if e["ats"] == ats}
    boards = list(db.execute(select(Company).where(Company.ats == ats, Company.id.in_(ids))).scalars()) if ids else []
    if tokens:
        known = {b.board_token.lower() for b in boards}
        boards += [c for c in db.execute(select(Company).where(Company.ats == ats, func.lower(Company.board_token).in_(tokens))).scalars()
                   if c.board_token.lower() not in known]
        # Suggested boards not yet used have no row; they count as unchecked.
        missing_rows = tokens - {b.board_token.lower() for b in boards}
        boards += [Company(name=t, ats=ats, board_token=t, origin="curated") for t in missing_rows]
    return boards


def _registry(db: Session) -> dict[str, JobSource]:
    return {r.key: r for r in db.execute(select(JobSource)).scalars()}


def overview(db: Session, settings: BackendSettings, user: User) -> SourcesOverview:
    from backend.api import serializers

    reg = _registry(db)
    feed = _feed_counts(db, user)
    rows = list(db.execute(select(SavedSearch).where(SavedSearch.user_id == user.id)).scalars())
    enabled_searches = [(r, SearchCriteria.model_validate(r.criteria or {})) for r in rows if r.enabled]
    last = db.execute(select(DiscoveryRun).where(DiscoveryRun.user_id == user.id, DiscoveryRun.status != "running")
                      .order_by(DiscoveryRun.id.desc()).limit(1)).scalar_one_or_none()
    recent = list(db.execute(select(DiscoveryRun).where(DiscoveryRun.user_id == user.id, DiscoveryRun.status != "running",
                                                         DiscoveryRun.source_results.is_not(None))
                             .order_by(DiscoveryRun.id.desc()).limit(20)).scalars())

    def last_run_for(key: str) -> dict[str, Any] | None:
        for r in recent:
            entry = (r.source_results or {}).get(key)
            if entry:
                return {**entry, "run_id": r.id, "at": r.completed_at.isoformat() if r.completed_at else None}
        return None

    out: list[SourceHealth] = []
    for ats, label in (("greenhouse", "Greenhouse"), ("lever", "Lever"), ("ashby", "Ashby"), ("smartrecruiters", "SmartRecruiters"),
                       ("recruitee", "Recruitee")):
        boards = _boards_for(db, user, enabled_searches, ats)
        counts = BoardCounts(total=len(boards), ok=sum(b.last_status in ("ok", "empty") for b in boards),
                             failing=sum(b.last_status in ("not_found", "error") for b in boards),
                             unchecked=sum(b.last_status is None for b in boards))
        used = any(ats in c.sources for _, c in enabled_searches)
        missing = None
        if not used:
            missing = f"None of your enabled saved searches uses {label}."
        elif not boards:
            missing = f"No {label} companies to search: add companies, or turn on suggested employers in a search."
        r = reg.get(ats)
        if not used or not boards:
            connection = "not_configured"
        elif counts.ok == 0 and counts.failing:
            connection = "failing"
        elif counts.failing:
            connection = "degraded"
        else:
            connection = r.health if r else "unknown"
        out.append(SourceHealth(key=ats, label=f"{label} job boards", kind="ats", enabled=used, configured=used and bool(boards),
                                missing=missing, connection=connection, last_attempt_at=r.last_run_at if r else None,
                                last_success_at=r.last_ok_at if r else None, last_error=r.last_error if r else None,
                                jobs_in_feed=feed.get(ats, 0), boards=counts, last_run=last_run_for(ats)))

    adz_pref = preference_service.platform_rows(db, user).get(preference_service.ADZUNA)
    adz_used = any("adzuna_api" in c.sources for _, c in enabled_searches) or bool(adz_pref and adz_pref.enabled)
    r = reg.get("adzuna_api")
    if not settings.adzuna_enabled:
        adz_missing, adz_conn = "Server credentials are missing: set ADZUNA_APP_ID and ADZUNA_APP_KEY in the backend's .env and restart it.", "not_configured"
    elif not adz_used:
        adz_missing, adz_conn = "Turn on Adzuna in Settings → Platforms or in a saved search.", "disabled"
    else:
        adz_missing, adz_conn = None, (r.health if r else "unknown")
    out.append(SourceHealth(key="adzuna_api", label="Adzuna Jobs API", kind="api", enabled=adz_used, configured=settings.adzuna_enabled,
                            missing=adz_missing, connection=adz_conn, last_attempt_at=r.last_run_at if r else None,
                            last_success_at=r.last_ok_at if r else None, last_error=r.last_error if r else None,
                            jobs_in_feed=feed.get("adzuna_api", 0), last_run=last_run_for("adzuna_api")))

    integ = preference_service.get_email_integration(db, user)
    plats = preference_service.platform_rows(db, user)
    opted = [p for p, row in plats.items() if row.enabled and "alert_email" in (row.discovery_sources or [])]
    mailbox = bool(integ and integ.enabled and integ.username and integ.password_encrypted)
    if not mailbox:
        mail_missing = "No mailbox connected: add one under Settings → Job-alert email to read LinkedIn, Indeed and Naukri alerts."
    elif not opted:
        mail_missing = "Mailbox connected, but no platform has 'Job-alert email' selected under Settings → Platforms."
    else:
        mail_missing = None
    if mail_missing:
        mail_conn = "not_configured"
    elif integ and integ.last_error:
        mail_conn = "degraded"
    else:
        mail_conn = "ok" if integ and integ.last_checked_at else "unknown"
    out.append(SourceHealth(key="alert_email", label="Job-alert emails", kind="email", enabled=bool(opted), configured=mail_missing is None,
                            missing=mail_missing, connection=mail_conn, last_attempt_at=integ.last_checked_at if integ else None,
                            last_success_at=integ.last_checked_at if integ and not integ.last_error else None,
                            last_error=integ.last_error if integ else None, jobs_in_feed=feed.get("alert_email", 0),
                            last_run=last_run_for("alert_email")))

    out.append(SourceHealth(key="manual", label="Clipper, links and imports (LinkedIn, Indeed, Naukri…)", kind="manual", enabled=True,
                            configured=True, missing=None, connection="ok", last_attempt_at=None, last_success_at=None, last_error=None,
                            jobs_in_feed=sum(feed.get(k, 0) for k in MANUAL_SOURCES)))
    return SourcesOverview(sources=out, last_run=serializers.run(last) if last else None, saved_searches=len(rows),
                           enabled_searches=len(enabled_searches))
