"""Distinguish uploaded materials from generated table receipts."""

import sqlalchemy as sa
from alembic import op

revision = "20261021_000001"
down_revision = "20261020_000002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "materials",
        sa.Column("origin", sa.String(20), nullable=False, server_default="upload"),
    )


def downgrade():
    op.drop_column("materials", "origin")
