"""Companies, watchlists, saved searches and notifications."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.schemas.jobs import DiscoveryRunOut

LEGACY_ALL_BOARDS = {"greenhouse", "lever", "ashby"}
AtsName = Literal["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee"]
SearchSource = Literal["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "adzuna_api"]
WorkModeName = Literal["Remote", "Hybrid", "On-site"]
EmploymentTypeName = Literal["Full-time", "Part-time", "Contract", "Internship", "Temporary"]


def _clean_list(values: list[str], limit: int) -> list[str]:
    out: list[str] = []
    for v in values:
        v = " ".join(str(v).split())[:100]
        if v and v.lower() not in (o.lower() for o in out):
            out.append(v)
    return out[:limit]


class DirectoryCompany(BaseModel):
    name: str
    ats: AtsName
    token: str
    industry: str | None = None
    domain: str | None = None
    curated: bool = False
    company_id: int | None = None
    watched: bool = False


class CompanyOut(BaseModel):
    id: int
    name: str
    ats: AtsName
    board_token: str
    region: str | None
    industry: str | None
    domain: str | None
    origin: str
    board_url: str
    last_fetched_at: datetime | None
    last_status: str | None
    last_error: str | None
    job_count: int | None


class WatchRequest(BaseModel):
    """Either a public board/job URL, or an ATS + board token (e.g. from the directory)."""

    url: str | None = Field(default=None, max_length=500)
    ats: AtsName | None = None
    token: str | None = Field(default=None, max_length=120)
    name: str | None = Field(default=None, max_length=200)
    industry: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _one_way(self) -> "WatchRequest":
        if not self.url and not (self.ats and self.token):
            raise ValueError("Provide a job-board URL, or an ATS and board token.")
        return self


class WatchManyRequest(BaseModel):
    companies: list[WatchRequest] = Field(min_length=1, max_length=50)


class SearchCriteria(BaseModel):
    keywords: list[str] = Field(default_factory=list, description="Job titles or title keywords; empty uses your preferred titles")
    exclude_keywords: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list, description="Cities or 'India'; empty uses your preferred locations")
    remote_ok: bool = True
    industries: list[str] = Field(default_factory=list)
    experience_years: float | None = Field(default=None, ge=0, le=60)
    employment_types: list[EmploymentTypeName] = Field(default_factory=list)
    work_modes: list[WorkModeName] = Field(default_factory=list)
    company_ids: list[int] = Field(default_factory=list, max_length=100)
    use_watchlist: bool = True
    include_suggested: bool = Field(default=False, description="Also search JobPilot's curated, verified employer boards")
    related_titles: bool = Field(default=True, description="Also match related titles (e.g. Collections Analyst for AR roles)")
    sources: list[SearchSource] = Field(default_factory=lambda: ["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee"])
    max_age_days: int | None = Field(default=None, ge=1, le=365, description="Skip postings older than this (unknown dates are kept)")

    @field_validator("keywords", "exclude_keywords", "locations", "industries")
    @classmethod
    def _tidy(cls, v: list[str]) -> list[str]:
        return _clean_list(v, 25)

    @field_validator("sources")
    @classmethod
    def _sources(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("Choose at least one source.")
        out = list(dict.fromkeys(v))
        # Searches saved before SmartRecruiters and Recruitee were added stored the then-default "all job boards"
        # (exactly these three). They keep meaning "all job boards".
        if set(out) - {"adzuna_api"} == LEGACY_ALL_BOARDS:
            out = [s for s in out if s != "adzuna_api"] + ["smartrecruiters", "recruitee"] + [s for s in out if s == "adzuna_api"]
        return out


class SavedSearchIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    criteria: SearchCriteria = Field(default_factory=SearchCriteria)
    schedule: Literal["manual", "daily", "weekly"] = "daily"
    min_match_score: float | None = Field(default=None, ge=0, le=100, description="Shortlist/notify threshold; empty uses your preference")
    enabled: bool = True


class SavedSearchOut(SavedSearchIn):
    id: int
    origin: str = "user"
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_run: DiscoveryRunOut | None = None


class NotificationOut(BaseModel):
    id: int
    kind: str
    title: str
    body: str | None
    link: str | None
    occurrences: int
    read_at: datetime | None
    created_at: datetime


class NotificationPrefs(BaseModel):
    new_matches: bool = True
    delivery: Literal["immediate", "daily_digest"] = "immediate"
    min_score: float | None = Field(default=None, ge=0, le=100, description="Only notify at or above this score (default: each search's own threshold)")
    sources: list[str] = Field(default_factory=list, max_length=20, description="Only these sources (empty = all)")
    email: Literal["off"] = Field(default="off", description="E-mail delivery needs an SMTP server; not configured yet")


class NotificationList(BaseModel):
    items: list[NotificationOut]
    unread: int


class CareerUrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=500, description="Company careers page URL, e.g. https://company.com/careers")
    company_name: str | None = Field(default=None, max_length=120)


class CareerAnalysisOut(BaseModel):
    url: str
    company_name: str
    detected_ats: str | None = None
    ats_token: str | None = None
    has_json_ld: bool = False
    json_ld_count: int = 0
    discovered_feed_url: str | None = None
    discovered_sitemap_url: str | None = None
    jobs_count: int = 0
    errors: list[str] = Field(default_factory=list)


class SourceConnectorOut(BaseModel):
    source_id: str
    name: str
    domain: str
    category: str
    access_method: str
    permission_status: str
    is_discoverable: bool
    status: str
    rate_limit_rpm: int
    last_success_at: datetime | None = None
    last_error: str | None = None
    jobs_discovered: int = 0


class ATSDetectRequest(BaseModel):
    url: str = Field(min_length=8, max_length=500, description="Employer career or job board URL")


class ATSDetectResponse(BaseModel):
    url: str
    domain: str
    ats_platform: str | None = None
    board_token: str | None = None
    api_endpoint: str | None = None
    detected_sources: list[str] = Field(default_factory=list)
    has_json_ld: bool = False
    sitemap_url: str | None = None
    feed_url: str | None = None
    confidence: float = 0.0
    method: str = "url_pattern"
    error: str | None = None


class ReapResponse(BaseModel):
    reaped_count: int
    cutoff_days: int
    timestamp: datetime

