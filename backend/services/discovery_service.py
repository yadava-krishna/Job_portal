"""Unified per-user job discovery from permitted sources, with global job dedup and per-user feeds."""

from __future__ import annotations

import hashlib
import logging
import tempfile
from datetime import date
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Iterable

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import BackendSettings
from backend.models import Application, DiscoveryRun, EmailIntegration, Job, RunError, User, UserJob, utcnow
from backend.schemas.jobs import ImportJobRequest
from backend.security import CredentialCipher
from backend.services import preference_service, resume_service
from backend.services.adzuna import AdzunaClient, AdzunaError
from backend.services.matching_service import UserMatcher
from core import timeutil
from core.models import JobPosting, Platform, RawJobRecord
from core.settings import EmailAlertsConfig
from discovery.deduplication import fingerprint
from discovery.job_extractor import JobExtractor
from discovery.sources import EmailAlertSource, ImportInboxSource, confirmation_emails, record_from_mapping
from intelligence.jd_analyzer import JDAnalyzer, parse_posted_date
from platforms import get_adapter
from platforms.base_platform import PlatformError

log = logging.getLogger(__name__)
VERIFIED_DATE_SOURCES = ("platform_api", "platform_page", "user_provided")
ESTIMATED_DATE_SOURCES = ("alert_email",)


def posted_confidence(posted_at: date | None, source: str | None) -> str:
    """verified | estimated | unknown. Mirrors the backfill in migration 0002."""
    if posted_at is None:
        return "unknown"
    if source in VERIFIED_DATE_SOURCES:
        return "verified"
    return "estimated" if source in ESTIMATED_DATE_SOURCES else "unknown"


# ---- global job upsert ------------------------------------------------------------

def _posting_columns(p: JobPosting) -> dict[str, Any]:
    return dict(
        platform=p.platform.value, external_job_id=p.platform_job_id, fingerprint=p.fingerprint or None, company=p.company or "",
        title=p.title or "", location=p.location, work_mode=p.work_mode, employment_type=p.employment_type,
        experience_required=p.experience_required, experience_min=p.exp_min_years, experience_max=p.exp_max_years,
        salary_range=p.salary_range, salary_min_lpa=p.salary_min_lpa, salary_max_lpa=p.salary_max_lpa, description=p.description,
        required_skills=p.required_skills, preferred_skills=p.preferred_skills, education_requirements=p.education_requirements,
        mandatory_qualifications=p.mandatory_qualifications, screening_questions=p.screening_questions,
        verification_flags=p.verification_flags, job_url=p.url, application_method=p.application_method, source=p.source,
    )


def upsert_job(db: Session, key: str, cols: dict[str, Any], posted_at: date | None, posted_source: str | None,
               *, snippet: bool = False) -> tuple[Job, bool]:
    """Insert a public listing, or enrich an existing one. Returns (job, created)."""
    job = db.execute(select(Job).where(Job.job_key == key)).scalar_one_or_none()
    if job is None:
        job = Job(job_key=key, posted_at=posted_at, posted_at_source=posted_source if posted_at else None,
                  posted_at_confidence=posted_confidence(posted_at, posted_source), discovered_at=utcnow(),
                  description_is_snippet=snippet, **cols)
        db.add(job)
        try:
            db.flush()
            return job, True
        except IntegrityError:  # concurrent insert of the same listing
            db.rollback()
            job = db.execute(select(Job).where(Job.job_key == key)).scalar_one()
    # Enrich: fill gaps, upgrade a snippet to a full description, prefer a verified posting date.
    for k, v in cols.items():
        if v in (None, "", []) or k in ("source",):
            continue
        current = getattr(job, k)
        if current in (None, "", []):
            setattr(job, k, v)
    new_desc = cols.get("description")
    if new_desc and not snippet and (job.description_is_snippet or not job.description or len(new_desc) > len(job.description or "")):
        for k in ("description", "required_skills", "preferred_skills", "education_requirements", "mandatory_qualifications"):
            setattr(job, k, cols[k])
        job.description_is_snippet = False
    rank = {"platform_api": 4, "platform_page": 3, "user_provided": 2, "alert_email": 1, None: 0}
    if posted_at and rank.get(posted_source, 0) > rank.get(job.posted_at_source, 0):
        job.posted_at, job.posted_at_source = posted_at, posted_source
        job.posted_at_confidence = posted_confidence(posted_at, posted_source)
    db.flush()
    return job, False


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

def start_run(db: Session, user: User, trigger: str, sources: list[str]) -> DiscoveryRun:
    run = DiscoveryRun(user_id=user.id, trigger=trigger, sources=sources, status="running", error_details=[], platform_stats={})
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


def finish_run(db: Session, run: DiscoveryRun, failed: bool = False) -> DiscoveryRun:
    run.completed_at = utcnow()
    run.status = "failed" if failed else ("partial" if run.error_details else "completed")
    db.commit()
    db.refresh(run)
    return run


# ---- ingestion -------------------------------------------------------------------------

