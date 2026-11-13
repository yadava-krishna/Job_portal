"""Saved searches: per-user criteria run against official job boards (and Adzuna), on demand or on a schedule."""

from __future__ import annotations

import logging
import threading
from dataclasses import replace
from datetime import timedelta
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import CandidateProfile, Company, DiscoveryRun, SavedSearch, User, UserCompany, utcnow
from backend.schemas.discovery import SavedSearchIn, SavedSearchOut, SearchCriteria
from backend.services import discovery_service, preference_service, resume_service, source_registry
from backend.services.adzuna import AdzunaClient, AdzunaError
from backend.services.ats import AtsError, smartrecruiters
from backend.services.company_service import curated, get_or_create, refresh_board
from backend.services.normalization import (
    ATS_SOURCES,
    NormalizedJob,
    enrich,
    from_posting,
    is_remote_text,
    location_tokens,
    remote_ok_for_india,
)
from backend.services.role_families import families_for, related_title
from core import timeutil
from core.skills import normalize_text
from intelligence.jd_analyzer import JDAnalyzer

log = logging.getLogger(__name__)
SEARCH_LIMIT = 20
MAX_BOARDS_PER_RUN = 250  # board results are not kept beyond the bounded cache (ats/cache.py)
MAX_JOBS_PER_RUN = 300
INTERVALS = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}
_STOPWORDS = {"and", "of", "the", "for", "in", "a", "an", "to", "with", "at", "or"}
_running: set[int] = set()
_running_lock = threading.Lock()


# ---- CRUD ---------------------------------------------------------------------------------------

