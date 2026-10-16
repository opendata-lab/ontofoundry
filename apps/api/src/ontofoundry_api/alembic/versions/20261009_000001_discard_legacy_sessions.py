"""Discard unsupported sessions and their decisions; retain all published data."""

import sqlalchemy as sa
from alembic import op

revision = "20261009_000001"
down_revision = "20261008_000001"
branch_labels = None
depends_on = None

# Child tables precede their parents. Run grants are stateless and become
# invalid as soon as their session disappears; service tokens stay untouched.
DEPENDENTS = (
    "proposal_decision_items",
    "proposal_item_dependencies",
    "proposal_items",
    "proposal_batches",
    "proposal_decision_requests",
    "modeling_session_migrations",
)


def discard_legacy_sessions(bind):
    """Portable, idempotent cleanup, including absent/null/non-string schemas."""
    names = set(sa.inspect(bind).get_table_names())
    if "modeling_sessions" not in names:
        return 0
    metadata = sa.MetaData()
    sessions = sa.Table(
        "modeling_sessions", metadata, autoload_with=bind, resolve_fks=False
    )
    rows = bind.execute(sa.select(sessions.c.id, sessions.c.draft_json)).all()
    obsolete = [
        row.id
        for row in rows
        if not isinstance(row.draft_json, dict)
        or row.draft_json.get("schema_version") != "3"
    ]
    for offset in range(0, len(obsolete), 400):
        ids = obsolete[offset : offset + 400]
        for name in DEPENDENTS:
            if name in names:
                table = sa.Table(name, metadata, autoload_with=bind, resolve_fks=False)
                bind.execute(sa.delete(table).where(table.c.session_id.in_(ids)))
        bind.execute(sa.delete(sessions).where(sessions.c.id.in_(ids)))
    return len(obsolete)


def upgrade():
    bind = op.get_bind()
    # These audit tables have no purpose after retiring legacy sessions. Drop
    # the per-item child first if an intermediate compatibility build created it.
    names = set(sa.inspect(bind).get_table_names())
    if "proposal_item_migrations" in names:
        op.drop_table("proposal_item_migrations")
    discard_legacy_sessions(bind)
    if "modeling_session_migrations" in names:
        op.drop_table("modeling_session_migrations")


def downgrade():
    # Removed user sessions cannot be reconstructed. Recreate only the schema
    # expected by the previous revision, never invent or downgrade user data.
    if "modeling_session_migrations" not in sa.inspect(op.get_bind()).get_table_names():
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
