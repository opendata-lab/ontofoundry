"""Exercise the migration against legacy rows, including failed-upgrade safety."""

import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from ontofoundry_api.services.auth_config import AuthConfig


def migration():
    path = Path(__file__).parents[1] / "src/ontofoundry_api/alembic/versions/20261112_000001_user_management.py"
    spec = importlib.util.spec_from_file_location("user_management_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legacy(conn, subjects):
    conn.execute(sa.text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, subject VARCHAR(255) NOT NULL, display_name VARCHAR(120), CONSTRAINT users_subject_key UNIQUE (subject))"))
    conn.execute(sa.text("CREATE INDEX ix_users_subject ON users(subject)"))
    conn.execute(sa.text("CREATE TABLE workspaces (id VARCHAR(36) PRIMARY KEY)"))
    conn.execute(sa.text("INSERT INTO workspaces VALUES ('fiction-space')"))
    for i, subject in enumerate(subjects):
        conn.execute(sa.text("INSERT INTO users VALUES (:id, :subject, '虚构用户')"), {"id": str(i), "subject": subject})


def test_prefix_strip_dev_visibility_unique_index_and_downgrade(monkeypatch):
    module = migration()
    with sa.create_engine("sqlite://").begin() as conn:
        legacy(conn, ["local:admin", "internal:u123", "provider:tenant:user", "dev:admin", "plain-user"])
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(conn)))
        module.upgrade()
        assert list(conn.execute(sa.text("SELECT username, last_login_at FROM users ORDER BY id"))) == [("admin", None), ("u123", None), ("tenant:user", None), ("dev", None), ("plain-user", None)]
        assert conn.scalar(sa.text("SELECT is_public FROM workspaces")) == 1
        conn.execute(sa.text("INSERT INTO workspaces (id) VALUES ('new-space')"))
        assert conn.scalar(sa.text("SELECT is_public FROM workspaces WHERE id='new-space'")) == 0
        with pytest.raises(sa.exc.IntegrityError):
            conn.execute(sa.text("INSERT INTO users (id, username) VALUES ('duplicate', 'ADMIN')"))
        monkeypatch.setattr("ontofoundry_api.services.auth_config.load_auth_config", lambda settings: AuthConfig(local_users={"ADMIN": "secret"}))
        module.downgrade()
        assert conn.scalar(sa.text("SELECT subject FROM users WHERE id='0'")) == "local:admin"
        assert conn.scalar(sa.text("SELECT subject FROM users WHERE id='3'")) == "dev:admin"
        assert "is_public" not in {c["name"] for c in sa.inspect(conn).get_columns("workspaces")}
        assert "last_login_at" not in {c["name"] for c in sa.inspect(conn).get_columns("users")}


@pytest.mark.parametrize("subjects,conflicts", [
    (["local:Admin", "internal:admin"], "admin"),
    (["dev:admin", "local:DEV"], "dev"),
    (["local:alpha", "sso:ALPHA", "local:beta", "sso:BETA"], "alpha, beta"),
])
def test_conflicts_list_names_and_leave_legacy_rows_intact(monkeypatch, subjects, conflicts):
    module = migration()
    with sa.create_engine("sqlite://").begin() as conn:
        legacy(conn, subjects)
        monkeypatch.setattr(module, "op", Operations(MigrationContext.configure(conn)))
        with pytest.raises(RuntimeError, match=conflicts):
            module.upgrade()
        assert list(conn.scalars(sa.text("SELECT subject FROM users ORDER BY id"))) == subjects
        assert "username" not in {c["name"] for c in sa.inspect(conn).get_columns("users")}
