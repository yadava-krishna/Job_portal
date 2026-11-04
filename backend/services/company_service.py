"""Employer job boards: the directory (curated + JobSync MIT data), company rows, user watchlists, board refresh."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import Company, Job, JobSourceLink, User, UserCompany, utcnow
from backend.schemas.discovery import CompanyOut, DirectoryCompany, WatchRequest
from backend.services.ats import AtsError, BoardResult, board_cache, parse_board_url
from backend.services.ats.base import valid_token

log = logging.getLogger(__name__)
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "ats_companies"
WATCHLIST_LIMIT = 100
BOARD_URLS = {
    "greenhouse": "https://job-boards.greenhouse.io/{token}",
    "lever": "https://jobs.lever.co/{token}",
    "ashby": "https://jobs.ashbyhq.com/{token}",
}


@lru_cache(maxsize=1)
def curated() -> tuple[dict[str, Any], ...]:
    data = json.loads((DATA_DIR / "curated_india.json").read_text())
    return tuple(data["companies"])


@lru_cache(maxsize=1)
def directory() -> tuple[dict[str, Any], ...]:
    """Curated entries first, then the JobSync directories (MIT, see data/ats_companies/NOTICE.md)."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for c in curated():
        seen.add((c["ats"], c["token"].lower()))
        out.append({**c, "curated": True})
    for ats in ("greenhouse", "lever", "ashby"):
        for c in json.loads((DATA_DIR / f"jobsync_{ats}.json").read_text()):
            key = (ats, str(c.get("token", "")).lower())
            if c.get("name") and c.get("token") and key not in seen:
                seen.add(key)
                out.append({"name": c["name"], "ats": ats, "token": c["token"], "curated": False})
    return tuple(out)


def board_url(c: Company) -> str:
    base = BOARD_URLS[c.ats].format(token=c.board_token)
    return base.replace("jobs.lever.co", "jobs.eu.lever.co") if c.ats == "lever" and c.region == "eu" else base


def company_out(c: Company) -> CompanyOut:
    return CompanyOut(id=c.id, name=c.name, ats=c.ats, board_token=c.board_token, region=c.region, industry=c.industry,
                      domain=c.domain, origin=c.origin, board_url=board_url(c), last_fetched_at=c.last_fetched_at,
                      last_status=c.last_status, last_error=c.last_error, job_count=c.job_count)


def _directory_entry(ats: str, token: str) -> dict[str, Any] | None:
    t = token.lower()
    return next((c for c in directory() if c["ats"] == ats and c["token"].lower() == t), None)


def search_directory(db: Session, user: User, q: str | None, ats: str | None, limit: int) -> list[DirectoryCompany]:
    needle = (q or "").strip().lower()
    rows = [c for c in directory() if (not ats or c["ats"] == ats)
            and (not needle or needle in c["name"].lower() or needle in c["token"].lower())]
    if needle:  # names starting with the query first
        rows.sort(key=lambda c: (not c["name"].lower().startswith(needle), not c.get("curated"), c["name"].lower()))
    rows = rows[:limit]
    watched = watched_keys(db, user)
    existing = {(c.ats, c.board_token.lower()): c.id for c in db.execute(select(Company)).scalars()} if rows else {}
    return [DirectoryCompany(name=c["name"], ats=c["ats"], token=c["token"], industry=c.get("industry"), domain=c.get("domain"),
                             curated=bool(c.get("curated")), company_id=existing.get((c["ats"], c["token"].lower())),
                             watched=(c["ats"], c["token"].lower()) in watched) for c in rows]


def watched_keys(db: Session, user: User) -> set[tuple[str, str]]:
    rows = db.execute(select(Company.ats, Company.board_token).join(UserCompany, UserCompany.company_id == Company.id)
                      .where(UserCompany.user_id == user.id)).all()
    return {(a, t.lower()) for a, t in rows}


