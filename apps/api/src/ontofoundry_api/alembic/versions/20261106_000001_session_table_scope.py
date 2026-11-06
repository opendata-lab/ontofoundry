"""Resolve modeling session input tables dynamically or from a selection.

Revision ID: 20261106_000001
Revises: 20261026_000001
"""

import sqlalchemy as sa
from alembic import op

revision = "20261106_000001"
down_revision = "20261026_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "modeling_sessions",
        sa.Column("table_scope", sa.String(16), nullable=False, server_default="all"),
    )
    db = op.get_bind()
    sessions = sa.table(
        "modeling_sessions",
        sa.column("id", sa.String),
        sa.column("linked_tables", sa.JSON),
        sa.column("table_scope", sa.String),
    )
    selected = [
        identity for identity, linked in db.execute(
            sa.select(sessions.c.id, sessions.c.linked_tables)
        ) if linked
    ]
    if selected:
        db.execute(
            sessions.update().where(sessions.c.id.in_(selected)).values(table_scope="selected")
        )


def downgrade() -> None:
    op.drop_column("modeling_sessions", "table_scope")
