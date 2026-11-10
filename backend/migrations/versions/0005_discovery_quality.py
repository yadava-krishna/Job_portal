"""discovery_quality: freshness_score, is_expired, and last_scraped_at on jobs table

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06 12:35:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add freshness and expiration columns to jobs table
    op.add_column('jobs', sa.Column('freshness_score', sa.Float(), server_default='1.0', nullable=False))
    op.add_column('jobs', sa.Column('is_expired', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('jobs', sa.Column('last_scraped_at', sa.DateTime(timezone=True), nullable=True))

    # 2. Create index on (is_expired, posted_at) for fast active-listing queries
    op.create_index('ix_jobs_active_posted', 'jobs', ['is_expired', 'posted_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_jobs_active_posted', table_name='jobs')
    op.drop_column('jobs', 'last_scraped_at')
    op.drop_column('jobs', 'is_expired')
    op.drop_column('jobs', 'freshness_score')
