from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

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
    location: str | None = None
    job_url: str | None = None
    apply_state: str | None = None
    apply_state_label: str | None = None


class AutofillOut(BaseModel):
    ready: bool
    fields: dict[str, Any]
    facts: dict[str, Any]
    missing: list[dict[str, str]]
    has_resume: bool
    resume_filename: str | None = None


class AnswersRequest(BaseModel):
    questions: list[str] = Field(max_length=60)
    application_id: int | None = None  # gives the employer context (company-only answers, this application's answers)
    # What the employer's form marks: {label: "required" | "optional"}. Labels not listed are unknown (never optional).
    requirements: dict[str, Literal["required", "optional"]] = Field(default_factory=dict, max_length=120)

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
    key: str | None = None
    label: str | None = None
    confidence: float | None = None
    sensitivity: str | None = None  # public | personal | private | never
    confirm: bool = False  # a commitment (salary, notice, authorisation...): ticked by the user before assisted submission
    stale: bool = False
    value_type: str | None = None
    remember_default: bool = False


class LearnItem(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    answer: str = Field(min_length=1, max_length=2000)


class LearnRequest(BaseModel):
    """Answers the user typed on an employer form and chose, item by item, to save for next time."""
    application_id: int | None = None
    items: list[LearnItem] = Field(min_length=1, max_length=30)


class LearnOut(BaseModel):
    saved: list[str]
    errors: list[dict[str, str]]


class ProveRequest(BaseModel):
    token_id: int
    nonce: str = Field(min_length=32, max_length=128, pattern=r"^[0-9a-f]+$")
    # v2: the proof also names the host the extension is about to send its credential to (anti-relay).
    v: int = Field(default=1, ge=1, le=2)
    host: str | None = Field(default=None, max_length=255, pattern=r"^[a-z0-9.-]+(:[0-9]{1,5})?$")


class ProveOut(BaseModel):
    proof: str


class ExtPackageOut(BaseModel):
    application_id: int
    resume: dict[str, Any] | None = None
    destination_url: str | None = None
    action: str | None = None
    overrides: dict[str, str] = Field(default_factory=dict)
    cover_letter: str | None = None  # prepared text, offered for a "cover letter" text box as a suggestion to review


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
    apply_state: str | None = None
    apply_state_label: str | None = None
    apply_mode: str | None = None
    apply_step: str | None = None
    apply_counts: dict[str, int] = Field(default_factory=dict)
    apply_resume: dict[str, Any] | None = None
    confirmation: dict[str, Any] | None = None


class ApplyStateRequest(BaseModel):
    state: str = Field(max_length=30)
    mode: str | None = Field(default=None, max_length=20)
    session: dict[str, Any] = Field(default_factory=dict)
    reference_id: str | None = Field(default=None, max_length=200)


class ExtResumeOut(BaseModel):
    kind: str  # upload | studio
    id: int
    name: str
    formats: list[str]
    active: bool = False
    pages: int | None = None
    updated_at: datetime | None = None
