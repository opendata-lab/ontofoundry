"""Create metadata sync progress and discard pre-source dataset content."""

import importlib

import sqlalchemy as sa
from alembic import op

revision = "20261020_000002"
down_revision = "20261020_000001"
branch_labels = None
depends_on = None


def upgrade():
    # Dataset identifiers and connection binding deliberately have no legacy path.
    cleanup = importlib.import_module("ontofoundry_api.alembic.versions.20261020_000001_unify_element_names")
    cleanup.discard_ontology(op.get_bind())
    op.create_table("metadata_sync_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("connection_id", sa.String(36), sa.ForeignKey("data_connections.id"), nullable=False),
        sa.Column("schema_name", sa.String(240), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("selected_json", sa.JSON(), nullable=False),
        sa.Column("inventory_json", sa.JSON(), nullable=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text()),
    )
    for column in ("workspace_id", "connection_id", "state"):
        op.create_index("ix_metadata_sync_jobs_" + column, "metadata_sync_jobs", [column])
    op.create_table("metadata_sync_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("metadata_sync_jobs.id"), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("table_names_json", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("results_json", sa.JSON(), nullable=False),
        sa.Column("history_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text()),
        sa.UniqueConstraint("job_id", "ordinal", name="uq_metadata_sync_batch_ordinal"),
    )
    op.create_index("ix_metadata_sync_batches_job_id", "metadata_sync_batches", ["job_id"])
    op.add_column(
        "modeling_sessions",
        sa.Column("linked_tables", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade():
    op.drop_column("modeling_sessions", "linked_tables")
    op.drop_table("metadata_sync_batches")
    op.drop_table("metadata_sync_jobs")
