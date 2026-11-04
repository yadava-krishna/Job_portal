"""ORM models. Every user-owned table carries user_id; queries must be scoped with it."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # user | admin. Enforced by the backend (require_admin), never only by the UI.
    role: Mapped[str] = mapped_column(String(20), default="user", server_default=text("'user'"), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(60))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set once a starter saved search has been created, so deleting it doesn't make it reappear.
    starter_search_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(300))


class Resume(Base):
    __tablename__ = "resumes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CandidateProfile(Base, TimestampMixin):
    __tablename__ = "candidate_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    active_resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    resume_path: Mapped[str | None] = mapped_column(String(500))
    parsed_profile: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    confirmed_profile: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    experience_months: Mapped[int | None] = mapped_column(Integer)
    verified_facts: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobPreference(Base, TimestampMixin):
    __tablename__ = "job_preferences"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    domains: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    industries: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    job_titles: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    title_keywords: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    locations: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    work_modes: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    experience_min: Mapped[float | None] = mapped_column(Float)
    experience_max: Mapped[float | None] = mapped_column(Float)
    employment_types: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    notice_period: Mapped[str | None] = mapped_column(String(100))
    preferred_companies: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    excluded_companies: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    min_match_score: Mapped[float] = mapped_column(Float, default=70, nullable=False)
    weights: Mapped[dict[str, float]] = mapped_column(JSONType, default=dict, nullable=False)
    application_settings: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)


class PlatformPreference(Base, TimestampMixin):
    __tablename__ = "platform_preferences"
    __table_args__ = (UniqueConstraint("user_id", "platform", name="uq_platform_pref_user_platform"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    discovery_sources: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)


class EmailIntegration(Base, TimestampMixin):
    __tablename__ = "email_integrations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    imap_host: Mapped[str] = mapped_column(String(200), default="imap.gmail.com", nullable=False)
    imap_port: Mapped[int] = mapped_column(Integer, default=993, nullable=False)
    username: Mapped[str | None] = mapped_column(String(320))
    password_encrypted: Mapped[str | None] = mapped_column(Text)
    folder: Mapped[str] = mapped_column(String(200), default="INBOX", nullable=False)
    lookback_days: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class Job(Base):
    """A public job listing. Matching, saving and applying are per user (UserJob, Application)."""

    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    external_job_id: Mapped[str | None] = mapped_column(String(100))
    fingerprint: Mapped[str | None] = mapped_column(String(300), index=True)
    company: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    title: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    location: Mapped[str | None] = mapped_column(String(300))
    work_mode: Mapped[str | None] = mapped_column(String(30))
    employment_type: Mapped[str | None] = mapped_column(String(30))
    experience_required: Mapped[str | None] = mapped_column(String(100))
    experience_min: Mapped[float | None] = mapped_column(Float)
    experience_max: Mapped[float | None] = mapped_column(Float)
    salary_range: Mapped[str | None] = mapped_column(String(100))
    salary_min_lpa: Mapped[float | None] = mapped_column(Float)
    salary_max_lpa: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text)
    description_is_snippet: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    required_skills: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    preferred_skills: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    education_requirements: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    mandatory_qualifications: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    screening_questions: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    verification_flags: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    job_url: Mapped[str | None] = mapped_column(String(1000))
    posted_at: Mapped[date | None] = mapped_column(Date, index=True)
    posted_at_source: Mapped[str | None] = mapped_column(String(20))  # platform_api | user_provided | alert_email
    # verified (API / listing page / user) | estimated (alert email, "x days ago") | unknown
    posted_at_confidence: Mapped[str | None] = mapped_column(String(12))
    discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canonical_url: Mapped[str | None] = mapped_column(String(1000), index=True)
    company_logo_url: Mapped[str | None] = mapped_column(String(1000))
    industry: Mapped[str | None] = mapped_column(String(100))
    # Cross-source identity: normalised company + title (see services/normalization.dedup_key).
    dedup_key: Mapped[str | None] = mapped_column(String(400), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL", name="fk_jobs_company_id"), index=True)
    department: Mapped[str | None] = mapped_column(String(200))
    # Set when a successful board fetch no longer lists the job.
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    application_method: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class DiscoveryRun(Base):
    __tablename__ = "discovery_runs"
    __table_args__ = (Index("ix_discovery_runs_user_started", "user_id", "started_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    sources: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False)
    jobs_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_new: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    jobs_matched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicates: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_details: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    platform_stats: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    saved_search_id: Mapped[int | None] = mapped_column(ForeignKey("saved_searches.id", ondelete="SET NULL", name="fk_discovery_runs_saved_search_id"), index=True)
    # Per source: {status: ok|empty|partial|failed|not_configured|disabled, message, found, new, duplicates, ...}
    source_results: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    summary: Mapped[str | None] = mapped_column(Text)  # plain-language outcome, shown instead of a bare "0 jobs"


class UserJob(Base):
    """A job in one user's feed, with that user's private score and state."""

    __tablename__ = "user_jobs"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_user_jobs_user_job"),
        Index("ix_user_jobs_user_status", "user_id", "status"),
        Index("ix_user_jobs_user_score", "user_id", "match_score"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    discovery_run_id: Mapped[int | None] = mapped_column(ForeignKey("discovery_runs.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="new", nullable=False)  # new|shortlisted|dismissed|applied
    is_saved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    match_score: Mapped[float | None] = mapped_column(Float)
    match_category: Mapped[str | None] = mapped_column(String(30))
    match: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    matching_skills: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    missing_skills: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    eligibility_status: Mapped[str | None] = mapped_column(String(20))
    eligibility_reasons: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    scoring_method: Mapped[str | None] = mapped_column(String(100))
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    saved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    seen_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)

    job: Mapped[Job] = relationship(lazy="joined")


class Application(Base, TimestampMixin):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_applications_user_job"),
        Index("ix_applications_user_status", "user_id", "status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    user_job_id: Mapped[int | None] = mapped_column(ForeignKey("user_jobs.id", ondelete="SET NULL"))
    # PREPARED | OPENED | CONFIRMATION_PENDING | SUBMITTED | FAILED | WITHDRAWN
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    # Post-submission pipeline: applied | screening | interview | offer | rejected | withdrawn
    stage: Mapped[str | None] = mapped_column(String(20))
    resume_id: Mapped[int | None] = mapped_column(ForeignKey("resumes.id", ondelete="SET NULL"))
    resume_used: Mapped[str | None] = mapped_column(String(255))
    cover_letter: Mapped[str | None] = mapped_column(Text)
    screening_answers: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    checklist: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(200))
    confirmation_text: Mapped[str | None] = mapped_column(Text)
    confirmation_source: Mapped[str | None] = mapped_column(String(100))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    job: Mapped[Job] = relationship(lazy="joined")


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str | None] = mapped_column(String(30))
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (Index("ix_reports_user_created", "user_id", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # daily | history
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RunError(Base):
    """Errors per user (discovery/source failures), shown in reports."""

    __tablename__ = "run_errors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    discovery_run_id: Mapped[int | None] = mapped_column(ForeignKey("discovery_runs.id", ondelete="CASCADE"))
    platform: Mapped[str | None] = mapped_column(String(20))
    job_key: Mapped[str | None] = mapped_column(String(200))
    error_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    recovery_status: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# --- v2 foundations (migration 0002) ---------------------------------------------------------------

class Invite(Base):
    """Per-invitee registration token (stored hashed). The env REGISTRATION_INVITE_CODE keeps working alongside."""

    __tablename__ = "invites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320))  # optional: only this address may use it
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    """Admin actions and sensitive reads. Append-only; details never contain secrets or resume text."""

    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_target", "target_type", "target_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(40))
    target_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class JobSource(Base, TimestampMixin):
    """Registry of discovery sources (ATS boards, APIs, clipper, email) with health, configurable by admins."""

    __tablename__ = "job_sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # ats | api | clip | email
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)  # never secrets: keys stay in env
    health: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False)  # ok | degraded | failing | unknown
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notifications_user_dedupe"),
        Index("ix_notifications_user_read", "user_id", "read_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    dedupe_key: Mapped[str | None] = mapped_column(String(200))  # repeat events bump occurrences instead of piling up
    occurrences: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class NotificationPref(Base, TimestampMixin):
    __tablename__ = "notification_prefs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    kinds: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)  # kind -> {in_app, email}
    email_digest: Mapped[str] = mapped_column(String(20), default="off", nullable=False)  # off | daily | weekly


class UserActivitySession(Base):
    """Active-time tracking: visible tab + recent input heartbeats, aggregated server-side (gap > 5 min = new session)."""

    __tablename__ = "user_activity_sessions"
    __table_args__ = (Index("ix_activity_sessions_user_started", "user_id", "started_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    active_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    heartbeats: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class JobView(Base):
    """Recently viewed jobs and the jobs-viewed metric: one row per (user, job)."""

    __tablename__ = "job_views"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_job_views_user_job"),
        Index("ix_job_views_user_last", "user_id", "last_viewed_at"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    first_viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    view_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class AICall(Base):
    """AI usage and cost metrics. Never stores prompts, responses or resume text."""

    __tablename__ = "ai_calls"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)  # match_score | summary | cover_letter | ...
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class ExtensionToken(Base):
    """Scoped, revocable browser-extension token (shown once, stored hashed)."""

    __tablename__ = "extension_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Interview(Base, TimestampMixin):
    __tablename__ = "interviews"
    __table_args__ = (Index("ix_interviews_user_scheduled", "user_id", "scheduled_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    round_name: Mapped[str | None] = mapped_column(String(100))
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    mode: Mapped[str | None] = mapped_column(String(20))  # video | phone | onsite
    location: Mapped[str | None] = mapped_column(String(300))
    interviewers: Mapped[str | None] = mapped_column(String(300))
    outcome: Mapped[str] = mapped_column(String(20), default="scheduled", nullable=False)  # scheduled|passed|failed|cancelled
    notes: Mapped[str | None] = mapped_column(Text)


class Offer(Base, TimestampMixin):
    __tablename__ = "offers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), unique=True, nullable=False)
    base_salary: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    bonus: Mapped[float | None] = mapped_column(Float)
    equity: Mapped[str | None] = mapped_column(String(200))
    joining_date: Mapped[date | None] = mapped_column(Date)
    decision_deadline: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="received", nullable=False)  # received|negotiating|accepted|declined
    notes: Mapped[str | None] = mapped_column(Text)


class ApplicationContact(Base, TimestampMixin):
    __tablename__ = "application_contacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    role: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320))
    phone: Mapped[str | None] = mapped_column(String(50))
    profile_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)


class SavedSearch(Base, TimestampMixin):
    """Scheduled discovery per user. Its runs are discovery_runs rows with saved_search_id set."""

    __tablename__ = "saved_searches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    origin: Mapped[str] = mapped_column(String(20), default="user", server_default=text("'user'"), nullable=False)  # user | starter
    criteria: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)  # keywords, locations, sources, filters
    schedule: Mapped[str] = mapped_column(String(20), default="daily", nullable=False)  # manual | daily | weekly
    min_match_score: Mapped[float | None] = mapped_column(Float)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Company(Base, TimestampMixin):
    """An employer with a public ATS job board. Rows are created on first use (watch, search, add by URL)."""

    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("ats", "board_token", name="uq_companies_ats_token"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ats: Mapped[str] = mapped_column(String(20), nullable=False)  # greenhouse | lever | ashby
    board_token: Mapped[str] = mapped_column(String(120), nullable=False)
    region: Mapped[str | None] = mapped_column(String(10))  # Lever: "eu" for api.eu.lever.co
    industry: Mapped[str | None] = mapped_column(String(100))
    domain: Mapped[str | None] = mapped_column(String(200))
    origin: Mapped[str] = mapped_column(String(20), default="user", nullable=False)  # curated | jobsync | user
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20))  # ok | empty | not_found | error
    last_error: Mapped[str | None] = mapped_column(String(500))
    job_count: Mapped[int | None] = mapped_column(Integer)


class UserCompany(Base):
    """A user's company watchlist."""

    __tablename__ = "user_companies"
    __table_args__ = (UniqueConstraint("user_id", "company_id", name="uq_user_companies_user_company"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    company: Mapped[Company] = relationship(lazy="joined")


class JobSourceLink(Base):
    """Every source a (deduplicated) job was seen on."""

    __tablename__ = "job_source_links"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    platform: Mapped[str | None] = mapped_column(String(20), index=True)  # LinkedIn, Greenhouse, Adzuna, ...
    source_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000))
    posted_at: Mapped[date | None] = mapped_column(Date)
    posted_at_source: Mapped[str | None] = mapped_column(String(20))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "code", name="uq_user_achievements_user_code"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


USER_OWNED_MODELS = (Resume, CandidateProfile, JobPreference, PlatformPreference, EmailIntegration, DiscoveryRun,
                     UserJob, Application, ApplicationEvent, Report, RunError, RefreshToken, Notification, NotificationPref,
                     UserActivitySession, JobView, ExtensionToken, Interview, Offer, ApplicationContact, SavedSearch,
                     UserAchievement, UserCompany)
