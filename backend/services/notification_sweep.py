"""Reminders and alerts that come from the state of a user's data rather than from a single event (spec: Phase 5,
in-app notifications). Run by the `notification_sweep` background job; follow-up and interview reminders are also run
by `notification_dispatch` every 30 minutes. Both share these functions and dedupe keys, so a reminder is never sent
twice whichever job finds it first.

Kinds (each with a stable dedupe key, so a sweep can run any number of times without repeating itself):

    follow_up_due           an open application's follow-up date is today or has passed      followup:<app>:<date>
    interview_upcoming      a scheduled interview starts in the next 24 hours                interview:<id>:<start>
    application_incomplete  prepared / opened / awaiting confirmation and untouched for       incomplete:<app>:<status>
                            more than 3 days, or Smart Apply couldn't confirm the submission
    listing_closed          a saved job, or one with an unsubmitted application, is closed   listing_closed:<job>
                            or expired (see services/freshness.py)
    discovery_failed        one of the user's discovery runs failed                          discovery_failed:<run>

A user can switch a kind off in Settings > Notifications, stored in `notification_prefs.kinds` as {"<kind>": {"in_app": false}}
(see notification_service.kind_enabled; a missing kind is on). Nothing here sends e-mail;
notification_dispatch e-mails unread notifications only when SMTP is configured and the user has consented.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.models import Application, DiscoveryRun, Interview, Job, Notification, NotificationPref, User, UserJob, utcnow
from backend.services import discovery_service, freshness
from backend.services.notification_service import kind_enabled, notify
from core import timeutil

KINDS = ("follow_up_due", "interview_upcoming", "application_incomplete", "listing_closed", "discovery_failed")

CLOSED_STAGES = ("rejected", "withdrawn", "archived")
INCOMPLETE_STATUSES = ("PREPARED", "OPENED", "CONFIRMATION_PENDING")
UNSUBMITTED_STATUSES = (*INCOMPLETE_STATUSES, "FAILED")
STALE_AFTER = timedelta(days=3)
# Look-back windows: old history is not worth an alert, and the first sweep after an upgrade must not flood anyone.
FOLLOW_UP_LOOKBACK = timedelta(days=30)
INCOMPLETE_LOOKBACK = timedelta(days=30)
FAILED_RUN_LOOKBACK = timedelta(days=3)
# More closed listings than this for one user in one sweep become a single summary (the individual alerts are kept,
# already marked read, so they never come back).
LISTING_SUMMARY_OVER = 3


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _local(dt: datetime) -> datetime:
    return _aware(dt).astimezone(timeutil.tz())  # type: ignore[union-attr]


def _short_date(d) -> str:
    return d.strftime("%d %b").lstrip("0")


class _Ctx:
    """Users and preferences loaded once per sweep."""

    def __init__(self, db: Session):
        self.db = db
        self.users = {u.id: u for u in db.execute(select(User).where(User.is_active.is_(True))).scalars()}
        self.kinds = {p.user_id: (p.kinds or {}) for p in db.execute(select(NotificationPref)).scalars()}

    def wants(self, user_id: int, kind: str) -> bool:
        return user_id in self.users and kind_enabled(self.kinds.get(user_id), kind)

    def notify(self, user_id: int, kind: str, title: str, body: str | None, link: str | None, key: str) -> Notification | None:
        if not self.wants(user_id, kind):
            return None
        return notify(self.db, self.users[user_id], kind=kind, title=title, body=body, link=link, dedupe_key=key)


def _ctx(db: Session, ctx: _Ctx | None) -> _Ctx:
    return ctx or _Ctx(db)


# ---------------- follow-ups and interviews (also run by notification_dispatch) ----------------

def follow_ups(db: Session, now: datetime | None = None, ctx: _Ctx | None = None) -> int:
    """Open applications whose follow-up date is today (local time) or overdue."""
    c = _ctx(db, ctx)
    now = now or utcnow()
    today = timeutil.today()
    end_of_today = datetime.combine(today + timedelta(days=1), time.min, tzinfo=timeutil.tz())
    rows = db.execute(select(Application).where(Application.follow_up_at.is_not(None), Application.follow_up_at < end_of_today,
                                                Application.follow_up_at >= now - FOLLOW_UP_LOOKBACK,
                                                Application.status != "WITHDRAWN",
                                                or_(Application.stage.is_(None), Application.stage.notin_(CLOSED_STAGES))))
    created = 0
    for a in rows.unique().scalars():
        due = _local(a.follow_up_at).date()
        body = "Your follow-up date is today." if due >= today else f"Your follow-up date was {_short_date(due)}."
        # Same key as the reminders sent before this sweep existed (UTC date of the stored time), so none repeat.
        key = f"followup:{a.id}:{a.follow_up_at.date().isoformat()}"
        if c.notify(a.user_id, "follow_up_due", f"Follow up with {a.job.company} about {a.job.title}", body,
                    f"/applied?app={a.id}", key):
            created += 1
    return created


def _when(start: datetime, now: datetime) -> str:
    local, today = _local(start), _local(now).date()
    day = "today" if local.date() == today else "tomorrow" if local.date() == today + timedelta(days=1) else _short_date(local)
    return f"{day} at {local:%H:%M}"


def interviews(db: Session, now: datetime | None = None, ctx: _Ctx | None = None) -> int:
    """Scheduled interviews starting in the next 24 hours. Rescheduling one gives a fresh reminder."""
    c = _ctx(db, ctx)
    now = now or utcnow()
    rows = db.execute(select(Interview).where(Interview.scheduled_at >= now, Interview.scheduled_at <= now + timedelta(hours=24),
                                              Interview.outcome == "scheduled")).scalars().all()
    created = 0
    for iv in rows:
        app = db.get(Application, iv.application_id)
        if app is None:
            continue
        start = _aware(iv.scheduled_at)
        link = f"/interview-prep?job={app.user_job_id}" if app.user_job_id else f"/applied?app={app.id}"
        body = f"{iv.round_name or 'Interview'} for {app.job.title}. Prepare in Interview prep."
        key = f"interview:{iv.id}:{start:%Y%m%dT%H%M}"
        if c.notify(iv.user_id, "interview_upcoming", f"Interview with {app.job.company} {_when(start, now)}", body, link, key):
            created += 1
    return created


# ---------------- unfinished applications ----------------

def _closed(job: Job) -> bool:
    return freshness.status(job)["state"] in ("closed", "expired")


_INCOMPLETE_BODY = {
    "PREPARED": "You prepared it {days} ago but haven't opened the application page yet.",
    "OPENED": "You opened the application page {days} ago. If you've applied, mark it as submitted.",
    "CONFIRMATION_PENDING": "Did you submit it? Confirm it so JobPilot can track the application.",
}


def incomplete_applications(db: Session, now: datetime | None = None, ctx: _Ctx | None = None) -> int:
    c = _ctx(db, ctx)
    now = now or utcnow()
    stale = Application.status.in_(INCOMPLETE_STATUSES) & (Application.updated_at < now - STALE_AFTER) \
        & (Application.updated_at >= now - INCOMPLETE_LOOKBACK)
    uncertain = (Application.apply_state == "submission_uncertain") & Application.status.notin_(("SUBMITTED", "WITHDRAWN"))
    created = 0
    for a in db.execute(select(Application).where(or_(stale, uncertain))).unique().scalars():
        if _closed(a.job):  # the listing_closed alert covers it; nudging to finish a closed job would be wrong
            continue
        link = f"/applied?app={a.id}"
        if a.apply_state == "submission_uncertain" and a.status not in ("SUBMITTED", "WITHDRAWN"):
            n = c.notify(a.user_id, "application_incomplete", f"Check whether your application to {a.job.company} went through",
                         f"JobPilot couldn't confirm that your {a.job.title} application was submitted. Open it to confirm or try again.",
                         link, f"incomplete:{a.id}:submission_uncertain")
        else:
            days = max(3, (now - _aware(a.updated_at)).days)
            n = c.notify(a.user_id, "application_incomplete", f"Finish your application to {a.job.company} for {a.job.title}",
                         _INCOMPLETE_BODY[a.status].format(days=f"{days} days"), link, f"incomplete:{a.id}:{a.status}")
        created += bool(n)
    return created


# ---------------- closed or expired listings ----------------

def closed_listings(db: Session, now: datetime | None = None, ctx: _Ctx | None = None) -> int:
    """Saved jobs and jobs with an unsubmitted application whose listing has closed or expired."""
    c = _ctx(db, ctx)
    today = timeutil.today()
    gone = or_(Job.closed_at.is_not(None), Job.is_expired.is_(True), Job.expires_at < today)
    # (user, job) -> (job, link, why); an application wins over a saved job for the link.
    found: dict[tuple[int, int], tuple[Job, str, str]] = {}
    submitted = {(u, j) for u, j in db.execute(select(Application.user_id, Application.job_id).join(Job, Job.id == Application.job_id)
                                               .where(gone, Application.status == "SUBMITTED"))}
    for uj in db.execute(select(UserJob).join(Job, Job.id == UserJob.job_id)
                         .where(gone, UserJob.is_saved.is_(True), UserJob.status.notin_(("dismissed", "applied")))).scalars():
        if (uj.user_id, uj.job_id) not in submitted:
            found[(uj.user_id, uj.job_id)] = (uj.job, f"/discover?job={uj.id}", "You saved this job.")
    for a in db.execute(select(Application).join(Job, Job.id == Application.job_id)
                        .where(gone, Application.status.in_(UNSUBMITTED_STATUSES))).unique().scalars():
        found[(a.user_id, a.job_id)] = (a.job, f"/applied?app={a.id}", "You started an application but haven't submitted it.")

    pending: dict[int, list[tuple[Job, str, str, str]]] = {}
    for (uid, job_id), (job, link, why) in found.items():
        key = f"listing_closed:{job_id}"
        if not c.wants(uid, "listing_closed"):
            continue
        if db.execute(select(Notification.id).where(Notification.user_id == uid, Notification.dedupe_key == key)).first():
            continue
        pending.setdefault(uid, []).append((job, link, why, key))

    created = 0
    for uid, items in pending.items():
        batch = len(items) > LISTING_SUMMARY_OVER
        for job, link, why, key in items:
            st = freshness.status(job)
            title = (f"{job.title} at {job.company} is no longer listed" if st["state"] == "closed"
                     else f"{job.title} at {job.company} has probably expired" if st["label"] == "Probably expired"
                     else f"Applications for {job.title} at {job.company} have closed")
            n = c.notify(uid, "listing_closed", title, f"{st['detail']} {why}", link, key)
            if n is not None and batch:
                n.read_at = utcnow()  # recorded so it never repeats; the summary below is the one alert
            elif n is not None:
                created += 1
        if batch:
            first = min(job.id for job, *_ in items)
            if c.notify(uid, "listing_closed", f"{len(items)} jobs you saved or started applying for are no longer open",
                        "Their listings have closed or expired. Each one is in your notifications.", "/saved",
                        f"listing_closed_summary:{first}:{len(items)}"):
                created += 1
    return created


# ---------------- failed discovery runs ----------------

def failed_discovery_runs(db: Session, now: datetime | None = None, ctx: _Ctx | None = None) -> int:
    """One alert per failed run. Runs cut off by a restart are marked failed at the next start-up
    (saved_search_service.mark_interrupted) and are alerted then; runs still marked running are left alone."""
    c = _ctx(db, ctx)
    now = now or utcnow()
    created = 0
    rows = db.execute(select(DiscoveryRun).where(DiscoveryRun.status == "failed", DiscoveryRun.started_at >= now - FAILED_RUN_LOOKBACK))
    for run in rows.scalars():
        if discovery_service.nothing_configured(run):
            continue  # e.g. the daily run when no alert mailbox or Adzuna key is set up: a setup gap, not a failure
        reason = run.summary
        if not reason:
            msgs = [e.get("message") for e in (run.error_details or []) if isinstance(e, dict) and e.get("message")]
            reason = msgs[0] if msgs else "Discovery could not run."
        scheduled = run.trigger in ("scheduled", "catch_up")
        title = "Your scheduled job search couldn't run" if scheduled else "A job search couldn't run"
        body = f"{reason[:280]} Check Source health, then run it again."
        if c.notify(run.user_id, "discovery_failed", title, body, "/searches?tab=sources", f"discovery_failed:{run.id}"):
            created += 1
    return created


def run(db: Session, now: datetime | None = None) -> dict[str, Any]:
    """The whole sweep. Returns how many notifications of each kind were created."""
    now = now or utcnow()
    ctx = _Ctx(db)
    out = {
        "follow_up_due": follow_ups(db, now, ctx),
        "interview_upcoming": interviews(db, now, ctx),
        "application_incomplete": incomplete_applications(db, now, ctx),
        "listing_closed": closed_listings(db, now, ctx),
        "discovery_failed": failed_discovery_runs(db, now, ctx),
    }
    db.commit()
    out["created"] = sum(out.values())
    return out
