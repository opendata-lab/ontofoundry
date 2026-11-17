"""Publish boundary: proposals from before a session's last publish are closed.

Revision ID: 20261117_000001
Revises: 20261116_000002
"""

import sqlalchemy as sa
from alembic import op

revision = "20261117_000001"
down_revision = "20261116_000002"
branch_labels = None
depends_on = None


def upgrade():
    # Existing sessions have no recorded boundary: their batches stay as they are.
    with op.batch_alter_table("modeling_sessions") as batch:
        batch.add_column(sa.Column("published_revision", sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table("modeling_sessions") as batch:
        batch.drop_column("published_revision")
