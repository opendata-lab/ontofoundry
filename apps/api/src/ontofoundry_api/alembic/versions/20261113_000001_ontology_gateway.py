"""Add personal tokens, asynchronous gateway audit records and feedback.

Revision ID: 20261113_000001
Revises: 20261112_000001
"""

import sqlalchemy as sa
from alembic import op

revision = "20261113_000001"
down_revision = "20261112_000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "personal_access_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("token_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_personal_access_tokens_user_id", "personal_access_tokens", ["user_id"])
    op.create_table(
        "ontology_gateway_calls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_id", sa.String(36), sa.ForeignKey("personal_access_tokens.id"), nullable=False),
        sa.Column("request_id", sa.String(100), nullable=False),
        sa.Column("tool", sa.String(64), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_gateway_calls_user_created", "ontology_gateway_calls", ["user_id", "created_at"])
    op.create_index("ix_gateway_calls_created", "ontology_gateway_calls", ["created_at"])
    op.create_table(
        "ontology_gateway_call_workspaces",
        sa.Column("call_id", sa.String(36), sa.ForeignKey("ontology_gateway_calls.id"), primary_key=True),
        sa.Column("workspace_id", sa.String(36), primary_key=True),
        sa.Column("version_id", sa.String(36), nullable=True),
        sa.Column("version_number", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_gateway_call_workspaces_space_created", "ontology_gateway_call_workspaces", ["workspace_id", "created_at"])
    op.create_table(
        "ontology_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_id", sa.String(36), sa.ForeignKey("personal_access_tokens.id"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("user_text", sa.Text(), nullable=False),
        sa.Column("agent_text", sa.Text(), nullable=False),
        sa.Column("element_ids", sa.JSON(), nullable=False),
        sa.Column("version_id", sa.String(36), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ontology_feedback_space_created", "ontology_feedback", ["workspace_id", "created_at"])


def downgrade():
    op.drop_table("ontology_feedback")
    op.drop_table("ontology_gateway_call_workspaces")
    op.drop_table("ontology_gateway_calls")
    op.drop_table("personal_access_tokens")
