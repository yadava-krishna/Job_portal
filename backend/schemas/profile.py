from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

WorkMode = Literal["Remote", "Hybrid", "On-site"]
EmploymentType = Literal["Full-time", "Contract", "Part-time", "Internship", "Temporary"]


def _clean_list(values: list[str], max_items: int = 50, max_len: int = 120) -> list[str]:
    out: list[str] = []
    for v in values:
        v = " ".join(str(v).split())[:max_len]
        if v and v.lower() not in {o.lower() for o in out}:
            out.append(v)
    return out[:max_items]


class ResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    original_filename: str
    size_bytes: int
    page_count: int
    sha256: str
    uploaded_at: datetime
    is_active: bool


class ExperienceItem(BaseModel):
    title: str = ""
    company: str = ""
    start: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    is_current: bool = False
    bullets: list[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    degree: str | None = None
    institution: str | None = None
    university: str | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)


class ProjectItem(BaseModel):
    name: str
    bullets: list[str] = Field(default_factory=list)


class EditableProfile(BaseModel):
    """The candidate-confirmed profile. Only what the user reviewed; nothing generated."""

    full_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=200)
    headline: str | None = Field(default=None, max_length=300)
    summary: str | None = Field(default=None, max_length=5000)
    skills: list[str] = Field(default_factory=list)
    experience: list[ExperienceItem] = Field(default_factory=list)
    education: list[EducationItem] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    projects: list[ProjectItem] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)

    @field_validator("skills", "certifications", "languages")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return _clean_list(v, 100)

    @field_validator("achievements")
    @classmethod
    def _clean_ach(cls, v: list[str]) -> list[str]:
        return _clean_list(v, 50, 1000)


class ExperienceSummary(BaseModel):
    months: int
    years: float
    years_months: str
    merged_periods: list[list[str]]
    method: str
    note: str | None = None


class ProfileOut(BaseModel):
    has_resume: bool
    resume: ResumeOut | None = None
    parsed: EditableProfile | None = None
    confirmed: EditableProfile | None = None
    confirmed_at: datetime | None = None
    experience: ExperienceSummary | None = None
    parse_warnings: list[str] = Field(default_factory=list)
    verified_facts: dict[str, Any] = Field(default_factory=dict)


class VerifiedFacts(BaseModel):
    """Facts only the candidate can confirm. Null means 'ask me' (NEEDS_CANDIDATE_INPUT)."""

    current_ctc: str | None = Field(default=None, max_length=100)
    expected_ctc: str | None = Field(default=None, max_length=100)
    notice_period: str | None = Field(default=None, max_length=100)
    willing_to_relocate: bool | None = None
    work_authorization: str | None = Field(default=None, max_length=200)
    earliest_start_date: str | None = Field(default=None, max_length=100)
    shift_flexibility: str | None = Field(default=None, max_length=200)


class Weights(BaseModel):
    core_skills: float = Field(default=35, ge=0, le=100)
    experience: float = Field(default=25, ge=0, le=100)
    responsibilities: float = Field(default=20, ge=0, le=100)
    education: float = Field(default=10, ge=0, le=100)
    location: float = Field(default=10, ge=0, le=100)


class ApplicationSettings(BaseModel):
    approval_required: bool = True
    cover_letter: Literal["never", "when_required", "always"] = "when_required"
    max_prepared_per_day: int = Field(default=25, ge=1, le=200)


class Preferences(BaseModel):
    domains: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    job_titles: list[str] = Field(default_factory=list)
    title_keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    work_modes: list[WorkMode] = Field(default_factory=lambda: ["Remote", "Hybrid", "On-site"])
    salary_min: float | None = Field(default=None, ge=0)
    salary_max: float | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    experience_min: float | None = Field(default=None, ge=0, le=60)
    experience_max: float | None = Field(default=None, ge=0, le=60)
    employment_types: list[EmploymentType] = Field(default_factory=lambda: ["Full-time"])
    notice_period: str | None = Field(default=None, max_length=100)
    preferred_companies: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    min_match_score: float = Field(default=70, ge=0, le=100)
    weights: Weights = Field(default_factory=Weights)
    application_settings: ApplicationSettings = Field(default_factory=ApplicationSettings)

    @field_validator("domains", "industries", "job_titles", "title_keywords", "locations", "preferred_companies", "excluded_companies")
    @classmethod
    def _clean(cls, v: list[str]) -> list[str]:
        return _clean_list(v)

    @field_validator("salary_max")
    @classmethod
    def _salary(cls, v, info):
        lo = info.data.get("salary_min")
        if v is not None and lo is not None and v < lo:
            raise ValueError("salary_max must be >= salary_min")
        return v

    @field_validator("experience_max")
    @classmethod
    def _exp(cls, v, info):
        lo = info.data.get("experience_min")
        if v is not None and lo is not None and v < lo:
            raise ValueError("experience_max must be >= experience_min")
        return v


class PreferencesOut(Preferences):
    is_configured: bool = False


class PlatformInfo(BaseModel):
    platform: str
    enabled: bool
    discovery_sources: list[str]
    available_sources: list[dict[str, str]]
    automated_search: bool
    automated_apply: bool
    application_method: str
    notes: str


class PlatformUpdate(BaseModel):
    platform: Literal["LinkedIn", "Indeed", "Naukri", "Adzuna"]
    enabled: bool
    discovery_sources: list[Literal["browser_clipper", "user_job_url", "file_import", "alert_email", "manual_search", "adzuna_api"]] = Field(default_factory=list)


class PlatformsUpdate(BaseModel):
    platforms: list[PlatformUpdate]


class EmailIntegrationIn(BaseModel):
    enabled: bool = False
    imap_host: str = Field(default="imap.gmail.com", max_length=200, pattern=r"^[A-Za-z0-9.\-]+$")
    imap_port: int = Field(default=993, ge=1, le=65535)
    username: str | None = Field(default=None, max_length=320)
    password: str | None = Field(default=None, max_length=200, description="Leave empty to keep the stored password")
    folder: str = Field(default="INBOX", max_length=200)
    lookback_days: int = Field(default=2, ge=1, le=14)


class EmailIntegrationOut(BaseModel):
    enabled: bool
    imap_host: str
    imap_port: int
    username: str | None
    has_password: bool
    folder: str
    lookback_days: int
    last_checked_at: datetime | None
    last_error: str | None


class OnboardingStatus(BaseModel):
    resume_uploaded: bool
    profile_confirmed: bool
    preferences_saved: bool
    platforms_selected: bool
    completed: bool
