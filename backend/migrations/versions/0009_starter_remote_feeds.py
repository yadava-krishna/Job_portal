"""data: turn on the public remote-job feeds for each user's auto-created starter search

Additive: only searches JobPilot created itself (origin = 'starter') get "remote_feeds" appended to their sources.
Searches a user built are left exactly as they are. Downgrade removes the value again.

Revision ID: 0009
Revises: 0008
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FEEDS = "remote_feeds"


def _rewrite(add: bool) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, criteria FROM saved_searches WHERE origin = 'starter'")).fetchall()
    for rid, criteria in rows:
        c = criteria if isinstance(criteria, dict) else json.loads(criteria or "{}")
        sources = list(c.get("sources") or [])
        if add and FEEDS not in sources:
            sources.append(FEEDS)
        elif not add and FEEDS in sources:
            sources = [s for s in sources if s != FEEDS] or ["greenhouse", "lever", "ashby", "smartrecruiters", "recruitee"]
        else:
            continue
        c["sources"] = sources
        value = "CAST(:c AS JSONB)" if bind.dialect.name == "postgresql" else ":c"
        bind.execute(sa.text(f"UPDATE saved_searches SET criteria = {value} WHERE id = :id"), {"c": json.dumps(c), "id": rid})


def upgrade() -> None:
    _rewrite(add=True)


def downgrade() -> None:
    _rewrite(add=False)
