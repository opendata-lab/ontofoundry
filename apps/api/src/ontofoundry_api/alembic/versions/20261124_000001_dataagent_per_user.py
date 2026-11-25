"""Detach modeling sessions from shared DataAgent conversations.

Revision ID: 20261124_000001
Revises: 20261117_000002

DataAgent no longer has shared conversations: every request names the
OntoFoundry user, and a session acts as its creator. Conversations created
under the old per-session pseudo user belong to no DataAgent account, so the
session can no longer read them. Drafts, proposals and materials stay; the
binding to the old conversation is cleared and the next message opens a new
one (user decision 2026-11-24).
"""

import sqlalchemy as sa
from alembic import op

revision = "20261124_000001"
down_revision = "20261117_000002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        sa.text(
            """
            UPDATE modeling_sessions
            SET dataagent_topic_id = NULL,
                dataagent_task_id = NULL,
                dataagent_run_token = NULL,
                task_status = 'idle',
                task_detail = ''
            WHERE dataagent_topic_id IS NOT NULL OR dataagent_task_id IS NOT NULL
            """
        )
    )


def downgrade():
    # The old conversation ids are not kept; nothing to restore.
    pass
