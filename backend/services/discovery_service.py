"""Unified per-user job discovery from permitted sources, with global job dedup and per-user feeds."""

from __future__ import annotations

import hashlib
import logging
import tempfile
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import Application, DiscoveryRun, EmailIntegration, Job, JobSourceLink, RunError, User, UserJob, utcnow
from backend.schemas.jobs import ImportJobRequest
from backend.security import CredentialCipher
from backend.services import preference_service, resume_service
from backend.services.adzuna import AdzunaClient, AdzunaError
from backend.services.matching_service import UserMatcher
from backend.services.normalization import (  # noqa: F401  (VERIFIED_DATE_SOURCES re-exported for routes)
    ATS_SOURCES,
    DATE_SOURCE_RANK,
    VERIFIED_DATE_SOURCES,
    NormalizedJob,
    from_posting,
    locations_compatible,
    posted_confidence,
)
from core import timeutil
from core.models import JobPosting, Platform, RawJobRecord
from core.skills import normalize_text
from core.settings import EmailAlertsConfig
from discovery.deduplication import fingerprint
from discovery.job_extractor import JobExtractor
from discovery.sources import EmailAlertSource, ImportInboxSource, confirmation_emails, record_from_mapping
from intelligence.jd_analyzer import JDAnalyzer, parse_posted_date
from platforms import get_adapter
from platforms.base_platform import PlatformError

log = logging.getLogger(__name__)


# ---- global job upsert with cross-source deduplication -------------------------------------------

def find_existing(db: Session, nj: NormalizedJob) -> tuple[Job | None, str | None]:
    """The job this listing is a copy of, and how it was recognised (None when it is new).

    1. the same source listing seen before, 2. the legacy job key, 3. the same canonical URL,
    4. the same normalised company + title on a *different* source with compatible locations, or on the *same* source
       board (same company) with exactly the same location (an employer re-posting one role). The same title in two
       cities on one board stays two jobs; user imports from different platforms keep their own rows.
    """
    link = db.execute(select(JobSourceLink).where(JobSourceLink.source_key == nj.source_key)).scalar_one_or_none()
    if link is not None:
        return db.get(Job, link.job_id), "source_key"
    job = db.execute(select(Job).where(Job.job_key == nj.key)).scalar_one_or_none()
    if job is not None:
        return job, "job_key"
    canon = nj.canonical_url
    if canon:
        job = db.execute(select(Job).where(Job.canonical_url == canon).order_by(Job.id).limit(1)).scalar_one_or_none()
        if job is not None:
            return job, "canonical_url"
    key = nj.dedup_key
    if not key:
        return None, None
    candidates = db.execute(select(Job).where(Job.dedup_key == key).order_by(Job.id).limit(25)).scalars().all()
    if not candidates:
        return None, None
    same_source = set(db.execute(select(JobSourceLink.job_id).where(
        JobSourceLink.job_id.in_([c.id for c in candidates]), JobSourceLink.source == nj.source)).scalars())
    here = normalize_text(nj.location)
    reposted = [c for c in candidates if nj.source in ATS_SOURCES and nj.company_id is not None and c.company_id == nj.company_id
                and (c.id in same_source or c.source == nj.source) and here and normalize_text(c.location) == here]
    if reposted:
        return reposted[0], "same_board_repost"
    candidates = [c for c in candidates if c.id not in same_source and c.source != nj.source]
    verdicts = [(c, locations_compatible(c.location, nj.location)) for c in candidates]
    compatible = [c for c, ok in verdicts if ok is True]
    if compatible:
        return compatible[0], "company_title_location"
    if len(candidates) == 1 and verdicts[0][1] is None:
        return candidates[0], "company_title"
    return None, None


def _enrich_existing(job: Job, nj: NormalizedJob) -> None:
    cols = nj.job_columns()
    for k, v in cols.items():
        if v in (None, "", []) or k in ("source", "platform", "company", "title"):
            continue
        if getattr(job, k) in (None, "", []):
            setattr(job, k, v)
    if nj.description and not nj.description_is_snippet and (
            job.description_is_snippet or not job.description or len(nj.description) > len(job.description or "")):
        for k in ("description", "required_skills", "preferred_skills", "education_requirements", "mandatory_qualifications"):
            setattr(job, k, cols[k])
        job.description_is_snippet = False
    if nj.posted_at and DATE_SOURCE_RANK.get(nj.posted_at_source, 0) > DATE_SOURCE_RANK.get(job.posted_at_source, 0):
        job.posted_at, job.posted_at_source = nj.posted_at, nj.posted_at_source
        job.posted_at_confidence = posted_confidence(nj.posted_at, nj.posted_at_source)


