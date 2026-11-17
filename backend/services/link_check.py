"""Daily dead-link check for jobs that no employer board re-confirms (feed jobs, imported and clipped jobs).

Polite by design:
* never visits sites whose terms forbid automated access (LinkedIn, Naukri, Indeed, Glassdoor): those jobs stay
  "check on the site";
* goes through the shared fetch client, so robots.txt, SSRF protection and per-domain rate limits apply;
* at most MAX_PER_RUN pages a day, each job at most once every RECHECK_DAYS;
* identifies itself honestly (no browser impersonation, no JavaScript rendering).

Outcomes: 404/410 or a page that clearly says the job is gone -> `gone` (the job is closed); a normal page -> `ok`;
anything else (timeouts, 403, 5xx, robots.txt says no) -> `unreachable`/`skipped`, which never closes a job.
"""

from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.models import Job, utcnow
from backend.services.freshness import recheckable
from backend.services.normalization import ATS_SOURCES, html_to_text

log = logging.getLogger(__name__)

MAX_PER_RUN = 60
RECHECK_DAYS = 3
_GONE_TEXT = re.compile(
    r"(job|position|posting|vacancy|role|opening)[^.<]{0,40}(is )?(no longer (available|open|accepting)|has (been )?(closed|filled|expired)|"
    r"not found|does not exist|was removed)|this job (has )?expired|the page you('|’)re looking for (can('|’)t|cannot) be found",
    re.I)


def classify(status_code: int | None, text: str | None) -> str:
    if status_code in (404, 410):
        return "gone"
    if status_code is not None and 200 <= status_code < 300:
        # Only the page title and the start of the visible text count: scripts and templates often contain
        # "not found" strings for other states of the page, which must never close an open job.
        raw = text or ""
        title = re.search(r"<title[^>]*>(.*?)</title>", raw[:20000], re.I | re.S)
        visible = html_to_text(raw[:400000])[:3000]
        return "gone" if _GONE_TEXT.search((title.group(1) if title else "") + "\n" + visible) else "ok"
    return "unreachable"


def due(db: Session, limit: int = MAX_PER_RUN) -> list[Job]:
    cutoff = utcnow() - timedelta(days=RECHECK_DAYS)
    rows = db.execute(
        select(Job).where(Job.closed_at.is_(None), Job.is_expired.is_(False), Job.job_url.is_not(None),
                          Job.source.not_in(ATS_SOURCES),  # boards re-confirm these on every discovery run
                          or_(Job.link_checked_at.is_(None), Job.link_checked_at < cutoff))
        .order_by(Job.link_checked_at.asc().nullsfirst(), Job.id.desc()).limit(limit * 3)
    ).scalars().all()
    return [j for j in rows if recheckable(j.job_url)][:limit]


def check(db: Session, jobs: list[Job] | None = None, fetch: Any = None) -> dict[str, int]:
    """Check due jobs (or the given ones). `fetch(url) -> (status_code, text)` is injectable for tests."""
    from backend.services.scrapling_client import RobotsDisallowedError, ScraplingError, ScraplingFetchError, client

    def default_fetch(url: str) -> tuple[int | None, str]:
        try:
            r = client.fetch_page(url, use_cache=False, timeout=12)
            return r.status, r.text
        except ScraplingFetchError as exc:
            return getattr(exc, "status_code", None), ""

    fetch = fetch or default_fetch
    out = {"checked": 0, "ok": 0, "gone": 0, "unreachable": 0, "skipped": 0}
    for job in jobs if jobs is not None else due(db):
        now = utcnow()
        try:
            code, text = fetch(job.job_url)
            result = classify(code, text)
        except RobotsDisallowedError:
            result = "skipped"  # the site asks robots not to visit this page: respect it
        except ScraplingError as exc:  # SSRF guard, policy refusal, DNS failure
            log.info("link check refused for job %s: %s", job.id, exc)
            result = "skipped"
        except Exception as exc:  # one bad page must not stop the run
            log.info("link check failed for job %s: %s", job.id, exc)
            result = "unreachable"
        job.link_status, job.link_checked_at = result, now
        if result == "gone":
            job.closed_at = now
        out["checked"] += 1
        out[result] += 1
    db.commit()
    return out
