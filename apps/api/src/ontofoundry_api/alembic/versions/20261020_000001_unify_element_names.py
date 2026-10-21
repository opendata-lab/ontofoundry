"""Discard ontology content before adopting name and display_name."""

import sqlalchemy as sa
from alembic import op

revision = "20261020_000001"
down_revision = "20261018_000001"
branch_labels = None
depends_on = None

CONTENT_TABLES = (
    "ontology_imports",
    "imports",
    "proposal_decision_items",
    "proposal_item_dependencies",
    "proposal_items",
    "proposal_batches",
    "proposal_decision_requests",
    "modeling_session_migrations",
    "modeling_sessions",
    "ontology_element_identities",
    "ontology_versions",
)


def discard_ontology(bind):
    tables = set(sa.inspect(bind).get_table_names())
    bind.execute(sa.text("UPDATE workspaces SET current_version_id = NULL"))
    for table in CONTENT_TABLES:
        if table in tables:
            bind.execute(sa.text(f'DELETE FROM "{table}"'))


def upgrade():
    discard_ontology(op.get_bind())


def downgrade():
    # No DDL changed. Discarded content can only be restored from a backup.
    pass
