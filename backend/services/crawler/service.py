"""JPSE Phase 1: the background crawler. Crawl once for everyone; Discover reads the catalogue instead of the network.

One tick (registry job ``catalogue_crawl``, every 10 minutes, plus priority refreshes requested from Discover):

1. make sure every enabled employer board and public feed has a ``crawl_state`` row (the durable frontier);
2. pick the targets that are due, highest priority and most overdue first;
3. fetch them in parallel within the politeness limits (crawler/politeness.py), sending each board's last ETag so an
   unchanged board answers 304 Not Modified;
4. apply each result in its own transaction: catalogue upsert + outbox events, closing only after a complete valid
   snapshot, the user-facing ``jobs`` rows confirmed or closed, board health recorded;
5. schedule the next visit: sooner for boards that change, later for quiet ones, never past 12 hours, at most 1 hour
   for boards someone watches; failures back off and a priority request never overrides a back-off.

The tick has a time budget; anything not reached stays due and is picked first next time.
"""

from __future__ import annotations

import logging
import random
import threading
import time
from collections import defaultdict, deque
from queue import Empty, Queue
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.models import Company, CrawlState, SavedSearch, UserCompany, utcnow
from backend.services.ats import ashby, greenhouse, lever, recruitee, smartrecruiters
from backend.services.ats.base import AtsError, BoardResult, CrawlContext, fetch_board
from backend.services.crawler import catalogue
from backend.services.crawler.politeness import PER_HOST_IN_FLIGHT, HostLimiter, host_of
from backend.services.normalization import NormalizedJob

log = logging.getLogger(__name__)

MIN_INTERVAL = 15 * 60
DEFAULT_INTERVAL = 3600
MAX_INTERVAL = 12 * 3600
WATCHED_CAP = 3600
BACKOFF_BASE = 5 * 60
BACKOFF_MAX = 6 * 3600
DEFAULT_BUDGET_S = 240
FEEDS = ("remotive", "himalayas", "remoteok", "arbeitnow")
FEED_LIMIT = 300
# Paginated APIs are fetched in full: a 304 on the first page says nothing about later pages.
NOT_CONDITIONAL = {"smartrecruiters"}

_crawl_lock = threading.Lock()


# ---- targets ------------------------------------------------------------------------------------------

def board_key(company: Company) -> str:
    return f"ats:{company.ats}:{company.board_token.lower()}" + (f":{company.region.lower()}" if company.region else "")


def feed_key(source_id: str) -> str:
    return f"feed:{source_id}"


def _api_url(company: Company) -> str:
    t = company.board_token
    return {"greenhouse": lambda: greenhouse.API.format(token=t), "ashby": lambda: ashby.API.format(token=t),
            "lever": lambda: lever.API.get(company.region, lever.API[None]).format(token=t),
            "smartrecruiters": lambda: smartrecruiters.API.format(token=t),
            "recruitee": lambda: recruitee.API.format(token=t.lower())}.get(company.ats, lambda: f"https://{company.ats}.invalid/")()


def sync_targets(db: Session) -> int:
    """One crawl_state row per enabled board and per feed; boards that were disabled stop being crawled."""
    have = {s.target_key: s for s in db.execute(select(CrawlState)).scalars()}
    added = 0
    for c in db.execute(select(Company)).scalars():
        key = board_key(c)
        s = have.get(key)
        if s is None:
            if c.enabled:
                db.add(CrawlState(target_key=key, kind="board", company_id=c.id, next_due_at=utcnow()))
                added += 1
        elif s.enabled != c.enabled:
            s.enabled = c.enabled
    for sid in FEEDS:
        if feed_key(sid) not in have:
            db.add(CrawlState(target_key=feed_key(sid), kind="feed", next_due_at=utcnow()))
            added += 1
    db.commit()
    return added


def watched_company_ids(db: Session) -> set[int]:
    """Boards someone follows: a watchlist entry, a saved search naming the company, or JobPilot's suggested employers
    when any enabled search includes them."""
    ids = set(db.execute(select(UserCompany.company_id)).scalars())
    suggested = False
    for crit in db.execute(select(SavedSearch.criteria).where(SavedSearch.enabled.is_(True))).scalars():
        crit = crit or {}
        ids.update(int(i) for i in crit.get("company_ids") or [] if str(i).isdigit())
        suggested = suggested or bool(crit.get("include_suggested"))
    if suggested:
        ids.update(db.execute(select(Company.id).where(Company.origin == "curated")).scalars())
    return ids