def _owned(db: Session, user: User, search_id: int) -> SavedSearch:
    row = db.execute(select(SavedSearch).where(SavedSearch.id == search_id, SavedSearch.user_id == user.id)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Saved search not found.")
    return row


def _validate_companies(db: Session, user: User, ids: list[int]) -> None:
    if not ids:
        return
    found = set(db.execute(select(Company.id).where(Company.id.in_(ids))).scalars())
    missing = sorted(set(ids) - found)
    if missing:
        raise HTTPException(422, f"Unknown company id(s): {', '.join(map(str, missing))}. Add companies to your watchlist first.")


def _schedule_next(row: SavedSearch) -> None:
    interval = INTERVALS.get(row.schedule)
    row.next_run_at = (row.last_run_at or utcnow()) + interval if interval and row.enabled else None


def create(db: Session, user: User, body: SavedSearchIn) -> SavedSearch:
    count = db.execute(select(func.count()).select_from(SavedSearch).where(SavedSearch.user_id == user.id)).scalar_one()
    if count >= SEARCH_LIMIT:
        raise HTTPException(422, f"You can keep up to {SEARCH_LIMIT} saved searches.")
    _validate_companies(db, user, body.criteria.company_ids)
    row = SavedSearch(user_id=user.id, name=body.name.strip(), criteria=body.criteria.model_dump(mode="json"), schedule=body.schedule,
                      min_match_score=body.min_match_score, enabled=body.enabled)
    _schedule_next(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def update(db: Session, user: User, search_id: int, body: SavedSearchIn) -> SavedSearch:
    row = _owned(db, user, search_id)
    _validate_companies(db, user, body.criteria.company_ids)
    row.name, row.criteria, row.schedule = body.name.strip(), body.criteria.model_dump(mode="json"), body.schedule
    row.min_match_score, row.enabled = body.min_match_score, body.enabled
    _schedule_next(row)
    db.commit()
    db.refresh(row)
    return row


def delete(db: Session, user: User, search_id: int) -> None:
    db.delete(_owned(db, user, search_id))  # its runs keep existing; discovery_runs.saved_search_id is set NULL
    db.commit()


def out(db: Session, row: SavedSearch) -> SavedSearchOut:
    from backend.api import serializers

    last = db.execute(select(DiscoveryRun).where(DiscoveryRun.saved_search_id == row.id).order_by(DiscoveryRun.id.desc()).limit(1)).scalar_one_or_none()
    return SavedSearchOut(id=row.id, name=row.name, origin=row.origin, criteria=SearchCriteria.model_validate(row.criteria or {}), schedule=row.schedule,
                          min_match_score=row.min_match_score, enabled=row.enabled, created_at=row.created_at, updated_at=row.updated_at,
                          last_run_at=row.last_run_at, next_run_at=row.next_run_at, last_run=serializers.run(last) if last else None)


def list_for(db: Session, user: User) -> list[SavedSearch]:
    return list(db.execute(select(SavedSearch).where(SavedSearch.user_id == user.id).order_by(SavedSearch.id)).scalars())


# ---- criteria -------------------------------------------------------------------------------------

def _phrase_tokens(phrase: str) -> set[str]:
    return {t for t in normalize_text(phrase).split() if t not in _STOPWORDS}


class Criteria:
    """A saved search's criteria with the user's preferences as fallbacks."""

    def __init__(self, c: SearchCriteria, fallback_titles: list[str], fallback_locations: list[str], domains: list[str] | None = None):
        self.c = c
        self.titles = c.keywords or fallback_titles
        self.families = families_for(*self.titles, *(domains or [])) if c.related_titles else []
        self.title_sets = [s for s in (_phrase_tokens(t) for t in self.titles) if s]
        self.exclude_sets = [s for s in (_phrase_tokens(t) for t in c.exclude_keywords) if s]
        locs = c.locations or fallback_locations
        self.remote_ok = c.remote_ok or any("remote" in l.lower() for l in locs)
        named = [l for l in locs if "remote" not in l.lower()]
        self.cities: set[str] = set().union(*(location_tokens(l) for l in named)) if named else set()
        self.regions = [normalize_text(l) for l in named if not location_tokens(l)]  # e.g. "India", "Karnataka"
        self.any_location = not named
        self.industries = {i.lower() for i in c.industries}

    def title_ok(self, title: str) -> bool:
        tokens = set(normalize_text(title).split())
        if any(s <= tokens for s in self.exclude_sets):
            return False
        return any(s <= tokens for s in self.title_sets) or (bool(self.families) and related_title(title, self.families) is not None)

    def location_ok(self, nj: NormalizedJob) -> bool:
        texts = nj.locations or [nj.location or ""]
        remote = nj.work_mode == "Remote" or any(is_remote_text(t) for t in texts)
        if remote and self.remote_ok and any(remote_ok_for_india(t) for t in texts):
            return True
        if self.any_location:
            return not remote or self.remote_ok
        for t in texts:
            if location_tokens(t) & self.cities:
                return True
            n = normalize_text(t)
            if any(r and r in n for r in self.regions):
                return True
            if "india" in self.regions and location_tokens(t):  # an Indian city satisfies "India"
                return True
        return False

    def details_ok(self, nj: NormalizedJob, today) -> bool:
        c = self.c
        if c.work_modes and nj.work_mode and nj.work_mode not in c.work_modes:
            return False
        if c.employment_types and nj.employment_type and nj.employment_type not in c.employment_types:
            return False
        if self.industries and nj.industry and nj.industry.lower() not in self.industries:
            return False
        if c.experience_years is not None:
            if nj.experience_min is not None and nj.experience_min > c.experience_years + 1:
                return False
            if nj.experience_max is not None and nj.experience_max + 3 < c.experience_years:
                return False
        if c.max_age_days and nj.posted_at and (today - nj.posted_at).days > c.max_age_days:
            return False
        return True


def criteria_for(db: Session, user: User, row: SavedSearch) -> Criteria:
    prefs = preference_service.get_preferences(db, user)
    titles = ((prefs.job_titles or []) + (prefs.title_keywords or [])) if prefs else []
    locations = (prefs.locations or []) if prefs else []
    domains = (prefs.domains or []) if prefs else []
    return Criteria(SearchCriteria.model_validate(row.criteria or {}), titles, locations, domains)


def _companies(db: Session, user: User, c: SearchCriteria) -> list[Company]:
    ids = list(c.company_ids)
    if c.use_watchlist:
        ids += list(db.execute(select(UserCompany.company_id).where(UserCompany.user_id == user.id)).scalars())
    if c.include_suggested:
        for entry in curated():  # verified when the list was built; rows are created on first use, no probe
            if entry["ats"] in c.sources:
                ids.append(get_or_create(db, entry["ats"], entry["token"], name=entry["name"], industry=entry.get("industry"),
                                         region=entry.get("region"), probe=False).id)
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    rows = db.execute(select(Company).where(Company.id.in_(ids), Company.enabled.is_(True), Company.ats.in_(c.sources))).scalars().all()
    order = {cid: i for i, cid in enumerate(ids)}
    return sorted(rows, key=lambda r: order[r.id])[:MAX_BOARDS_PER_RUN]


# ---- running --------------------------------------------------------------------------------------

def _board_items(db: Session, user: User, run: DiscoveryRun, crit: Criteria, analyzer: JDAnalyzer,
                 seen_boards: set[int] | None = None) -> list[NormalizedJob]:
    """Fetch each company board once per run, filter by the criteria, and record each ATS's outcome on the run."""
    seen_boards = set() if seen_boards is None else seen_boards
    companies = _companies(db, user, crit.c)
    if not companies:
        if any(s in ATS_SOURCES for s in crit.c.sources):
            discovery_service._error(db, user, run, "NO_COMPANIES", "Add companies to your watchlist (or to this search) to search their job boards.",
                                     recovery="ADD_COMPANIES")
            if not any(e["status"] in discovery_service.RAN for k, e in (run.source_results or {}).items() if k in ATS_SOURCES):
                discovery_service.source_result(run, "company_boards", status="not_configured",
                                                message="No companies to search. Add companies, or turn on JobPilot's suggested employers.")
        return []
    today = timeutil.today()
    items: list[NormalizedJob] = []
    failures: dict[str, list[str]] = {}
    for n, company in enumerate(companies, 1):
        discovery_service.progress(db, run, f"Fetching job listings: {company.name} ({n} of {len(companies)} company boards)…")
        if company.id in seen_boards:
            result = None
        else:
            seen_boards.add(company.id)
            discovery_service.source_result(run, company.ats)
            try:
                result = refresh_board(db, company)
            except AtsError as exc:
                kind = "BOARD_NOT_FOUND" if exc.kind == "not_found" else "BOARD_FETCH_FAILED"
                discovery_service._error(db, user, run, kind, f"{company.name} ({company.ats}): {exc}", platform=company.ats.title(),
                                         recovery="CHECK_COMPANY_BOARD" if exc.kind == "not_found" else "RETRY_NEXT_RUN")
                discovery_service.source_result(run, company.ats, boards_failed=1, failed_requests=1)
                failures.setdefault(company.ats, []).append(f"{company.name} ({'board not found' if exc.kind == 'not_found' else 'unreachable'})")
                continue
            discovery_service._stat(run, company.ats.title(), "boards_checked")
            discovery_service.source_result(run, company.ats, boards_ok=1, listings_checked=len(result.jobs))
        if result is None:  # already fetched for another search in this run
            try:
                result = refresh_board(db, company)
            except AtsError:
                continue
        for nj in result.jobs:
            if not crit.title_ok(nj.title) or not crit.location_ok(nj):
                continue
            nj = _copy(nj, company)
            smartrecruiters.complete(nj, company.board_token)  # full job ad, fetched only for postings this search kept
            enrich(nj, analyzer)
            if crit.details_ok(nj, today):
                items.append(nj)
        if len(items) >= MAX_JOBS_PER_RUN:
            discovery_service._error(db, user, run, "RUN_CAPPED", f"Stopped after {MAX_JOBS_PER_RUN} matching jobs; narrow the search.",
                                     recovery="NARROW_SEARCH")
            break
    for ats in ATS_SOURCES:
        entry = (run.source_results or {}).get(ats)
        if not entry:
            continue
        bad = failures.get(ats, [])
        if entry.get("boards_ok", 0) == 0:
            status_ = "failed"
        elif entry.get("boards_failed", 0):
            status_ = "partial"
        else:
            status_ = "ok"
        msg = None
        if entry.get("boards_failed", 0):
            shown = ", ".join(bad[:5]) + (f" and {len(bad) - 5} more" if len(bad) > 5 else "")
            msg = f"{_plural(entry['boards_failed'], 'board')} could not be read: {shown}." if shown else entry.get("message")
        discovery_service.source_result(run, ats, status=status_, message=msg)
    db.commit()
    return items[:MAX_JOBS_PER_RUN]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _copy(nj: NormalizedJob, company: Company) -> NormalizedJob:
    """Board results are cached and shared between users; never mutate the cached object."""
    from dataclasses import replace

    return replace(nj, company=company.name, company_id=company.id, industry=company.industry or nj.industry,
                   locations=list(nj.locations), required_skills=list(nj.required_skills), preferred_skills=list(nj.preferred_skills))


def _adzuna_items(db: Session, settings: BackendSettings, user: User, run: DiscoveryRun, crit: Criteria,
                  client: AdzunaClient | None) -> list[NormalizedJob]:
    discovery_service.source_result(run, "adzuna_api")
    if client is None and not settings.adzuna_enabled:
        discovery_service._error(db, user, run, "ADZUNA_NOT_CONFIGURED",
                                 "Adzuna is not configured on this server (ADZUNA_APP_ID / ADZUNA_APP_KEY in .env).", platform="Adzuna",
                                 recovery="CONFIGURE_ADZUNA")
        discovery_service.source_result(run, "adzuna_api", status="not_configured",
                                        message="Adzuna API credentials are not configured on this server (ADZUNA_APP_ID / ADZUNA_APP_KEY).")
        return []
    client = client or AdzunaClient(settings.adzuna_app_id, settings.adzuna_app_key, settings.adzuna_country)  # type: ignore[arg-type]
    if not crit.titles:
        discovery_service._error(db, user, run, "NO_KEYWORDS", "Add job titles or keywords to search Adzuna.", platform="Adzuna",
                                 recovery="UPDATE_SEARCH")
        discovery_service.source_result(run, "adzuna_api", status="not_configured", message="Add job titles or keywords to search Adzuna.")
        return []
    locations = [l for l in (crit.c.locations or []) if "remote" not in l.lower()][:2] or [None]
    days = crit.c.max_age_days or 7
    postings = []
    try:
        for title in crit.titles[:6]:
            for loc in locations:
                postings += discovery_service.adzuna_postings(client, settings, title, loc, max_days_old=min(days, 30))
        source_registry.record(db, "adzuna_api", ok=True)
        discovery_service.source_result(run, "adzuna_api", status="ok", listings_checked=len(postings))
    except AdzunaError as exc:
        source_registry.record(db, "adzuna_api", ok=False, error=str(exc))
        discovery_service._error(db, user, run, "ADZUNA_API", str(exc), platform="Adzuna")
        discovery_service.source_result(run, "adzuna_api", status="partial" if postings else "failed", failed_requests=1, message=str(exc))
    seen: set[str] = set()
    items = []
    for p, posted_at, posted_source, snippet in postings:
        if p.job_key in seen:
            continue
        seen.add(p.job_key)
        nj = from_posting(p, posted_at, posted_source, snippet=snippet, source="adzuna_api")
        if crit.title_ok(nj.title) and crit.details_ok(nj, timeutil.today()):
            items.append(nj)
    return items


# Public remote-job feeds (official JSON APIs, no login). Each is fetched once per run and filtered with the search's
# own title, location and detail rules, so only relevant postings reach the feed.
FEED_SOURCES = ("remotive", "himalayas", "remoteok", "arbeitnow")
FEED_LIMIT = 300


def _fetch_feed(source_id: str) -> tuple[list[NormalizedJob], str | None]:
    from backend.services.connectors import registry

    conn = registry.get(source_id)
    if conn is None:
        return [], "connector not available"
    before = conn.health.last_run_at
    jobs = registry.run_connector(source_id, criteria={"limit": FEED_LIMIT})
    failed = conn.health.status == "failing" and conn.health.last_run_at != before
    return jobs, (conn.health.last_error or "the feed could not be read") if failed and not jobs else None


def _feed_items(db: Session, user: User, run: DiscoveryRun, crit: Criteria, analyzer: JDAnalyzer,
                cache: dict[str, list[NormalizedJob]]) -> list[NormalizedJob]:
    today = timeutil.today()
    items: list[NormalizedJob] = []
    for sid in FEED_SOURCES:
        if sid not in cache:
            discovery_service.progress(db, run, f"Reading the {discovery_service.SOURCE_LABELS.get(sid, sid)} remote-jobs feed…")
            discovery_service.source_result(run, sid)
            try:
                jobs, err = _fetch_feed(sid)
            except Exception as exc:  # one feed failing must not stop the others
                jobs, err = [], f"{type(exc).__name__}: {exc}"
            cache[sid] = jobs
            if err:
                discovery_service._error(db, user, run, "FEED_FETCH_FAILED", f"{discovery_service.SOURCE_LABELS.get(sid, sid)}: {err}",
                                         platform=discovery_service.SOURCE_LABELS.get(sid, sid), recovery="RETRY_NEXT_RUN")
                discovery_service.source_result(run, sid, status="failed", failed_requests=1, message=str(err)[:300])
            else:
                discovery_service.source_result(run, sid, status="ok", listings_checked=len(jobs))
        for nj in cache[sid]:
            if crit.title_ok(nj.title) and crit.location_ok(nj) and crit.details_ok(nj, today):
                items.append(enrich(replace(nj, locations=list(nj.locations), required_skills=list(nj.required_skills),
                                            preferred_skills=list(nj.preferred_skills)), analyzer))
    return items


def start(db: Session, user: User, row: SavedSearch, trigger: str = "manual") -> tuple[DiscoveryRun, bool]:
    """(run, created). A run of this search already in progress is returned instead of starting another."""
    running = db.execute(select(DiscoveryRun).where(DiscoveryRun.saved_search_id == row.id, DiscoveryRun.status == "running",
                                                    DiscoveryRun.started_at > utcnow() - timedelta(minutes=15))).scalars().first()
    if running:
        return running, False
    sources = list(SearchCriteria.model_validate(row.criteria or {}).sources)
    return discovery_service.start_run(db, user, trigger, sources, saved_search_id=row.id), True


def collect(db: Session, settings: BackendSettings, user: User, row: SavedSearch, run: DiscoveryRun, analyzer: JDAnalyzer,
            *, adzuna_client: AdzunaClient | None = None, seen_boards: set[int] | None = None,
            feed_cache: dict[str, list[NormalizedJob]] | None = None) -> list[NormalizedJob]:
    crit = criteria_for(db, user, row)
    feed_cache = {} if feed_cache is None else feed_cache
    if not crit.title_sets:
        discovery_service._error(db, user, run, "NO_KEYWORDS", f"'{row.name}': add job titles or keywords to this search (or to your preferences).",
                                 recovery="UPDATE_SEARCH")
        discovery_service.source_result(run, "search", status="not_configured",
                                        message="No job titles to search for. Add titles to your preferences or to the search.")
        return []
    items: list[NormalizedJob] = []
    if any(s in ATS_SOURCES for s in crit.c.sources):
        items += _board_items(db, user, run, crit, analyzer, seen_boards)
    if "adzuna_api" in crit.c.sources:
        items += _adzuna_items(db, settings, user, run, crit, adzuna_client)
    if "remote_feeds" in crit.c.sources:
        items += _feed_items(db, user, run, crit, analyzer, feed_cache)
    row.last_run_at = utcnow()
    _schedule_next(row)
    return items


def _threshold(db: Session, user: User, row: SavedSearch | None) -> float:
    if row is not None and row.min_match_score is not None:
        return row.min_match_score
    prefs = preference_service.get_preferences(db, user)
    return prefs.min_match_score if prefs else 70


def execute(db: Session, settings: BackendSettings, user: User, row: SavedSearch, run: DiscoveryRun,
            *, adzuna_client: AdzunaClient | None = None) -> DiscoveryRun:
    """Run one saved search to completion. Never raises: failures are recorded on the run."""
    run_id, search_id = run.id, row.id
    with _running_lock:
        if row.id in _running:
            discovery_service._error(db, user, run, "ALREADY_RUNNING", "This search is already running.")
            return discovery_service.finish_run(db, run)
        _running.add(row.id)
    try:
        analyzer = JDAnalyzer(resume_service.taxonomy(settings))
        discovery_service.progress(db, run, "Connecting to sources…")
        items = collect(db, settings, user, row, run, analyzer, adzuna_client=adzuna_client)
        discovery_service.progress(db, run, f"Removing duplicates and matching {len(items)} listings against your resume…")
        matcher = discovery_service._matcher_or_none(db, settings, user, run)
        discovery_service.ingest_normalized(db, user, run, _dedupe_batch(items), matcher, notify_min_score=_threshold(db, user, row),
                                            explicit_sources=True)
        return discovery_service.finish_run(db, run)
    except Exception as exc:
        log.exception("Saved search %s failed", search_id)
        db.rollback()
        run = db.get(DiscoveryRun, run_id)
        discovery_service._error(db, user, run, "DISCOVERY_FAILED", f"{type(exc).__name__}: {exc}")
        return discovery_service.finish_run(db, run, failed=True)
    finally:
        with _running_lock:
            _running.discard(search_id)


# ---- starter search and "run everything" -----------------------------------------------------------

STARTER_NAME = "Jobs matching my profile"


def ensure_starter(db: Session, settings: BackendSettings, user: User) -> SavedSearch | None:
    """Give every onboarded user a daily search built from their preferences, over JobPilot's verified employer boards.

    Created once: if the user deletes it, it is not recreated. Titles and locations are read from the preferences at
    run time, so editing preferences updates the search.
    """
    if user.starter_search_created_at is not None:
        return None
    if db.execute(select(func.count()).select_from(SavedSearch).where(SavedSearch.user_id == user.id)).scalar_one():
        user.starter_search_created_at = utcnow()
        db.commit()
        return None
    prefs = preference_service.get_preferences(db, user)
    if prefs is None or not ((prefs.job_titles or []) + (prefs.title_keywords or [])):
        return None  # nothing to search for yet; retried after onboarding
    prof = db.execute(select(CandidateProfile).where(CandidateProfile.user_id == user.id)).scalar_one_or_none()
    years = round(prof.experience_months / 12, 1) if prof and prof.experience_months else None
    sources = ["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "remote_feeds"] + (["adzuna_api"] if settings.adzuna_enabled else [])
    criteria = SearchCriteria(include_suggested=True, use_watchlist=True, related_titles=True, remote_ok=True,
                              experience_years=years, sources=sources)
    row = SavedSearch(user_id=user.id, name=STARTER_NAME, origin="starter", criteria=criteria.model_dump(mode="json"),
                      schedule="daily", min_match_score=None, enabled=True, next_run_at=utcnow())
    db.add(row)
    user.starter_search_created_at = utcnow()
    db.commit()
    db.refresh(row)
    return row


def run_all(db: Session, settings: BackendSettings, user: User, run: DiscoveryRun, *, scheduled: bool = False,
            email_factory=None, adzuna_client: AdzunaClient | None = None) -> DiscoveryRun:
    """"Run discovery now": alert emails, Adzuna and every enabled saved search, in one run with per-source outcomes.

    A scheduled run includes only searches due in the next 12 hours, so the 15-minute tick doesn't repeat them.
    """
    run_id = run.id
    try:
        ensure_starter(db, settings, user)
        discovery_service.progress(db, run, "Connecting to sources…")
        matcher = discovery_service._matcher_or_none(db, settings, user, run)
        discovery_service.legacy_sources(db, settings, user, run, ["alert_email", "adzuna_api"], matcher,
                                         email_factory=email_factory, adzuna_client=adzuna_client)
        analyzer = JDAnalyzer(resume_service.taxonomy(settings))
        rows = [r for r in list_for(db, user) if r.enabled]
        if scheduled:
            horizon = utcnow() + timedelta(hours=12)
            rows = [r for r in rows if r.schedule != "manual" and r.next_run_at is not None and r.next_run_at <= horizon]
        if not rows and not scheduled:
            discovery_service.source_result(run, "search", status="not_configured",
                                            message="You have no saved searches. Add job titles to your preferences, or create a search.")
        items: list[NormalizedJob] = []
        seen: set[int] = set()
        feeds: dict[str, list[NormalizedJob]] = {}
        for row in rows:
            items += collect(db, settings, user, row, run, analyzer, adzuna_client=adzuna_client, seen_boards=seen, feed_cache=feeds)
        thresholds = [_threshold(db, user, r) for r in rows] or [_threshold(db, user, None)]
        discovery_service.progress(db, run, f"Removing duplicates and matching {len(items)} listings against your resume…")
        discovery_service.ingest_normalized(db, user, run, _dedupe_batch(items), matcher, notify_min_score=min(thresholds),
                                            explicit_sources=True)
        return discovery_service.finish_run(db, run)
    except Exception as exc:
        log.exception("Discovery run %s failed", run_id)
        db.rollback()
        run = db.get(DiscoveryRun, run_id)
        discovery_service._error(db, user, run, "DISCOVERY_FAILED", f"{type(exc).__name__}: {exc}")
        return discovery_service.finish_run(db, run, failed=True)


def _dedupe_batch(items: Iterable[NormalizedJob]) -> list[NormalizedJob]:
    seen: set[str] = set()
    out = []
    for nj in items:
        if nj.source_key not in seen:
            seen.add(nj.source_key)
            out.append(nj)
    return out


def due(db: Session, now=None) -> list[SavedSearch]:
    now = now or utcnow()
    return list(db.execute(select(SavedSearch).join(User, User.id == SavedSearch.user_id).where(
        SavedSearch.enabled.is_(True), SavedSearch.schedule != "manual", SavedSearch.next_run_at.is_not(None),
        SavedSearch.next_run_at <= now, User.is_active.is_(True), User.onboarding_completed_at.is_not(None),
    ).order_by(SavedSearch.next_run_at)).scalars())


def ensure_starters(db: Session, settings: BackendSettings) -> int:
    users = db.execute(select(User).where(User.is_active.is_(True), User.onboarding_completed_at.is_not(None),
                                          User.starter_search_created_at.is_(None))).scalars().all()
    return sum(1 for u in users if ensure_starter(db, settings, u) is not None)


def run_due(db: Session, settings: BackendSettings) -> int:
    ensure_starters(db, settings)
    done = 0
    for row in due(db):
        user = db.get(User, row.user_id)
        run, created = start(db, user, row, trigger="scheduled")
        if created:
            execute(db, settings, user, row, run)
            done += 1
    return done


def mark_interrupted(db: Session, older_than_minutes: int = 30) -> int:
    """Runs left 'running' by a restart can never finish; close them so the UI and reports are accurate (S10)."""
    cutoff = utcnow() - timedelta(minutes=older_than_minutes)
    rows = db.execute(select(DiscoveryRun).where(DiscoveryRun.status == "running", DiscoveryRun.started_at < cutoff)).scalars().all()
    for r in rows:
        r.status, r.completed_at = "failed", utcnow()
        r.error_details = [*(r.error_details or []), {"type": "INTERRUPTED", "platform": None,
                                                      "message": "The server restarted before this run finished."}]
    db.commit()
    return len(rows)
