from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class InterviewIn(BaseModel):
    round_name: str | None = Field(default=None, max_length=100)
    scheduled_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=600)
    mode: Literal["video", "phone", "onsite"] | None = None
    location: str | None = Field(default=None, max_length=300, description="Address or meeting link")
    interviewers: str | None = Field(default=None, max_length=300)
    outcome: Literal["scheduled", "passed", "failed", "cancelled"] = "scheduled"
    notes: str | None = Field(default=None, max_length=5000)


class InterviewOut(InterviewIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    application_id: int
    company: str | None = None
    title: str | None = None


class OfferIn(BaseModel):
    base_salary: float | None = Field(default=None, ge=0)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    bonus: float | None = Field(default=None, ge=0)
    equity: str | None = Field(default=None, max_length=200)
    joining_date: date | None = None
    decision_deadline: date | None = None
    status: Literal["received", "negotiating", "accepted", "declined"] = "received"
    notes: str | None = Field(default=None, max_length=5000)


class OfferOut(OfferIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    application_id: int
    company: str | None = None
    title: str | None = None


class ContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    role: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=50)
    profile_url: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)


class ContactOut(ContactIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    application_id: int


class TodayItem(BaseModel):
    kind: str
    title: str
    detail: str | None = None
    due: datetime | date | None = None
    application_id: int | None = None
    user_job_id: int | None = None
    interview_id: int | None = None


class TodayOut(BaseModel):
    your_move: list[TodayItem]
    coming_up: list[TodayItem]
    waiting_on_them: list[TodayItem]


class HeartbeatIn(BaseModel):
    visible: bool = True
    active: bool = Field(default=True, description="There was keyboard/mouse/touch input in the last 2 minutes")


class ActivityOut(BaseModel):
    days: int
    active_minutes: int
    sessions: int
    average_session_minutes: float
    jobs_viewed: int
    jobs_saved: int
    applications_completed: int
    interviews: int
    offers: int
    per_day: list[dict[str, Any]]


class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=200)
    confirm: Literal["DELETE"]