def due(db: Session, now: datetime, limit: int | None = None, only: set[str] | None = None) -> list[CrawlState]:
    q = (select(CrawlState).where(CrawlState.enabled.is_(True), CrawlState.next_due_at <= now,
                                  (CrawlState.cooldown_until.is_(None)) | (CrawlState.cooldown_until <= now))
         .order_by(CrawlState.priority.desc(), CrawlState.next_due_at))
    if only is not None:
        q = q.where(CrawlState.target_key.in_(only))
    if limit:
        q = q.limit(limit)
    return list(db.execute(q).scalars())


def request_refresh(db: Session, company_ids: list[int]) -> int:
    """Ask for these boards on the next tick (Discover does this). A back-off still wins: a board that is cooling down
    after errors is not hit sooner because someone asked."""
    if not company_ids:
        return 0
    from sqlalchemy import exists, or_

    from backend.models import CrawlResult

    recent = utcnow() - timedelta(seconds=MIN_INTERVAL)
    # Never sooner than the minimum interval (politeness), never while jp-fetchd holds the board (it stamps
    # last_attempt_at when it claims), never while a result waits to be applied.
    n = db.execute(update(CrawlState).where(
        CrawlState.company_id.in_(company_ids), CrawlState.enabled.is_(True),
        or_(CrawlState.last_attempt_at.is_(None), CrawlState.last_attempt_at < recent),
        ~exists().where(CrawlResult.state_id == CrawlState.id, CrawlResult.state == "pending"),
    ).values(priority=1, next_due_at=utcnow()).execution_options(synchronize_session=False)).rowcount
    db.commit()
    return n or 0


# ---- fetching (worker threads; no database access here) -----------------------------------------------

@dataclass
class Outcome:
    state_id: int
    status: str                      # ok | not_modified | not_found | error
    jobs: list[NormalizedJob] = field(default_factory=list)
    etag: str | None = None
    body_hash: str | None = None
    error: str | None = None
    ms: int = 0
    requests: int = 0
    bytes: int = 0
    keep: set[str] = field(default_factory=set)        # still listed, content unchanged (jp-fetchd sends only changes)
    before_commit: Callable[[], None] | None = None     # extra writes that must share the applying transaction


def _fetch_board(task: dict[str, Any], limiter: HostLimiter, fetch: Callable[..., BoardResult]) -> Outcome:
    t0 = time.perf_counter()
    out = Outcome(task["state_id"], "error")
    try:
        with limiter.slot(task["host"]):
            with CrawlContext(task["etag"], conditional=task["ats"] not in NOT_CONDITIONAL) as ctx:
                try:
                    res = fetch(task["ats"], task["token"], company_name=task["name"], region=task["region"])
                    out.status, out.jobs = "ok", res.jobs
                except AtsError as exc:
                    out.status = {"not_modified": "not_modified", "not_found": "not_found"}.get(exc.kind, "error")
                    out.error = None if exc.kind == "not_modified" else str(exc)
                out.etag, out.body_hash, out.requests, out.bytes = ctx.etag_out, ctx.body_hash, ctx.requests, ctx.bytes
    except PermissionError as exc:
        out.status, out.error = "error", str(exc)
    except Exception as exc:  # a parser bug on one board must not stop the tick
        log.exception("crawl of %s failed", task.get("token"))
        out.status, out.error = "error", f"{type(exc).__name__}: {exc}"[:500]
    out.ms = int((time.perf_counter() - t0) * 1000)
    return out


def _fetch_feed(task: dict[str, Any]) -> Outcome:
    from backend.services.saved_search_service import _fetch_feed as read_feed

    t0 = time.perf_counter()
    out = Outcome(task["state_id"], "error")
    try:
        jobs, err = read_feed(task["feed"])
        out.status, out.jobs, out.error = ("error", [], err) if err else ("ok", jobs, None)
    except Exception as exc:
        out.error = f"{type(exc).__name__}: {exc}"[:500]
    out.ms = int((time.perf_counter() - t0) * 1000)
    return out


# ---- applying (main thread, one transaction per target) ---------------------------------------------------

def _aware(dt: datetime | None) -> datetime | None:
    return dt.replace(tzinfo=timezone.utc) if dt is not None and dt.tzinfo is None else dt


