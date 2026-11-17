"""JPSE Phase 2: the jp-fetchd contract tables (crawl_results, crawl_result_items, crawl_raw_items)

Additive only. jp-fetchd (engine/fetchd, C) writes a result and its items per board in one transaction; the Python
service applies each result once, in one transaction with the catalogue change, and records the applied posting hashes
in crawl_raw_items. Downgrade drops the three tables.

Revision ID: 0013
Revises: 0012
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BigId = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "crawl_results",
        sa.Column("id", BigId, primary_key=True, autoincrement=True),
        sa.Column("state_id", sa.Integer, sa.ForeignKey("crawl_state.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_key", sa.String(200), nullable=False),
        sa.Column("status", sa.String(15), nullable=False),
        sa.Column("http_status", sa.Integer, nullable=True),
        sa.Column("etag", sa.String(300), nullable=True),
        sa.Column("body_hash", sa.String(40), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("bytes", sa.BigInteger, nullable=True),
        sa.Column("requests", sa.Integer, nullable=True),
        sa.Column("item_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("state", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("apply_error", sa.String(500), nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("applied_at", TS, nullable=True),
    )
    op.create_index("ix_crawl_results_pending", "crawl_results", ["state", "id"])
    op.create_index("ix_crawl_results_target", "crawl_results", ["state_id", "state"])
    op.create_table(
        "crawl_result_items",
        sa.Column("id", BigId, primary_key=True, autoincrement=True),
        sa.Column("result_id", BigId, sa.ForeignKey("crawl_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_id", sa.String(200), nullable=False),
        sa.Column("raw_hash", sa.String(40), nullable=False),
        sa.Column("raw", sa.Text, nullable=True),
    )
    op.create_index("ix_crawl_result_items_result", "crawl_result_items", ["result_id"])
    op.create_table(
        "crawl_raw_items",
        sa.Column("target_key", sa.String(200), primary_key=True),
        sa.Column("raw_id", sa.String(200), primary_key=True),
        sa.Column("raw_hash", sa.String(40), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("crawl_raw_items")
    op.drop_table("crawl_result_items")
    op.drop_table("crawl_results")
