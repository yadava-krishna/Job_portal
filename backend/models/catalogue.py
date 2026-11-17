"""JPSE Phase 1 (migration 0012): the crawl frontier, the catalogue of every permitted posting, and the durable outbox.

PostgreSQL stays the source of truth (JOBPILOT_JPSE_BLUEPRINT.md §4):

- ``crawl_state``: one row per crawl target (an employer board, or a public feed). The background crawler resumes
  from it after any restart: validators (ETag), adaptive interval, back-off, and the last complete snapshot.
- ``catalogue_postings``: every posting the crawler saw, for everyone, not only jobs that matched a user. Identity is
  the source's own requisition key (``source_key``, e.g. ``greenhouse:stripe:4745511005``), never company+title.
- ``index_outbox``: written in the same transaction as each posting change, so a future index (jp-searchd) can apply
  every revision at least once and in per-posting order. LISTEN/NOTIFY is never the only delivery mechanism.

No table here is user-owned; nothing personal is stored.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base
from backend.models import JSONType, utcnow

BigId = BigInteger().with_variant(Integer(), "sqlite")  # SQLite autoincrements INTEGER PRIMARY KEY only


class CrawlState(Base):
    __tablename__ = "crawl_state"
    __table_args__ = (Index("ix_crawl_state_due", "next_due_at", "priority"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    target_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)  # "ats:greenhouse:stripe" | "feed:himalayas"
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # board | feed
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)  # >0: someone asked for it now
    interval_s: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # back-off; priority never overrides it
    etag: Mapped[str | None] = mapped_column(String(300))
    body_hash: Mapped[str | None] = mapped_column(String(40))
    snapshot_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # bumped on every complete snapshot that changed
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # last complete, valid snapshot (incl. 304)
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20))  # changed | unchanged | not_modified | suspicious_empty | not_found | error
    last_error: Mapped[str | None] = mapped_column(String(500))
    last_duration_ms: Mapped[int | None] = mapped_column(Integer)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    postings_open: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unchanged_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CataloguePosting(Base):
    __tablename__ = "catalogue_postings"
    __table_args__ = (
        Index("ix_catalogue_target_seq", "target_key", "snapshot_seq"),
        Index("ix_catalogue_open_posted", "closed_at", "posted_at"),
        Index("ix_catalogue_company", "company_id"),
    )

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    source_key: Mapped[str] = mapped_column(String(300), unique=True, nullable=False)
    target_key: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id", ondelete="SET NULL"))
    # Searchable facts. Raw text is kept; normalised values come from core/locations.py and core/salary.py.
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(300), nullable=False)
    location: Mapped[str | None] = mapped_column(String(500))
    location_normalized: Mapped[str | None] = mapped_column(String(300))
    country: Mapped[str | None] = mapped_column(String(80))
    remote_scope: Mapped[list[str] | None] = mapped_column(JSONType)
    work_mode: Mapped[str | None] = mapped_column(String(20))
    employment_type: Mapped[str | None] = mapped_column(String(40))
    seniority: Mapped[str | None] = mapped_column(String(40))
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_min: Mapped[float | None] = mapped_column(Float)
    salary_max: Mapped[float | None] = mapped_column(Float)
    salary_period: Mapped[str | None] = mapped_column(String(10))
    posted_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    job_url: Mapped[str | None] = mapped_column(String(1000))
    skills: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    # The full source record without its description, and the description separately: a saved-search run filters on the
    # small record first and loads descriptions only for postings it keeps.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    snapshot_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # crawl_state.snapshot_seq it was last seen in
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IndexOutbox(Base):
    __tablename__ = "index_outbox"
    __table_args__ = (Index("ix_index_outbox_pending", "state", "id"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    posting_id: Mapped[int] = mapped_column(ForeignKey("catalogue_postings.id", ondelete="CASCADE"), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    event: Mapped[str] = mapped_column(String(10), nullable=False)  # upsert | close | reopen
    state: Mapped[str] = mapped_column(String(10), default="pending", nullable=False)  # pending | done | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CrawlResult(Base):
    """One board fetch by jp-fetchd (migration 0013). Written in one transaction with its items; applied once by Python."""

    __tablename__ = "crawl_results"
    __table_args__ = (Index("ix_crawl_results_pending", "state", "id"), Index("ix_crawl_results_target", "state_id", "state"))

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    state_id: Mapped[int] = mapped_column(ForeignKey("crawl_state.id", ondelete="CASCADE"), nullable=False)
    target_key: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False)  # ok | not_modified | unchanged | not_found | error
    http_status: Mapped[int | None] = mapped_column(Integer)
    etag: Mapped[str | None] = mapped_column(String(300))
    body_hash: Mapped[str | None] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(String(500))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    bytes: Mapped[int | None] = mapped_column(BigInteger)
    requests: Mapped[int | None] = mapped_column(Integer)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    state: Mapped[str] = mapped_column(String(10), default="pending", nullable=False)  # pending | applied | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    apply_error: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CrawlResultItem(Base):
    """A posting in a jp-fetchd result: its source id and content hash, plus its raw JSON when it changed."""

    __tablename__ = "crawl_result_items"
    __table_args__ = (Index("ix_crawl_result_items_result", "result_id"),)

    id: Mapped[int] = mapped_column(BigId, primary_key=True, autoincrement=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("crawl_results.id", ondelete="CASCADE"), nullable=False)
    raw_id: Mapped[str] = mapped_column(String(200), nullable=False)
    raw_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    raw: Mapped[str | None] = mapped_column(Text)  # minified JSON; NULL = unchanged since the last applied snapshot


class CrawlRawItem(Base):
    """The posting hashes of each board's last applied snapshot. Written only by the Python applier, in the same
    transaction as the catalogue change, so jp-fetchd's "unchanged" can never refer to something that was not applied."""

    __tablename__ = "crawl_raw_items"

    target_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    raw_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    raw_hash: Mapped[str] = mapped_column(String(40), nullable=False)
