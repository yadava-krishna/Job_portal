"""Portal account linking (LinkedIn OpenID Connect, Indeed OAuth)

Additive only:
  external_identities  a portal account linked through the portal's official sign-in: provider + stable subject id,
                       the identity fields the provider shared, granted scopes, encrypted tokens, expiry and status.
                       Unique (provider, subject): one portal account per JobPilot user. Unique (user_id, provider).
  oauth_states         pending sign-ins: SHA-256 of the state, nonce, encrypted PKCE verifier, exact redirect URI,
                       10-minute expiry, single use. Bound to the user who started it.
Both cascade on user deletion. Downgrade drops both tables.

Revision ID: 0017
Revises: 0016
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "external_identities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("email", sa.String(320)),
        sa.Column("email_verified", sa.Boolean()),
        sa.Column("picture_url", sa.Text()),
        sa.Column("scopes", JSONType, nullable=False, server_default="[]"),
        sa.Column("access_token_encrypted", sa.Text()),
        sa.Column("refresh_token_encrypted", sa.Text()),
        sa.Column("access_expires_at", TS),
        sa.Column("refresh_expires_at", TS),
        sa.Column("status", sa.String(30), nullable=False, server_default="linked"),
        sa.Column("status_detail", sa.String(300)),
        sa.Column("checks", JSONType, nullable=False, server_default="{}"),
        sa.Column("linked_at", TS, nullable=False),
        sa.Column("last_validated_at", TS),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("updated_at", TS, nullable=False),
        sa.UniqueConstraint("provider", "subject", name="uq_external_identity_subject"),
        sa.UniqueConstraint("user_id", "provider", name="uq_external_identity_user_provider"),
    )
    op.create_index("ix_external_identities_user_id", "external_identities", ["user_id"])
    op.create_table(
        "oauth_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("nonce", sa.String(100)),
        sa.Column("code_verifier_encrypted", sa.Text()),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("scopes", JSONType, nullable=False, server_default="[]"),
        sa.Column("created_at", TS, nullable=False),
        sa.Column("expires_at", TS, nullable=False),
        sa.Column("used_at", TS),
    )
    op.create_index("ix_oauth_states_user_id", "oauth_states", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_oauth_states_user_id", table_name="oauth_states")
    op.drop_table("oauth_states")
    op.drop_index("ix_external_identities_user_id", table_name="external_identities")
    op.drop_table("external_identities")
