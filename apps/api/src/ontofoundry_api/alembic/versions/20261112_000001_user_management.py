"""Identify users by username and add workspace visibility.

Revision ID: 20261112_000001
Revises: 20261106_000001
"""

from collections import Counter

import sqlalchemy as sa
from alembic import op

revision = "20261112_000001"
down_revision = "20261106_000001"
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    users = list(db.execute(sa.text("SELECT id, subject FROM users")))
    renamed = [(uid, "dev" if subject == "dev:admin" else subject.split(":", 1)[-1]) for uid, subject in users]
    counts = Counter(name.lower() for _, name in renamed)
    conflicts = sorted(name for name, count in counts.items() if count > 1)
    if conflicts:
        raise RuntimeError("用户名冲突，请处理后重试：" + ", ".join(conflicts))
    # PostgreSQL's baseline has both a unique constraint and a separate index.
    inspector = sa.inspect(db)
    with op.batch_alter_table("users") as batch:
        for constraint in inspector.get_unique_constraints("users"):
            if constraint["column_names"] == ["subject"]:
                batch.drop_constraint(constraint["name"], type_="unique")
        for index in inspector.get_indexes("users"):
            if index["column_names"] == ["subject"] and not index.get("duplicates_constraint"):
                batch.drop_index(index["name"])
        batch.alter_column("subject", new_column_name="username", existing_type=sa.String(255))
        batch.add_column(sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    for uid, name in renamed:
        db.execute(sa.text("UPDATE users SET username = :name WHERE id = :id"), {"id": uid, "name": name})
    op.create_index("ix_users_username_lower", "users", [sa.text("lower(username)")], unique=True)
    op.add_column("workspaces", sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()))
    with op.batch_alter_table("workspaces") as batch:
        batch.alter_column("is_public", server_default=sa.false(), existing_type=sa.Boolean(), existing_nullable=False)


def downgrade():
    # Provider prefixes cannot be reconstructed. Back up users before rollback.
    from ontofoundry_api.config import Settings
    from ontofoundry_api.services.auth_config import load_auth_config

    config = load_auth_config(Settings())
    local = {name.lower() for name in config.local_users}
    db = op.get_bind()
    for uid, name in db.execute(sa.text("SELECT id, username FROM users")).all():
        subject = "dev:admin" if name == "dev" else f"local:{name}" if name.lower() in local else name
        db.execute(sa.text("UPDATE users SET username = :subject WHERE id = :id"), {"id": uid, "subject": subject})
    op.drop_index("ix_users_username_lower", table_name="users")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_login_at")
        batch.alter_column("username", new_column_name="subject", existing_type=sa.String(255))
    op.create_index("ix_users_subject", "users", ["subject"], unique=True)
    with op.batch_alter_table("workspaces") as batch:
        batch.drop_column("is_public")
