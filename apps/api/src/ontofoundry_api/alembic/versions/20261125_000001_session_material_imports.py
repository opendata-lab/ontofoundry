"""Record Ossie imports attached to modeling sessions."""

import sqlalchemy as sa
from alembic import op

revision = "20261125_000001"
down_revision = "20261124_000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "session_material_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("modeling_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("material_sha256", sa.String(64), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column(
            "batch_id",
            sa.String(36),
            sa.ForeignKey("proposal_batches.id", ondelete="SET NULL"),
        ),
        sa.UniqueConstraint(
            "session_id", "material_sha256", name="uq_session_material_import"
        ),
    )


def downgrade():
    op.drop_table("session_material_imports")
