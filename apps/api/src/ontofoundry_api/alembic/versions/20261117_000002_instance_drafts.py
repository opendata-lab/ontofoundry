"""Instance drafts: a session's pending change to a published instance (AI-11).

Revision ID: 20261117_000002
Revises: 20261117_000001

Existing data needs no rewrite: published instances stay active, and staged
instances of open sessions keep waiting for their session's publish.
"""

import sqlalchemy as sa
from alembic import op

revision = "20261117_000002"
down_revision = "20261117_000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "instance_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "kind", "target_id", name="uq_instance_draft_target"),
    )
    op.create_index("ix_instance_drafts_workspace_id", "instance_drafts", ["workspace_id"])
    op.create_index("ix_instance_drafts_session_id", "instance_drafts", ["session_id"])


def downgrade():
    op.drop_index("ix_instance_drafts_session_id", table_name="instance_drafts")
    op.drop_index("ix_instance_drafts_workspace_id", table_name="instance_drafts")
    op.drop_table("instance_drafts")
