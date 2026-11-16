"""Add unique personal sessions and transactional human-save receipts.

Revision ID: 20261116_000001
Revises: 20261113_000001
"""

import sqlalchemy as sa
from alembic import op

revision = "20261116_000001"
down_revision = "20261113_000001"
branch_labels = None
depends_on = None


def upgrade():
    # Existing sessions remain ordinary sessions, with no inferred ownership.
    with op.batch_alter_table("modeling_sessions") as batch:
        batch.add_column(sa.Column("personal_owner_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("human_batch_id", sa.String(36), nullable=True))
        batch.create_foreign_key("fk_personal_session_user", "users", ["personal_owner_id"], ["id"])
        batch.create_unique_constraint("uq_personal_session", ["workspace_id", "personal_owner_id"])
    op.create_table(
        "element_save_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("response_json", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("workspace_id", "session_id", "idempotency_key", name="uq_element_save_key"),
        sa.ForeignKeyConstraint(
            ["workspace_id", "session_id"],
            ["modeling_sessions.workspace_id", "modeling_sessions.id"], name="fk_element_save_session",
        ),
    )


def downgrade():
    op.drop_table("element_save_requests")
    with op.batch_alter_table("modeling_sessions") as batch:
        batch.drop_constraint("uq_personal_session", type_="unique")
        batch.drop_constraint("fk_personal_session_user", type_="foreignkey")
        batch.drop_column("human_batch_id")
        batch.drop_column("personal_owner_id")
