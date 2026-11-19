"""Smart Apply: answer memory and the prepared application package

Additive only: a new `answer_memory` table and an `applications.package` JSON column (default {}). Downgrade drops
both.

Revision ID: 0015
Revises: 0014
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "answer_memory",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("scope_ref", sa.String(200), nullable=False, server_default=""),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("value_type", sa.String(20), nullable=False),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("value_json", JSONType, nullable=True),
        sa.Column("value_text", sa.Text, nullable=True),
        sa.Column("value_encrypted", sa.Text, nullable=True),
        sa.Column("sensitivity", sa.String(10), nullable=False, server_default="personal"),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="1"),
        sa.Column("status", sa.String(12), nullable=False, server_default="verified"),
        sa.Column("question_text", sa.String(500), nullable=True),
        sa.Column("question_norm", sa.String(500), nullable=True),
        sa.Column("last_confirmed_at", TS, nullable=True),
        sa.Column("revalidate_days", sa.Integer, nullable=True),
        sa.Column("history", JSONType, nullable=False, server_default="[]"),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.UniqueConstraint("user_id", "key", "scope_ref", name="uq_answer_memory_user_key_scope"),
    )
    op.create_index("ix_answer_memory_user_id", "answer_memory", ["user_id"])
    op.add_column("applications", sa.Column("package", JSONType, nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("applications", "package")
    op.drop_index("ix_answer_memory_user_id", table_name="answer_memory")
    op.drop_table("answer_memory")
