"""Session table scopes retain selections while resolving current run inputs."""

import importlib.util
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_linked_tables import link, register, save_links
from test_modeling import ROOT, create_session

from ontofoundry_api.api import agent_conversation
from ontofoundry_api.db_models import MetadataSnapshotRecord, ModelingSessionRecord


def test_table_scope_migration_maps_existing_links_and_downgrades():
    path = (
        Path(__file__).parents[1] / "src/ontofoundry_api/alembic/versions"
        / "20261106_000001_session_table_scope.py"
    )
    spec = importlib.util.spec_from_file_location("session_table_scope", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "20261026_000001"
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    sessions = sa.Table(
        "modeling_sessions", metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("linked_tables", sa.JSON),
    )
    metadata.create_all(engine)
    with engine.begin() as db:
        selected = [link("fiction-connection", "fiction_orders")]
        db.execute(sessions.insert(), [
            {"id": "empty", "linked_tables": []},
            {"id": "selected", "linked_tables": selected},
            {"id": "null", "linked_tables": None},
        ])
        migration.op = Operations(MigrationContext.configure(db))
        migration.upgrade()
        rows = dict(db.execute(sa.text("SELECT id, table_scope FROM modeling_sessions")).all())
        assert rows == {"empty": "all", "selected": "selected", "null": "all"}
        assert db.scalar(sa.select(sessions.c.linked_tables).where(sessions.c.id == "selected")) == selected
        db.execute(sessions.insert().values(id="new", linked_tables=[]))
        assert db.scalar(sa.text("SELECT table_scope FROM modeling_sessions WHERE id = 'new'")) == "all"
        column = next(c for c in sa.inspect(db).get_columns("modeling_sessions") if c["name"] == "table_scope")
        assert column["type"].length == 16 and column["nullable"] is False
        migration.downgrade()
        assert {c["name"] for c in sa.inspect(db).get_columns("modeling_sessions")} == {"id", "linked_tables"}
    engine.dispose()


def test_save_scope_defaults_transitions_and_revision_conflict(client):
    session = create_session(client)
    assert session["table_scope"] == "all" and session["linked_tables"] == []
    connection = register(client, ["fiction_orders"])
    saved = save_links(client, session, [link(connection, "fiction_orders")]).json()
    assert saved["table_scope"] == "selected"

    def save(current, **scope):
        return client.put(ROOT + f"/sessions/{current['id']}", json={
            "revision": current["revision"], "draft": current["draft"], **scope,
        })

    unchanged = save(saved).json()
    assert unchanged["table_scope"] == "selected" and unchanged["linked_tables"] == saved["linked_tables"]
    response = save(unchanged, table_scope="all", linked_tables=[link("fiction-deleted", "fiction_orders")])
    assert response.status_code == 200, response.text
    all_tables = response.json()
    assert all_tables["table_scope"] == "all" and all_tables["linked_tables"] == []
    assert save(unchanged, table_scope="selected").status_code == 409
    response = save(all_tables, table_scope="selected", linked_tables=[])
    assert response.status_code == 200, response.text
    assert response.json()["table_scope"] == "selected" and response.json()["linked_tables"] == []
    assert save(response.json(), table_scope="invalid").status_code == 422


def test_save_more_than_200_registered_tables(client):
    connection = register(client, [f"fiction_orders_{i}" for i in range(201)])
    tables = [link(connection, f"fiction_orders_{i}") for i in range(201)]
    response = save_links(client, create_session(client), tables)
    assert response.status_code == 200, response.text
    assert response.json()["table_scope"] == "selected"
    assert response.json()["linked_tables"] == tables


def test_registered_tables_observed_at_prefers_table_then_snapshot_then_null(client):
    connection = register(client, ["fiction_orders", "fiction_stores"])
    with client.app.state.session_factory() as db:
        snapshot = db.get(MetadataSnapshotRecord, (connection, "retail"))
        snapshot.observed_at = datetime(2026, 11, 5, 12, tzinfo=UTC)
        tables = deepcopy(snapshot.snapshot_json["tables"])
        tables[0]["observed_at"] = "2026-11-06T12:00:00+00:00"
        snapshot.snapshot_json = {"tables": tables}
        db.commit()
        db.refresh(snapshot)
        fallback = snapshot.observed_at.isoformat()
    response = client.get(ROOT + "/registered-tables")
    assert response.status_code == 200, response.text
    items = {i["table_name"]: i for i in response.json()["items"]}
    assert items["fiction_orders"]["observed_at"] == "2026-11-06T12:00:00+00:00"
    assert items["fiction_stores"]["observed_at"] == fallback
    with client.app.state.session_factory() as db:
        db.get(MetadataSnapshotRecord, (connection, "retail")).observed_at = None
        db.commit()
    items = {i["table_name"]: i for i in client.get(ROOT + "/registered-tables").json()["items"]}
    assert items["fiction_stores"]["observed_at"] is None


@pytest.mark.parametrize("scope", ["all", "selected", "document_only"])
def test_run_resolves_current_tables_and_records_skipped_selections(client, monkeypatch, scope):
    session = create_session(client)
    assert session["table_scope"] == "all"
    initial_tables = {
        f"{table['schema_name']}.{table['table_name']}"
        for table in client.get(ROOT + "/registered-tables").json()["items"]
    }
    connection = register(client, ["fiction_orders", "fiction_gone", "fiction_removed"])
    selected = [link(connection, name) for name in ["fiction_orders", "fiction_gone", "fiction_removed"]]
    if scope != "all":
        response = save_links(client, session, selected if scope == "selected" else [])
        assert response.status_code == 200, response.text
    with client.app.state.session_factory() as db:
        snapshot = db.get(MetadataSnapshotRecord, (connection, "retail"))
        tables = deepcopy(snapshot.snapshot_json["tables"])
        tables[1]["missing"] = True
        snapshot.snapshot_json = {"tables": tables[:2] + [{"name": "fiction_new", "columns": []}]}
        db.commit()
    uploads = {}

    class Agent:
        async def create_topic(self, *_):
            return {"topic_id": "fiction-topic"}

        async def upload(self, topic_id, name, data, media_type):
            uploads[name] = data
            return {"rel_path": "inputs/" + name}

        async def deliver(self, **kwargs):
            return {"task_id": "fiction-task", "task_status": "running"}

    monkeypatch.setattr(agent_conversation, "_client", lambda *_: Agent())
    monkeypatch.setattr(agent_conversation, "_require_configured", lambda _: None)
    response = client.post(ROOT + f"/sessions/{session['id']}/agent-conversation/messages", json={
        "content": "根据虚构表建模",
    })
    assert response.status_code == 202, response.text
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        assert row.run_manifest_json["skipped_tables"] == (selected[1:] if scope == "selected" else [])
        assert row.linked_tables == (selected if scope == "selected" else [])
        catalog = row.run_manifest_json["input_files"].get("tables") or []
    receipts = [json.loads(data)["tables"] for name, data in uploads.items() if name.startswith("ontofoundry-tables-")]
    expected = initial_tables | {"retail.fiction_orders", "retail.fiction_new"} if scope == "all" else {"retail.fiction_orders"}
    if scope == "document_only":
        assert receipts == [] and catalog == []
    else:
        assert len(receipts) == 1
        assert {t["table_name"] for t in receipts[0]} == {name.split(".")[1] for name in expected}
        assert {t["table"] for t in catalog} == expected
