"""Persist import previews and their confirmation/completion history."""

import sqlalchemy as sa
from alembic import op

revision = "20261018_000001"
down_revision = "20261016_000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ontology_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False
        ),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("adapter", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(240), nullable=False),
        sa.Column("raw_sha256", sa.String(64), nullable=False),
        sa.Column("raw_artifact", sa.Text(), nullable=False),
        sa.Column("material_id", sa.String(36), sa.ForeignKey("materials.id")),
        sa.Column("formatted_sha256", sa.String(64)),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("converted_json", sa.JSON(), nullable=False),
        sa.Column("preview_json", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("base_version_id", sa.String(36)),
        sa.Column("base_version_sha256", sa.String(64), nullable=False),
        sa.Column("session_id", sa.String(36)),
        sa.Column("batch_id", sa.String(36), sa.ForeignKey("proposal_batches.id")),
        sa.Column("confirmation_sha256", sa.String(64)),
        sa.Column("completions_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["modeling_sessions.workspace_id", "modeling_sessions.id"],
        ),
        sa.UniqueConstraint("session_id", name="uq_import_session"),
    )
    op.create_index(
        "ix_ontology_imports_workspace_id", "ontology_imports", ["workspace_id"]
    )


def downgrade():
    op.drop_table("ontology_imports")