def ingest_postings(db: Session, user: User, run: DiscoveryRun, items: Iterable[tuple[JobPosting, date | None, str | None, bool]],
                    matcher: UserMatcher | None, source: str) -> list[UserJob]:
    enabled = preference_service.enabled_platform_names(db, user)
    out: list[UserJob] = []
    for posting, posted_at, posted_source, snippet in items:
        platform = posting.platform.value if source != "adzuna_api" else preference_service.ADZUNA
        _stat(run, platform, "records_seen")
        run.jobs_found += 1
        if platform not in enabled and source not in ("user_job_url", "file_import", "browser_clipper"):
            _stat(run, platform, "skipped_platform_disabled")
            continue
        cols = _posting_columns(posting)
        if source == "adzuna_api":
            cols["platform"] = preference_service.ADZUNA
        job, _ = upsert_job(db, posting.job_key, cols, posted_at, posted_source, snippet=snippet)
        uj, created = add_to_feed(db, user, job, run, source)
        if created:
            run.jobs_new += 1
            _stat(run, platform, "new")
        else:
            run.duplicates += 1
            _stat(run, platform, "duplicates_skipped")
        if matcher is not None and uj.status in ("new", "shortlisted") and (created or uj.match_score is None or not snippet):
            try:
                matcher.apply(uj)
                if uj.status == "shortlisted":
                    run.jobs_matched += 1
            except Exception as exc:  # scoring failure must not lose the job
                _error(db, user, run, "SCORING_FAILED", f"{type(exc).__name__}: {exc}", platform=platform, job_key=posting.job_key)
        out.append(uj)
    db.commit()
    return out


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
    """Run automated sources (alert emails, Adzuna) for one user. Safe to call from a background thread."""
    wanted = sources or ["alert_email", "adzuna_api"]
    run = run or start_run(db, user, trigger, wanted)
    try:
        matcher = _matcher_or_none(db, settings, user, run)
        enabled = preference_service.platform_rows(db, user)

        if "alert_email" in wanted:
            integ, source = email_factory(db, user) if email_factory else _email_source(db, settings, user)
            email_platforms = [p for p in Platform if enabled.get(p.value) and enabled[p.value].enabled
                               and "alert_email" in (enabled[p.value].discovery_sources or [])]
            if source is None:
                if email_platforms:
                    _error(db, user, run, "EMAIL_NOT_CONFIGURED", "Job-alert email is selected but the mailbox is not configured in Settings.",
                           recovery="CONFIGURE_EMAIL")
            else:
                items = []
                for p in email_platforms:
                    try:
                        for rec in source.fetch(p):
                            posting, posted_at, posted_source = _posting_from_record(rec, settings)
                            items.append((posting, posted_at, posted_source, False))
                    except PlatformError as exc:
                        _error(db, user, run, "EMAIL_SOURCE", str(exc), platform=p.value)
                ingest_postings(db, user, run, items, matcher, "alert_email")
                try:
                    _confirm_from_emails(db, user, source)
                except PlatformError as exc:
                    _error(db, user, run, "EMAIL_VERIFICATION", str(exc))
                if integ is not None:
                    integ.last_checked_at = utcnow()
                    integ.last_error = "; ".join(e["message"] for e in run.error_details if e["type"].startswith("EMAIL")) or None

        if "adzuna_api" in wanted:
            adz = enabled.get(preference_service.ADZUNA)
            if adz and adz.enabled:
                if not settings.adzuna_enabled and adzuna_client is None:
                    _error(db, user, run, "ADZUNA_NOT_CONFIGURED", "Adzuna is not configured on this server.", platform="Adzuna")
                else:
                    client = adzuna_client or AdzunaClient(settings.adzuna_app_id, settings.adzuna_app_key, settings.adzuna_country)  # type: ignore[arg-type]
                    ingest_postings(db, user, run, _adzuna_items(db, user, run, client, settings), matcher, "adzuna_api")
        return finish_run(db, run)
    except Exception as exc:
        log.exception("Discovery run %s failed", run.id)
        db.rollback()
        run = db.get(DiscoveryRun, run.id)
        _error(db, user, run, "DISCOVERY_FAILED", f"{type(exc).__name__}: {exc}")
        return finish_run(db, run, failed=True)


def _adzuna_items(db: Session, user: User, run: DiscoveryRun, client: AdzunaClient, settings: BackendSettings):
    prefs = preference_service.get_preferences(db, user)
    titles = ((prefs.job_titles if prefs else []) + (prefs.title_keywords if prefs else []))[:6] or []
    locations = [l for l in (prefs.locations if prefs else []) if "remote" not in l.lower()][:2] or [None]
    if not titles:
        _error(db, user, run, "ADZUNA_NO_TITLES", "Add preferred job titles to search Adzuna.", platform="Adzuna", recovery="UPDATE_PREFERENCES")
        return []
    analyzer = JDAnalyzer(resume_service.taxonomy(settings))
    seen: set[str] = set()
    items = []
    for title in titles:
        for loc in locations:
            try:
                results = client.search(title, loc, max_days_old=2, results=20)
            except AdzunaError as exc:
                _error(db, user, run, "ADZUNA_API", str(exc), platform="Adzuna")
                return items
            for a in results:
                if a.id in seen or not a.url:
                    continue
                seen.add(a.id)
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

