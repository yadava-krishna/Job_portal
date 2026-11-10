"""Analytics events, consent records and in-app research feedback.

Events: the sixteen PRD events below are the product's conversion events. Failed or aborted attempts are recorded
with success=False and never count as conversions. Properties are limited to ids, counts and short codes: never
resume text, answers, e-mail addresses or other personal data (see docs/operations/OBSERVABILITY_COST_PRIVACY.md).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import AnalyticsEvent, Consent, User, UserFeedback, utcnow
from backend.models.career import CONSENT_KINDS

log = logging.getLogger(__name__)

PRD_EVENTS = (
    "onboarding_completed", "job_viewed", "job_saved", "job_dismissed", "resume_created", "resume_template_changed",
    "resume_bullet_edited", "resume_exported", "resume_used_in_application", "application_prepared",
    "application_submitted", "interview_recorded", "gap_viewed", "resource_started", "resource_completed",
    "reflection_completed",
)
OPERATIONAL_EVENTS = ("export_failed", "discovery_failed", "extension_fill_failed", "parse_failed", "application_aborted")
_ALLOWED_PROP_TYPES = (int, float, bool, str, type(None))
FEEDBACK_TOPICS = (
    "job_relevance", "matching_truthfulness", "gap_usefulness", "word_docs_comparison", "ats_template_trust",
    "export_use", "learning_effectiveness", "extension_time_saved", "tracking_states", "mentor_influence", "drop_off",
)


def track(db: Session, user_id: int | None, name: str, *, success: bool = True, commit: bool = False, **props: Any) -> None:
    """Record an event. Never raises: analytics must not break the action being measured."""
    if name not in PRD_EVENTS and name not in OPERATIONAL_EVENTS:
        log.warning("unknown analytics event %s", name)
        return
    clean = {k: (v if isinstance(v, _ALLOWED_PROP_TYPES) else str(v))[:80] if isinstance(v, str) else v
             for k, v in props.items() if isinstance(v, _ALLOWED_PROP_TYPES)}
    try:
        db.add(AnalyticsEvent(user_id=user_id, name=name, success=success, properties=clean))
        if commit:
            db.commit()
    except Exception:  # pragma: no cover - defensive
        log.exception("could not record analytics event %s", name)


def track_once(db: Session, user_id: int, name: str, **props: Any) -> None:
    """Record an event only the first time it happens for this user (e.g. onboarding_completed)."""
    exists = db.execute(select(AnalyticsEvent.id).where(AnalyticsEvent.user_id == user_id, AnalyticsEvent.name == name)).first()
    if not exists:
        track(db, user_id, name, **props)


def event_counts(db: Session, days: int = 30) -> dict[str, dict[str, int]]:
    since = utcnow() - timedelta(days=days)
    rows = db.execute(select(AnalyticsEvent.name, AnalyticsEvent.success, func.count(), func.count(func.distinct(AnalyticsEvent.user_id)))
                      .where(AnalyticsEvent.created_at >= since).group_by(AnalyticsEvent.name, AnalyticsEvent.success)).all()
    out: dict[str, dict[str, int]] = {n: {"count": 0, "users": 0, "failed": 0} for n in PRD_EVENTS + OPERATIONAL_EVENTS}
    for name, ok, n, users in rows:
        d = out.setdefault(name, {"count": 0, "users": 0, "failed": 0})
        if ok:
            d["count"] += n
            d["users"] = max(d["users"], users)
        else:
            d["failed"] += n
    return out


# ---------------- consent ----------------

CONSENT_TEXT = {
    "ai_processing": "Let JobPilot send the minimum needed job and profile text to the configured AI provider to improve "
                     "scoring and suggestions. Without it, rule-based features are used.",
    "learning_tracking": "Track time on learning sessions you start (active vs idle, only while the session is open).",
    "mentor_sharing": "Allow mentors you invite to see the parts of your profile you choose.",
    "extension": "Let the browser extension read and fill forms on job sites when you click it.",
    "email_notifications": "Send reminders and digests by e-mail (when e-mail is set up).",
    "research_feedback": "Occasionally ask short questions about whether JobPilot is helping.",
}


def consents(db: Session, user: User) -> list[dict[str, Any]]:
    rows = {c.kind: c for c in db.execute(select(Consent).where(Consent.user_id == user.id)).scalars()}
    return [{"kind": k, "granted": bool(rows.get(k) and rows[k].granted), "text": CONSENT_TEXT[k],
             "granted_at": rows[k].granted_at if k in rows else None, "revoked_at": rows[k].revoked_at if k in rows else None}
            for k in CONSENT_KINDS]


def set_consent(db: Session, user: User, kind: str, granted: bool) -> list[dict[str, Any]]:
    if kind not in CONSENT_KINDS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown consent kind {kind}")
    row = db.execute(select(Consent).where(Consent.user_id == user.id, Consent.kind == kind)).scalar_one_or_none()
    if row is None:
        row = Consent(user_id=user.id, kind=kind)
        db.add(row)
    row.granted = granted
    if granted:
        row.granted_at, row.revoked_at = utcnow(), None
    else:
        row.revoked_at = utcnow()
    db.commit()
    return consents(db, user)


def has_consent(db: Session, user_id: int, kind: str) -> bool:
    row = db.execute(select(Consent.granted).where(Consent.user_id == user_id, Consent.kind == kind)).scalar_one_or_none()
    return bool(row)


def require_consent(db: Session, user: User, kind: str) -> None:
    if not has_consent(db, user.id, kind):
        raise HTTPException(status.HTTP_403_FORBIDDEN, {"message": "This needs your permission first.", "consent": kind,
                                                        "text": CONSENT_TEXT[kind]})


# ---------------- research feedback ----------------

def add_feedback(db: Session, user: User, topic: str, rating: int | None, comment: str | None, context: dict) -> UserFeedback:
    if topic not in FEEDBACK_TOPICS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown feedback topic")
    fb = UserFeedback(user_id=user.id, topic=topic, rating=rating, comment=(comment or "").strip()[:2000] or None,
                      context={k: v for k, v in (context or {}).items() if isinstance(v, (int, str, bool))})
    db.add(fb)
    db.commit()
    return fb


def feedback_summary(db: Session) -> list[dict[str, Any]]:
    rows = db.execute(select(UserFeedback.topic, func.count(), func.avg(UserFeedback.rating)).group_by(UserFeedback.topic)).all()
    return [{"topic": t, "responses": n, "average_rating": round(float(a), 2) if a is not None else None} for t, n, a in rows]
