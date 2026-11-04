from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.schemas.jobs import JobListing

ApplicationStatusName = Literal["PREPARED", "OPENED", "CONFIRMATION_PENDING", "SUBMITTED", "FAILED", "WITHDRAWN"]
StageName = Literal["applied", "screening", "interview", "offer", "rejected", "withdrawn"]


class PrepareRequest(BaseModel):
    user_job_id: int
    include_cover_letter: bool | None = None


class ConfirmRequest(BaseModel):
    submitted: bool = Field(description="True only if you actually submitted the application on the platform")
    reference_id: str | None = Field(default=None, max_length=200)
    confirmation_text: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)


class StatusChangeRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class StageRequest(BaseModel):
    stage: StageName
    note: str | None = Field(default=None, max_length=2000)


class EventOut(BaseModel):
    id: int
    event_type: str
    from_status: str | None
    to_status: str | None
    details: str | None
    created_at: datetime


class ApplicationOut(BaseModel):
    id: int
    status: str
    stage: str | None
    user_job_id: int | None
    match_score: float | None
    match_category: str | None
    resume_used: str | None
    reference_id: str | None
    confirmation_text: str | None
    confirmation_source: str | None
    created_at: datetime
    opened_at: datetime | None
    submitted_at: datetime | None
    job: JobListing


class ApplicationDetail(ApplicationOut):
    cover_letter: str | None
    screening_answers: list[dict[str, Any]]
    checklist: list[dict[str, Any]]
    needs_candidate_input: list[str]
    notes: str | None
    events: list[EventOut]


class OpenResponse(BaseModel):
    application: ApplicationDetail
    url: str


class ReportOut(BaseModel):
    id: int
    kind: str
    report_date: date
    file_name: str
    size_bytes: int
    created_at: datetime
