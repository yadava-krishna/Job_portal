from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class PairingCodeOut(BaseModel):
    code: str
    expires_at: datetime
    expires_in_seconds: int


class PairRequest(BaseModel):
    code: str = Field(min_length=6, max_length=20)
    device_name: str = Field(default="Chrome", max_length=100)

    @field_validator("device_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join("".join(c for c in v if c.isprintable()).split())[:100]
        return v or "Chrome"


class TokenOut(BaseModel):
    token: str = Field(description="Shown once. Stored only as a hash on the server.")
    token_id: int
    expires_at: datetime
    scopes: list[str]
    user_display_name: str


class DeviceOut(BaseModel):
    id: int
    name: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None


class StatusOut(BaseModel):
    connected: bool = True
    user_display_name: str
    token_id: int
    expires_at: datetime | None
    rotate_recommended: bool
    profile_ready: bool
    missing: list[dict[str, str]]


class MatchRequest(BaseModel):
    url: str = Field(max_length=2000)


class MatchOut(BaseModel):
    supported: bool
    platform: str | None
    in_jobpilot: bool
    user_job_id: int | None = None
    title: str | None = None
    company: str | None = None
    application_id: int | None = None
    application_status: str | None = None
    submitted_at: datetime | None = None


class AutofillOut(BaseModel):
    ready: bool
    fields: dict[str, Any]
    facts: dict[str, Any]
    missing: list[dict[str, str]]
    has_resume: bool
    resume_filename: str | None = None


class AnswersRequest(BaseModel):
    questions: list[str] = Field(max_length=60)

    @field_validator("questions")
    @classmethod
    def _q(cls, v: list[str]) -> list[str]:
        return [" ".join(q.split())[:500] for q in v if q and q.strip()]


class AnswerOut(BaseModel):
    question: str
    answer: str | None
    source: str | None
    status: str  # VERIFIED | SUGGESTED | NEEDS_INPUT
    reason: str | None = None


class StartRequest(BaseModel):
    user_job_id: int


class ExtConfirmRequest(BaseModel):
    submitted: bool
    reference_id: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)


class ExtApplicationOut(BaseModel):
    application_id: int
    status: str
    submitted_at: datetime | None
    already_submitted: bool = False
