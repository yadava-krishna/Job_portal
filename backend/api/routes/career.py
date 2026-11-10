"""Career graph API: snapshot and next step, career goals, consent, research feedback, skills and evidence, gaps,
learning resources and sessions."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from backend.api.deps import CurrentUser, DbSession, SettingsDep
from backend.models import Gap, JobPreference
from backend.services import career_service as cs
from backend.services import learning_service as ls
from backend.services import platform_service as ps

router = APIRouter(tags=["career"])


# ---------- snapshot / goals / consent / feedback ----------

@router.get("/career/snapshot")
def snapshot(user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict:
    return cs.snapshot(db, settings, user)


class GoalsIn(BaseModel):
    search_mode: Literal["india", "international", "both"] = "india"
    target_countries: list[str] = Field(default_factory=list, max_length=20)
    seniority: Literal["intern", "entry", "junior", "mid", "senior", "lead", "manager", "director"] | None = None
    open_to_relocation: bool | None = None
    work_authorization: list[str] = Field(default_factory=list, max_length=20)
    needs_sponsorship: bool | None = None

    @field_validator("target_countries", "work_authorization")
    @classmethod
    def _codes(cls, v: list[str]) -> list[str]:
        out = [c.strip().upper() for c in v if c.strip()]
        if any(len(c) != 2 or not c.isalpha() for c in out):
            raise ValueError("use two-letter country codes, e.g. IN, GB, DE")
        return list(dict.fromkeys(out))


def _goals_out(p: JobPreference | None) -> dict:
    return {"search_mode": p.search_mode if p else "india", "target_countries": p.target_countries if p else [],
            "seniority": p.seniority if p else None, "open_to_relocation": p.open_to_relocation if p else None,
            "work_authorization": p.work_authorization if p else [], "needs_sponsorship": p.needs_sponsorship if p else None}


@router.get("/career-goals")
def get_goals(user: CurrentUser, db: DbSession) -> dict:
    return _goals_out(db.execute(select(JobPreference).where(JobPreference.user_id == user.id)).scalar_one_or_none())


@router.put("/career-goals")
def put_goals(body: GoalsIn, user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict:
    from backend.services import matching_service

    p = db.execute(select(JobPreference).where(JobPreference.user_id == user.id)).scalar_one_or_none()
    if p is None:
        p = JobPreference(user_id=user.id)
        db.add(p)
    for k, v in body.model_dump().items():
        setattr(p, k, v)
    if body.search_mode == "india" and not body.work_authorization:
        p.work_authorization = ["IN"]
    db.commit()
    try:  # goals change eligibility and the work-authorisation dimension: re-score the feed
        matching_service.rescore_user(db, settings, user)
    except Exception:
        pass
    return _goals_out(p)


class ConsentIn(BaseModel):
    granted: bool


@router.get("/consents")
def get_consents(user: CurrentUser, db: DbSession) -> list[dict]:
    return ps.consents(db, user)


@router.put("/consents/{kind}")
def put_consent(kind: str, body: ConsentIn, user: CurrentUser, db: DbSession) -> list[dict]:
    return ps.set_consent(db, user, kind, body.granted)


class FeedbackIn(BaseModel):
    topic: str = Field(max_length=40)
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)
    context: dict = Field(default_factory=dict)


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
def feedback(body: FeedbackIn, user: CurrentUser, db: DbSession) -> dict:
    fb = ps.add_feedback(db, user, body.topic, body.rating, body.comment, body.context)
    return {"id": fb.id, "topic": fb.topic}


@router.get("/feedback/topics")
def feedback_topics(user: CurrentUser) -> list[str]:
    return list(ps.FEEDBACK_TOPICS)


# ---------- skills & evidence ----------

def _skill_out(s) -> dict:
    return {"id": s.id, "name": s.name, "canonical": s.canonical, "state": s.state, "state_label": cs.STATE_LABELS[s.state],
            "proficiency": s.proficiency, "years": s.years, "source": s.source, "verified": s.verified,
            "evidence_supports": cs.evidence_ceiling(s),
            "evidence": [{"id": e.id, "type": e.evidence_type, "title": e.title, "url": e.url, "description": e.description,
                          "source": e.source, "occurred_on": e.occurred_on, "created_at": e.created_at} for e in s.evidence]}


@router.get("/skills")
def skills(user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict:
    cs.sync_skills_from_profile(db, settings, user)
    return {"states": [{"key": k, "label": v} for k, v in cs.STATE_LABELS.items()],
            "skills": [_skill_out(s) for s in cs.list_skills(db, user)]}


class SkillIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    proficiency: Literal["beginner", "intermediate", "advanced", "expert"] | None = None
    years: float | None = Field(default=None, ge=0, le=50)


@router.post("/skills", status_code=status.HTTP_201_CREATED)
def add_skill(body: SkillIn, user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict:
    return _skill_out(cs.add_skill(db, settings, user, body.name, body.proficiency, body.years))


class StateIn(BaseModel):
    state: str


@router.put("/skills/{skill_id}/state")
def set_state(skill_id: int, body: StateIn, user: CurrentUser, db: DbSession) -> dict:
    return _skill_out(cs.set_state(db, user, cs.owned_skill(db, user, skill_id), body.state))


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_skill(skill_id: int, user: CurrentUser, db: DbSession) -> None:
    db.delete(cs.owned_skill(db, user, skill_id))
    db.commit()


class EvidenceIn(BaseModel):
    evidence_type: Literal["course", "certificate", "project", "employment", "publication", "assessment", "practice", "other"]
    title: str = Field(min_length=2, max_length=300)
    url: str | None = Field(default=None, max_length=1000)
    description: str | None = Field(default=None, max_length=5000)
    occurred_on: date | None = None

    @field_validator("url")
    @classmethod
    def _url(cls, v):
        if v and not v.startswith(("https://", "http://")):
            raise ValueError("links must start with https://")
        return v or None


@router.post("/skills/{skill_id}/evidence", status_code=status.HTTP_201_CREATED)
def add_evidence(skill_id: int, body: EvidenceIn, user: CurrentUser, db: DbSession) -> dict:
    skill = cs.owned_skill(db, user, skill_id)
    cs.add_evidence(db, user, skill, body.evidence_type, body.title, body.url, body.description, body.occurred_on)
    db.refresh(skill)
    return _skill_out(skill)


@router.delete("/evidence/{evidence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_evidence(evidence_id: int, user: CurrentUser, db: DbSession) -> None:
    cs.delete_evidence(db, user, evidence_id)


# ---------- gaps ----------

@router.get("/gaps")
def gaps(user: CurrentUser, db: DbSession, settings: SettingsDep, refresh: bool = False, include_closed: bool = True) -> dict:
    rows = cs.generate_gaps(db, settings, user) if refresh or not cs.list_gaps(db, user) else cs.list_gaps(db, user)
    best, alts = cs.best_gap(db, user)
    if best:
        cs.mark_gap_viewed(db, user, best)
    return {"best": cs._gap_out(best) if best else None, "alternatives": [cs._gap_out(g) for g in alts],
            "gaps": [cs._gap_out(g) for g in rows if include_closed or g.status != "closed"]}


@router.get("/gaps/{gap_id}")
def gap_detail(gap_id: int, user: CurrentUser, db: DbSession) -> dict:
    g = db.execute(select(Gap).where(Gap.id == gap_id, Gap.user_id == user.id)).scalar_one_or_none()
    if g is None:
        from fastapi import HTTPException
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gap not found")
    cs.mark_gap_viewed(db, user, g)
    return {**cs._gap_out(g), "learning": ls.resources_for(db, g.canonical, g.evidence_state)}


@router.get("/jobs/{user_job_id}/gaps")
def job_gaps(user_job_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep) -> list[dict]:
    from backend.services.interview_service import owned_user_job

    return cs.job_gaps(db, settings, user, owned_user_job(db, user, user_job_id))


@router.get("/jobs/{user_job_id}/requirements")
def job_requirements(user_job_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep) -> list[dict]:
    from backend.services.interview_service import owned_user_job

    uj = owned_user_job(db, user, user_job_id)
    return [{"kind": r.kind, "text": r.text, "canonical": r.canonical, "importance": r.importance, "hard": r.hard, "years": r.years}
            for r in cs.extract_requirements(db, settings, uj.job)]


@router.post("/matches/recompute")
def recompute(user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict:
    from backend.services import matching_service

    n = matching_service.rescore_user(db, settings, user)
    cs.generate_gaps(db, settings, user)
    return {"rescored": n}


# ---------- learning ----------

@router.get("/resources")
def resources(user: CurrentUser, db: DbSession, skill: str = Query(min_length=1, max_length=120)) -> dict:
    s = db.execute(select(cs.CandidateSkill).where(cs.CandidateSkill.user_id == user.id, cs.CandidateSkill.canonical.ilike(skill))).scalar_one_or_none()
    return ls.resources_for(db, skill, s.state if s else None)


class SessionIn(BaseModel):
    resource_id: int | None = None
    gap_id: int | None = None
    skill: str | None = Field(default=None, max_length=120)


def _session_out(s) -> dict:
    return {"id": s.id, "skill": s.skill, "resource_id": s.resource_id, "gap_id": s.gap_id, "status": s.status,
            "started_at": s.started_at, "ended_at": s.ended_at, "active_minutes": s.active_seconds // 60,
            "active_seconds": s.active_seconds, "idle_seconds": s.idle_seconds, "notes": s.notes, "helpful": s.helpful}


@router.post("/learning-sessions", status_code=status.HTTP_201_CREATED)
def start_session(body: SessionIn, user: CurrentUser, db: DbSession) -> dict:
    return _session_out(ls.start(db, user, body.resource_id, body.gap_id, body.skill))


@router.get("/learning-sessions")
def list_sessions(user: CurrentUser, db: DbSession) -> dict:
    return {"sessions": [_session_out(s) for s in ls.sessions(db, user)], "stats": ls.stats(db, user)}


class BeatIn(BaseModel):
    active: bool = True


@router.post("/learning-sessions/{session_id}/heartbeat")
def session_heartbeat(session_id: int, body: BeatIn, user: CurrentUser, db: DbSession) -> dict:
    return _session_out(ls.heartbeat(db, user, session_id, body.active))


@router.post("/learning-sessions/{session_id}/pause")
def session_pause(session_id: int, user: CurrentUser, db: DbSession) -> dict:
    return _session_out(ls.pause(db, user, session_id))


@router.post("/learning-sessions/{session_id}/resume")
def session_resume(session_id: int, user: CurrentUser, db: DbSession) -> dict:
    return _session_out(ls.resume(db, user, session_id))


class CompleteIn(BaseModel):
    notes: str | None = Field(default=None, max_length=5000)
    knowledge_check: dict[str, str] = Field(default_factory=dict)
    helpful: bool | None = None
    evidence_url: str | None = Field(default=None, max_length=1000)
    evidence_title: str | None = Field(default=None, max_length=300)

    @field_validator("evidence_url")
    @classmethod
    def _url(cls, v):
        if v and not v.startswith(("https://", "http://")):
            raise ValueError("links must start with https://")
        return v or None


@router.post("/learning-sessions/{session_id}/complete")
def session_complete(session_id: int, body: CompleteIn, user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict:
    out = ls.complete(db, settings, user, session_id, body.notes, body.knowledge_check, body.helpful, body.evidence_url, body.evidence_title)
    return {"session": _session_out(out["session"]), "skill_state": out["skill_state"],
            "skill_state_label": cs.STATE_LABELS[out["skill_state"]]}
