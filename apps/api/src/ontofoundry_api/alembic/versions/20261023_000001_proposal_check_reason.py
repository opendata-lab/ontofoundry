"""Persist unacceptable proposal diagnostics.

Revision ID: 20261023_000001
Revises: 20261022_000004
"""

from alembic import op
import sqlalchemy as sa

revision = "20261023_000001"
down_revision = "20261022_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("proposal_items", sa.Column("status_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("proposal_items", "status_reason")
