"""Is this job still open? One plain-language status per job, from evidence JobPilot actually has.

    closed      the employer's board stopped listing it, or its page now says "not found"
    expired     past the closing date its source published, or old and not confirmed recently
    open        confirmed recently: listed on the employer's board / in an official feed, or its page loaded
    unconfirmed confirmed once, but not in the last few days
    unchecked   JobPilot has no way to re-check it (e.g. a job you clipped from LinkedIn, whose terms forbid automated
                visits); check it yourself on the site

Nothing here guesses: "open" always names when and how it was confirmed.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from core import timeutil

RECENT = timedelta(days=3)
SOURCE_NAMES = {"greenhouse": "the employer's Greenhouse board", "lever": "the employer's Lever board",
                "ashby": "the employer's Ashby board", "smartrecruiters": "the employer's SmartRecruiters board",
                "recruitee": "the employer's Recruitee board", "himalayas": "the Himalayas feed", "remoteok": "the RemoteOK feed",
                "remotive": "the Remotive feed", "arbeitnow": "the Arbeitnow feed", "adzuna_api": "Adzuna"}
NOT_RECHECKABLE = ("linkedin.com", "naukri.com", "indeed.com", "indeed.co", "glassdoor.")


def _aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _ago(dt: datetime, now: datetime) -> str:
    secs = max(0, (now - dt).total_seconds())
    if secs < 3600:
        return "less than an hour ago"
    if secs < 86400:
        h = int(secs // 3600)
        return f"{h} hour{'s' if h != 1 else ''} ago"
    d = int(secs // 86400)
    return f"{d} day{'s' if d != 1 else ''} ago"


def _fmt(d: date | datetime) -> str:
    return d.strftime("%d %b %Y").lstrip("0")


def recheckable(url: str | None) -> bool:
    host = (url or "").lower()
    return bool(host) and not any(b in host for b in NOT_RECHECKABLE)


def status(job: Any, now: datetime | None = None, today: date | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    today = today or timeutil.today()
    verified = _aware(job.last_verified_at)
    link_at = _aware(getattr(job, "link_checked_at", None))
    link = getattr(job, "link_status", None)
    where = SOURCE_NAMES.get(job.source, "its source")
    closed = _aware(job.closed_at)
    if closed is not None:
        how = "its page returned \"not found\"" if link == "gone" else f"{where} stopped listing it"
        return {"state": "closed", "label": "No longer listed", "detail": f"Closed: {how} on {_fmt(closed)}.", "checked_at": closed}
    expires = getattr(job, "expires_at", None)
    if expires and expires < today:
        return {"state": "expired", "label": "Applications closed", "detail": f"The source gave a closing date of {_fmt(expires)}.",
                "checked_at": verified}
    if job.is_expired:
        return {"state": "expired", "label": "Probably expired",
                "detail": "Posted more than 45 days ago and not confirmed as still listed in the last 3 days.", "checked_at": verified}
    best = max((t for t in (verified, link_at if link == "ok" else None) if t), default=None)
    if best is not None and now - best <= RECENT:
        how = f"listed on {where}" if best == verified else "its job page loaded normally"
        closes = f" Applications close on {_fmt(expires)}." if expires else ""
        return {"state": "open", "label": "Open", "detail": f"Confirmed {_ago(best, now)}: {how}.{closes}", "checked_at": best}
    if best is not None:
        return {"state": "unconfirmed", "label": "Not recently confirmed",
                "detail": f"Last confirmed {_ago(best, now)}. Check the posting before you spend time on it.", "checked_at": best}
    if link == "unreachable" and link_at:
        return {"state": "unchecked", "label": "Couldn't check",
                "detail": f"JobPilot tried to open the job page {_ago(link_at, now)} but the site didn't answer.", "checked_at": link_at}
    if not recheckable(job.job_url):
        return {"state": "unchecked", "label": "Check on the site",
                "detail": "This site does not allow automated checks, so JobPilot can't confirm it is still open.", "checked_at": None}
    return {"state": "unchecked", "label": "Not checked yet",
            "detail": "JobPilot hasn't confirmed this job is still open yet. The daily link check will.", "checked_at": None}
