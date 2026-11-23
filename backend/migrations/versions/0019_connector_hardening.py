"""Connector hardening (V3.3): which key encrypted a saved connector secret, which configuration a test result is
for, and simulated test results kept apart from real ones.

Additive only, on portal_provider_configs:
  client_secret_key_id  public id of the ENCRYPTION_KEY that encrypted client_secret_encrypted (never the key)
  last_test_config      fingerprint of the configuration (client id, redirect URI, scopes, source) the last real test
                        ran against: a result for other settings is ignored
  simulated_test        the last test against OAUTH_DEV_ENDPOINTS; never changes the real verification result
Downgrade drops the three columns.

Revision ID: 0019
Revises: 0018
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    with op.batch_alter_table("portal_provider_configs") as b:
        b.add_column(sa.Column("client_secret_key_id", sa.String(16)))
        b.add_column(sa.Column("last_test_config", sa.String(64)))
        b.add_column(sa.Column("simulated_test", JSONType))


def downgrade() -> None:
    with op.batch_alter_table("portal_provider_configs") as b:
        b.drop_column("simulated_test")
        b.drop_column("last_test_config")
        b.drop_column("client_secret_key_id")
