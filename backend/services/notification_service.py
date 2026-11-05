"""In-app notifications. A dedupe key per event makes repeated discovery runs idempotent."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import Notification, NotificationPref, User, UserJob, utcnow
from core import timeutil

DEFAULT_PREFS = {"new_matches": True, "delivery": "immediate", "min_score": None, "sources": []}


def prefs(db: Session, user: User) -> dict:
    row = db.execute(select(NotificationPref).where(NotificationPref.user_id == user.id)).scalar_one_or_none()
    stored = (row.kinds or {}).get("new_match", {}) if row else {}
    return {**DEFAULT_PREFS, **{k: v for k, v in stored.items() if k in DEFAULT_PREFS}}


def save_prefs(db: Session, user: User, values: dict) -> dict:
    row = db.execute(select(NotificationPref).where(NotificationPref.user_id == user.id)).scalar_one_or_none()
    if row is None:
        row = NotificationPref(user_id=user.id, kinds={}, email_digest="off")
        db.add(row)
    row.kinds = {**(row.kinds or {}), "new_match": {k: values[k] for k in DEFAULT_PREFS if k in values}}
    db.commit()
    return prefs(db, user)


def notify(db: Session, user: User, *, kind: str, title: str, body: str | None = None, link: str | None = None,
           dedupe_key: str | None = None) -> Notification | None:
    """Create a notification; with a dedupe key, an existing one is left alone and None is returned."""
    if dedupe_key:
        exists = db.execute(select(Notification.id).where(Notification.user_id == user.id,
                                                          Notification.dedupe_key == dedupe_key)).scalar_one_or_none()
        if exists is not None:
            return None
    n = Notification(user_id=user.id, kind=kind, title=title[:200], body=body, link=link, dedupe_key=dedupe_key)
    db.add(n)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:  # a concurrent run created it first: the unique (user, dedupe_key) constraint wins
        return None
    return n


def notify_new_match(db: Session, user: User, uj: UserJob, source: str | None = None) -> Notification | None:
    """A new job at or above the search's threshold, filtered by the user's notification preferences."""
    p = prefs(db, user)
    job = uj.job
    if not p["new_matches"]:
        return None
    if p["min_score"] is not None and (uj.match_score is None or uj.match_score < p["min_score"]):
        return None
    if p["sources"] and (source or job.source) not in p["sources"]:
        return None
    if p["delivery"] == "daily_digest":
        return _digest(db, user, uj)
    score = f"{uj.match_score:.0f}%" if uj.match_score is not None else "unscored"
    return notify(db, user, kind="new_match", title=f"{score} match: {job.title} at {job.company}"[:200],
                  body=f"Found on {job.platform}. {job.location or 'Location not stated'}.",
                  link=f"/discover?job={uj.id}", dedupe_key=f"new_match:{job.id}")


def list_for(db: Session, user: User, *, unread_only: bool = False, limit: int = 30) -> tuple[list[Notification], int]:
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    items = db.execute(stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)).scalars().all()
    unread = db.execute(select(func.count()).select_from(Notification).where(Notification.user_id == user.id,
                                                                            Notification.read_at.is_(None))).scalar_one()
    return list(items), unread


def mark_read(db: Session, user: User, notification_id: int | None = None) -> int:
    stmt = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if notification_id is not None:
        stmt = stmt.where(Notification.id == notification_id)
    count = db.execute(stmt.values(read_at=utcnow())).rowcount
    db.commit()
    return count


def _digest(db: Session, user: User, uj: UserJob) -> Notification | None:
    """One notification per day that counts the day's new matches (instead of one per job)."""
    # Called only when a job first enters the feed, so each job is counted once.
    key = f"digest:new_match:{timeutil.today().isoformat()}"
    row = db.execute(select(Notification).where(Notification.user_id == user.id, Notification.dedupe_key == key)).scalar_one_or_none()
    if row is None:
        return notify(db, user, kind="digest", title="New matching jobs today", body="1 new matching job.",
                      link="/discover?sort=discovered", dedupe_key=key)
    row.occurrences += 1
    row.body = f"{row.occurrences} new matching jobs."
    row.read_at = None
    return row
