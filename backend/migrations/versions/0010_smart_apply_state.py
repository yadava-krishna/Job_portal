"""smart apply: fine-grained application state recorded by the browser extension

Additive only: four nullable/defaulted columns on applications. Existing rows keep their status and get no apply
state (NULL), which the app treats as "not started with Smart Apply". Downgrade drops the four columns.

Revision ID: 0010
Revises: 0009
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("applications", sa.Column("apply_state", sa.String(30), nullable=True))
    op.add_column("applications", sa.Column("apply_state_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("applications", sa.Column("apply_mode", sa.String(20), nullable=True))
    op.add_column("applications", sa.Column("apply_session", JSONType, server_default="{}", nullable=False))


def downgrade() -> None:
    op.drop_column("applications", "apply_session")
    op.drop_column("applications", "apply_mode")
    op.drop_column("applications", "apply_state_at")
    op.drop_column("applications", "apply_state")
