"""In-app notifications. A dedupe key per event makes repeated discovery runs idempotent."""

from __future__ import annotations

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import Notification, NotificationPref, User, UserJob, utcnow
from core import timeutil

DEFAULT_PREFS = {"new_matches": True, "delivery": "immediate", "min_score": None, "sources": []}

# Every kind a user can switch off. new_match comes from discovery; the rest from notification_sweep.
SWITCHABLE_KINDS = ("new_match", "follow_up_due", "interview_upcoming", "application_incomplete", "listing_closed",
                    "discovery_failed")


def kind_enabled(kinds: dict | None, kind: str) -> bool:
    """Is `kind` switched on in a stored `notification_prefs.kinds` map? Missing means on.

    Stored shapes that mean off: `false`, `{"in_app": false}`, and for new_match also `{"new_matches": false}`
    (the shape the preferences API has always written)."""
    raw = (kinds or {}).get(kind)
    if raw is False:
        return False
    if isinstance(raw, dict):
        if raw.get("in_app") is False:
            return False
        if kind == "new_match" and raw.get("new_matches") is False:
            return False
    return True


def _row(db: Session, user: User) -> NotificationPref | None:
    return db.execute(select(NotificationPref).where(NotificationPref.user_id == user.id)).scalar_one_or_none()


def prefs(db: Session, user: User) -> dict:
    row = _row(db, user)
    kinds = (row.kinds if row else None) or {}
    stored = kinds.get("new_match")
    out = {**DEFAULT_PREFS, **{k: v for k, v in (stored if isinstance(stored, dict) else {}).items() if k in DEFAULT_PREFS}}
    out["new_matches"] = kind_enabled(kinds, "new_match")
    out["kinds"] = {k: kind_enabled(kinds, k) for k in SWITCHABLE_KINDS}
    return out


def save_prefs(db: Session, user: User, values: dict) -> dict:
    """Save the keys present in `values`; anything left out keeps its stored value.

    `values` may hold the new-match settings (DEFAULT_PREFS keys) and `kinds`, a partial {kind: on/off} map.
    `new_matches` and `kinds["new_match"]` are the same switch; when both are given, `new_matches` wins."""
    row = _row(db, user)
    if row is None:
        row = NotificationPref(user_id=user.id, kinds={}, email_digest="off")
        db.add(row)
    switches = {k: bool(v) for k, v in (values.get("kinds") or {}).items() if k in SWITCHABLE_KINDS}
    if "new_matches" in values:
        switches["new_match"] = bool(values["new_matches"])
    kinds = dict(row.kinds or {})
    old = kinds.get("new_match")
    new_match = dict(old) if isinstance(old, dict) else {}
    new_match.update({k: values[k] for k in DEFAULT_PREFS if k in values and k != "new_matches"})
    if "new_match" in switches:
        new_match["new_matches"] = switches["new_match"]
        new_match.pop("in_app", None)  # an older {"in_app": false} must not override the switch just set
    elif old is False:
        new_match["new_matches"] = False  # keep a stored `false` off while other new-match settings change
    kinds["new_match"] = new_match
    for kind, on in switches.items():
        if kind != "new_match":
            prev = kinds.get(kind)
            kinds[kind] = {**(prev if isinstance(prev, dict) else {}), "in_app": on}
    row.kinds = kinds  # a new dict, so the JSON column is marked dirty
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
