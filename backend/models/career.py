"""Career graph additions (migration 0007): resume studio, skills/evidence/gaps, learning, interview practice,
mentor and reflection, international mobility, consent, analytics events and background job runs.

Every user-owned table carries user_id and is listed in CAREER_USER_OWNED so ownership tests cover it.
See docs/architecture/CAREER_GRAPH.md for how these connect to jobs, applications and interviews.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base
from backend.models import JSONType, TimestampMixin, utcnow

# Skill progression. Order matters: later states are stronger evidence. Courses/projects never become employment.
SKILL_STATES = ("aware", "learning", "practising", "project_evidence", "professional_experience", "interview_ready")
EVIDENCE_TYPES = ("course", "certificate", "project", "employment", "publication", "assessment", "practice", "other")
CONSENT_KINDS = ("ai_processing", "learning_tracking", "mentor_sharing", "extension", "email_notifications", "research_feedback")


# ---------- Consent & analytics ----------

class Consent(Base, TimestampMixin):
    __tablename__ = "consents"
    __table_args__ = (UniqueConstraint("user_id", "kind", name="uq_consents_user_kind"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    granted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    policy_version: Mapped[str] = mapped_column(String(20), default="1", nullable=False)


class AnalyticsEvent(Base):
    """Product events (the 16 PRD events plus operational failures). Properties never hold resume text or PII."""

    __tablename__ = "analytics_events"
    __table_args__ = (Index("ix_analytics_events_name_created", "name", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    properties: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AnalyticsDaily(Base):
    """analytics_rollup output: one row per day and metric."""

    __tablename__ = "analytics_daily"
    __table_args__ = (UniqueConstraint("day", "metric", name="uq_analytics_daily"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    metric: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[float] = mapped_column(Float, default=0, nullable=False)


class UserFeedback(Base):
    """Answers to in-app research prompts (job relevance, matching truthfulness, template trust, ...)."""

    __tablename__ = "user_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(40), nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text)
    context: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class JobRun(Base):
    """One execution of a named background job (daily_discovery, cleanup_and_retention, ...)."""

    __tablename__ = "job_runs"
    __table_args__ = (Index("ix_job_runs_name_started", "name", "started_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), default="schedule", nullable=False)  # schedule | manual | replay
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)  # running|ok|failed|skipped|blocked
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)


# ---------- Skills, evidence, requirements, gaps ----------

class CandidateSkill(Base, TimestampMixin):
    __tablename__ = "candidate_skills"
    __table_args__ = (UniqueConstraint("user_id", "canonical", name="uq_candidate_skills_user_canonical"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    canonical: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(30), default="aware", nullable=False)  # SKILL_STATES
    proficiency: Mapped[str | None] = mapped_column(String(20))  # beginner|intermediate|advanced|expert
    years: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)  # resume_parse|manual|learning|import
    confidence: Mapped[float | None] = mapped_column(Float)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence: Mapped[list[SkillEvidence]] = relationship(back_populates="skill", cascade="all, delete-orphan",
                                                         order_by="SkillEvidence.created_at")


class SkillEvidence(Base):
    __tablename__ = "skill_evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("candidate_skills.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(30), nullable=False)  # EVIDENCE_TYPES
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000))
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(30), default="manual", nullable=False)  # manual|learning_session|resume_parse
    learning_session_id: Mapped[int | None] = mapped_column(ForeignKey("learning_sessions.id", ondelete="SET NULL"))
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    occurred_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    skill: Mapped[CandidateSkill] = relationship(back_populates="evidence")


class JobRequirement(Base):
    __tablename__ = "job_requirements"
    __table_args__ = (UniqueConstraint("job_id", "kind", "canonical", name="uq_job_requirements"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # skill|experience|education|certification|language|authorization
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    canonical: Mapped[str] = mapped_column(String(120), nullable=False)
    importance: Mapped[str] = mapped_column(String(10), default="required", nullable=False)  # required|preferred
    hard: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    years: Mapped[float | None] = mapped_column(Float)
    extractor_version: Mapped[str] = mapped_column(String(20), default="rules-1", nullable=False)


class Gap(Base, TimestampMixin):
    __tablename__ = "gaps"
    __table_args__ = (UniqueConstraint("user_id", "canonical", name="uq_gaps_user_canonical"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    skill: Mapped[str] = mapped_column(String(120), nullable=False)
    canonical: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)  # high|medium|low
    score: Mapped[float] = mapped_column(Float, default=0, nullable=False)  # ranking weight
    explanation: Mapped[str] = mapped_column(Text, default="", nullable=False)
    next_action: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    job_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejection_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    job_ids: Mapped[list[int]] = mapped_column(JSONType, default=list, nullable=False)
    evidence_state: Mapped[str | None] = mapped_column(String(30))  # candidate's current SKILL_STATE, if any
    status: Mapped[str] = mapped_column(String(15), default="open", nullable=False)  # open|in_progress|closed|ignored
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MatchHistory(Base):
    """Before/after record when evidence changes a job's score (gap closure reasoning)."""

    __tablename__ = "match_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_job_id: Mapped[int] = mapped_column(ForeignKey("user_jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    score_version: Mapped[str] = mapped_column(String(20), nullable=False)
    old_score: Mapped[float | None] = mapped_column(Float)
    new_score: Mapped[float | None] = mapped_column(Float)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------- Learning ----------

