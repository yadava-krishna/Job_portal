"""Portal sign-in setup by an admin (LinkedIn, Indeed)

Additive only:
  portal_provider_configs  per provider: the developer app's client ID and its client secret encrypted with
                           CredentialCipher (never returned by any API), who saved it, and the result of the admin's
                           last real sign-in test. Server environment settings (LINKEDIN_CLIENT_ID, ...) take precedence.
  oauth_states.purpose     "link" (a user linking their account) or "test" (an admin testing the setup: nothing is
                           linked, only the result is recorded).
Downgrade drops the table and the column.

Revision ID: 0018
Revises: 0017
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "portal_provider_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(20), nullable=False, unique=True),
        sa.Column("client_id", sa.String(200)),
        sa.Column("client_secret_encrypted", sa.Text()),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("last_test_at", TS),
        sa.Column("last_test_status", sa.String(30)),
        sa.Column("last_test_detail", sa.String(300)),
        sa.Column("last_test_simulated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
    )
    with op.batch_alter_table("oauth_states") as b:
        b.add_column(sa.Column("purpose", sa.String(10), nullable=False, server_default="link"))


def downgrade() -> None:
    with op.batch_alter_table("oauth_states") as b:
        b.drop_column("purpose")
    op.drop_table("portal_provider_configs")
