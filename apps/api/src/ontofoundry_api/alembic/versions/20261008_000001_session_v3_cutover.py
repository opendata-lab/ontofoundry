"""Archive session cutovers without rewriting historical versions/manifests."""

import sqlalchemy as sa
from alembic import op

revision = "20261008_000001"
down_revision = "20260930_000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "modeling_session_migrations",
        sa.Column("session_id", sa.String(36), primary_key=True),
        sa.Column("source_revision", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("source_schema_version", sa.String(8), nullable=False),
        sa.Column("source_draft_json", sa.JSON(), nullable=False),
        sa.Column("source_draft_sha256", sa.String(64), nullable=False),
        sa.Column("pinned_manifest_json", sa.JSON(), nullable=True),
        sa.Column("run_token", sa.String(128), nullable=True),
        sa.Column("candidates_json", sa.JSON(), nullable=False),
        sa.Column("result_state", sa.String(20), nullable=False),
        sa.Column("migrated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["modeling_sessions.workspace_id", "modeling_sessions.id"],
        ),
    )


def downgrade():
    op.drop_table("modeling_session_migrations")
