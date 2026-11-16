"""Add append-only change_events table across proposal, draft and version layers.

Revision ID: 20261116_000002
Revises: 20261116_000001
"""

import sqlalchemy as sa
from alembic import op

revision = "20261116_000002"
down_revision = "20261116_000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "change_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("seq", sa.Integer(), server_default="0", nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("actor_kind", sa.String(16), nullable=False),
        sa.Column("run_token", sa.String(128), nullable=True),
        sa.Column("subject", sa.String(16), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("target_kind", sa.String(24), nullable=True),
        sa.Column("target_id", sa.String(36), nullable=True),
        sa.Column("proposal_id", sa.String(36), nullable=True),
        sa.Column("batch_id", sa.String(36), nullable=True),
        sa.Column("version_id", sa.String(36), nullable=True),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=True),
        sa.Column("cause_id", sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["modeling_sessions.workspace_id", "modeling_sessions.id"],
            name="fk_change_event_session",
        ),
        sa.CheckConstraint(
            "actor_kind IN ('human', 'agent', 'import')",
            name="ck_change_event_actor_kind",
        ),
        sa.CheckConstraint(
            "subject IN ('proposal', 'draft', 'version')",
            name="ck_change_event_subject",
        ),
        sa.CheckConstraint(
            "(subject = 'proposal' AND action IN ('created','revised','superseded','accepted','rejected','restored','back_to_pending'))"
            " OR (subject = 'draft' AND action IN ('added','updated','removed'))"
            " OR (subject = 'version' AND action = 'published')",
            name="ck_change_event_action",
        ),
        sa.CheckConstraint(
            "(subject = 'version' AND target_kind IS NULL AND target_id IS NULL AND version_id IS NOT NULL)"
            " OR (subject IN ('proposal', 'draft') AND target_kind IS NOT NULL AND target_id IS NOT NULL)",
            name="ck_change_event_target",
        ),
    )
    op.create_index("ix_change_events_workspace_id", "change_events", ["workspace_id"])
    op.create_index("ix_change_events_session_id", "change_events", ["session_id"])
    op.create_index("ix_change_events_target_id", "change_events", ["target_id"])
    op.create_index("ix_change_events_proposal_id", "change_events", ["proposal_id"])
    op.create_index("ix_change_events_batch_id", "change_events", ["batch_id"])
    op.create_index("ix_change_events_cause_id", "change_events", ["cause_id"])
    op.create_index(
        "ix_change_events_session_target_at",
        "change_events",
        ["workspace_id", "session_id", "target_id", "at", "seq"],
    )
    op.create_index(
        "ix_change_events_session_at",
        "change_events",
        ["workspace_id", "session_id", "at", "seq"],
    )


def downgrade():
    op.drop_index("ix_change_events_session_at", table_name="change_events")
    op.drop_index("ix_change_events_session_target_at", table_name="change_events")
    op.drop_index("ix_change_events_cause_id", table_name="change_events")
    op.drop_index("ix_change_events_batch_id", table_name="change_events")
    op.drop_index("ix_change_events_proposal_id", table_name="change_events")
    op.drop_index("ix_change_events_target_id", table_name="change_events")
    op.drop_index("ix_change_events_session_id", table_name="change_events")
    op.drop_index("ix_change_events_workspace_id", table_name="change_events")
    op.drop_table("change_events")