def next_interval(current: int, changed: bool, watched: bool) -> int:
    i = current or DEFAULT_INTERVAL
    i = max(MIN_INTERVAL, i // 2) if changed else min(MAX_INTERVAL, int(i * 1.5))
    return min(i, WATCHED_CAP) if watched else i


def _schedule(state: CrawlState, now: datetime, interval: int) -> None:
    state.interval_s = interval
    state.next_due_at = now + timedelta(seconds=int(interval * random.uniform(0.9, 1.1)))  # spread the load
    state.priority = 0


def _fail(state: CrawlState, now: datetime, status: str, error: str | None) -> None:
    state.consecutive_failures += 1
    state.last_status, state.last_error = status, (error or "")[:500] or None
    if status == "not_found":
        state.cooldown_until = None
        _schedule(state, now, MAX_INTERVAL)
    else:
        wait = min(BACKOFF_MAX, BACKOFF_BASE * 2 ** min(state.consecutive_failures - 1, 10))
        state.cooldown_until = now + timedelta(seconds=wait)
        state.next_due_at, state.priority = state.cooldown_until, 0


def _company_health(db: Session, company: Company, now: datetime, out: Outcome, count: int | None) -> None:
    from backend.services import source_registry

    company.last_fetched_at = now
    if out.status in ("ok", "not_modified"):
        company.last_error = None
        if count is not None:
            company.last_status, company.job_count = ("ok" if count else "empty"), count
        source_registry.record(db, company.ats, ok=True)
    else:
        company.last_error = (out.error or "")[:500]
        company.last_status = "not_found" if out.status == "not_found" else "error"
        source_registry.record(db, company.ats, ok=out.status == "not_found", error=None if out.status == "not_found" else out.error)


def apply_outcome(db: Session, state: CrawlState, out: Outcome, watched: bool, now: datetime | None = None) -> dict[str, Any]:
    now = now or utcnow()
    state.last_attempt_at, state.last_duration_ms = now, out.ms
    company = db.get(Company, state.company_id) if state.company_id else None
    report: dict[str, Any] = {"target": state.target_key, "status": out.status, "ms": out.ms}
    if out.status in ("not_found", "error"):
        _fail(state, now, out.status, out.error)
        if company is not None:
            _company_health(db, company, now, out, None)
        db.commit()
        return report
    state.consecutive_failures, state.cooldown_until, state.last_error = 0, None, None
    if out.status == "not_modified":
        catalogue.mark_still_listed(db, state, now)
        if company is not None:
            catalogue.sync_jobs(db, company, catalogue.snapshot_keys(db, state), now)
            _company_health(db, company, now, out, None)
        state.last_status, state.last_success_at = "not_modified", now
        state.unchanged_streak += 1
        if out.etag:
            state.etag = out.etag
        if out.body_hash:
            state.body_hash = out.body_hash
        _schedule(state, now, next_interval(state.interval_s, False, watched))
        if out.before_commit:
            out.before_commit()
        db.commit()
        return report
    # A complete snapshot. A board whose body is byte-identical to the last snapshot changed nothing.
    if out.body_hash and state.body_hash == out.body_hash and state.last_success_at is not None and state.kind == "board":
        catalogue.mark_still_listed(db, state, now)
        res = catalogue.ApplyResult(unchanged=len(out.jobs))
    else:
        for nj in out.jobs:
            if company is not None:
                nj.company_id = company.id
        res = catalogue.apply_snapshot(db, state, out.jobs, closes=state.kind == "board", now=now, keep=out.keep)
    if res.suspicious:
        # Not trusted: keep the previous snapshot, close nothing, look again soon with a full fetch.
        state.last_status, state.last_error = "suspicious_empty", "The board answered with no jobs; nothing was closed."
        state.etag = state.body_hash = None
        _schedule(state, now, MIN_INTERVAL)
        db.commit()
        report.update(status="suspicious_empty")
        return report
    if company is not None:
        live = {nj.source_key for nj in out.jobs} | out.keep
        report["jobs_closed"] = catalogue.sync_jobs(db, company, live, now)
        _company_health(db, company, now, out, state.postings_open)
    first_snapshot = state.last_success_at is None
    state.etag, state.body_hash = out.etag, out.body_hash
    state.last_success_at = now
    if res.any_change:
        state.last_changed_at, state.unchanged_streak, state.last_status = now, 0, "changed"
    else:
        state.unchanged_streak, state.last_status = state.unchanged_streak + 1, "unchanged"
    # The first snapshot is "all new" by definition; it says nothing about how often the board changes.
    _schedule(state, now, next_interval(state.interval_s, res.any_change and not first_snapshot, watched))
    if out.before_commit:
        out.before_commit()
    elif state.kind == "board":  # written by the Python crawler or a live fetch: jp-fetchd's hashes no longer describe it
        from sqlalchemy import delete

        from backend.models import CrawlRawItem
        db.execute(delete(CrawlRawItem).where(CrawlRawItem.target_key == state.target_key))
    db.commit()
    report.update(new=res.new, changed=res.changed, closed=res.closed, reopened=res.reopened, listed=len(out.jobs) + len(out.keep))
    return report


def store_live(db: Session, state: CrawlState, jobs: list[NormalizedJob]) -> dict[str, Any]:
    """Store a snapshot a saved-search run just fetched live (the board had no recent crawl), as a complete result."""
    return apply_outcome(db, state, Outcome(state.id, "ok", jobs=jobs), watched=True)


# ---- one tick ---------------------------------------------------------------------------------------------

def crawl(db: Session, *, budget_s: float = DEFAULT_BUDGET_S, limit: int | None = None, only: set[str] | None = None,
          fetch: Callable[..., BoardResult] = fetch_board, limiter: HostLimiter | None = None,
          feed_reader: Callable[[dict[str, Any]], Outcome] | None = None) -> dict[str, Any]:
    """Crawl what is due. Returns a summary; never raises for a single target's failure."""
    if not _crawl_lock.acquire(blocking=False):
        return {"skipped": "a crawl is already running"}
    t0 = time.perf_counter()
    totals: dict[str, Any] = {"targets": 0, "ok": 0, "not_modified": 0, "unchanged": 0, "changed": 0, "errors": 0,
                              "new": 0, "updated": 0, "closed": 0, "suspicious": 0, "cut_by_budget": 0}
    try:
        sync_targets(db)
        states = due(db, utcnow(), limit, only)
        from backend.services.crawler import fetchd
        if fetchd.enabled():  # jp-fetchd owns the employer boards; this crawler reads the public feeds only
            states = [s for s in states if s.kind == "feed"]
        if not states:
            return {**totals, "seconds": round(time.perf_counter() - t0, 1)}
        watched = watched_company_ids(db)
        companies = {c.id: c for c in db.execute(select(Company).where(
            Company.id.in_([s.company_id for s in states if s.company_id]))).scalars()}
        limiter = limiter or HostLimiter()
        tasks: list[tuple[CrawlState, dict[str, Any]]] = []
        for s in states:
            if s.kind == "feed":
                tasks.append((s, {"state_id": s.id, "kind": "feed", "feed": s.target_key.split(":", 1)[1]}))
            elif s.company_id in companies:
                c = companies[s.company_id]
                tasks.append((s, {"state_id": s.id, "kind": "board", "ats": c.ats, "token": c.board_token, "name": c.name,
                                  "region": c.region, "etag": s.etag if s.last_success_at else None, "host": host_of(_api_url(c))}))
        by_id = {s.id: s for s, _ in tasks}
        deadline = time.monotonic() + budget_s
        # One queue per host, worked by at most PER_HOST_IN_FLIGHT threads each: a slow or failing host only ever holds
        # its own slots, never a thread another host could use (no head-of-line blocking). The global cap still applies
        # inside each fetch (HostLimiter).
        queues: dict[str, deque] = defaultdict(deque)
        for _s, task in tasks:
            queues[task.get("host") or f"feed:{task.get('feed')}"].append(task)
        results: Queue = Queue()
        stop = threading.Event()

        def worker(host: str) -> None:
            q = queues[host]
            while not stop.is_set():
                try:
                    task = q.popleft()
                except IndexError:
                    return
                try:
                    out = (feed_reader or _fetch_feed)(task) if task["kind"] == "feed" else _fetch_board(task, limiter, fetch)
                except Exception as exc:  # never lose a result slot
                    out = Outcome(task["state_id"], "error", error=f"{type(exc).__name__}: {exc}"[:500])
                results.put(out)

        threads = [threading.Thread(target=worker, args=(h,), name=f"crawl-{h[:20]}", daemon=True)
                   for h, q in queues.items() for _ in range(min(PER_HOST_IN_FLIGHT, len(q)))]
        for t in threads:
            t.start()
        pending = len(tasks)
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0 and not stop.is_set():
                stop.set()  # stop taking new targets; fetches already in flight still finish and are applied
            try:
                out = results.get(timeout=max(0.5, min(5.0, remaining)) if remaining > 0 else 5.0)
            except Empty:
                if stop.is_set() and not any(t.is_alive() for t in threads):
                    break
                continue
            pending -= 1
            state = by_id[out.state_id]
            try:
                rep = apply_outcome(db, state, out, watched=state.company_id in watched)
            except Exception:
                log.exception("applying crawl result for %s failed", state.target_key)
                db.rollback()
                totals["errors"] += 1
                continue
            totals["targets"] += 1
            st = rep["status"]
            totals["errors"] += st in ("error", "not_found")
            totals["not_modified"] += st == "not_modified"
            totals["suspicious"] += st == "suspicious_empty"
            if st == "ok":
                totals["ok"] += 1
                changed = any(rep.get(k) for k in ("new", "changed", "closed", "reopened"))
                totals["changed" if changed else "unchanged"] += 1
                totals["new"] += rep.get("new", 0)
                totals["updated"] += rep.get("changed", 0)
                totals["closed"] += rep.get("closed", 0)
        totals["cut_by_budget"] = sum(len(q) for q in queues.values())  # still due: picked first next tick
        CrawlContext.close_all()
        totals["seconds"] = round(time.perf_counter() - t0, 1)
        log.info("catalogue crawl: %s", totals)
        return totals
    finally:
        _crawl_lock.release()


# ---- after a tick: percolation, outbox retention, user-requested refresh -------------------------------------

PERCOLATE_MIN_GAP = timedelta(minutes=30)
OUTBOX_RETENTION = timedelta(days=14)


def user_company_ids(db: Session, user_id: int) -> list[int]:
    """Boards any of this user's enabled saved searches covers (the same set a run reads)."""
    from backend.models import User
    from backend.schemas.discovery import SearchCriteria
    from backend.services.saved_search_service import _companies

    user = db.get(User, user_id)
    ids: list[int] = []
    for row in db.execute(select(SavedSearch).where(SavedSearch.user_id == user_id, SavedSearch.enabled.is_(True))).scalars():
        ids += [c.id for c in _companies(db, user, SearchCriteria.model_validate(row.criteria or {}))]
    return list(dict.fromkeys(ids))


def percolate(db: Session, settings, *, now: datetime | None = None) -> int:
    """Re-run, from the catalogue, every scheduled saved search whose boards or feeds changed since it last ran, at most
    once per 30 minutes per search. New matches then reach users (and their notifications) without anyone clicking
    Discover. Manual-only searches are left alone."""
    from backend.models import User
    from backend.schemas.discovery import SearchCriteria
    from backend.services import saved_search_service as sss

    now = now or utcnow()
    changed = {s.target_key: _aware(s.last_changed_at) for s in db.execute(select(CrawlState).where(
        CrawlState.last_changed_at.is_not(None))).scalars()}
    if not changed:
        return 0
    ran = 0
    rows = db.execute(select(SavedSearch).join(User, User.id == SavedSearch.user_id).where(
        SavedSearch.enabled.is_(True), SavedSearch.schedule != "manual", User.is_active.is_(True),
        User.onboarding_completed_at.is_not(None))).scalars().all()
    for row in rows:
        last = _aware(row.last_run_at)
        if last is not None and now - last < PERCOLATE_MIN_GAP:
            continue
        user = db.get(User, row.user_id)
        crit = SearchCriteria.model_validate(row.criteria or {})
        keys = {board_key(c) for c in sss._companies(db, user, crit)}
        if "remote_feeds" in crit.sources:
            keys.update(feed_key(f) for f in FEEDS)
        if not any(changed.get(k) and (last is None or changed[k] > last) for k in keys):
            continue
        run, created = sss.start(db, user, row, trigger="background")
        if created:
            sss.execute(db, settings, user, row, run)
            ran += 1
    return ran


def prune_outbox(db: Session, now: datetime | None = None) -> int:
    """Outbox events are kept 14 days. jp-searchd (Phase 3) starts from a full snapshot, then consumes newer events."""
    from sqlalchemy import delete

    from backend.models import IndexOutbox

    cutoff = (now or utcnow()) - OUTBOX_RETENTION
    n = db.execute(delete(IndexOutbox).where(IndexOutbox.created_at < cutoff)).rowcount or 0
    db.commit()
    return n


def refresh_for_user(db: Session, settings, user_id: int, budget_s: float = 120) -> dict[str, Any]:
    """After a Discover click has answered from the catalogue: re-check this user's boards now (cheap when they answer
    304), then let percolation bring anything new into their feed."""
    ids = user_company_ids(db, user_id)
    request_refresh(db, ids)
    keys = {s.target_key for s in db.execute(select(CrawlState).where(CrawlState.company_id.in_(ids))).scalars()} if ids else set()
    keys.update(feed_key(f) for f in FEEDS)
    rep = crawl(db, budget_s=budget_s, only=keys)
    if rep.get("changed") or rep.get("new"):
        rep["percolated"] = percolate(db, settings)
    return rep
