"""Schemas for Resume Studio, Tailoring, and ATS Diagnostics."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TailorResumeRequest(BaseModel):
    job_id: int


class TailoredResumeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    job_id: int
    title: str
    selected_bullets: list[dict[str, Any]]
    tailored_summary: str | None
    is_truthful_audited: bool
    created_at: datetime
    updated_at: datetime


class ATSDiagnosticReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    tailored_resume_id: int | None
    user_id: int
    tier1_structure_score: float
    tier2_content_score: float
    tier3_parsing_score: float
    overall_score: float
    findings: list[dict[str, str]]
    created_at: datetime