def _fit_columns(obj) -> None:
    """Trim text that is longer than its column (e.g. a salary field holding a whole pay table), instead of failing."""
    from sqlalchemy import String, inspect as sa_inspect

    for col in sa_inspect(type(obj)).columns:
        length = getattr(col.type, "length", None)
        if isinstance(col.type, String) and length:
            value = getattr(obj, col.key, None)
            if isinstance(value, str) and len(value) > length:
                setattr(obj, col.key, value[: length - 1].rstrip() + "…")


def calculate_freshness(posted_at: date | None, reference_date: date | None = None) -> float:
    """Calculate freshness decay factor from 0.0 to 1.0 based on posting age."""
    if posted_at is None:
        return 0.70  # Baseline moderate freshness for undated postings
    ref = reference_date or date.today()
    delta_days = (ref - posted_at).days
    if delta_days <= 1:
        return 1.0
    elif delta_days <= 7:
        return 0.85
    elif delta_days <= 14:
        return 0.70
    elif delta_days <= 30:
        return 0.50
    elif delta_days <= 60:
        return 0.30
    return 0.15


def reap_expired_jobs(db: Session, max_age_days: int = 45) -> int:
    """Flag active jobs older than max_age_days as expired."""
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=max_age_days)
    now = utcnow()
    stmt = (
        select(Job)
        .where(Job.is_expired == False, Job.posted_at != None, Job.posted_at < cutoff)
    )
    stale_jobs = db.execute(stmt).scalars().all()
    count = 0
    for j in stale_jobs:
        j.is_expired = True
        j.closed_at = now
        j.freshness_score = 0.05
        count += 1
    if count > 0:
        db.commit()
    return count


def upsert_normalized(db: Session, nj: NormalizedJob) -> tuple[Job, bool]:
    """Insert a public listing, or merge it into the job it duplicates. Returns (job, created)."""
    now = utcnow()
    job, _how = find_existing(db, nj)
    created = False
    if job is None:
        freshness = calculate_freshness(nj.posted_at)
        job = Job(job_key=nj.key, posted_at=nj.posted_at, posted_at_source=nj.posted_at_source if nj.posted_at else None,
                  posted_at_confidence=posted_confidence(nj.posted_at, nj.posted_at_source), discovered_at=now,
                  description_is_snippet=nj.description_is_snippet, freshness_score=freshness, is_expired=False,
                  last_scraped_at=now, **nj.job_columns())
        _fit_columns(job)
        db.add(job)
        try:
            with db.begin_nested():
                db.flush()
            created = True
        except IntegrityError:  # concurrent insert of the same listing
            job, _how = find_existing(db, nj)
            if job is None:
                raise
    if not created:
        _enrich_existing(job, nj)
        job.freshness_score = calculate_freshness(job.posted_at)
        job.last_scraped_at = now
        job.is_expired = False
        _fit_columns(job)
    if nj.source in ATS_SOURCES:
        job.last_verified_at, job.closed_at = now, None  # listed on the employer's board right now
    from backend.services.career_service import infer_seniority, sponsorship_signal
    job.sponsorship_signal, job.sponsorship_evidence = sponsorship_signal(job.description)
    if not job.seniority:
        job.seniority = infer_seniority(job.title, job.experience_min)
    if job.sponsorship_evidence:
        job.sponsorship_evidence = job.sponsorship_evidence[:300]
    link = db.execute(select(JobSourceLink).where(JobSourceLink.source_key == nj.source_key)).scalar_one_or_none()
    if link is None:
        link = JobSourceLink(job_id=job.id, source=nj.source, platform=nj.platform, source_key=nj.source_key, url=nj.job_url,
                             posted_at=nj.posted_at, posted_at_source=nj.posted_at_source if nj.posted_at else None,
                             first_seen_at=now, last_seen_at=now)
        _fit_columns(link)
        db.add(link)
    else:
        link.last_seen_at, link.url = now, nj.job_url or link.url
    db.flush()
    return job, created