class LearningResource(Base, TimestampMixin):
    __tablename__ = "learning_resources"
    __table_args__ = (UniqueConstraint("url", "skill", name="uq_learning_resources_url_skill"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    skill: Mapped[str] = mapped_column(String(120), nullable=False, index=True)  # canonical skill
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(30), nullable=False)  # documentation|course|tutorial|video|exercise|lab
    level: Mapped[str] = mapped_column(String(20), default="beginner", nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    is_free: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    credibility: Mapped[float] = mapped_column(Float, default=0.8, nullable=False)  # official docs 1.0
    source: Mapped[str] = mapped_column(String(60), default="curated", nullable=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_status: Mapped[str] = mapped_column(String(20), default="unchecked", nullable=False)  # ok|broken|unchecked
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    helpful_votes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unhelpful_votes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class LearningSession(Base, TimestampMixin):
    __tablename__ = "learning_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_id: Mapped[int | None] = mapped_column(ForeignKey("learning_resources.id", ondelete="SET NULL"), index=True)
    gap_id: Mapped[int | None] = mapped_column(ForeignKey("gaps.id", ondelete="SET NULL"))
    skill: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(15), default="active", nullable=False)  # active|paused|completed|abandoned
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    active_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idle_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    knowledge_check: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    helpful: Mapped[bool | None] = mapped_column(Boolean)


# ---------- Interview practice & intelligence ----------

class InterviewPractice(Base, TimestampMixin):
    __tablename__ = "interview_practice"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    user_job_id: Mapped[int | None] = mapped_column(ForeignKey("user_jobs.id", ondelete="SET NULL"))
    application_id: Mapped[int | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    questions: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    answers: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)  # question id -> {answer, self_rating}
    feedback: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(15), default="open", nullable=False)  # open|completed
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InterviewInsight(Base):
    """A candidate-curated reference (Glassdoor/Reddit/AmbitionBox/Indeed link, or own note) with attribution."""

    __tablename__ = "interview_insights"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company: Mapped[str | None] = mapped_column(String(300))
    role: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str] = mapped_column(String(30), nullable=False)  # glassdoor|reddit|ambitionbox|indeed|other|own
    url: Mapped[str | None] = mapped_column(String(1000))
    question: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------- Mentor & reflection ----------

class Reflection(Base, TimestampMixin):
    __tablename__ = "reflections"
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_reflections_user_week"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    obstacle: Mapped[str] = mapped_column(Text, nullable=False)
    next_action: Mapped[str] = mapped_column(Text, nullable=False)
    mood: Mapped[int | None] = mapped_column(Integer)


class MentorAction(Base, TimestampMixin):
    __tablename__ = "mentor_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)  # high|medium|low
    due_on: Mapped[date | None] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(30), default="ai_mentor", nullable=False)  # ai_mentor|human_mentor|self|reflection
    rule: Mapped[str | None] = mapped_column(String(60))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MentorAssignment(Base, TimestampMixin):
    """Candidate-consented link between a candidate and a human mentor. Revocation ends all access immediately."""

    __tablename__ = "mentor_assignments"
    __table_args__ = (UniqueConstraint("candidate_id", "mentor_id", name="uq_mentor_assignment"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    mentor_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(15), default="active", nullable=False)  # active|revoked
    scopes: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)  # profile|funnel|gaps|actions|applications
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MentorSession(Base, TimestampMixin):
    __tablename__ = "mentor_sessions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("mentor_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    meeting_url: Mapped[str | None] = mapped_column(String(1000))
    agenda: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(15), default="scheduled", nullable=False)  # scheduled|done|cancelled
    summary: Mapped[str | None] = mapped_column(Text)


class MentorNote(Base, TimestampMixin):
    __tablename__ = "mentor_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey("mentor_assignments.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    visibility: Mapped[str] = mapped_column(String(15), default="shared", nullable=False)  # shared|private (author only)


# ---------- International mobility ----------

class Country(Base, TimestampMixin):
    __tablename__ = "countries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(2), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str | None] = mapped_column(String(50))
    currency: Mapped[str | None] = mapped_column(String(3))
    official_source_url: Mapped[str | None] = mapped_column(String(1000))
    notes: Mapped[str | None] = mapped_column(Text)


