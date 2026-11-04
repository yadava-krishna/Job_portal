"""Domain models shared across modules."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Platform(StrEnum):
    LINKEDIN = "LinkedIn"
    INDEED = "Indeed"
    NAUKRI = "Naukri"

    @classmethod
    def parse(cls, value: str) -> "Platform":
        v = value.strip().lower()
        for p in cls:
            if p.value.lower() == v:
                return p
        raise ValueError(f"Unknown platform {value!r} (expected LinkedIn, Indeed or Naukri)")


class PipelineStatus(StrEnum):
    """Where a discovered job stands before any application exists."""

    DISCOVERED = "DISCOVERED"
    SCORED = "SCORED"
    SHORTLISTED = "SHORTLISTED"
    BELOW_THRESHOLD = "BELOW_THRESHOLD"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NEEDS_DESCRIPTION = "NEEDS_DESCRIPTION"
    SCORING_FAILED = "SCORING_FAILED"
    LIMIT_DEFERRED = "LIMIT_DEFERRED"
    CROSS_PLATFORM_DUPLICATE = "CROSS_PLATFORM_DUPLICATE"
    APPLICATION_CREATED = "APPLICATION_CREATED"


class ApplicationStatus(StrEnum):
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    PENDING_MANUAL_SUBMISSION = "PENDING_MANUAL_SUBMISSION"
    SUBMITTING = "SUBMITTING"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    REJECTED_BY_CANDIDATE = "REJECTED_BY_CANDIDATE"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    INELIGIBLE = "INELIGIBLE"


NEEDS_CANDIDATE_INPUT = "NEEDS_CANDIDATE_INPUT"


class RawJobRecord(BaseModel):
    """A job as received from a source, before normalisation."""

    platform: Platform
    source: str  # import_inbox | email_alert | manual
    url: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    posted_date: str | None = None
    salary: str | None = None
    experience: str | None = None
    employment_type: str | None = None
    work_mode: str | None = None
    job_id: str | None = None
    application_method: str | None = None
    screening_questions: list[str] = Field(default_factory=list)
    cover_letter_required: bool | None = None
    source_ref: str | None = None  # file name / email message id
    extra: dict[str, Any] = Field(default_factory=dict)


class JobPosting(BaseModel):
    """A normalised job ready for matching."""

    job_key: str
    platform: Platform
    platform_job_id: str | None = None
    company: str = ""
    title: str = ""
    url: str | None = None
    location: str | None = None
    work_mode: str | None = None
    employment_type: str | None = None
    experience_required: str | None = None
    exp_min_years: float | None = None
    exp_max_years: float | None = None
    salary_range: str | None = None
    salary_min_lpa: float | None = None
    salary_max_lpa: float | None = None
    posted_date: date | None = None
    description: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    education_requirements: list[str] = Field(default_factory=list)
    mandatory_qualifications: list[str] = Field(default_factory=list)
    application_method: str | None = None
    source: str = "import_inbox"
    screening_questions: list[str] = Field(default_factory=list)
    cover_letter_required: bool | None = None
    fingerprint: str = ""
    verification_flags: list[str] = Field(default_factory=list)

    @property
    def has_description(self) -> bool:
        return bool(self.description and len(self.description.strip()) >= 80)


class ComponentScore(BaseModel):
    name: str
    score: float = Field(ge=0, le=100)
    weight: float
    weighted: float
    evidence: str
    method: str  # llm | rule_based | deterministic


class MatchResult(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    category: str
    components: list[ComponentScore]
    matching_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    missing_optional_skills: list[str] = Field(default_factory=list)
    relevant_experience: str = ""
    experience_gap: str = ""
    matching_responsibilities: list[str] = Field(default_factory=list)
    reasons_for: list[str] = Field(default_factory=list)
    reasons_against: list[str] = Field(default_factory=list)
    recommendation: str = ""
    scoring_method: str = "rule_based"
    confidence: str = "medium"
    notes: list[str] = Field(default_factory=list)

    def explanation(self) -> str:
        parts = [f"{c.name}: {c.score:.0f}/100 x {c.weight:g}% = {c.weighted:.1f} ({c.evidence})" for c in self.components]
        text = "; ".join(parts) + f". Total {self.overall_score:.1f} via {self.scoring_method}"
        if self.notes:
            text += ". Notes: " + " ".join(self.notes)
        return text


class EligibilityResult(BaseModel):
    status: EligibilityStatus
    reasons: list[str] = Field(default_factory=list)