def add_to_feed(db: Session, user: User, job: Job, run: DiscoveryRun | None, source: str) -> tuple[UserJob, bool]:
    uj = db.execute(select(UserJob).where(UserJob.user_id == user.id, UserJob.job_id == job.id)).unique().scalar_one_or_none()
    if uj is not None:
        uj.seen_count += 1
        return uj, False
    uj = UserJob(user_id=user.id, job_id=job.id, discovery_run_id=run.id if run else None, source=source, status="new")
    db.add(uj)
    db.flush()
    db.refresh(uj)
    return uj, True


# ---- runs ---------------------------------------------------------------------------

def start_run(db: Session, user: User, trigger: str, sources: list[str], saved_search_id: int | None = None) -> DiscoveryRun:
    run = DiscoveryRun(user_id=user.id, trigger=trigger, sources=sources, status="running", error_details=[], platform_stats={},
                       saved_search_id=saved_search_id)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _error(db: Session, user: User, run: DiscoveryRun | None, kind: str, message: str, *, platform: str | None = None,
           job_key: str | None = None, recovery: str = "RETRY_NEXT_RUN") -> None:
    db.add(RunError(user_id=user.id, discovery_run_id=run.id if run else None, platform=platform, job_key=job_key,
                    error_type=kind, description=message[:2000], recovery_status=recovery))
    if run is not None:
        run.error_details = [*(run.error_details or []), {"type": kind, "platform": platform, "message": message[:500]}]


def _stat(run: DiscoveryRun, platform: str, key: str, n: int = 1) -> None:
    stats = dict(run.platform_stats or {})
    entry = dict(stats.get(platform, {"records_seen": 0, "new": 0, "duplicates_skipped": 0}))
    entry[key] = entry.get(key, 0) + n
    stats[platform] = entry
    run.platform_stats = stats


SOURCE_LABELS = {
    "greenhouse": "Greenhouse", "lever": "Lever", "ashby": "Ashby", "smartrecruiters": "SmartRecruiters", "recruitee": "Recruitee", "adzuna_api": "Adzuna", "alert_email": "Job-alert emails",
    "company_boards": "Company job boards", "search": "Search settings",
    "remotive": "Remotive", "himalayas": "Himalayas", "remoteok": "RemoteOK", "arbeitnow": "Arbeitnow",
}
RAN = ("ok", "empty", "partial")          # the source was reached and answered
PROBLEM = ("failed", "partial")           # something that should have worked didn't
WARNING_ERRORS = ("ADZUNA_NOT_CONFIGURED", "EMAIL_NOT_CONFIGURED", "NO_COMPANIES")


def source_result(run: DiscoveryRun, key: str, *, status: str | None = None, message: str | None = None, **inc: int) -> dict:
    """Create or update one source's outcome on a run. Counters in **inc are added."""
    results = dict(run.source_results or {})
    entry = dict(results.get(key) or {"label": SOURCE_LABELS.get(key, key), "status": "pending", "message": None,
                                      "found": 0, "new": 0, "duplicates": 0, "failed_requests": 0})
    for k, v in inc.items():
        entry[k] = entry.get(k, 0) + v
    if status:
        entry["status"] = status
    if message is not None:
        entry["message"] = message[:500]
    results[key] = entry
    run.source_results = results
    return entry


def progress(db: Session, run: DiscoveryRun, text: str) -> None:
    """While a run is in progress its summary is the current stage, so the UI can show real progress."""
    if run.status == "running":
        run.summary = text
        db.commit()


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def summarize(run: DiscoveryRun) -> str | None:
    """A plain-language outcome. Never just "0 jobs": says what ran, what didn't, and why."""
    results = run.source_results or {}
    if not results:
        return None
    ran = {k: e for k, e in results.items() if e["status"] in RAN}
    notes = [f"{e['label']}: {e['message']}" for e in results.values() if e["status"] not in ("ok", "empty") and e.get("message")]
    if run.status == "failed" and not ran:
        return "Discovery could not run. " + " ".join(notes) if notes else "Discovery could not run."
    found = sum(e.get("found", 0) for e in ran.values())
    checked = sum(e.get("listings_checked", 0) for e in ran.values())
    boards = sum(e.get("boards_ok", 0) for e in ran.values())
    where = ", ".join(e["label"] for e in ran.values())
    head = f"Checked {where}" + (f" ({_plural(boards, 'company board')}, {_plural(checked, 'listing')})" if boards else "") + ". "
    if found == 0:
        head += "No listings matched your titles and locations right now. Try broader titles or more locations, or add companies."
    else:
        head += f"{_plural(found, 'matching job')}: {run.jobs_new} new, {run.duplicates} already in your feed."
    return head + (" " + " ".join(notes) if notes else "")