class VisaRoute(Base, TimestampMixin):
    __tablename__ = "visa_routes"
    __table_args__ = (UniqueConstraint("country_code", "code", name="uq_visa_routes_country_code"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    requires_sponsorship: Mapped[bool | None] = mapped_column(Boolean)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    verified_at: Mapped[date | None] = mapped_column(Date)  # when a person checked it against the official page
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # automated source check
    effective_from: Mapped[date | None] = mapped_column(Date)
    review_by: Mapped[date | None] = mapped_column(Date)  # stale after this date
    confidence: Mapped[str] = mapped_column(String(15), default="unverified", nullable=False)  # verified|unverified|stale
    source_hash: Mapped[str | None] = mapped_column(String(64))
    source_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rules: Mapped[list[VisaRule]] = relationship(back_populates="route", cascade="all, delete-orphan", order_by="VisaRule.id")


class VisaRule(Base):
    __tablename__ = "visa_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("visa_routes.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # education|experience|language|salary|sponsorship|other
    description: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)  # e.g. {"min_years": 2}
    source_url: Mapped[str | None] = mapped_column(String(1000))
    route: Mapped[VisaRoute] = relationship(back_populates="rules")


class VisaWatch(Base):
    __tablename__ = "visa_watches"
    __table_args__ = (UniqueConstraint("user_id", "route_id", name="uq_visa_watch"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    route_id: Mapped[int] = mapped_column(ForeignKey("visa_routes.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------- Resume studio ----------

class ResumeTemplate(Base):
    __tablename__ = "resume_templates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ats_safe: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    supports_docx: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)


class ResumeVersion(Base, TimestampMixin):
    __tablename__ = "resume_versions"
    __table_args__ = (Index("ix_resume_versions_user", "user_id", "updated_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    template_id: Mapped[int] = mapped_column(ForeignKey("resume_templates.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    target_job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("resume_versions.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(15), default="draft", nullable=False)  # draft|locked|archived
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # optimistic concurrency for autosave
    settings: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)  # font_size, density, columns
    content_checksum: Mapped[str | None] = mapped_column(String(64))
    sections: Mapped[list[ResumeSection]] = relationship(back_populates="version", cascade="all, delete-orphan",
                                                         order_by="ResumeSection.position")
    template: Mapped[ResumeTemplate] = relationship(lazy="joined")


class ResumeSection(Base):
    __tablename__ = "resume_sections"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resume_version_id: Mapped[int] = mapped_column(ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)  # header|summary|experience|education|projects|skills|...
    heading: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[ResumeVersion] = relationship(back_populates="sections")
    blocks: Mapped[list[ResumeBlock]] = relationship(back_populates="section", cascade="all, delete-orphan",
                                                     order_by="ResumeBlock.position")


class ResumeBlock(Base):
    __tablename__ = "resume_blocks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("resume_sections.id", ondelete="CASCADE"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)  # entry|text|skill_group|contact
    source_profile_ref: Mapped[str | None] = mapped_column(String(80))  # e.g. "experience:12" in the master profile
    content_json: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    visible: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    section: Mapped[ResumeSection] = relationship(back_populates="blocks")
    bullets: Mapped[list[ResumeBullet]] = relationship(back_populates="block", cascade="all, delete-orphan",
                                                       order_by="ResumeBullet.position")


class ResumeBullet(Base):
    __tablename__ = "resume_bullets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    block_id: Mapped[int] = mapped_column(ForeignKey("resume_blocks.id", ondelete="CASCADE"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="user", nullable=False)  # profile|user|suggestion
    approved: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    block: Mapped[ResumeBlock] = relationship(back_populates="bullets")


class ResumeExport(Base):
    __tablename__ = "resume_exports"
    __table_args__ = (UniqueConstraint("resume_version_id", "format", "checksum", name="uq_resume_exports_cache"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_version_id: Mapped[int] = mapped_column(ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    format: Mapped[str] = mapped_column(String(10), nullable=False)  # pdf|docx
    file_key: Mapped[str] = mapped_column(String(500), nullable=False)  # storage key, never an absolute path
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)  # content checksum the file was rendered from
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ResumeFeedback(Base):
    __tablename__ = "resume_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_version_id: Mapped[int] = mapped_column(ForeignKey("resume_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    checksum: Mapped[str | None] = mapped_column(String(64))
    score: Mapped[float | None] = mapped_column(Float)
    issues_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


CAREER_USER_OWNED = (Consent, UserFeedback, CandidateSkill, SkillEvidence, Gap, MatchHistory, LearningSession,
                     InterviewPractice, InterviewInsight, Reflection, MentorAction, VisaWatch, ResumeVersion,
                     ResumeExport, ResumeFeedback)
