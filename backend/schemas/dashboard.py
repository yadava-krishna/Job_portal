from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from backend.schemas.tracker import TodayItem


class OverviewJob(BaseModel):
    user_job_id: int
    title: str
    company: str
    match_score: float | None = None
    location: str | None = None
    salary: str | None = None
    discovered_at: datetime | None = None
    freshness: str
    eligibility_status: str | None = None


class NewJobs(BaseModel):
    count: int
    min_score: float
    days: int
    top: list[OverviewJob]


class SavedJobs(BaseModel):
    count: int
    no_longer_open: int
    top: list[OverviewJob]


class RecentSubmitted(BaseModel):
    application_id: int
    title: str
    company: str
    submitted_at: datetime | None = None
    stage: str


class UploadedResume(BaseModel):
    filename: str
    uploaded_at: datetime


class LatestVersion(BaseModel):
    id: int
    name: str
    updated_at: datetime | None = None
    status: str


class ResumeStatus(BaseModel):
    state: str  # missing | not_exported | ready
    message: str | None = None
    uploaded: UploadedResume | None = None
    profile_confirmed: bool
    versions: int
    latest: LatestVersion | None = None
    last_export_at: datetime | None = None


class SourceProblem(BaseModel):
    source: str
    label: str
    status: str
    message: str | None = None


class LastRun(BaseModel):
    id: int
    status: str
    started_at: datetime
    completed_at: datetime | None = None
    jobs_found: int
    jobs_new: int


class DiscoveryHealth(BaseModel):
    state: str  # never_run | running | ok | partial | failed | not_configured
    problems: list[SourceProblem]
    last_run: LastRun | None = None


class OverviewOut(BaseModel):
    new_jobs: NewJobs
    attention: list[TodayItem]
    upcoming: list[TodayItem]
    waiting: list[TodayItem]
    saved: SavedJobs
    recent_submitted: list[RecentSubmitted]
    resume: ResumeStatus
    discovery: DiscoveryHealth