def finish_run(db: Session, run: DiscoveryRun, failed: bool = False) -> DiscoveryRun:
    run.completed_at = utcnow()
    results = run.source_results or {}
    if failed:
        run.status = "failed"
    elif results:
        for key, e in results.items():  # a source that answered but matched nothing is "empty", not a success with jobs
            if e["status"] == "ok" and e.get("found", 0) == 0:
                source_result(run, key, status="empty")
        results = run.source_results or {}
        ran = [e for e in results.values() if e["status"] in RAN]
        hard_errors = [e for e in run.error_details or [] if e["type"] not in WARNING_ERRORS]
        if not ran:
            run.status = "failed"  # nothing could run: unconfigured, disabled or failed everywhere
        elif any(e["status"] in PROBLEM for e in results.values()) or hard_errors:
            run.status = "partial"
        else:
            run.status = "completed"
    else:
        run.status = "partial" if run.error_details else "completed"
    run.summary = summarize(run)
    db.commit()
    db.refresh(run)
    return run


# ---- ingestion -------------------------------------------------------------------------

USER_PROVIDED_SOURCES = ("user_job_url", "file_import", "browser_clipper")


def ingest_normalized(db: Session, user: User, run: DiscoveryRun, items: Iterable[NormalizedJob], matcher: UserMatcher | None,
                      *, notify_min_score: float | None = None, explicit_sources: bool = False) -> list[UserJob]:
    """explicit_sources: the user chose these sources for this run (a saved search), so platform toggles don't apply."""
    """The single ingest path for every source: dedup, add to the user's feed, score, notify once."""
    from backend.services import notification_service

    enabled = preference_service.enabled_platform_names(db, user)
    out: list[UserJob] = []
    for nj in items:
        platform = nj.platform
        _stat(run, platform, "records_seen")
        run.jobs_found += 1
        # Platform toggles govern the LinkedIn/Indeed/Naukri/Adzuna sources; ATS boards are chosen per saved search.
        if not explicit_sources and platform not in enabled and nj.source not in USER_PROVIDED_SOURCES and nj.source not in ATS_SOURCES:
            _stat(run, platform, "skipped_platform_disabled")
            continue
        try:  # one malformed listing must never fail the whole run
            with db.begin_nested():
                job, job_created = upsert_normalized(db, nj)
                uj, created = add_to_feed(db, user, job, run, nj.source)
        except Exception as exc:
            run.jobs_found -= 1
            _error(db, user, run, "LISTING_SKIPPED", f"{nj.company}: {nj.title[:80]}: {type(exc).__name__}", platform=platform, job_key=nj.key)
            if nj.source in (run.source_results or {}):
                source_result(run, nj.source, failed_requests=1)
            continue
        if job_created:
            _stat(run, platform, "new_listings")
        tracked = nj.source in (run.source_results or {})
        if created:
            run.jobs_new += 1
            _stat(run, platform, "new")
        else:
            run.duplicates += 1
            _stat(run, platform, "duplicates_skipped")
        if tracked:
            source_result(run, nj.source, found=1, new=int(created), duplicates=int(not created))
        if matcher is not None and uj.status in ("new", "shortlisted") and (created or uj.match_score is None or not nj.description_is_snippet):
            try:
                matcher.apply(uj, min_score=notify_min_score)
                if uj.status == "shortlisted":
                    run.jobs_matched += 1
            except Exception as exc:  # scoring failure must not lose the job
                _error(db, user, run, "SCORING_FAILED", f"{type(exc).__name__}: {exc}", platform=platform, job_key=nj.key)
        if created and notify_min_score is not None and uj.match_score is not None and uj.match_score >= notify_min_score \
                and job.closed_at is None:
            notification_service.notify_new_match(db, user, uj, nj.source)
        out.append(uj)
    db.commit()
    return out


