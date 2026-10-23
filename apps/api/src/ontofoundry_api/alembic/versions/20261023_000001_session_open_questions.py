"""Keep the agent's unanswered questions on the modeling session.

Revision ID: 20261023_000001
Revises: 20261022_000004
Create Date: 2026-10-23
"""

import sqlalchemy as sa
from alembic import op

revision = "20261023_000001"
down_revision = "20261022_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "modeling_sessions",
        sa.Column("open_questions", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("modeling_sessions", "open_questions")
