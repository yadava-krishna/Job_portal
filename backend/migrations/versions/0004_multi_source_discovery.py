"""multi_source_discovery: source_connectors, user_career_urls, and extraction provenance

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06 11:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')

    # 1. source_connectors table
    op.create_table(
        'source_connectors',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_id', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('domain', sa.String(length=255), nullable=True),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('access_method', sa.String(length=50), nullable=False),
        sa.Column('permission_status', sa.String(length=50), server_default='permission_required', nullable=False),
        sa.Column('enabled', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('config', json_type, server_default='{}', nullable=False),
        sa.Column('rate_limit_rpm', sa.Integer(), server_default='10', nullable=False),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('health_status', sa.String(length=20), server_default='unknown', nullable=False),
        sa.Column('jobs_discovered', sa.Integer(), server_default='0', nullable=False),
        sa.Column('jobs_updated', sa.Integer(), server_default='0', nullable=False),
        sa.Column('jobs_rejected', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_id', name='uq_source_connectors_source_id')
    )

    # 2. user_career_urls table
    op.create_table(
        'user_career_urls',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=True),
        sa.Column('detected_ats', sa.String(length=50), nullable=True),
        sa.Column('detected_sources', json_type, server_default='[]', nullable=False),
        sa.Column('robots_txt_status', sa.String(length=20), nullable=True),
        sa.Column('sitemap_url', sa.Text(), nullable=True),
        sa.Column('feed_url', sa.Text(), nullable=True),
        sa.Column('has_json_ld', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('last_crawled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('jobs_found', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'url', name='uq_user_career_urls_user_url')
    )
    op.create_index(op.f('ix_user_career_urls_user_id'), 'user_career_urls', ['user_id'], unique=False)

    # 3. Add columns to jobs table
    op.add_column('jobs', sa.Column('country', sa.String(length=10), nullable=True))
    op.add_column('jobs', sa.Column('seniority', sa.String(length=50), nullable=True))
    op.add_column('jobs', sa.Column('application_url', sa.String(length=1000), nullable=True))
    op.add_column('jobs', sa.Column('extraction_method', sa.String(length=50), nullable=True))
    op.add_column('jobs', sa.Column('extraction_confidence', sa.Float(), nullable=True))
    op.add_column('jobs', sa.Column('parser_version', sa.String(length=50), nullable=True))

    # 4. Add columns to job_source_links table
    op.add_column('job_source_links', sa.Column('extraction_method', sa.String(length=50), nullable=True))
    op.add_column('job_source_links', sa.Column('extraction_confidence', sa.Float(), nullable=True))
    op.add_column('job_source_links', sa.Column('connector_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_job_source_links_connector_id', 'job_source_links', 'source_connectors', ['connector_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_job_source_links_connector_id', 'job_source_links', type_='foreignkey')
    op.drop_column('job_source_links', 'connector_id')
    op.drop_column('job_source_links', 'extraction_confidence')
    op.drop_column('job_source_links', 'extraction_method')

    op.drop_column('jobs', 'parser_version')
    op.drop_column('jobs', 'extraction_confidence')
    op.drop_column('jobs', 'extraction_method')
    op.drop_column('jobs', 'application_url')
    op.drop_column('jobs', 'seniority')
    op.drop_column('jobs', 'country')

    op.drop_index(op.f('ix_user_career_urls_user_id'), table_name='user_career_urls')
    op.drop_table('user_career_urls')
    op.drop_table('source_connectors')