def ingest_postings(db: Session, user: User, run: DiscoveryRun, items: Iterable[tuple[JobPosting, date | None, str | None, bool]],
                    matcher: UserMatcher | None, source: str) -> list[UserJob]:
    """Legacy sources (clipper, URL/file import, alert emails, Adzuna) → the unified ingest path."""
    normalized = (from_posting(p, posted_at, posted_source, snippet=snippet, source=source) for p, posted_at, posted_source, snippet in items)
    return ingest_normalized(db, user, run, normalized, matcher)


def _matcher_or_none(db: Session, settings: BackendSettings, user: User, run: DiscoveryRun) -> UserMatcher | None:
    try:
        return UserMatcher(db, settings, user)
    except HTTPException as exc:
        _error(db, user, run, "PROFILE_NOT_CONFIRMED", str(exc.detail), recovery="CONFIRM_PROFILE_THEN_RESCORE")
        return None


def _posting_from_record(rec: RawJobRecord, settings: BackendSettings) -> tuple[JobPosting, date | None, str | None]:
    adapter = get_adapter(rec.platform)
    posting = JobExtractor(adapter).to_posting(rec)
    posted_at, posted_source = None, None
    if rec.posted_date:
        posted_at = parse_posted_date(rec.posted_date, timeutil.today())
        posted_source = "user_provided" if posted_at else None
    elif rec.extra.get("alert_date"):
        try:
            posted_at = parsedate_to_datetime(rec.extra["alert_date"]).astimezone(timeutil.tz()).date()
            posted_source = "alert_email"
        except (TypeError, ValueError):
            pass
    return posting, posted_at, posted_source


def import_job(db: Session, settings: BackendSettings, user: User, req: ImportJobRequest) -> tuple[DiscoveryRun, list[UserJob]]:
    data = req.model_dump(mode="json", exclude_none=True, exclude={"posted_date_source", "captured_via"})
    try:
        rec = record_from_mapping(data, source="manual")
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    source = "browser_clipper" if req.captured_via == "clipper" else "user_job_url"
    run = start_run(db, user, "manual", [source])
    posting, posted_at, posted_source = _posting_from_record(rec, settings)
    if posted_at and req.posted_date_source == "page":
        posted_source = "platform_page"
    matcher = _matcher_or_none(db, settings, user, run)
    feed = ingest_postings(db, user, run, [(posting, posted_at, posted_source, False)], matcher, source)
    return finish_run(db, run), feed


def import_file(db: Session, settings: BackendSettings, user: User, filename: str, content: bytes) -> tuple[DiscoveryRun, list[UserJob], list[str]]:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in (".json", ".csv", ".txt"):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Upload a .json, .csv or .txt job file.")
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(413, "Job files must be 2 MB or smaller.")
    run = start_run(db, user, "manual", ["file_import"])
    with tempfile.TemporaryDirectory(dir=settings.user_dir(user.id).parent if settings.user_dir(user.id).parent.exists() else None) as tmp:
        (Path(tmp) / f"import{suffix}").write_bytes(content)
        loaded = ImportInboxSource(Path(tmp)).load()
    errors = [e for f in loaded for e in f.errors]
    for e in errors:
        _error(db, user, run, "IMPORT_ERROR", e, recovery="FIX_FILE_AND_REIMPORT")
    items = []
    for rec in (r for f in loaded for r in f.records):
        try:
            posting, posted_at, posted_source = _posting_from_record(rec, settings)
            items.append((posting, posted_at, posted_source, False))
        except ValueError as exc:
            errors.append(str(exc))
            _error(db, user, run, "IMPORT_ERROR", str(exc), platform=rec.platform.value)
    matcher = _matcher_or_none(db, settings, user, run)
    feed = ingest_postings(db, user, run, items, matcher, "file_import")
    return finish_run(db, run), feed, errors


