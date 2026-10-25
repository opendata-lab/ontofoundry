"""Fix a session's mode (model or chat) for its whole conversation.

Revision ID: 20261025_000001
Revises: 20261023_000001
"""

from alembic import op
import sqlalchemy as sa

revision = "20261025_000001"
down_revision = "20261023_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "modeling_sessions",
        sa.Column("mode", sa.String(8), nullable=False, server_default="model"),
    )


def downgrade() -> None:
    op.drop_column("modeling_sessions", "mode")
