"""Personal token contracts, ownership, digests and credential isolation."""

import base64
import hashlib
import json

import pytest
from gateway_helpers import GATEWAY, TOKENS, WID, call, rpc, token, user
from sqlalchemy import select
from test_auth import login_client as login_fixture

from ontofoundry_api.contracts.gateway import gateway_schema
from ontofoundry_api.db_models import PersonalAccessTokenRecord

login_client = login_fixture


def test_token_lifecycle_and_digest_only(client):
    principal = user(client, role="viewer")
    created = token(client)
    assert set(created) == {"id", "name", "permissions", "created_at", "token"}
    assert created["token"].startswith("ofpat.")
    assert len(base64.urlsafe_b64decode(created["token"][6:] + "=")) == 32
    with client.app.state.session_factory() as db:
        record = db.get(PersonalAccessTokenRecord, created["id"])
        assert record.user_id == principal.id
        assert record.token_sha256 == hashlib.sha256(created["token"].encode()).hexdigest()
        assert created["token"] not in str(record.__dict__)
    items = client.get(TOKENS).json()["items"]
    assert len(items) == 1
    assert set(items[0]) == {"id", "name", "permissions", "created_at", "updated_at", "last_used_at"}
    assert items[0]["last_used_at"] is None
    path = TOKENS + "/" + created["id"]
    renamed = client.patch(path, json={"name": "星港笔记本"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "星港笔记本"
    updated = client.patch(path, json={"permissions": ["ontology:read", "mappings:read"]})
    assert updated.json()["permissions"] == ["ontology:read", "mappings:read"]
    assert "token" not in updated.json()
    assert not call(client, created["token"], "list_spaces")["isError"]
    assert client.delete(path).status_code == 204
    assert client.delete(path).status_code == 204
    assert client.get(TOKENS).json() == {"items": []}
    assert client.patch(path, json={"name": "失效"}).status_code == 404
    assert rpc(client, created["token"], "tools/list").status_code == 401


@pytest.mark.parametrize("payload", [
    {"name": "", "permissions": ["ontology:read"]},
    {"name": "  ", "permissions": ["ontology:read"]},
    {"name": "x" * 101, "permissions": ["ontology:read"]},
    {"name": "虚构", "permissions": []},
    {"name": "虚构", "permissions": ["mappings:read"]},
    {"name": "虚构", "permissions": ["ontology:read", "instances:read"]},
])
def test_invalid_create_uses_service_error(client, payload):
    response = client.post(TOKENS, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_ARGUMENTS"


@pytest.mark.parametrize("payload", [{}, {"permissions": []}, {"permissions": ["ontology:read", "unknown"]}, {"permissions": None}, {"name": None}, {"name": "  "}])
def test_invalid_patch(client, payload):
    item = token(client)
    assert client.patch(TOKENS + "/" + item["id"], json=payload).status_code == 422


def test_ownership_and_newest_first(client):
    user(client, role="viewer")
    first, second = token(client), token(client)
    assert [t["id"] for t in client.get(TOKENS).json()["items"]] == [second["id"], first["id"]]
    user(client)
    assert client.get(TOKENS).json() == {"items": []}
    path = TOKENS + "/" + first["id"]
    assert client.patch(path, json={"name": "其他用户"}).status_code == 404
    assert client.delete(path).status_code == 404


def test_credential_entry_points_are_isolated(client):
    item = token(client)
    client.app.state.settings.mcp_token = "fiction-fixed-token"
    for credential in (None, "fiction-fixed-token", "ofrun.fiction", "ofpat.unknown"):
        assert rpc(client, credential, "tools/list").status_code == 401
    headers = {"Authorization": "Bearer " + item["token"]}
    assert client.get(TOKENS, headers=headers).status_code == 401
    assert client.post(TOKENS, json={"name": "虚构", "permissions": ["ontology:read"]}, headers=headers).status_code == 401
    assert client.post(f"/api/v1/ontology/workspaces/{WID}/mcp", headers=headers, json={}).status_code == 401
    assert client.get(GATEWAY).status_code == 405


def test_real_login_session_required(login_client):
    assert login_client.post(TOKENS, json={"name": "虚构", "permissions": ["ontology:read"]}).status_code == 401
    with login_client.app.state.session_factory() as db:
        from ontofoundry_api.db_models import UserRecord
        db.add(UserRecord(id="fiction-admin", username="admin", display_name="虚构管理员"))
        db.commit()
    assert login_client.post("/api/v1/auth/login/local", json={"username": "admin", "password": "admin123"}).status_code == 204
    created = token(login_client)
    assert not call(login_client, created["token"], "list_spaces")["isError"]
    assert rpc(login_client, None, "tools/list").status_code == 401


def test_gateway_schema_artifact():
    from pathlib import Path

    from jsonschema import Draft202012Validator

    from ontofoundry_api.contracts import gateway

    schema = gateway_schema()
    Draft202012Validator.check_schema(schema)
    path = Path(gateway.__file__).with_name("ontofoundry.gateway.v1.schema.json")
    assert json.loads(path.read_text()) == schema


def test_no_plaintext_token_stored(client):
    item = token(client)
    with client.app.state.session_factory() as db:
        rows = db.scalars(select(PersonalAccessTokenRecord)).all()
        assert len(rows) == 1
        assert all(item["token"] not in str(row.__dict__) for row in rows)


def test_four_table_migration_matches_models_and_preserves_existing_tables(monkeypatch):
    import importlib.util
    from pathlib import Path

    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from ontofoundry_api.database import Base

    path = Path(__file__).parents[1] / "src/ontofoundry_api/alembic/versions/20261113_000001_ontology_gateway.py"
    spec = importlib.util.spec_from_file_location("gateway_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    names = {"personal_access_tokens", "ontology_gateway_calls", "ontology_gateway_call_workspaces", "ontology_feedback"}
    with sa.create_engine("sqlite://").begin() as conn:
        conn.execute(sa.text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(sa.text("CREATE TABLE workspaces (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(sa.text("INSERT INTO users VALUES ('fiction-user')"))
        monkeypatch.setattr(migration, "op", Operations(MigrationContext.configure(conn)))
        migration.upgrade()
        inspector = sa.inspect(conn)
        assert set(inspector.get_table_names()) == names | {"users", "workspaces"}
        for name in names:
            columns = {c["name"]: c for c in inspector.get_columns(name)}
            model = Base.metadata.tables[name]
            assert columns.keys() == {c.name for c in model.columns}
            for column in model.columns:
                assert columns[column.name]["nullable"] == column.nullable
            assert {i["name"] for i in inspector.get_indexes(name)} == {i.name for i in model.indexes}
        assert inspector.get_pk_constraint("ontology_gateway_call_workspaces")["constrained_columns"] == ["call_id", "workspace_id"]
        assert inspector.get_unique_constraints("personal_access_tokens")[0]["column_names"] == ["token_sha256"]
        migration.downgrade()
        assert set(sa.inspect(conn).get_table_names()) == {"users", "workspaces"}
        assert conn.scalar(sa.text("SELECT id FROM users")) == "fiction-user"
