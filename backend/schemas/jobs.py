from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

PlatformName = Literal["LinkedIn", "Indeed", "Naukri"]


class JobSourceOut(BaseModel):
    source: str
    platform: str | None
    url: str | None
    first_seen_at: datetime


class JobListing(BaseModel):
    id: int
    platform: str
    external_job_id: str | None
    company: str
    title: str
    location: str | None
    work_mode: str | None
    employment_type: str | None
    experience_required: str | None
    salary_range: str | None
    job_url: str | None
    posted_at: date | None
    posted_at_source: str | None
    posted_label: str
    description_preview: str | None
    has_full_description: bool
    source: str
    # verified (official API / listing page / you) | estimated (alert email) | unknown: never shown as "today"
    posted_at_confidence: str = "unknown"
    first_seen_at: datetime | None = None
    last_verified_at: datetime | None = None
    closed_at: datetime | None = None
    industry: str | None = None
    department: str | None = None
    seniority: str | None = None
    sponsorship_signal: str | None = None  # verified | inferred | none | unknown
    sources: list[JobSourceOut] = Field(default_factory=list)


class UserJobOut(BaseModel):
    """A job in the current user's feed (user-specific fields + the public listing)."""

    user_job_id: int
    status: str
    is_saved: bool
    match_score: float | None
    match_category: str | None
    matching_skills: list[str]
    missing_skills: list[str]
    eligibility_status: str | None
    eligibility: str | None = None  # pass | fail | unknown (v2, separate from the score)
    scoring_method: str | None
    discovered_at: datetime
    saved_at: datetime | None
    dismissed_at: datetime | None
    application_id: int | None
    application_status: str | None
    job: JobListing


class JobDetail(UserJobOut):
    description: str | None
    responsibilities: list[str]
    required_skills: list[str]
    preferred_skills: list[str]
    education_requirements: list[str]
    mandatory_qualifications: list[str]
    verification_flags: list[str]
    description_is_snippet: bool


class JobAnalysis(BaseModel):
    user_job_id: int
    overall_score: float | None
    category: str | None
    components: list[dict[str, Any]]
    matching_skills: list[str]
    missing_skills: list[str]
    missing_optional_skills: list[str]
    relevant_experience: str
    experience_gap: str
    education_match: str | None
    location_match: str | None
    responsibilities_match: list[str]
    reasons_for: list[str]
    reasons_against: list[str]
    recommendation: str
    explanation: str
    eligibility_status: str | None
    eligibility_reasons: list[str]
    scoring_method: str | None
    confidence: str | None
    notes: list[str]
    # Versioned 8-dimension breakdown (scoring_v2). `components` above is the underlying v1 matcher output.
    score_version: str | None = None
    dimensions: list[dict[str, Any]] = []
    eligibility: str | None = None  # pass | fail | unknown, separate from the suitability score
    unknown_dimensions: list[str] = []
    disclaimer: str | None = None


class JobList(BaseModel):
    items: list[UserJobOut]
    total: int
    # Jobs that match every other filter but were left out by a posting-date filter because their date is unknown.
    hidden_unknown_dates: int = 0
    page: int
    page_size: int


class ImportJobRequest(BaseModel):
    url: HttpUrl | None = None
    platform: PlatformName | None = None
    title: str | None = Field(default=None, max_length=300)
    company: str | None = Field(default=None, max_length=300)
    location: str | None = Field(default=None, max_length=300)
    description: str | None = Field(default=None, max_length=60000)
    posted_date: str | None = Field(default=None, max_length=50, description="YYYY-MM-DD or e.g. '2 days ago'")
    salary: str | None = Field(default=None, max_length=100)
    experience: str | None = Field(default=None, max_length=100)
    work_mode: str | None = Field(default=None, max_length=30)
    employment_type: str | None = Field(default=None, max_length=30)
    screening_questions: list[str] = Field(default_factory=list, max_length=30)
    # "page": the date was read from the listing page by the browser clipper (the platform's own data).
    posted_date_source: Literal["user", "page"] = "user"
    captured_via: Literal["form", "clipper"] = "form"


class DiscoverRequest(BaseModel):
    sources: list[Literal["alert_email", "adzuna_api"]] | None = None


class DiscoveryRunOut(BaseModel):
    id: int
    trigger: str
    status: str
    sources: list[str]
    started_at: datetime
    completed_at: datetime | None
    jobs_found: int
    jobs_new: int
    jobs_matched: int
    duplicates: int
    error_details: list[dict[str, Any]]
    platform_stats: dict[str, Any]
    saved_search_id: int | None = None
    source_results: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None


class ImportResult(BaseModel):
    run: DiscoveryRunOut
    user_job_ids: list[int]
    errors: list[str]


class SearchLinkOut(BaseModel):
    platform: str
    title: str
    location: str
    url: str
