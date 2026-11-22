"""Answer memory: the answers you confirmed for questions application forms keep asking (Settings -> Answers)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, status

from backend.api.deps import CurrentUser, DbSession, SettingsDep
from backend.schemas.applications import ClassifyIn, MemoryAnswerIn
from backend.services import answer_memory

router = APIRouter(prefix="/answers", tags=["answers"])


@router.get("/memory")
def list_memory(user: CurrentUser, db: DbSession, settings: SettingsDep, reveal: bool = False) -> list[dict[str, Any]]:
    """Your remembered answers with when you last confirmed each and their history. Salary and work-authorisation
    answers are hidden unless `reveal=true`."""
    return answer_memory.listing(db, settings, user, reveal=reveal)


@router.put("/memory")
def put_memory(body: MemoryAnswerIn, user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict[str, Any]:
    """Save or correct one answer (by canonical key, or by the question's wording). Validated; sensitive questions refused."""
    row = answer_memory.save(db, settings, user, question=body.question or "", answer=body.answer, key=body.key or None, source="settings",
                             scope_ref=body.scope_ref or None)
    return next(r for r in answer_memory.listing(db, settings, user, reveal=True) if r["key"] == row.key and r["scope_ref"] == row.scope_ref)


@router.delete("/memory/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_memory(key: str, user: CurrentUser, db: DbSession, scope_ref: str = "") -> None:
    answer_memory.forget(db, user, key, scope_ref)


@router.get("/conflicts")
def conflicts(user: CurrentUser, db: DbSession, settings: SettingsDep) -> list[dict[str, Any]]:
    """Remembered answers that disagree with your confirmed profile (e.g. after you changed jobs or moved)."""
    return answer_memory.profile_conflicts(db, settings, user)


@router.get("/catalogue")
def catalogue(user: CurrentUser) -> list[dict[str, Any]]:
    """The questions JobPilot recognises, whatever the wording."""
    return answer_memory.catalogue()


@router.post("/classify")
def classify(body: ClassifyIn, user: CurrentUser) -> dict[str, Any]:
    """How JobPilot reads one question: its canonical field, confidence, and whether it is never answered automatically."""
    m = answer_memory.classify(body.question)
    return {"question": body.question, "key": m.key, "label": m.label, "confidence": round(m.confidence, 2), "never": m.never,
            "reason": m.reason, "value_type": m.canon.value_type if m.canon else None, "notes": m.notes,
            "scope": m.scope if m.key else None}
