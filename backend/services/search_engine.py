"""JPSE Phase 3: the client for jp-searchd (engine/searchd), with the PostgreSQL fallback the blueprint requires.

``search()`` asks the native engine over its Unix socket with a short deadline. If the engine is off, not ready,
slow or failing, the same query runs in PostgreSQL (GIN full-text over the catalogue + the same exact filters), so a
caller always gets an answer. Mode (``JPSE_SEARCH``):

- ``off``: PostgreSQL only;
- ``shadow`` (default): answer from PostgreSQL, ask the engine too and log how much the two top lists agree;
- ``on``: answer from the engine, PostgreSQL only as the fallback.

Filters are exact and never loosened (blueprint §2): an unknown filter value matches nothing.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

SOCKET = os.environ.get("JPSE_SEARCH_SOCKET", "/run/jpse/searchd.sock")
DEADLINE_S = float(os.environ.get("JPSE_SEARCH_DEADLINE_MS", "250")) / 1000
MAX_LIMIT = 20000


def mode() -> str:
    m = os.environ.get("JPSE_SEARCH", "shadow").strip().lower()
    return m if m in ("off", "shadow", "on") else "shadow"


@dataclass
class Query:
    terms: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)      # ISO codes; matched with remote_open_to as one OR group
    remote_open_to: list[str] = field(default_factory=list)  # remote postings open to these countries (or "*" anywhere)
    work_modes: list[str] = field(default_factory=list)       # "Remote" | "Hybrid" | "On-site"
    employment_types: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    company_ids: list[int] = field(default_factory=list)
    posted_within_days: int | None = None
    salary_currency: str | None = None
    salary_min: float | None = None
    salary_unknown_ok: bool = False
    all_terms: bool = False
    title_only: bool = False   # candidate mode: terms are normalize_text words, matched against titles only
    prefix: bool = False       # with title_only: 5+ letter words also match title words starting with them
    limit: int = 50

    def groups(self) -> list[list[str]]:
        g: list[list[str]] = []
        place = [f"country:{c}" for c in self.countries] + [f"remote:{c}" for c in self.remote_open_to]
        if place:
            g.append(place)
        for prefix, vals in (("mode", self.work_modes), ("type", self.employment_types), ("source", self.sources),
                             ("company", [str(i) for i in self.company_ids])):
            if vals:
                g.append([f"{prefix}:{v}" for v in vals])
        return g

    def posted_after_day(self) -> int | None:
        if not self.posted_within_days:
            return None
        return (date.today() - timedelta(days=self.posted_within_days) - date(1970, 1, 1)).days

    def to_request(self) -> dict[str, Any]:
        req: dict[str, Any] = {"method": "search", "limit": max(1, min(MAX_LIMIT, self.limit))}
        if self.terms:
            req["terms"] = [t[:200] for t in self.terms if t and t.strip()][:64]
        if self.groups():
            req["filters"] = self.groups()
        if self.posted_after_day() is not None:
            req["posted_after_day"] = self.posted_after_day()
        if self.salary_currency and self.salary_min:
            req["salary"] = {"currency": self.salary_currency, "min": self.salary_min, "unknown_ok": self.salary_unknown_ok}
        if self.all_terms:
            req["all_terms"] = True
        if self.title_only:
            req["title_only"] = True
        if self.prefix:
            req["prefix"] = True
        return req


@dataclass
class Result:
    ids: list[int]
    scores: list[float]
    engine: str          # "jp-searchd" | "postgres"
    took_ms: float
    candidates: int | None = None


class EngineError(Exception):
    pass


# ---- the native engine ----------------------------------------------------------------------------------

_local = threading.local()


def _conn() -> socket.socket:
    s = getattr(_local, "sock", None)
    if s is None:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(DEADLINE_S)
        s.connect(SOCKET)
        _local.sock = s
    return s


def _drop() -> None:
    s = getattr(_local, "sock", None)
    if s is not None:
        try:
            s.close()
        finally:
            _local.sock = None


def _recv_exact(s: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise EngineError("connection closed")
        buf += chunk
    return bytes(buf)


def call(req: dict[str, Any]) -> dict[str, Any]:
    """One request/response on this thread's persistent connection; any failure drops the connection."""
    body = json.dumps(req, separators=(",", ":")).encode()
    for attempt in (1, 2):  # the server closes idle connections: a stale socket gets one fresh retry
        reused = getattr(_local, "sock", None) is not None
        try:
            s = _conn()
            s.sendall(struct.pack(">I", len(body)) + body)
            (n,) = struct.unpack(">I", _recv_exact(s, 4))
            if n > 64 * 1024 * 1024:
                raise EngineError("oversized response")
            return json.loads(_recv_exact(s, n))
        except (OSError, ValueError, EngineError) as exc:
            _drop()
            if attempt == 1 and reused and not isinstance(exc, (socket.timeout, ValueError)):
                continue
            raise EngineError(str(exc) or type(exc).__name__) from None
    raise EngineError("unreachable")