def _email_source(db: Session, settings: BackendSettings, user: User) -> tuple[EmailIntegration | None, EmailAlertSource | None]:
    integ = preference_service.get_email_integration(db, user)
    if integ is None or not integ.enabled or not integ.username or not integ.password_encrypted:
        return integ, None
    password = CredentialCipher(settings).decrypt(integ.password_encrypted)
    if not password:
        return integ, None
    cfg = EmailAlertsConfig(enabled=True, imap_host=integ.imap_host, imap_port=integ.imap_port, folder=integ.folder,
                            lookback_days=integ.lookback_days, max_messages=200)
    return integ, EmailAlertSource(cfg, username=integ.username, password=password)


def run_discovery(db: Session, settings: BackendSettings, user: User, sources: list[str] | None, trigger: str = "manual",
                  run: DiscoveryRun | None = None, email_factory=None, adzuna_client: AdzunaClient | None = None) -> DiscoveryRun:
    """Run the per-user automated sources (alert emails, Adzuna). Safe to call from a background thread."""
    wanted = sources or ["alert_email", "adzuna_api"]
    run = run or start_run(db, user, trigger, wanted)
    run_id = run.id
    try:
        matcher = _matcher_or_none(db, settings, user, run)
        legacy_sources(db, settings, user, run, wanted, matcher, email_factory=email_factory, adzuna_client=adzuna_client)
        active_connectors = [s for s in wanted if s not in ("alert_email", "adzuna_api")]
        if active_connectors:
            run_scrapling_sources(db, user, run, matcher, settings, wanted_connectors=active_connectors)
        return finish_run(db, run)
    except Exception as exc:
        log.exception("Discovery run %s failed", run_id)
        db.rollback()
        run = db.get(DiscoveryRun, run_id)
        _error(db, user, run, "DISCOVERY_FAILED", f"{type(exc).__name__}: {exc}")
        return finish_run(db, run, failed=True)


def legacy_sources(db: Session, settings: BackendSettings, user: User, run: DiscoveryRun, wanted: list[str], matcher,
                   *, email_factory=None, adzuna_client: AdzunaClient | None = None) -> None:
    """Alert emails and preference-based Adzuna. Every requested source records an outcome, including why it didn't run."""
    from backend.services import source_registry

    enabled = preference_service.platform_rows(db, user)
    if "alert_email" in wanted:
        source_result(run, "alert_email")
        integ, source = email_factory(db, user) if email_factory else _email_source(db, settings, user)
        email_platforms = [p for p in Platform if enabled.get(p.value) and enabled[p.value].enabled
                           and "alert_email" in (enabled[p.value].discovery_sources or [])]
        if source is None:
            source_result(run, "alert_email", status="not_configured",
                          message="No mailbox is connected. Add one under Settings → Job-alert email to read LinkedIn, Indeed and Naukri alerts.")
            if email_platforms:
                _error(db, user, run, "EMAIL_NOT_CONFIGURED", "Job-alert email is selected but the mailbox is not configured in Settings.",
                       recovery="CONFIGURE_EMAIL")
        elif not email_platforms:
            source_result(run, "alert_email", status="not_configured",
                          message="A mailbox is connected, but no platform has 'Job-alert email' selected under Settings → Platforms.")
        else:
            items, failures = [], 0
            for p in email_platforms:
                try:
                    for rec in source.fetch(p):
                        posting, posted_at, posted_source = _posting_from_record(rec, settings)
                        items.append((posting, posted_at, posted_source, False))
                except PlatformError as exc:
                    failures += 1
                    _error(db, user, run, "EMAIL_SOURCE", str(exc), platform=p.value)
            if failures == len(email_platforms):
                source_result(run, "alert_email", status="failed", failed_requests=failures,
                              message=f"Could not read the mailbox: {run.error_details[-1]['message']}")
            else:
                source_result(run, "alert_email", status="partial" if failures else "ok", failed_requests=failures)
                ingest_postings(db, user, run, items, matcher, "alert_email")
            source_registry.record(db, "alert_email", ok=failures < len(email_platforms),
                                   error=None if failures < len(email_platforms) else run.error_details[-1]["message"])
            try:
                _confirm_from_emails(db, user, source)
            except PlatformError as exc:
                _error(db, user, run, "EMAIL_VERIFICATION", str(exc))
            if integ is not None:
                integ.last_checked_at = utcnow()
                integ.last_error = "; ".join(e["message"] for e in run.error_details if e["type"].startswith("EMAIL")) or None

    if "adzuna_api" in wanted:
        source_result(run, "adzuna_api")
        adz = enabled.get(preference_service.ADZUNA)
        if not settings.adzuna_enabled and adzuna_client is None:
            source_result(run, "adzuna_api", status="not_configured",
                          message="Adzuna API credentials are not configured on this server (ADZUNA_APP_ID / ADZUNA_APP_KEY).")
            if adz and adz.enabled:
                _error(db, user, run, "ADZUNA_NOT_CONFIGURED", "Adzuna is not configured on this server.", platform="Adzuna")
        elif not (adz and adz.enabled):
            source_result(run, "adzuna_api", status="disabled", message="Adzuna is turned off in your Settings → Platforms.")
        else:
            client = adzuna_client or AdzunaClient(settings.adzuna_app_id, settings.adzuna_app_key, settings.adzuna_country)  # type: ignore[arg-type]
            before = len(run.error_details or [])
            items = _adzuna_items(db, user, run, client, settings)
            errors = (run.error_details or [])[before:]
            api_errors = [e for e in errors if e["type"] == "ADZUNA_API"]
            if api_errors and not items:
                source_result(run, "adzuna_api", status="failed", failed_requests=len(api_errors), message=api_errors[-1]["message"])
                source_registry.record(db, "adzuna_api", ok=False, error=api_errors[-1]["message"])
            elif any(e["type"] == "ADZUNA_NO_TITLES" for e in errors):
                source_result(run, "adzuna_api", status="not_configured", message="Add preferred job titles to search Adzuna.")
            else:
                source_result(run, "adzuna_api", status="partial" if api_errors else "ok", failed_requests=len(api_errors))
                source_registry.record(db, "adzuna_api", ok=True)
                ingest_postings(db, user, run, items, matcher, "adzuna_api")


