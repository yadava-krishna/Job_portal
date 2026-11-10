"""strategic_expansion: career intelligence, resume studio, apply orchestrator, analytics, government benefits, task queue

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-06 14:15:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

JSONType = sa.JSON().with_variant(JSONB(), "postgresql")

revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. candidate_profiles_v2
    op.create_table(
        'candidate_profiles_v2',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False),
        sa.Column('headline', sa.String(255), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('years_experience', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('relevant_it_experience', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('highest_education_level', sa.String(50), nullable=True),
        sa.Column('preferred_locations', JSONType, server_default='[]', nullable=False),
        sa.Column('work_modes', JSONType, server_default='[]', nullable=False),
        sa.Column('work_authorization', sa.String(100), server_default='India (Citizen)', nullable=False),
        sa.Column('expected_ctc_inr', sa.Integer(), nullable=True),
        sa.Column('notice_period_days', sa.Integer(), server_default='30', nullable=False),
        sa.Column('verified_facts', JSONType, server_default='{}', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 2. profile_work_experiences
    op.create_table(
        'profile_work_experiences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('profile_id', sa.Integer(), sa.ForeignKey('candidate_profiles_v2.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('company', sa.String(200), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('is_current', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('technologies', JSONType, server_default='[]', nullable=False),
        sa.Column('verified_bullets', JSONType, server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 3. profile_skills
    op.create_table(
        'profile_skills',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('profile_id', sa.Integer(), sa.ForeignKey('candidate_profiles_v2.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(100), nullable=False, index=True),
        sa.Column('category', sa.String(50), server_default='technical', nullable=False),
        sa.Column('proficiency', sa.String(30), server_default='INTERMEDIATE', nullable=False),
        sa.Column('years', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('is_verified', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    )

    # 4. job_match_reports
    op.create_table(
        'job_match_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('job_id', sa.Integer(), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('composite_score', sa.Float(), nullable=False),
        sa.Column('eligibility_score', sa.Float(), nullable=False),
        sa.Column('skill_score', sa.Float(), nullable=False),
        sa.Column('experience_score', sa.Float(), nullable=False),
        sa.Column('preference_score', sa.Float(), nullable=False),
        sa.Column('matched_skills', JSONType, server_default='[]', nullable=False),
        sa.Column('missing_skills', JSONType, server_default='[]', nullable=False),
        sa.Column('disqualifiers', JSONType, server_default='[]', nullable=False),
        sa.Column('explanation', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('user_id', 'job_id', name='uq_job_match_reports_user_job'),
    )

    # 5. tailored_resumes
    op.create_table(
        'tailored_resumes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('job_id', sa.Integer(), sa.ForeignKey('jobs.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('selected_bullets', JSONType, server_default='[]', nullable=False),
        sa.Column('tailored_summary', sa.Text(), nullable=True),
        sa.Column('is_truthful_audited', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('user_id', 'job_id', name='uq_tailored_resumes_user_job'),
    )

    # 6. ats_diagnostic_reports
    op.create_table(
        'ats_diagnostic_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('resume_id', sa.Integer(), nullable=True),
        sa.Column('tailored_resume_id', sa.Integer(), sa.ForeignKey('tailored_resumes.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('tier1_structure_score', sa.Float(), nullable=False),
        sa.Column('tier2_content_score', sa.Float(), nullable=False),
        sa.Column('tier3_parsing_score', sa.Float(), nullable=False),
        sa.Column('overall_score', sa.Float(), nullable=False),
        sa.Column('findings', JSONType, server_default='[]', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 7. Add route columns to applications table
    op.add_column('applications', sa.Column('application_route', sa.String(50), server_default='ROUTE_D_EXTERNAL_MANUAL', nullable=False))
    op.add_column('applications', sa.Column('tailored_resume_id', sa.Integer(), sa.ForeignKey('tailored_resumes.id', ondelete='SET NULL'), nullable=True))
    op.add_column('applications', sa.Column('route_metadata', JSONType, server_default='{}', nullable=False))

    # 8. stage_transitions
    op.create_table(
        'stage_transitions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('application_id', sa.Integer(), sa.ForeignKey('applications.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('from_stage', sa.String(30), nullable=True),
        sa.Column('to_stage', sa.String(30), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('transitioned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 9. it_government_schemes
    op.create_table(
        'it_government_schemes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('code', sa.String(100), unique=True, nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('state_or_central', sa.String(50), nullable=False),
        sa.Column('beneficiary_type', sa.String(50), nullable=False),
        sa.Column('max_funding_inr', sa.Float(), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('eligibility_criteria', JSONType, server_default='[]', nullable=False),
        sa.Column('benefits_summary', sa.Text(), nullable=False),
        sa.Column('application_url', sa.Text(), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # 10. user_saved_schemes
    op.create_table(
        'user_saved_schemes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('scheme_id', sa.Integer(), sa.ForeignKey('it_government_schemes.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('is_eligible', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('eligibility_reasons', JSONType, server_default='[]', nullable=False),
        sa.Column('saved_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('user_id', 'scheme_id', name='uq_user_saved_schemes_user_scheme'),
    )

    # 11. task_queue
    op.create_table(
        'task_queue',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('task_type', sa.String(100), nullable=False, index=True),
        sa.Column('payload', JSONType, server_default='{}', nullable=False),
        sa.Column('status', sa.String(30), server_default='QUEUED', nullable=False, index=True),
        sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('max_retries', sa.Integer(), server_default='3', nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('task_queue')
    op.drop_table('user_saved_schemes')
    op.drop_table('it_government_schemes')
    op.drop_table('stage_transitions')
    op.drop_column('applications', 'route_metadata')
    op.drop_column('applications', 'tailored_resume_id')
    op.drop_column('applications', 'application_route')
    op.drop_table('ats_diagnostic_reports')
    op.drop_table('tailored_resumes')
    op.drop_table('job_match_reports')
    op.drop_table('profile_skills')
    op.drop_table('profile_work_experiences')
    op.drop_table('candidate_profiles_v2')
