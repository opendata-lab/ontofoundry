"""Drop issued service tokens; the ontology MCP uses the deployment's fixed token.

Revision ID: 20261022_000003
Revises: 20261022_000001
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op

revision = "20261022_000003"
down_revision = "20261022_000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("service_token_scopes")
    op.drop_table("service_tokens")


def downgrade() -> None:
    # Restores the empty tables only; dropped tokens cannot be recovered.
    op.create_table(
        "service_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False, index=True),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "service_token_scopes",
        sa.Column("token_id", sa.String(36), sa.ForeignKey("service_tokens.id"), primary_key=True),
        sa.Column("scope", sa.String(40), primary_key=True),
    )
