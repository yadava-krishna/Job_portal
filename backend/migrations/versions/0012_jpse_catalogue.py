"""JPSE Phase 1: crawl frontier, catalogue of every permitted posting, durable index outbox

Additive only: three new tables, nothing existing is altered. On PostgreSQL a GIN full-text index over the catalogue is
the search baseline and the fallback the blueprint requires (JOBPILOT_JPSE_BLUEPRINT.md §9). Downgrade drops the tables.

Revision ID: 0012
Revises: 0011
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(JSONB(), "postgresql")
BigId = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "crawl_state",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("target_key", sa.String(200), nullable=False, unique=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="CASCADE"), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("priority", sa.SmallInteger, nullable=False, server_default="0"),
        sa.Column("interval_s", sa.Integer, nullable=False, server_default="3600"),
        sa.Column("next_due_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("cooldown_until", TS, nullable=True),
        sa.Column("etag", sa.String(300), nullable=True),
        sa.Column("body_hash", sa.String(40), nullable=True),
        sa.Column("snapshot_seq", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempt_at", TS, nullable=True),
        sa.Column("last_success_at", TS, nullable=True),
        sa.Column("last_changed_at", TS, nullable=True),
        sa.Column("last_status", sa.String(20), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("last_duration_ms", sa.Integer, nullable=True),
        sa.Column("consecutive_failures", sa.Integer, nullable=False, server_default="0"),
        sa.Column("postings_open", sa.Integer, nullable=False, server_default="0"),
        sa.Column("unchanged_streak", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_crawl_state_due", "crawl_state", ["next_due_at", "priority"])

    op.create_table(
        "catalogue_postings",
        sa.Column("id", BigId, primary_key=True, autoincrement=True),
        sa.Column("source_key", sa.String(300), nullable=False, unique=True),
        sa.Column("target_key", sa.String(200), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("company_id", sa.Integer, sa.ForeignKey("companies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("company", sa.String(300), nullable=False),
        sa.Column("location", sa.String(500), nullable=True),
        sa.Column("location_normalized", sa.String(300), nullable=True),
        sa.Column("country", sa.String(80), nullable=True),
        sa.Column("remote_scope", JSONType, nullable=True),
        sa.Column("work_mode", sa.String(20), nullable=True),
        sa.Column("employment_type", sa.String(40), nullable=True),
        sa.Column("seniority", sa.String(40), nullable=True),
        sa.Column("salary_currency", sa.String(3), nullable=True),
        sa.Column("salary_min", sa.Float, nullable=True),
        sa.Column("salary_max", sa.Float, nullable=True),
        sa.Column("salary_period", sa.String(10), nullable=True),
        sa.Column("posted_at", sa.Date, nullable=True),
        sa.Column("expires_at", sa.Date, nullable=True),
        sa.Column("job_url", sa.String(1000), nullable=True),
        sa.Column("skills", JSONType, nullable=False),
        sa.Column("payload", JSONType, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("content_hash", sa.String(40), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("snapshot_seq", sa.Integer, nullable=False, server_default="0"),
        sa.Column("first_seen_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("changed_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", TS, nullable=True),
    )
    op.create_index("ix_catalogue_target_seq", "catalogue_postings", ["target_key", "snapshot_seq"])
    op.create_index("ix_catalogue_open_posted", "catalogue_postings", ["closed_at", "posted_at"])
    op.create_index("ix_catalogue_company", "catalogue_postings", ["company_id"])
    if op.get_bind().dialect.name == "postgresql":
        # Weighted full-text baseline: title (A), company (B), location (C). Descriptions are added by jp-searchd later.
        op.execute(
            "CREATE INDEX ix_catalogue_fts ON catalogue_postings USING GIN (("
            "setweight(to_tsvector('simple', coalesce(title, '')), 'A') || "
            "setweight(to_tsvector('simple', coalesce(company, '')), 'B') || "
            "setweight(to_tsvector('simple', coalesce(location, '')), 'C')))"
        )

    op.create_table(
        "index_outbox",
        sa.Column("id", BigId, primary_key=True, autoincrement=True),
        sa.Column("posting_id", BigId, sa.ForeignKey("catalogue_postings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("event", sa.String(10), nullable=False),
        sa.Column("state", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("lease_until", TS, nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", TS, nullable=True),
    )
    op.create_index("ix_index_outbox_pending", "index_outbox", ["state", "id"])


def downgrade() -> None:
    op.drop_table("index_outbox")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_catalogue_fts")
    op.drop_table("catalogue_postings")
    op.drop_table("crawl_state")