def engine_search(q: Query) -> Result:
    t0 = time.perf_counter()
    r = call(q.to_request())
    if not r.get("ok"):
        raise EngineError(r.get("error") or "engine error")
    hits = r.get("hits") or []
    return Result([int(h[0]) for h in hits], [float(h[1]) for h in hits], "jp-searchd", (time.perf_counter() - t0) * 1000,
                  r.get("candidates"))


def engine_health() -> dict[str, Any]:
    try:
        return call({"method": "health"})
    except EngineError as exc:
        return {"ok": False, "error": str(exc)}


# ---- PostgreSQL (fallback and baseline) ----------------------------------------------------------------------

_FTS = ("setweight(to_tsvector('simple', coalesce(title, '')), 'A') || setweight(to_tsvector('simple', coalesce(company, '')), 'B') || "
        "setweight(to_tsvector('simple', coalesce(location, '')), 'C')")


def postgres_search(db: Session, q: Query) -> Result:
    t0 = time.perf_counter()
    where = ["closed_at IS NULL", "(expires_at IS NULL OR expires_at >= current_date)"]
    params: dict[str, Any] = {"limit": max(1, min(MAX_LIMIT, q.limit))}
    pg = db.get_bind().dialect.name == "postgresql"
    if q.countries or q.remote_open_to:
        ors = []
        if q.countries:
            ors.append("country = ANY(:countries)" if pg else "country IN :countries")
            params["countries"] = list(q.countries) if pg else tuple(q.countries)
        for i, c in enumerate(q.remote_open_to):
            ors.append(f"remote_scope::text LIKE :rs{i}")
            params[f"rs{i}"] = f'%"{c}"%'
        where.append("(" + " OR ".join(ors) + ")")
    for col, vals, key in (("work_mode", q.work_modes, "modes"), ("employment_type", q.employment_types, "types"),
                           ("source", q.sources, "sources"), ("company_id", q.company_ids, "cids")):
        if vals:
            where.append(f"{col} = ANY(:{key})" if pg else f"{col} IN :{key}")
            params[key] = list(vals) if pg else tuple(vals)
    if q.posted_within_days:
        where.append("posted_at >= :since")
        params["since"] = date.today() - timedelta(days=q.posted_within_days)
    if q.salary_currency and q.salary_min:
        cond = "(salary_currency = :cur AND coalesce(salary_max, salary_min) >= :smin)"
        if q.salary_unknown_ok:
            cond = f"({cond} OR salary_currency IS NULL)"
        where.append(cond)
        params.update(cur=q.salary_currency, smin=q.salary_min)
    terms = [w for t in q.terms for w in t.lower().split() if w.isalnum() or w.replace("+", "").replace("#", "").isalnum()]
    if terms and pg:
        params["tsq"] = (" & " if q.all_terms else " | ").join(dict.fromkeys(terms))
        where.append(f"{_FTS} @@ to_tsquery('simple', :tsq)")
        order = f"ts_rank({_FTS}, to_tsquery('simple', :tsq)) DESC, id"
    elif terms:  # SQLite (tests): word match on title/company
        conds = []
        for i, w in enumerate(dict.fromkeys(terms)):
            conds.append(f"(lower(title) LIKE :w{i} OR lower(company) LIKE :w{i})")
            params[f"w{i}"] = f"%{w}%"
        where.append("(" + (" AND " if q.all_terms else " OR ").join(conds) + ")")
        order = "posted_at DESC, id"
    else:
        order = "posted_at DESC NULLS LAST, id" if pg else "posted_at IS NULL, posted_at DESC, id"  # unknown dates last, as the engine
    sql = f"SELECT id FROM catalogue_postings WHERE {' AND '.join(where)} ORDER BY {order} LIMIT :limit"
    if not pg:
        from sqlalchemy import bindparam

        stmt = text(sql)
        for k in ("countries", "modes", "types", "sources", "cids"):
            if k in params:
                stmt = stmt.bindparams(bindparam(k, expanding=True))
        ids = [r[0] for r in db.execute(stmt, params)]
    else:
        ids = [r[0] for r in db.execute(text(sql), params)]
    return Result(ids, [], "postgres", (time.perf_counter() - t0) * 1000)


# ---- the entry point ----------------------------------------------------------------------------------------

def search(db: Session, q: Query) -> Result:
    m = mode()
    if m == "on":
        try:
            return engine_search(q)
        except EngineError as exc:
            log.warning("jp-searchd unavailable (%s); answering from PostgreSQL", exc)
            return postgres_search(db, q)
    pg = postgres_search(db, q)
    if m == "shadow":
        try:
            e = engine_search(q)
            k = min(50, len(pg.ids), len(e.ids))
            overlap = len(set(pg.ids[:k]) & set(e.ids[:k])) / k if k else 1.0
            log.info("jpse shadow: terms=%d pg=%d/%.1fms engine=%d/%.1fms top%d_overlap=%.2f", len(q.terms), len(pg.ids), pg.took_ms,
                     len(e.ids), e.took_ms, k, overlap)
        except EngineError as exc:
            log.info("jpse shadow: engine unavailable (%s)", exc)
    return pg
