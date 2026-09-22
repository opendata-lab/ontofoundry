"""Drop the modeling session's local chat copy.

DataAgent is the authoritative store for conversations. Keeping a second copy
here meant reconciling two representations by hand, which is what the old
``_sync_dataagent`` state machine existed to do.

Nothing migrates the content: the rows referenced topics in the local ``da_*``
tables, which the next revision removes, so they mean nothing to the external
service.

Revision ID: 20260921_000002
Revises: 20260921_000001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260921_000002"
down_revision = "20260921_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("modeling_sessions", "messages_json")


def downgrade() -> None:
    """Restores the column, not its contents — those are gone for good."""
    op.add_column(
        "modeling_sessions",
        sa.Column("messages_json", sa.JSON(), nullable=False, server_default="[]"),
    )
