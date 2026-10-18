"""Discard old ontology content and enable core-1. Backups restore old data."""

import sqlalchemy as sa
from alembic import op

revision = "20261016_000001"
down_revision = "20261009_000001"
branch_labels = None
depends_on = None


def discard_ontology(bind):
    tables = set(sa.inspect(bind).get_table_names())
    bind.execute(sa.text("UPDATE workspaces SET current_version_id = NULL"))
    for table in (
        "proposal_decision_items",
        "proposal_item_dependencies",
        "proposal_items",
        "proposal_batches",
        "proposal_decision_requests",
        "modeling_session_migrations",
        "modeling_sessions",
        "ontology_element_identities",
        "ontology_versions",
    ):
        if table in tables:
            bind.execute(sa.text(f'DELETE FROM "{table}"'))


def upgrade():
    bind = op.get_bind()
    discard_ontology(bind)
    if "ossie_json" in {
        c["name"] for c in sa.inspect(bind).get_columns("ontology_versions")
    }:
        with op.batch_alter_table("ontology_versions") as batch:
            batch.drop_column("ossie_json")
    if "atomic_group_id" not in {
        c["name"] for c in sa.inspect(bind).get_columns("proposal_items")
    }:
        with op.batch_alter_table("proposal_items") as batch:
            batch.add_column(sa.Column("atomic_group_id", sa.String(36), nullable=True))


def downgrade():
    # Reverting DDL cannot recreate discarded ontology content.
    with op.batch_alter_table("proposal_items") as batch:
        batch.drop_column("atomic_group_id")
    with op.batch_alter_table("ontology_versions") as batch:
        batch.add_column(
            sa.Column("ossie_json", sa.JSON(), nullable=False, server_default="{}")
        )
