"""JPSE: index index_outbox by time, for jp-searchd's time-window overlap when following changes

Additive only. Downgrade drops the index.

Revision ID: 0014
Revises: 0013
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_index_outbox_created", "index_outbox", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_index_outbox_created", table_name="index_outbox")
