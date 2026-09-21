"""Add explicit DataAgent state to modeling sessions.

Revision ID: 20260921_000001
Revises: 20260916_000001
Create Date: 2026-09-21 00:00:01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260921_000001"
down_revision = "20260916_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "modeling_sessions",
        sa.Column("dataagent_topic_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "modeling_sessions",
        sa.Column("dataagent_task_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "modeling_sessions",
        sa.Column("dataagent_task_mode", sa.String(8), nullable=False, server_default=""),
    )
    op.add_column(
        "modeling_sessions",
        sa.Column("dataagent_run_token", sa.String(32), nullable=True),
    )
    op.add_column(
        "modeling_sessions",
        sa.Column("uploaded_material_ids", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "modeling_sessions",
        sa.Column("last_result_task_id", sa.String(64), nullable=True),
    )
    op.add_column(
        "modeling_sessions",
        sa.Column("result_state", sa.String(20), nullable=False, server_default=""),
    )
    op.add_column(
        "modeling_sessions",
        sa.Column("result_warnings", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "modeling_sessions",
        sa.Column("result_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("modeling_sessions", "result_claimed_at")
    op.drop_column("modeling_sessions", "result_warnings")
    op.drop_column("modeling_sessions", "result_state")
    op.drop_column("modeling_sessions", "last_result_task_id")
    op.drop_column("modeling_sessions", "uploaded_material_ids")
    op.drop_column("modeling_sessions", "dataagent_run_token")
    op.drop_column("modeling_sessions", "dataagent_task_mode")
    op.drop_column("modeling_sessions", "dataagent_task_id")
    op.drop_column("modeling_sessions", "dataagent_topic_id")
