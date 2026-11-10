"""Interview preparation and practice, interview feedback, rejections and funnel, AI mentor and reflection,
human mentoring (candidate and mentor sides), and international mobility."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from backend.api.deps import CurrentUser, DbSession, SettingsDep
from backend.models import User
from backend.services import application_service
from backend.services import international_service as intl
from backend.services import interview_service as iv
from backend.services import mentor_service as ms

router = APIRouter(tags=["growth"])


# ---------- interview prep ----------

def _practice_out(p) -> dict:
    return {"id": p.id, "title": p.title, "user_job_id": p.user_job_id, "application_id": p.application_id, "status": p.status,
            "questions": p.questions, "answers": p.answers, "feedback": p.feedback, "created_at": p.created_at,
            "completed_at": p.completed_at}


@router.get("/interview-prep/{user_job_id}")
def prep(user_job_id: int, user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict:
    uj = iv.owned_user_job(db, user, user_job_id)
    from sqlalchemy import select

    from backend.models import InterviewInsight

    insights = db.execute(select(InterviewInsight).where(InterviewInsight.user_id == user.id, InterviewInsight.company == uj.job.company)
                          .order_by(InterviewInsight.created_at.desc())).scalars().all()
    return {"job": {"user_job_id": uj.id, "title": uj.job.title, "company": uj.job.company},
            "questions": iv.generate_questions(settings, db, user, uj),
            "reference_links": iv.reference_links(uj.job.company or "", uj.job.title or ""),
            "reference_note": "These open the sites' own search pages. JobPilot doesn't copy their content; save what you find useful below.",
            "insights": [{"id": i.id, "source": i.source, "url": i.url, "question": i.question, "note": i.note, "created_at": i.created_at} for i in insights]}


class PracticeIn(BaseModel):
    user_job_id: int


@router.post("/interview-practice", status_code=status.HTTP_201_CREATED)
def start_practice(body: PracticeIn, user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict:
    return _practice_out(iv.start_practice(settings, db, user, body.user_job_id))


@router.get("/interview-practice")
def list_practice(user: CurrentUser, db: DbSession) -> list[dict]:
    from sqlalchemy import select

    from backend.models import InterviewPractice

    rows = db.execute(select(InterviewPractice).where(InterviewPractice.user_id == user.id).order_by(InterviewPractice.created_at.desc())).scalars()
    return [_practice_out(p) for p in rows]


@router.get("/interview-practice/{practice_id}")
def get_practice(practice_id: int, user: CurrentUser, db: DbSession) -> dict:
    return _practice_out(iv.owned_practice(db, user, practice_id))


class AnswerIn(BaseModel):
    question_id: str = Field(max_length=10)
    answer: str = Field(min_length=1, max_length=6000)
    self_rating: int | None = Field(default=None, ge=1, le=5)


@router.post("/interview-practice/{practice_id}/answers")
def answer(practice_id: int, body: AnswerIn, user: CurrentUser, db: DbSession) -> dict:
    return _practice_out(iv.save_answer(db, user, practice_id, body.question_id, body.answer, body.self_rating))


class InsightIn(BaseModel):
    company: str | None = Field(default=None, max_length=300)
    role: str | None = Field(default=None, max_length=300)
    source: Literal["glassdoor", "reddit", "ambitionbox", "indeed", "other", "own"]
    url: str | None = Field(default=None, max_length=1000)
    question: str | None = Field(default=None, max_length=3000)
    note: str | None = Field(default=None, max_length=3000)


@router.post("/interview-insights", status_code=status.HTTP_201_CREATED)
def add_insight(body: InsightIn, user: CurrentUser, db: DbSession) -> dict:
    i = iv.add_insight(db, user, body.model_dump())
    return {"id": i.id, "source": i.source}


class InterviewFeedbackIn(BaseModel):
    interview_type: Literal["hr", "technical", "behavioural", "case", "panel", "final"] | None = None
    outcome: Literal["scheduled", "passed", "failed", "cancelled"] | None = None
    topics: list[str] | None = Field(default=None, max_length=20)
    strengths: str | None = Field(default=None, max_length=3000)
    weaknesses: str | None = Field(default=None, max_length=3000)
    candidate_feedback: str | None = Field(default=None, max_length=5000)


@router.post("/interviews/{interview_id}/feedback")
def interview_feedback(interview_id: int, body: InterviewFeedbackIn, user: CurrentUser, db: DbSession) -> dict:
    x = iv.record_feedback(db, user, interview_id, body.model_dump())
    return {"id": x.id, "interview_type": x.interview_type, "outcome": x.outcome, "topics": x.topics, "strengths": x.strengths,
            "weaknesses": x.weaknesses, "candidate_feedback": x.candidate_feedback, "feedback_at": x.feedback_at}


# ---------- rejections, funnel, resume version on an application ----------

class RejectionIn(BaseModel):
    reason: Literal["skills_gap", "experience_level", "eligibility", "salary", "interview_performance", "position_filled",
                    "culture_fit", "no_reason_given", "other"]
    detail: str | None = Field(default=None, max_length=2000)
    known: bool = Field(description="True only if the employer actually told you this reason")


@router.post("/applications/{application_id}/rejection")
def rejection(application_id: int, body: RejectionIn, user: CurrentUser, db: DbSession) -> dict:
    app = application_service.owned_application(db, user, application_id)
    a = iv.record_rejection(db, user, app, body.reason, body.detail, body.known)
    return {"id": a.id, "stage": a.stage, "rejection_reason": a.rejection_reason, "rejection_reason_known": a.rejection_reason_known}


@router.get("/rejection-reasons")
def rejection_reasons(user: CurrentUser) -> list[dict]:
    return [{"key": k, "label": v} for k, v in iv.REJECTION_REASONS.items()]


@router.get("/analytics/funnel")
def funnel(user: CurrentUser, db: DbSession) -> dict:
    return iv.funnel(db, user)


class ResumeVersionIn(BaseModel):
    resume_version_id: int


@router.put("/applications/{application_id}/resume-version")
def attach_version(application_id: int, body: ResumeVersionIn, user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict:
    app = application_service.owned_application(db, user, application_id)
    a = application_service.attach_resume_version(db, settings, user, app, body.resume_version_id)
    return {"id": a.id, "resume_version_id": a.resume_version_id, "resume_export_id": a.resume_export_id,
            "resume_checksum": a.resume_checksum, "resume_used": a.resume_used}


# ---------- AI mentor & reflection ----------

@router.get("/mentor/plan")
def mentor_plan(user: CurrentUser, db: DbSession, settings: SettingsDep) -> dict:
    return ms.plan(db, settings, user)


class ReflectionIn(BaseModel):
    outcome: str = Field(min_length=2, max_length=3000)
    obstacle: str = Field(min_length=2, max_length=3000)
    next_action: str = Field(min_length=2, max_length=1000)
    mood: int | None = Field(default=None, ge=1, le=5)


@router.post("/mentor/reflection", status_code=status.HTTP_201_CREATED)
def reflection(body: ReflectionIn, user: CurrentUser, db: DbSession) -> dict:
    return ms.reflection_out(ms.reflect(db, user, body.outcome, body.obstacle, body.next_action, body.mood))


@router.get("/mentor/reflections")
def reflections(user: CurrentUser, db: DbSession) -> list[dict]:
    return [ms.reflection_out(r) for r in ms.reflections(db, user)]


class ActionIn(BaseModel):
    title: str = Field(min_length=2, max_length=300)
    reason: str = Field(default="", max_length=2000)
    priority: Literal["high", "medium", "low"] = "medium"
    due_on: date | None = None


@router.get("/mentor/actions")
def list_actions(user: CurrentUser, db: DbSession, include_done: bool = False) -> list[dict]:
    return [ms.action_out(a) for a in ms.actions(db, user, include_done)]


@router.post("/mentor/actions", status_code=status.HTTP_201_CREATED)
def add_action(body: ActionIn, user: CurrentUser, db: DbSession) -> dict:
    return ms.action_out(ms.add_action(db, user, body.title, body.reason, body.priority, body.due_on))


class ActionPatch(BaseModel):
    done: bool | None = None
    dismissed: bool | None = None
    due_on: date | None = None


@router.patch("/mentor/actions/{action_id}")
def patch_action(action_id: int, body: ActionPatch, user: CurrentUser, db: DbSession) -> dict:
    from backend.models import utcnow

    a = ms.owned_action(db, user, action_id)
    if body.done is not None:
        a.completed_at = utcnow() if body.done else None
    if body.dismissed:
        a.dismissed_at = utcnow()
    if body.due_on is not None:
        a.due_on = body.due_on
    db.commit()
    return ms.action_out(a)


# ---------- human mentoring: candidate side ----------

class InviteMentorIn(BaseModel):
    mentor_email: str = Field(min_length=3, max_length=320)
    scopes: list[Literal["profile", "funnel", "gaps", "actions", "applications"]] = Field(default_factory=lambda: ["funnel", "gaps", "actions"])


@router.get("/mentoring/mentors")
def my_mentors(user: CurrentUser, db: DbSession) -> dict:
    return {"mentors": ms.candidate_assignments(db, user), "sessions": ms.candidate_sessions(db, user)}


@router.post("/mentoring/mentors", status_code=status.HTTP_201_CREATED)
def invite_mentor(body: InviteMentorIn, user: CurrentUser, db: DbSession) -> dict:
    a = ms.invite_mentor(db, user, body.mentor_email, list(body.scopes))
    return {"id": a.id, "status": a.status, "scopes": a.scopes}


@router.delete("/mentoring/mentors/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_mentor(assignment_id: int, user: CurrentUser, db: DbSession) -> None:
    ms.revoke(db, user, assignment_id)


class NoteIn(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    visibility: Literal["shared", "private"] = "shared"


@router.get("/mentoring/mentors/{assignment_id}/notes")
def candidate_notes(assignment_id: int, user: CurrentUser, db: DbSession) -> list[dict]:
    return ms.notes(db, user, ms._candidate_assignment(db, user, assignment_id))


@router.post("/mentoring/mentors/{assignment_id}/notes", status_code=status.HTTP_201_CREATED)
def candidate_note(assignment_id: int, body: NoteIn, user: CurrentUser, db: DbSession) -> dict:
    n = ms.add_note(db, user, assignment_id, body.body, body.visibility, as_mentor=False)
    return {"id": n.id}


class SessionIn(BaseModel):
    scheduled_at: datetime | None = None
    duration_minutes: int = Field(default=30, ge=10, le=180)
    meeting_url: str | None = Field(default=None, max_length=1000)
    agenda: str | None = Field(default=None, max_length=3000)


@router.post("/mentoring/mentors/{assignment_id}/sessions", status_code=status.HTTP_201_CREATED)
def candidate_session(assignment_id: int, body: SessionIn, user: CurrentUser, db: DbSession) -> dict:
    return ms.session_out(ms.schedule_session(db, user, assignment_id, body.model_dump(), as_mentor=False))


class SessionPatch(BaseModel):
    status: Literal["scheduled", "done", "cancelled"] | None = None
    summary: str | None = Field(default=None, max_length=5000)
    agenda: str | None = Field(default=None, max_length=3000)


@router.patch("/mentoring/sessions/{session_id}")
def patch_session(session_id: int, body: SessionPatch, user: CurrentUser, db: DbSession) -> dict:
    return ms.session_out(ms.update_session(db, user, session_id, body.model_dump()))


# ---------- human mentoring: mentor side ----------

def _mentor(user: CurrentUser) -> User:
    return ms.require_mentor(user)


@router.get("/mentor-workspace/candidates")
def mentor_candidates(db: DbSession, mentor: User = Depends(_mentor)) -> list[dict]:
    return ms.mentor_candidates(db, mentor)


@router.get("/mentor-workspace/candidates/{assignment_id}")
def mentor_candidate(assignment_id: int, db: DbSession, settings: SettingsDep, mentor: User = Depends(_mentor)) -> dict:
    return ms.candidate_summary(db, settings, mentor, assignment_id)


@router.post("/mentor-workspace/candidates/{assignment_id}/notes", status_code=status.HTTP_201_CREATED)
def mentor_note(assignment_id: int, body: NoteIn, db: DbSession, mentor: User = Depends(_mentor)) -> dict:
    return {"id": ms.add_note(db, mentor, assignment_id, body.body, body.visibility, as_mentor=True).id}


@router.post("/mentor-workspace/candidates/{assignment_id}/sessions", status_code=status.HTTP_201_CREATED)
def mentor_session(assignment_id: int, body: SessionIn, db: DbSession, mentor: User = Depends(_mentor)) -> dict:
    return ms.session_out(ms.schedule_session(db, mentor, assignment_id, body.model_dump(), as_mentor=True))


@router.post("/mentor-workspace/candidates/{assignment_id}/actions", status_code=status.HTTP_201_CREATED)
def mentor_action(assignment_id: int, body: ActionIn, db: DbSession, mentor: User = Depends(_mentor)) -> dict:
    return ms.action_out(ms.mentor_recommend(db, mentor, assignment_id, body.title, body.reason, body.priority, body.due_on))


# ---------- international ----------

@router.get("/countries")
def countries(user: CurrentUser, db: DbSession) -> list[dict]:
    return intl.countries(db)


@router.get("/visa-routes")
def visa_routes(user: CurrentUser, db: DbSession, country: str | None = None) -> list[dict]:
    return intl.routes(db, user, country)


@router.get("/country-fit")
def country_fit(user: CurrentUser, db: DbSession, country: str) -> dict:
    return intl.country_fit(db, user, country)


class WatchIn(BaseModel):
    watching: bool


@router.put("/visa-routes/{route_id}/watch")
def watch(route_id: int, body: WatchIn, user: CurrentUser, db: DbSession) -> dict:
    intl.watch(db, user, route_id, body.watching)
    return {"route_id": route_id, "watching": body.watching}
