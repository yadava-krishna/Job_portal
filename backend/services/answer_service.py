"""Screening answers for application forms, classified so the user always knows what to review.

VERIFIED     taken from something the user confirmed (verified answers in Settings)
SUGGESTED    derived from the confirmed profile or resume (e.g. years from employment dates); review before submitting
NEEDS_INPUT  not answerable from verified information; JobPilot never guesses salary, notice, authorisation or experience
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from applications.screening_answers import ScreeningAnswerer
from backend.config import BackendSettings
from backend.models import User
from backend.services.matching_service import UserMatcher
from core.models import NEEDS_CANDIDATE_INPUT


def classify(raw: dict[str, Any]) -> dict[str, Any]:
    if raw.get("status") == NEEDS_CANDIDATE_INPUT or raw.get("answer") in (None, "", NEEDS_CANDIDATE_INPUT):
        return {"question": raw["question"], "answer": None, "source": None, "status": "NEEDS_INPUT", "reason": raw.get("source")}
    source = raw.get("source") or ""
    kind = "VERIFIED" if source.startswith(("verified_facts.", "answer_bank.")) else "SUGGESTED"
    return {"question": raw["question"], "answer": raw["answer"], "source": source, "status": kind, "reason": None}


def answer_questions(db: Session, settings: BackendSettings, user: User, questions: list[str]) -> list[dict[str, Any]]:
    if not questions:
        return []
    try:
        m = UserMatcher(db, settings, user, use_llm=False)
    except HTTPException:
        return [{"question": q, "answer": None, "source": None, "status": "NEEDS_INPUT", "reason": "confirm your profile first"}
                for q in questions]
    answerer = ScreeningAnswerer(m.profile, m.verified_facts, m.taxonomy)
    return [classify(answerer.answer(q)) for q in questions]
