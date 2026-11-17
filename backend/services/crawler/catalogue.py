"""The posting catalogue: applying a crawled snapshot, and reading a board or feed back for a saved-search run.

Correctness rules from the JPSE blueprint (§4, "Closed-job correctness"):

- identity is the source's own key (``NormalizedJob.source_key``), never company + title + location;
- every new or changed posting gets a new revision and an ``index_outbox`` event in the same transaction;
- postings are closed only after a complete, valid snapshot of the board. A board that suddenly returns nothing
  while it listed several jobs before is treated as suspicious: nothing is closed and the board is retried soon;
- feeds publish only their newest items, so a posting dropping out of a feed is not "closed", it is just not in the
  latest snapshot.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.models import CataloguePosting, Company, CrawlState, IndexOutbox, Job, JobSourceLink, utcnow
from backend.services.ats.base import BoardResult
from backend.services.normalization import NormalizedJob, normalize_facts

SUSPICIOUS_EMPTY_MIN = 5  # a board that listed at least this many open jobs and now lists none is not trusted
_DATE_FIELDS = ("posted_at", "expires_at")
_SKIP_FIELDS = {"description", "observed_at"}


# ---- (de)serialisation ------------------------------------------------------------------------------

def to_payload(nj: NormalizedJob) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for f in dataclasses.fields(nj):
        if f.name in _SKIP_FIELDS:
            continue
        v = getattr(nj, f.name)
        out[f.name] = v.isoformat() if isinstance(v, (date, datetime)) else (list(v) if isinstance(v, list) else v)
    return out


def from_payload(payload: dict[str, Any], description: str | None, observed_at: datetime | None = None) -> NormalizedJob:
    names = {f.name for f in dataclasses.fields(NormalizedJob)}
    kw = {k: v for k, v in payload.items() if k in names}
    for k in _DATE_FIELDS:
        if isinstance(kw.get(k), str):
            kw[k] = date.fromisoformat(kw[k])
    for k, v in list(kw.items()):
        if isinstance(v, list):
            kw[k] = list(v)
    if observed_at is not None and observed_at.tzinfo is None:  # SQLite returns naive UTC
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    return NormalizedJob(**kw, description=description, observed_at=observed_at)


def content_hash(payload: dict[str, Any], description: str | None) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str) + "\x00" + (description or "")
    return hashlib.blake2b(raw.encode("utf-8"), digest_size=16).hexdigest()


def _facts(nj: NormalizedJob) -> dict[str, Any]:
    """The searchable columns, from the same normaliser every ingested job uses (core/locations.py, core/salary.py)."""
    ns = SimpleNamespace(location=nj.location, work_mode=nj.work_mode, country=nj.country, salary_range=nj.salary_range,
                         salary_min_lpa=nj.salary_min_lpa, salary_max_lpa=nj.salary_max_lpa, location_normalized=None,
                         remote_scope=None, salary_currency=None, salary_min=None, salary_max=None, salary_period=None,
                         salary_period_assumed=None, normalized_version=None)
    normalize_facts(ns)
    return dict(title=(nj.title or "")[:500], company=(nj.company or "")[:300], location=(nj.location or None) and nj.location[:500],
                location_normalized=ns.location_normalized, country=(ns.country or None) and str(ns.country)[:80],
                remote_scope=ns.remote_scope, work_mode=ns.work_mode, employment_type=(nj.employment_type or None) and nj.employment_type[:40],
                seniority=(nj.seniority or None) and nj.seniority[:40], salary_currency=ns.salary_currency, salary_min=ns.salary_min,
                salary_max=ns.salary_max, salary_period=ns.salary_period, posted_at=nj.posted_at, expires_at=nj.expires_at,
                job_url=(nj.job_url or None) and nj.job_url[:1000],
                skills=list(dict.fromkeys([*nj.required_skills, *nj.preferred_skills]))[:60])


# ---- applying a snapshot ------------------------------------------------------------------------------

@dataclasses.dataclass
class ApplyResult:
    new: int = 0
    changed: int = 0
    unchanged: int = 0
    closed: int = 0
    reopened: int = 0
    suspicious: bool = False

    @property
    def any_change(self) -> bool:
        return bool(self.new or self.changed or self.closed or self.reopened)


def apply_snapshot(db: Session, state: CrawlState, jobs: Iterable[NormalizedJob], *, closes: bool, now: datetime | None = None,
                   keep: frozenset[str] | set[str] = frozenset()) -> ApplyResult:
    """Upsert a complete snapshot of one target. The caller commits (one transaction per target).

    ``keep``: source keys still listed whose content did not change (jp-fetchd sends only changed postings in full);
    they stay as they are, marked as seen in this snapshot."""
    now = now or utcnow()
    res = ApplyResult()
    incoming: dict[str, NormalizedJob] = {}
    for nj in jobs:
        incoming.setdefault(nj.source_key, nj)  # a board listing one requisition twice keeps the first
    keep = set(keep) - set(incoming)
    existing = {p.source_key: p for p in db.execute(select(CataloguePosting).where(
        CataloguePosting.target_key == state.target_key)).scalars()}
    open_before = sum(1 for p in existing.values() if p.closed_at is None)
    if closes and not incoming and not keep and open_before >= SUSPICIOUS_EMPTY_MIN:
        res.suspicious = True
        return res
    seq = state.snapshot_seq + 1
    # A posting moved from another target (e.g. a company renamed its board) keeps its identity and history.
    elsewhere = {}
    missing = [k for k in incoming if k not in existing]
    for i in range(0, len(missing), 500):
        for p in db.execute(select(CataloguePosting).where(CataloguePosting.source_key.in_(missing[i:i + 500]))).scalars():
            elsewhere[p.source_key] = p
    for key, nj in incoming.items():
        payload = to_payload(nj)
        h = content_hash(payload, nj.description)
        p = existing.get(key) or elsewhere.get(key)
        if p is None:
            p = CataloguePosting(source_key=key[:300], target_key=state.target_key, source=nj.source, company_id=nj.company_id,
                                 payload=payload, description=nj.description, content_hash=h, revision=1, snapshot_seq=seq,
                                 first_seen_at=now, last_seen_at=now, changed_at=now, **_facts(nj))
            db.add(p)
            db.flush()
            db.add(IndexOutbox(posting_id=p.id, revision=1, event="upsert"))
            res.new += 1
            continue
        p.target_key, p.snapshot_seq, p.last_seen_at = state.target_key, seq, now
        if p.closed_at is not None:
            p.closed_at = None
            p.revision += 1
            db.add(IndexOutbox(posting_id=p.id, revision=p.revision, event="reopen"))
            res.reopened += 1
        if p.content_hash != h:
            for k, v in _facts(nj).items():
                setattr(p, k, v)
            p.payload, p.description, p.content_hash, p.changed_at = payload, nj.description, h, now
            p.company_id = nj.company_id if nj.company_id is not None else p.company_id
            p.revision += 1
            db.add(IndexOutbox(posting_id=p.id, revision=p.revision, event="upsert"))
            res.changed += 1
        else:
            res.unchanged += 1
    for key in keep:
        p = existing.get(key)
        if p is not None and p.closed_at is None:  # an unchanged posting the parser rejected before has no row: ignore
            p.snapshot_seq, p.last_seen_at = seq, now
            res.unchanged += 1
    if closes:
        for key, p in existing.items():
            if key not in incoming and key not in keep and p.closed_at is None:
                p.closed_at = now
                p.revision += 1
                db.add(IndexOutbox(posting_id=p.id, revision=p.revision, event="close"))
                res.closed += 1
    state.snapshot_seq = seq
    state.postings_open = len(incoming) + len(keep)
    return res


def mark_still_listed(db: Session, state: CrawlState, now: datetime) -> None:
    """A 304 answer: everything in the last snapshot is still listed."""
    db.execute(update(CataloguePosting).where(CataloguePosting.target_key == state.target_key,
                                              CataloguePosting.snapshot_seq == state.snapshot_seq)
               .values(last_seen_at=now).execution_options(synchronize_session=False))


def sync_jobs(db: Session, company: Company, live_keys: set[str], seen_at: datetime) -> int:
    """Keep the user-facing ``jobs`` rows in step with a complete board snapshot: confirm what is still listed (honest
    "last confirmed" times for freshness) and close what left the board (company_service._close_missing's rule)."""
    from backend.services.company_service import _close_missing

    prefix = f"{company.ats}:{company.board_token.lower()}:"
    links = db.execute(select(JobSourceLink).where(JobSourceLink.source == company.ats,
                                                   JobSourceLink.source_key.startswith(prefix))).scalars().all()
    live_jobs = {l.job_id for l in links if l.source_key in live_keys}
    if live_jobs:
        for l in links:
            if l.source_key in live_keys:
                l.last_seen_at = seen_at
        db.execute(update(Job).where(Job.id.in_(live_jobs)).values(last_verified_at=seen_at, closed_at=None)
                   .execution_options(synchronize_session=False))
    return _close_missing(db, company, live_keys)


# ---- reading back ---------------------------------------------------------------------------------------

def snapshot(db: Session, state: CrawlState) -> list[CataloguePosting]:
    """Postings in the target's latest complete snapshot (open ones only, for boards)."""
    q = select(CataloguePosting).where(CataloguePosting.target_key == state.target_key,
                                       CataloguePosting.snapshot_seq == state.snapshot_seq)
    if state.kind == "board":
        q = q.where(CataloguePosting.closed_at.is_(None))
    return list(db.execute(q.order_by(CataloguePosting.id)).scalars())


def snapshot_keys(db: Session, state: CrawlState) -> set[str]:
    q = select(CataloguePosting.source_key).where(CataloguePosting.target_key == state.target_key,
                                                  CataloguePosting.snapshot_seq == state.snapshot_seq,
                                                  CataloguePosting.closed_at.is_(None))
    return set(db.execute(q).scalars())


def board_result(db: Session, state: CrawlState, company: Company) -> tuple[BoardResult, list[int]]:
    """(BoardResult, posting ids in the same order), rebuilt from the catalogue in the shape ats.fetch_board returns,
    so every saved-search filter downstream runs unchanged. Descriptions are left out here and loaded by
    ``with_descriptions`` only for the postings a search keeps."""
    rows = snapshot(db, state)
    res = BoardResult(company.ats, company.board_token, company.name)
    res.jobs = [from_payload(p.payload, None, state.last_success_at) for p in rows]
    return res, [p.id for p in rows]


def feed_jobs(db: Session, state: CrawlState) -> list[NormalizedJob]:
    """A feed's latest snapshot, with descriptions (feeds are small)."""
    return [from_payload(p.payload, p.description, state.last_success_at) for p in snapshot(db, state)]


def with_descriptions(db: Session, items: list[tuple[int, NormalizedJob]]) -> list[NormalizedJob]:
    ids = [i for i, _ in items]
    desc: dict[int, str | None] = {}
    for i in range(0, len(ids), 500):
        desc.update(dict(db.execute(select(CataloguePosting.id, CataloguePosting.description)
                                    .where(CataloguePosting.id.in_(ids[i:i + 500]))).all()))
    return [dataclasses.replace(nj, description=desc.get(pid)) for pid, nj in items]
