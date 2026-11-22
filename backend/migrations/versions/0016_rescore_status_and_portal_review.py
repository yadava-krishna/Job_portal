"""Match-score refresh status and portal profile review

Additive only:
  job_preferences.rescore_requested_at / rescored_at  when a preference or profile change asked for new match scores,
                                                      and when they were last recomputed (both nullable)
  candidate_profiles.portal_review                    per-portal checklist items the user marked done (JSON, default {})
Downgrade drops the three columns.

Revision ID: 0016
Revises: 0015
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.add_column("job_preferences", sa.Column("rescore_requested_at", TS, nullable=True))
    op.add_column("job_preferences", sa.Column("rescored_at", TS, nullable=True))
    op.add_column("candidate_profiles", sa.Column("portal_review", JSONType, nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("candidate_profiles", "portal_review")
    op.drop_column("job_preferences", "rescored_at")
    op.drop_column("job_preferences", "rescore_requested_at")