def run_scrapling_sources(db: Session, user: User, run: DiscoveryRun, matcher, settings: BackendSettings, wanted_connectors: list[str] | None = None) -> None:
    """Execute multi-source discovery using Scrapling connectors for permitted sources."""
    from backend.services.connectors import registry

    prefs = preference_service.get_preferences(db, user)
    titles = ((prefs.job_titles if prefs else []) + (prefs.title_keywords if prefs else [])) or []

    connectors_to_run = wanted_connectors or ["remotive", "himalayas", "remoteok", "arbeitnow", "ncs_india", "government", "academic"]

    for src_id in connectors_to_run:
        source_result(run, src_id)
        try:
            query_str = titles[0] if titles else None
            criteria = {"query": query_str, "limit": 25} if query_str else {"limit": 25}
            jobs = registry.run_connector(src_id, criteria=criteria)
            if jobs:
                source_result(run, src_id, status="ok", jobs_found=len(jobs))
                ingest_normalized(db, user, run, jobs, matcher, src_id)
            else:
                source_result(run, src_id, status="ok", jobs_found=0)
        except Exception as exc:
            log.warning("Scrapling connector %s execution error: %s", src_id, exc)
            source_result(run, src_id, status="failed", message=str(exc))



def _adzuna_items(db: Session, user: User, run: DiscoveryRun, client: AdzunaClient, settings: BackendSettings):
    prefs = preference_service.get_preferences(db, user)
    titles = ((prefs.job_titles if prefs else []) + (prefs.title_keywords if prefs else []))[:6] or []
    locations = [l for l in (prefs.locations if prefs else []) if "remote" not in l.lower()][:2] or [None]
    if not titles:
        _error(db, user, run, "ADZUNA_NO_TITLES", "Add preferred job titles to search Adzuna.", platform="Adzuna", recovery="UPDATE_PREFERENCES")
        return []
    seen: set[str] = set()
    items = []
    for title in titles:
        for loc in locations:
            try:
                results = adzuna_postings(client, settings, title, loc, max_days_old=2)
            except AdzunaError as exc:
                _error(db, user, run, "ADZUNA_API", str(exc), platform="Adzuna")
                return items
            for item in results:
                if item[0].job_key not in seen:
                    seen.add(item[0].job_key)
                    items.append(item)
    return items