def get_or_create(db: Session, ats: str, token: str, *, name: str | None = None, industry: str | None = None,
                  region: str | None = None, user: User | None = None, probe: bool = True) -> Company:
    token = valid_token(token)
    row = db.execute(select(Company).where(Company.ats == ats, func.lower(Company.board_token) == token.lower())).scalar_one_or_none()
    if row is not None:
        return row
    entry = _directory_entry(ats, token)
    result: BoardResult | None = None
    if probe and not (entry and entry.get("curated")):
        # Unknown or JobSync-listed boards are checked once, so typos and stale tokens are caught up front.
        try:
            result = board_cache.get(ats, token, company_name=name or (entry or {}).get("name"), region=region)
        except AtsError as exc:
            if exc.kind == "not_found":
                raise HTTPException(422, f"No {ats.title()} job board called '{token}' was found.") from None
            if exc.kind == "transient":
                raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, f"{ats.title()} could not be reached. Try again shortly.") from None
            raise HTTPException(422, str(exc)) from None
    display = (name or (entry or {}).get("name") or (result.company_name if result else None) or token).strip()[:200]
    row = Company(name=display, ats=ats, board_token=token, region=region, industry=industry or (entry or {}).get("industry"),
                  domain=(entry or {}).get("domain"), origin="curated" if entry and entry.get("curated") else ("jobsync" if entry else "user"),
                  created_by_id=user.id if user and not entry else None)
    if result is not None:
        row.last_fetched_at, row.last_status, row.job_count = utcnow(), "ok" if result.jobs else "empty", len(result.jobs)
    db.add(row)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        row = db.execute(select(Company).where(Company.ats == ats, func.lower(Company.board_token) == token.lower())).scalar_one()
    return row


def watchlist(db: Session, user: User) -> list[Company]:
    rows = db.execute(select(UserCompany).where(UserCompany.user_id == user.id).order_by(UserCompany.id)).unique().scalars()
    return [r.company for r in rows]


def watch(db: Session, user: User, req: WatchRequest) -> Company:
    if req.url:
        try:
            ats, token, region = parse_board_url(req.url)
        except AtsError as exc:
            raise HTTPException(422, str(exc)) from None
    else:
        ats, token, region = req.ats, req.token, None  # type: ignore[assignment]
    try:
        company = get_or_create(db, ats, token, name=req.name, industry=req.industry, region=region, user=user)
    except AtsError as exc:
        raise HTTPException(422, str(exc)) from None
    exists = db.execute(select(UserCompany).where(UserCompany.user_id == user.id, UserCompany.company_id == company.id)).unique().scalar_one_or_none()
    if exists is None:
        count = db.execute(select(func.count()).select_from(UserCompany).where(UserCompany.user_id == user.id)).scalar_one()
        if count >= WATCHLIST_LIMIT:
            raise HTTPException(422, f"Your watchlist is limited to {WATCHLIST_LIMIT} companies.")
        db.add(UserCompany(user_id=user.id, company_id=company.id))
    db.commit()
    db.refresh(company)
    return company


def unwatch(db: Session, user: User, company_id: int) -> None:
    row = db.execute(select(UserCompany).where(UserCompany.user_id == user.id, UserCompany.company_id == company_id)).unique().scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That company is not on your watchlist.")
    db.delete(row)
    db.commit()


def refresh_board(db: Session, company: Company) -> BoardResult:
    """Fetch a board (shared cache), record its health, and mark jobs that left the board as closed."""
    from backend.services import source_registry

    try:
        result = board_cache.get(company.ats, company.board_token, company_name=company.name, region=company.region)
    except AtsError as exc:
        company.last_fetched_at, company.last_error = utcnow(), str(exc)[:500]
        company.last_status = "not_found" if exc.kind == "not_found" else "error"
        source_registry.record(db, company.ats, ok=exc.kind == "not_found", error=None if exc.kind == "not_found" else str(exc))
        raise
    company.last_fetched_at, company.last_error = utcnow(), None
    company.last_status, company.job_count = ("ok" if result.jobs else "empty"), len(result.jobs)
    source_registry.record(db, company.ats, ok=True)
    _close_missing(db, company, {j.source_key for j in result.jobs})
    return result


def _close_missing(db: Session, company: Company, live_keys: set[str]) -> int:
    prefix = f"{company.ats}:{company.board_token.lower()}:"
    links = db.execute(select(JobSourceLink).where(JobSourceLink.source == company.ats,
                                                   JobSourceLink.source_key.startswith(prefix))).scalars().all()
    live_jobs = {l.job_id for l in links if l.source_key in live_keys}  # a merged job stays open while any posting is live
    gone = [l.job_id for l in links if l.source_key not in live_keys and l.job_id not in live_jobs]
    if not gone:
        return 0
    now = utcnow()
    closed = 0
    for job in db.execute(select(Job).where(Job.id.in_(gone), Job.closed_at.is_(None))).scalars():
        job.closed_at = now
        closed += 1
    return closed
