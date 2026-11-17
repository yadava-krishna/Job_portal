"""discovery quality: normalised location, remote scope and salary; expiry date and link-check results

Additive only: nullable columns on jobs plus one index. Existing rows keep every value they have; the new columns start
NULL and are filled by the job_normalisation background job (and by every discovery run from now on). Downgrade drops
the columns and the index.

Revision ID: 0011
Revises: 0010
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(JSONB(), "postgresql")

COLUMNS = [
    sa.Column("location_normalized", sa.String(300), nullable=True),
    sa.Column("remote_scope", JSONType, nullable=True),
    sa.Column("salary_currency", sa.String(3), nullable=True),
    sa.Column("salary_min", sa.Float, nullable=True),
    sa.Column("salary_max", sa.Float, nullable=True),
    sa.Column("salary_period", sa.String(10), nullable=True),
    sa.Column("salary_period_assumed", sa.Boolean, nullable=True),
    sa.Column("expires_at", sa.Date, nullable=True),
    sa.Column("link_status", sa.String(12), nullable=True),
    sa.Column("link_checked_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("normalized_version", sa.String(20), nullable=True),
]


def upgrade() -> None:
    for col in COLUMNS:
        op.add_column("jobs", col)
    op.create_index("ix_jobs_dedup_key_open", "jobs", ["dedup_key", "closed_at"])


def downgrade() -> None:
    op.drop_index("ix_jobs_dedup_key_open", table_name="jobs")
    for col in reversed(COLUMNS):
        op.drop_column("jobs", col.name)