def adzuna_postings(client: AdzunaClient, settings: BackendSettings, title: str, location: str | None, *, max_days_old: int = 2,
                    results: int = 20) -> list[tuple[JobPosting, date | None, str | None, bool]]:
    """One Adzuna search → (posting, posted date, date source, is_snippet). Raises AdzunaError."""
    analyzer = JDAnalyzer(resume_service.taxonomy(settings))
    items = []
    for a in client.search(title, location, max_days_old=max_days_old, results=results):
        if not a.url:
            continue
        analysis = analyzer.analyze(a.description, title=a.title)
        sal = None
        if a.salary_min or a.salary_max:
            lo, hi = (round(x / 1e5, 1) if x else None for x in (a.salary_min, a.salary_max))
            sal = f"{lo or '?'}-{hi or '?'} LPA"
        posting = JobPosting(
            job_key=f"adzuna:{a.id}", platform=Platform.LINKEDIN, platform_job_id=a.id, company=a.company, title=a.title,
            url=a.url, location=a.location, work_mode=analysis.work_mode,
            employment_type={"full_time": "Full-time", "part_time": "Part-time"}.get(a.contract_time or "") or
            ("Contract" if a.contract_type == "contract" else None),
            experience_required=analysis.experience_text, exp_min_years=analysis.exp_min, exp_max_years=analysis.exp_max,
            salary_range=sal, salary_min_lpa=round(a.salary_min / 1e5, 2) if a.salary_min else None,
            salary_max_lpa=round(a.salary_max / 1e5, 2) if a.salary_max else None, description=a.description,
            required_skills=analysis.required_skills, preferred_skills=analysis.preferred_skills,
            education_requirements=analysis.education, mandatory_qualifications=analysis.mandatory_qualifications,
            application_method="Apply on the original listing (opened via Adzuna)", source="adzuna_api",
            fingerprint=fingerprint(a.company, a.title),
        )
        items.append((posting, a.created, "platform_api" if a.created else None, True))
    return items


def _confirm_from_emails(db: Session, user: User, source: EmailAlertSource) -> int:
    """Platform confirmation emails independently verify a submission."""
    from backend.services import application_service
    from applications.submission_verifier import match_confirmation_email

    pending = db.execute(select(Application).where(Application.user_id == user.id,
                                                   Application.status.in_(["PREPARED", "OPENED", "CONFIRMATION_PENDING"]))).unique().scalars().all()
    confirmed = 0
    for platform, mail in confirmation_emails(source):
        for app in pending:
            if app.status == "SUBMITTED" or app.job.platform != platform.value:
                continue
            if match_confirmation_email(mail.subject, mail.body, app.job.company or "", app.job.title or ""):
                application_service.mark_submitted(db, user, app, reference_id=None, confirmation_text=mail.subject[:500],
                                                   source=f"email:{hashlib.sha1(mail.message_id.encode()).hexdigest()[:12]}")
                confirmed += 1
    db.commit()
    return confirmed


def posted_label(job: Job, today: date | None = None) -> str:
    today = today or timeutil.today()
    if not job.posted_at:
        return "Unknown"
    if job.posted_at_source == "alert_email":
        return f"On or before {job.posted_at.strftime('%d %b')} (alert email)"
    if posted_confidence(job.posted_at, job.posted_at_source) != "verified":
        return f"Around {job.posted_at.strftime('%d %b %Y')} (unverified)"
    days = (today - job.posted_at).days
    suffix = {"user_provided": " (reported by you)", "platform_page": " (per listing)"}.get(job.posted_at_source or "", "")
    if days == 0:
        return "Today" + suffix
    if days == 1:
        return "Yesterday" + suffix
    return f"{job.posted_at.strftime('%d %b %Y')}{suffix}"


def search_links(db: Session, user: User) -> list[dict[str, str]]:
    from backend.services.matching_service import configs_for

    _, search, _ = configs_for(preference_service.get_preferences(db, user))
    if not search.job_titles:
        return []
    enabled = preference_service.enabled_platform_names(db, user)
    links = []
    for p in Platform:
        if p.value in enabled:
            links += [{"platform": l.platform.value, "title": l.title, "location": l.location, "url": l.url}
                      for l in get_adapter(p).build_search_links(search)]
    return links

