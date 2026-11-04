"""Daily execution workflow.

1. load configuration            9. calculate match scores
2. validate the resume path     10. filter eligible jobs
3. load the candidate profile   11. prepare applications / approval tasks
4. start the run (lock + DB)    12. verify application outcomes
5. search enabled platforms     13. persist everything (SQLite, as it goes)
6. extract job details          14. generate the daily Excel report
7. deduplicate                  15. save logs
8. analyse descriptions         16. print the daily summary
"""

from __future__ import annotations

import fcntl
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypeVar

from applications.application_manager import ApplicationManager
from applications.submission_verifier import find_email_confirmations
from core import timeutil
from core.llm import LLMClient, LLMError, build_llm
from core.models import EligibilityStatus, PipelineStatus, Platform
from core.settings import Settings
from core.skills import SkillTaxonomy
from database.db import Database, row_to_posting
from discovery.sources import EmailAlertSource, ImportInboxSource, JobSource
from intelligence.eligibility import evaluate_eligibility
from intelligence.job_matcher import JobMatcher
from platforms import enabled_platforms, get_adapter
from platforms.base_platform import PlatformError, SearchLink
from reports.excel_generator import ExcelReportGenerator
from reports.summary_generator import console_summary, daily_summary
from resume.profile_builder import ProfileBuilder

log = logging.getLogger(__name__)
T = TypeVar("T")


class RunAlreadyInProgress(Exception):
    pass


class RunInterrupted(Exception):
    pass


class RunLock:
    """Exclusive, non-blocking file lock; released automatically if the process dies."""

    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+")
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._fh.close()
            self._fh = None
            raise RunAlreadyInProgress(f"Another run holds {self.path}; not starting a second one.") from exc
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(f"{os.getpid()} {timeutil.iso_now()}\n")
        self._fh.flush()

    def release(self) -> None:
        if self._fh:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None


def with_retry(fn: Callable[[], T], *, attempts: int = 3, base_delay: float = 2.0, what: str = "operation",
               stop: threading.Event | None = None) -> T:
    """Retry transient PlatformError / LLMError with exponential backoff."""
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except (PlatformError, LLMError) as exc:
            if not getattr(exc, "transient", False) or attempt == attempts:
                raise
            delay = base_delay * 2 ** (attempt - 1)
            log.warning("%s failed (%s); retry %d/%d in %.0fs.", what, exc, attempt, attempts - 1, delay)
            if stop is not None and stop.wait(delay):
                raise RunInterrupted("Stop requested during retry wait") from exc
            if stop is None:
                time.sleep(delay)
    raise AssertionError("unreachable")


@dataclass
class RunResult:
    run_id: int
    status: str
    report_path: str | None
    stats: dict[str, Any] = field(default_factory=dict)
    summary_text: str = ""


