"""Application preparation, status transitions and mode handling."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from applications.screening_answers import ScreeningAnswerer
from applications.submission_verifier import Evidence
from core import timeutil
from core.llm import LLMClient
from core.models import NEEDS_CANDIDATE_INPUT, ApplicationStatus, EligibilityStatus, JobPosting, MatchResult, PipelineStatus
from core.settings import ApplicationMode, Settings
from database.db import Database, DuplicateApplicationError, row_to_posting
from intelligence.cover_letter import generate_cover_letter
from platforms import get_adapter
from platforms.base_platform import SecurityChallengeEncountered, SubmissionNotPermitted

log = logging.getLogger(__name__)

S = ApplicationStatus
ALLOWED_TRANSITIONS: dict[ApplicationStatus, set[ApplicationStatus]] = {
    S.AWAITING_APPROVAL: {S.APPROVED, S.PENDING_MANUAL_SUBMISSION, S.REJECTED_BY_CANDIDATE, S.SUBMITTED, S.FAILED},
    S.APPROVED: {S.SUBMITTING, S.PENDING_MANUAL_SUBMISSION, S.SUBMITTED, S.FAILED, S.REJECTED_BY_CANDIDATE},
    S.SUBMITTING: {S.SUBMITTED, S.FAILED, S.BLOCKED, S.NEEDS_VERIFICATION},
    S.PENDING_MANUAL_SUBMISSION: {S.SUBMITTED, S.FAILED, S.REJECTED_BY_CANDIDATE},
    S.NEEDS_VERIFICATION: {S.SUBMITTED, S.FAILED, S.PENDING_MANUAL_SUBMISSION},
    S.FAILED: {S.PENDING_MANUAL_SUBMISSION, S.SUBMITTED, S.REJECTED_BY_CANDIDATE},
    S.BLOCKED: {S.PENDING_MANUAL_SUBMISSION, S.SUBMITTED, S.FAILED, S.REJECTED_BY_CANDIDATE},
    S.SUBMITTED: set(),
    S.REJECTED_BY_CANDIDATE: set(),
}


class TransitionError(Exception):
    pass


def transition(db: Database, app_id: int, to: ApplicationStatus, *, event_type: str, details: str | None = None,
               run_id: int | None = None, **fields: Any) -> None:
    row = db.get_application(app_id)
    if row is None:
        raise TransitionError(f"Application {app_id} not found")
    current = ApplicationStatus(row["status"])
    if to not in ALLOWED_TRANSITIONS[current]:
        raise TransitionError(f"Application {app_id} is {current}; it cannot move to {to}.")
    db.update_application(app_id, new_status=to, expected_status=current.value, event_type=event_type, details=details, run_id=run_id, **fields)


@dataclass
class ProcessingOutcome:
    created: list[int] = field(default_factory=list)
    deferred: int = 0
    cross_platform_duplicates: int = 0
    duplicates_prevented: int = 0
    submitted: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class ApplicationManager:
    def __init__(self, settings: Settings, db: Database, profile: dict[str, Any], candidate_id: int, taxonomy, llm: LLMClient | None):
        self.settings = settings
        self.db = db
        self.profile = profile
        self.candidate_id = candidate_id
        self.llm = llm
        facts = settings.load_verified_facts().get("verified_facts", {})
        self.answerer = ScreeningAnswerer(profile, facts, taxonomy)

    @property
    def mode(self) -> ApplicationMode:
        return self.settings.applications.mode

    def process_shortlist(self, run_id: int | None, stop_requested=lambda: False) -> ProcessingOutcome:
        out = ProcessingOutcome()
        if self.mode == ApplicationMode.DISCOVERY_ONLY:
            log.info("DISCOVERY_ONLY mode: shortlisted jobs are reported but no applications are prepared.")
            return out
        limit = self.settings.applications.max_per_day
        already = self.db.applications_created_on(timeutil.today())
        for row in self.db.shortlist_without_application():
            if stop_requested():
                break
            if already + len(out.created) >= limit:
                self.db.set_pipeline_status(row["id"], PipelineStatus.LIMIT_DEFERRED, note=f"Daily limit of {limit} reached; will be prepared on a later run.")
                out.deferred += 1
                continue
            if self.settings.applications.block_cross_platform_duplicates:
                dup = self.db.active_application_for_fingerprint(row["fingerprint"], row["id"])
                if dup:
                    self.db.set_pipeline_status(row["id"], PipelineStatus.CROSS_PLATFORM_DUPLICATE,
                                                note=f"Same company and title already has application #{dup['id']} on {dup['platform']}.")
                    self.db.add_event(event_type="CROSS_PLATFORM_DUPLICATE_SKIPPED", job_id=row["id"], run_id=run_id, details=f"existing application {dup['id']}")
                    out.cross_platform_duplicates += 1
                    continue
            try:
                app_id = self.prepare(row, run_id)
            except DuplicateApplicationError:
                out.duplicates_prevented += 1
                continue
            out.created.append(app_id)
            if self.mode == ApplicationMode.PERMITTED_AUTO_APPLY:
                if self.try_submit(app_id, run_id):
                    out.submitted.append(app_id)
        return out

    def prepare(self, job_row, run_id: int | None) -> int:
        """Create the application record and its package. Raises DuplicateApplicationError."""
        job = row_to_posting(job_row)
        match = MatchResult.model_validate_json(job_row["match_json"]) if job_row["match_json"] else None
        cl_cfg = self.settings.applications.cover_letter
        cover_letter, cl_method = None, None
        if cl_cfg.enabled or (cl_cfg.generate_when_required and job.cover_letter_required):
            cover_letter, cl_method = generate_cover_letter(job, self.profile, match, self.llm)
        screening = self.answerer.answer_all(job.screening_questions)
        adapter = get_adapter(job.platform, self.settings)
        checklist = self._checklist(job, job_row, adapter)

        needs_review = job_row["eligibility_status"] == EligibilityStatus.NEEDS_REVIEW.value
        if self.mode == ApplicationMode.APPROVAL_REQUIRED or (self.mode == ApplicationMode.PERMITTED_AUTO_APPLY and needs_review):
            status = S.AWAITING_APPROVAL
        elif self.mode == ApplicationMode.PERMITTED_AUTO_APPLY and adapter.capabilities.automated_apply:
            status = S.APPROVED
        else:
            status = S.PENDING_MANUAL_SUBMISSION

        app_id = self.db.create_application(
            job_row["id"], self.candidate_id, status, self.mode.value, run_id,
            resume_path=self.profile["resume"]["path"], resume_sha256=self.profile["resume"]["sha256"],
            cover_letter=cover_letter, screening_json=json.dumps(screening, ensure_ascii=False),
        )
        package = {
            "application_id": app_id,
            "prepared_at": timeutil.iso_now(),
            "mode": self.mode.value,
            "status": status.value,
            "job": job.model_dump(mode="json", exclude={"description"}),
            "match": match.model_dump() if match else None,
            "resume": {"path": self.profile["resume"]["path"], "sha256": self.profile["resume"]["sha256"]},
            "cover_letter": cover_letter,
            "cover_letter_method": cl_method,
            "screening": screening,
            "needs_candidate_input": [s["question"] for s in screening if s["status"] == NEEDS_CANDIDATE_INPUT],
            "pre_submission_checklist": checklist,
            "submission": adapter.capabilities.application_method,
        }
        path = self._write_package(package, job, job_row["description"])
        self.db.conn.execute("UPDATE applications SET package_path=? WHERE id=?", (str(path), app_id))
        if self.mode == ApplicationMode.PERMITTED_AUTO_APPLY and not adapter.capabilities.automated_apply:
            self.db.add_event(event_type="AUTO_APPLY_UNAVAILABLE", application_id=app_id, job_id=job_row["id"], run_id=run_id,
                              details=f"{job.platform} has no authorised automated submission; switched to assisted submission.")
        log.info("Prepared application #%d (%s) for %s - %s [%s].", app_id, status, job.company, job.title, job.platform)
        return app_id

    def try_submit(self, app_id: int, run_id: int | None) -> bool:
        """Submit through an authorised mechanism, if the platform declares one. Returns True only on verified success."""
        row = self.db.get_application(app_id)
        if row is None or row["status"] != S.APPROVED.value:
            return False
        job_row = self.db.get_job(row["job_key"])
        job = row_to_posting(job_row)
        adapter = get_adapter(job.platform, self.settings)
        if not adapter.capabilities.automated_apply:
            transition(self.db, app_id, S.PENDING_MANUAL_SUBMISSION, event_type="ASSISTED_FALLBACK", run_id=run_id,
                       details="No authorised automated submission mechanism; candidate must submit.")
            return False
        package = json.loads(Path(row["package_path"]).read_text(encoding="utf-8")) if row["package_path"] else {}
        transition(self.db, app_id, S.SUBMITTING, event_type="SUBMISSION_STARTED", run_id=run_id)
        try:
            result = adapter.submit_application(job, package)
        except SecurityChallengeEncountered as exc:
            transition(self.db, app_id, S.BLOCKED, event_type="SECURITY_CHALLENGE", details=str(exc), run_id=run_id, error=str(exc))
            return False
        except SubmissionNotPermitted as exc:
            transition(self.db, app_id, S.NEEDS_VERIFICATION, event_type="SUBMISSION_REFUSED", details=str(exc), run_id=run_id, error=str(exc))
            return False
        except Exception as exc:  # outcome unknown: never retry automatically
            transition(self.db, app_id, S.NEEDS_VERIFICATION, event_type="SUBMISSION_ERROR", details=repr(exc), run_id=run_id, error=repr(exc))
            return False
        if not result.get("confirmed"):
            transition(self.db, app_id, S.NEEDS_VERIFICATION, event_type="SUBMISSION_UNCONFIRMED", details=json.dumps(result)[:500], run_id=run_id)
            return False
        self.record_submission(self.db, app_id, Evidence(result.get("reference_id"), result.get("confirmation_text"), f"platform:{job.platform}"), run_id=run_id)
        return True

    @staticmethod
    def record_submission(db: Database, app_id: int, evidence: Evidence, run_id: int | None = None) -> None:
        details = f"source={evidence.source}" + (f"; reference={evidence.reference_id}" if evidence.reference_id else "")
        transition(db, app_id, S.SUBMITTED, event_type="SUBMISSION_CONFIRMED", details=details, run_id=run_id,
                   submitted_at=timeutil.iso_now(), reference_id=evidence.reference_id,
                   confirmation_text=evidence.confirmation_text, confirmation_source=evidence.source)

    # ---- helpers ------------------------------------------------------------------
    def _checklist(self, job: JobPosting, job_row, adapter) -> list[dict[str, str]]:
        items = [
            {"check": "Listing is on the official platform domain", "status": "PASS" if adapter.is_official_url(job.url) else "CHECK MANUALLY"},
            {"check": "Employer name present", "status": "PASS" if job.company else "CHECK MANUALLY"},
            {"check": "Job is still open", "status": "CHECK MANUALLY (job pages are not fetched automatically)"},
            {"check": "Employer is genuine (company page, no fees requested)", "status": "CHECK MANUALLY"},
        ]
        elig = json.loads(job_row["eligibility_json"]) if job_row["eligibility_json"] else {}
        if elig.get("status") == EligibilityStatus.NEEDS_REVIEW.value:
            for r in elig.get("reasons", []):
                items.append({"check": r, "status": "REVIEW"})
        for flag in job.verification_flags:
            items.append({"check": flag, "status": "REVIEW"})
        return items

    def _write_package(self, package: dict[str, Any], job: JobPosting, description: str | None) -> Path:
        day_dir = self.settings.packages_dir / timeutil.today().isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{package['application_id']:05d}_{job.platform}_{job.company}_{job.title}")[:100]
        json_path = day_dir / f"{safe}.json"
        json_path.write_text(json.dumps(package, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        (day_dir / f"{safe}.txt").write_text(render_package_text(package, description), encoding="utf-8")
        return json_path


def render_package_text(p: dict[str, Any], description: str | None) -> str:
    job, match = p["job"], p.get("match") or {}
    lines = [
        f"APPLICATION PACKAGE #{p['application_id']}  ({p['status']}, mode {p['mode']})",
        "=" * 72,
        f"Job:       {job['title']} at {job['company']}",
        f"Platform:  {job['platform']}   Job ID: {job.get('platform_job_id') or '-'}",
        f"URL:       {job.get('url') or '-'}",
        f"Location:  {job.get('location') or '-'} ({job.get('work_mode') or 'mode not stated'})",
        f"Match:     {match.get('overall_score', '-')} - {match.get('category', '-')}",
        f"Submit:    {p['submission']}",
        f"Resume:    {p['resume']['path']}",
        "",
        "PRE-SUBMISSION CHECKLIST",
        *[f"  [{c['status']}] {c['check']}" for c in p["pre_submission_checklist"]],
        "",
        "SCREENING ANSWERS",
        *[f"  Q: {s['question']}\n  A: {s['answer']}   ({s['source']})" for s in p["screening"]],
    ]
    if p["needs_candidate_input"]:
        lines += ["", "NEEDS YOUR INPUT BEFORE SUBMITTING:", *[f"  - {q}" for q in p["needs_candidate_input"]]]
    if p.get("cover_letter"):
        lines += ["", f"COVER LETTER ({p['cover_letter_method']})", "-" * 72, p["cover_letter"]]
    if match:
        lines += ["", "WHY THIS JOB", f"  Matching skills: {', '.join(match.get('matching_skills', [])) or '-'}",
                  f"  Missing skills:  {', '.join(match.get('missing_skills', [])) or '-'}", f"  {match.get('recommendation', '')}"]
    lines += ["", "AFTER YOU SUBMIT, record it with:",
              f"  python main.py mark-submitted {p['application_id']} --reference <ID> --confirmation \"<confirmation text>\""]
    if description:
        lines += ["", "JOB DESCRIPTION", "-" * 72, description]
    return "\n".join(lines) + "\n"
