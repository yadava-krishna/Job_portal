"""job search: full-text GIN index (PostgreSQL only) and indexes for the new filters

Revision ID: 0008
Revises: 0007
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TSV = "to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(company, '') || ' ' || coalesce(description, ''))"


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"CREATE INDEX IF NOT EXISTS ix_jobs_fulltext ON jobs USING gin ({TSV})")
    op.create_index("ix_jobs_sponsorship_signal", "jobs", ["sponsorship_signal"])
    op.create_index("ix_user_jobs_user_eligibility", "user_jobs", ["user_id", "eligibility"])


def downgrade() -> None:
    op.drop_index("ix_user_jobs_user_eligibility", table_name="user_jobs")
    op.drop_index("ix_jobs_sponsorship_signal", table_name="jobs")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_jobs_fulltext")
