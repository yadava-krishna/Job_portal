"""Applying jp-fetchd results (JPSE Phase 2).

jp-fetchd (engine/fetchd, C) does the network work for employer boards: it fetches, validates, splits each board into
postings and hashes them, and writes one ``crawl_results`` row per board with its ``crawl_result_items``. Only postings
whose hash changed carry their raw JSON. This module turns a result into the same ``Outcome`` the Python crawler
produces, parsing the changed postings with the very same ``backend/services/ats/<ats>.py`` parsers, so identities
and fields cannot differ between the two crawlers. Everything for one board is applied in one transaction, together
with the posting hashes in ``crawl_raw_items`` that jp-fetchd compares against next time.

Switch: ``JPSE_FETCHD=1`` makes jp-fetchd own the boards (the Python crawler then only reads the public feeds).
Without it nothing here runs and the Python crawler does everything, as before.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models import Company, CrawlRawItem, CrawlResult, CrawlResultItem, CrawlState, utcnow
from backend.services.ats import ashby, greenhouse, lever, recruitee, smartrecruiters
from backend.services.crawler import service as crawler

log = logging.getLogger(__name__)

PARSERS = {"greenhouse": greenhouse.parse_job, "lever": lever.parse_job, "ashby": ashby.parse_job,
           "smartrecruiters": smartrecruiters.parse_job, "recruitee": recruitee.parse_job}
MAX_ATTEMPTS = 3


def enabled() -> bool:
    return os.environ.get("JPSE_FETCHD", "").strip() == "1"


def _outcome(db: Session, r: CrawlResult, state: CrawlState, company: Company) -> crawler.Outcome:
    out = crawler.Outcome(state.id, {"ok": "ok", "not_modified": "not_modified", "unchanged": "not_modified",
                                     "not_found": "not_found"}.get(r.status, "error"),
                          etag=r.etag, body_hash=r.body_hash, error=r.error, ms=r.duration_ms or 0, requests=r.requests or 0,
                          bytes=r.bytes or 0)
    if r.status != "ok":
        return out
    parse = PARSERS[company.ats]
    token = company.board_token
    items = db.execute(select(CrawlResultItem.raw_id, CrawlResultItem.raw_hash, CrawlResultItem.raw)
                       .where(CrawlResultItem.result_id == r.id).order_by(CrawlResultItem.id)).all()
    seen_company: str | None = None
    for raw_id, _h, raw in items:
        if raw is None:
            out.keep.add(f"{company.ats}:{token.lower()}:{raw_id}")
            continue
        try:
            nj = parse(json.loads(raw), token, company.name)
        except (ValueError, TypeError, KeyError, AttributeError) as exc:  # one odd posting never sinks the board
            log.info("jp-fetchd posting %s on %s skipped: %s", raw_id, company.board_token, exc)
            continue
        if nj is not None:
            seen_company = seen_company or nj.company
            out.jobs.append(nj)

    def record_hashes() -> None:
        db.execute(delete(CrawlRawItem).where(CrawlRawItem.target_key == state.target_key))
        db.add_all([CrawlRawItem(target_key=state.target_key, raw_id=i[0][:200], raw_hash=i[1]) for i in items])

    out.before_commit = record_hashes
    return out


def apply_pending(db: Session, *, limit: int = 100) -> dict[str, Any]:
    """Apply pending results, oldest first. Each result is applied at most once; a failure is retried, then parked."""
    totals = {"applied": 0, "failed": 0, "new": 0, "changed": 0, "closed": 0, "not_modified": 0}
    q = select(CrawlResult).where(CrawlResult.state == "pending").order_by(CrawlResult.id).limit(limit)
    if db.get_bind().dialect.name == "postgresql":
        q = q.with_for_update(skip_locked=True)
    ids = [r.id for r in db.execute(q).scalars()]
    db.rollback()  # release the locks; each result below gets its own transaction
    watched = crawler.watched_company_ids(db) if ids else set()
    for rid in ids:
        r = db.get(CrawlResult, rid)
        if r is None or r.state != "pending":
            continue
        state = db.get(CrawlState, r.state_id)
        company = db.get(Company, state.company_id) if state and state.company_id else None
        if state is None or company is None or company.ats not in PARSERS:
            r.state, r.apply_error, r.applied_at = "failed", "Unknown target or job-board type.", utcnow()
            db.commit()
            totals["failed"] += 1
            continue
        try:
            out = _outcome(db, r, state, company)
            r.state, r.applied_at = "applied", utcnow()  # committed by apply_outcome, in the same transaction
            rep = crawler.apply_outcome(db, state, out, watched=company.id in watched)
            totals["applied"] += 1
            totals["new"] += rep.get("new", 0)
            totals["changed"] += rep.get("changed", 0)
            totals["closed"] += rep.get("closed", 0)
            totals["not_modified"] += rep["status"] == "not_modified"
        except Exception as exc:
            log.exception("applying jp-fetchd result %s for %s failed", rid, getattr(state, "target_key", "?"))
            db.rollback()
            r = db.get(CrawlResult, rid)
            r.attempts += 1
            r.apply_error = f"{type(exc).__name__}: {exc}"[:500]
            if r.attempts >= MAX_ATTEMPTS:
                r.state, r.applied_at = "failed", utcnow()
                # the board is due again so jp-fetchd fetches it afresh
                db.get(CrawlState, r.state_id).next_due_at = utcnow()
            db.commit()
            totals["failed"] += 1
    return totals


def prune(db: Session, *, keep_days: int = 3) -> int:
    """Applied and failed results are kept 3 days for diagnosis; their items go with them (ON DELETE CASCADE)."""
    from datetime import timedelta

    cutoff = utcnow() - timedelta(days=keep_days)
    rows = db.execute(select(CrawlResult.id).where(CrawlResult.state != "pending", CrawlResult.created_at < cutoff)).scalars().all()
    for i in range(0, len(rows), 500):
        db.execute(delete(CrawlResultItem).where(CrawlResultItem.result_id.in_(rows[i:i + 500])))
        db.execute(delete(CrawlResult).where(CrawlResult.id.in_(rows[i:i + 500])))
    db.commit()
    return len(rows)