class DailyRunner:
    def __init__(self, settings: Settings, *, llm: LLMClient | None | str = "auto", sources: list[JobSource] | None = None,
                 stop_event: threading.Event | None = None, retry_base_delay: float = 2.0):
        self.settings = settings
        self._llm_override = llm
        self._sources_override = sources
        self.stop_event = stop_event or threading.Event()
        self.retry_base_delay = retry_base_delay

    def _check_stop(self) -> None:
        if self.stop_event.is_set():
            raise RunInterrupted("Stop requested")

    def run(self, trigger: str = "manual", attempt: int = 1) -> RunResult:
        s = self.settings
        timeutil.set_timezone(s.timezone)
        s.ensure_directories()
        lock = RunLock(s.data_root / ".run.lock")
        lock.acquire()
        db = Database(s.db_path)
        run_id = None
        try:
            stale = db.recover_stale_runs()
            if stale:
                log.warning("Recovered %d interrupted run(s): %s", len(stale), stale)
            recovered_apps = db.recover_submitting_applications()
            if recovered_apps:
                log.warning("Applications %s were interrupted mid-submission and now need verification.", recovered_apps)
            run_id = db.start_run(trigger, attempt)
            # Snapshot of the effective (secret-free) configuration used for this run.
            (s.data_root / "config" / "effective_settings.json").write_text(s.model_dump_json(indent=2), encoding="utf-8")
            log.info("Run %d started (trigger=%s, attempt=%d, mode=%s).", run_id, trigger, attempt, s.applications.mode)
            return self._execute(db, run_id)
        except RunInterrupted as exc:
            log.warning("Run %s interrupted: %s", run_id, exc)
            if run_id is not None:
                db.finish_run(run_id, "interrupted", error=str(exc))
            return RunResult(run_id or 0, "interrupted", None)
        except Exception as exc:
            log.exception("Run %s failed: %s", run_id, exc)
            if run_id is not None:
                db.add_run_error(run_id, "RUN_FAILED", f"{type(exc).__name__}: {exc}", recovery_status="RETRY_SCHEDULED" if trigger != "manual" else "RERUN_MANUALLY")
                db.finish_run(run_id, "failed", error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            db.close()
            lock.release()

    # ------------------------------------------------------------------------------
    def _execute(self, db: Database, run_id: int) -> RunResult:
        s = self.settings
        warnings: list[str] = []
        stats: dict[str, Any] = {"platforms": {}, "new_jobs": 0, "rescored": 0, "scored": 0, "scoring_failed": 0,
                                 "shortlisted": 0, "applications_created": 0, "deferred": 0}

        # 2-3. resume and profile
        profile = ProfileBuilder(s).load_or_build()
        if profile["total_experience"].get("discrepancy_note"):
            warnings.append(profile["total_experience"]["discrepancy_note"])
        for w in profile.get("warnings", []):
            log.info("Profile note: %s", w)
        candidate_id = db.upsert_candidate(s.candidate.name, profile)
        taxonomy = SkillTaxonomy.from_file(s.taxonomy_path)

        if self._llm_override == "auto":
            llm, llm_desc = build_llm(s.llm)
        else:
            llm, llm_desc = self._llm_override, (self._llm_override.name if self._llm_override else "rule_based (configured)")  # type: ignore[union-attr]
        stats["scoring"] = llm_desc
        if llm is None and "unavailable" in llm_desc:
            warnings.append(f"AI scoring unavailable - jobs scored with the {llm_desc}.")

        # 5-7. search, extract, deduplicate
        inbox, email_source, sources = self._sources()
        search_links: list[SearchLink] = []
        seen_keys: set[str] = set()
        enabled = enabled_platforms(s)
        for platform in Platform:
            self._check_stop()
            if platform not in enabled:
                stats["platforms"][platform.value] = {"records_seen": 0, "jobs": 0, "new": 0, "duplicates_skipped": 0, "status": "disabled"}
                db.add_platform_status(run_id, platform.value, "disabled", "assisted", 0, 0, None)
                if inbox:
                    for rec in inbox.fetch(platform):
                        db.add_run_error(run_id, "PLATFORM_DISABLED", f"Imported job '{rec.title}' ({rec.source_ref}) belongs to a disabled platform; the file was left in the inbox.",
                                         platform=platform.value, recovery_status="KEPT_IN_INBOX")
                continue
            adapter = get_adapter(platform, s, sources)
            search_links += adapter.build_search_links(s.search)
            try:
                result = with_retry(lambda: adapter.search_jobs(s.search), base_delay=self.retry_base_delay, what=f"{platform} search", stop=self.stop_event)
            except PlatformError as exc:
                db.add_platform_status(run_id, platform.value, "error", "assisted", 0, 0, str(exc))
                db.add_run_error(run_id, "PLATFORM_ACCESS", str(exc), platform=platform.value, recovery_status="RETRY_NEXT_RUN")
                stats["platforms"][platform.value] = {"records_seen": 0, "jobs": 0, "new": 0, "duplicates_skipped": 0, "status": "error"}
                continue
            for err in result.errors:
                db.add_run_error(run_id, "SOURCE_ERROR", err, platform=platform.value, recovery_status="RETRY_NEXT_RUN")
            p_stats = {"records_seen": result.records_seen, "jobs": len(result.jobs), "new": 0, "duplicates_skipped": 0,
                       "status": "partial" if result.errors else "ok"}
            for job in result.jobs:
                if job.job_key in seen_keys:
                    p_stats["duplicates_skipped"] += 1
                    continue
                seen_keys.add(job.job_key)
                existing = db.get_job(job.job_key)
                if existing is None:
                    db.insert_job(job, run_id)
                    p_stats["new"] += 1
                    continue
                db.touch_job(existing["id"], run_id)
                if db.enrich_job(existing["id"], job):
                    stats["rescored"] += 1
                    db.add_event(event_type="DESCRIPTION_UPDATED", job_id=existing["id"], run_id=run_id)
                    continue
                if s.applications.reprocess_seen_jobs and db.get_application_by_job_key(job.job_key) is None:
                    db.conn.execute("UPDATE jobs SET match_score=NULL, pipeline_status='DISCOVERED' WHERE id=?", (existing["id"],))
                    stats["rescored"] += 1
                    continue
                p_stats["duplicates_skipped"] += 1
            stats["new_jobs"] += p_stats["new"]
            stats["platforms"][platform.value] = p_stats
            db.add_platform_status(run_id, platform.value, p_stats["status"], "assisted", result.records_seen, len(result.jobs),
                                   "; ".join(result.errors)[:1000] or None)
            log.info("%s: %d records, %d new, %d duplicates skipped.", platform, result.records_seen, p_stats["new"], p_stats["duplicates_skipped"])
        if inbox:
            for fname, err in inbox.errors():
                db.add_run_error(run_id, "IMPORT_ERROR", err, recovery_status="FILE_MOVED_TO_FAILED")

        # 8-10. analyse, score, eligibility
        self._score(db, run_id, profile, taxonomy, llm, llm_desc, stats)

        # 11. applications
        self._check_stop()
        manager = ApplicationManager(s, db, profile, candidate_id, taxonomy, llm)
        outcome = manager.process_shortlist(run_id, stop_requested=self.stop_event.is_set)
        stats.update(applications_created=len(outcome.created), deferred=outcome.deferred,
                     cross_platform_duplicates=outcome.cross_platform_duplicates, duplicate_applications_prevented=outcome.duplicates_prevented)
        if outcome.deferred:
            warnings.append(f"{outcome.deferred} shortlisted job(s) deferred by the daily limit of {s.applications.max_per_day}.")

        # 12. verify outcomes from confirmation emails
        if email_source is not None:
            try:
                confirmed = find_email_confirmations(db, email_source, run_id)
                stats["confirmed_by_email"] = len(confirmed)
            except PlatformError as exc:
                db.add_run_error(run_id, "VERIFICATION", f"Could not check confirmation emails: {exc}", recovery_status="RETRY_NEXT_RUN")

        if inbox:
            keep = {r.source_ref.split("#")[0] for p in Platform if p not in enabled for r in inbox.fetch(p) if r.source_ref}
            inbox.archive(timeutil.today().isoformat(), keep=keep)

        # 14. report
        profile_years = profile["total_experience"]["months"] / 12
        db.save_run_stats(run_id, stats)  # so the report's daily summary includes this run
        report = ExcelReportGenerator(db, s.data_root, s.candidate.name, profile_years, s.matching.min_match_score).generate(timeutil.today(), search_links)
        db.finish_run(run_id, "completed", stats=stats, report_path=str(report))

        summary = daily_summary(db, timeutil.today())
        text = console_summary(summary, report_path=str(report), mode=s.applications.mode.value, scoring=llm_desc, warnings=warnings)
        log.info("Run %d completed.%s", run_id, text, extra={"file_only": True})
        return RunResult(run_id, "completed", str(report), stats, text)

    def _sources(self) -> tuple[ImportInboxSource | None, EmailAlertSource | None, list[JobSource]]:
        if self._sources_override is not None:
            inbox = next((x for x in self._sources_override if isinstance(x, ImportInboxSource)), None)
            email = next((x for x in self._sources_override if isinstance(x, EmailAlertSource)), None)
            return inbox, email, self._sources_override
        s = self.settings
        inbox = ImportInboxSource(s.inbox_dir) if s.sources.import_inbox.enabled else None
        email = EmailAlertSource(s.sources.email_alerts) if s.sources.email_alerts.enabled else None
        return inbox, email, [x for x in (inbox, email) if x is not None]

    def _score(self, db: Database, run_id: int, profile: dict[str, Any], taxonomy: SkillTaxonomy, llm: LLMClient | None,
               llm_desc: str, stats: dict[str, Any]) -> None:
        s = self.settings
        facts = s.load_verified_facts().get("verified_facts", {})
        matcher = JobMatcher(s.matching, s.search, profile, taxonomy, llm, llm_desc, willing_to_relocate=facts.get("willing_to_relocate"))
        rows = db.jobs_needing_scoring()
        if not rows:
            return
        log.info("Scoring %d job(s) with %s.", len(rows), llm_desc)
        today = timeutil.today()
        jobs = {row["id"]: row_to_posting(row) for row in rows}

        def score(job_id: int):
            job = jobs[job_id]
            return with_retry(lambda: matcher.score(job), base_delay=self.retry_base_delay, what=f"scoring {job.job_key}", stop=self.stop_event)

        workers = s.llm.max_concurrency if llm is not None else 1
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(score, jid): jid for jid in jobs}
            for fut in as_completed(futures):
                jid = futures[fut]
                job = jobs[jid]
                if self.stop_event.is_set():
                    for f in futures:
                        f.cancel()
                    raise RunInterrupted("Stop requested during scoring")
                try:
                    match = fut.result()
                except Exception as exc:
                    db.set_pipeline_status(jid, PipelineStatus.SCORING_FAILED, note=f"Scoring failed: {exc}")
                    db.add_run_error(run_id, "SCORING_FAILED", f"{type(exc).__name__}: {exc}", platform=job.platform.value,
                                     job_key=job.job_key, recovery_status="RETRY_NEXT_RUN")
                    stats["scoring_failed"] += 1
                    continue
                elig = evaluate_eligibility(job, s.eligibility, s.search, matcher.candidate_years, today)
                if not job.has_description and s.matching.require_description_for_shortlist:
                    status = PipelineStatus.NEEDS_DESCRIPTION
                elif elig.status == EligibilityStatus.INELIGIBLE:
                    status = PipelineStatus.NOT_ELIGIBLE
                elif match.overall_score < s.matching.min_match_score:
                    status = PipelineStatus.BELOW_THRESHOLD
                else:
                    status = PipelineStatus.SHORTLISTED
                    stats["shortlisted"] += 1
                db.save_match(jid, match, elig, status, run_id)
                stats["scored"] += 1
                log.info("Scored %s | %s - %s: %.1f (%s), %s -> %s", job.platform, job.company, job.title,
                         match.overall_score, match.category, elig.status, status)
