"""Table receipts share immutable material storage, evidence and usage rules."""

import hashlib
import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from jsonschema import Draft202012Validator
from sqlalchemy import func, inspect, select
from test_linked_tables import link, register, save_links
from test_modeling import ROOT, create_session

from ontofoundry_api.api import agent_conversation
from ontofoundry_api.contracts import export_schema
from ontofoundry_api.db_models import (
    MaterialChunkRecord,
    MaterialRecord,
    MetadataSnapshotRecord,
    ModelingSessionRecord,
)
from ontofoundry_api.domain.evidence import EvidenceError, check_material_evidence
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.modeling_input import (
    linked_tables_payload,
    store_linked_tables_receipt,
)

WORKSPACE = str(DEMO_WORKSPACE_ID)


def receipt(client, linked):
    with client.app.state.session_factory() as db:
        catalog, material = store_linked_tables_receipt(
            db, client.app.state.settings, WORKSPACE, linked
        )
        db.commit()
        db.refresh(material)
        db.expunge(material)
        return catalog, material


def source(client, material):
    return client.app.state.settings.data_dir / WORKSPACE / (material.sha256 + ".md")


def change_column(client, connection_id, physical_type="BIGINT"):
    with client.app.state.session_factory() as db:
        snapshot = db.get(MetadataSnapshotRecord, (connection_id, "retail"))
        updated = deepcopy(snapshot.snapshot_json)
        updated["tables"][0]["columns"][1]["type"] = physical_type
        snapshot.snapshot_json = updated
        db.commit()


def evidence(material, text):
    lines = text.splitlines()
    number = next(i for i, line in enumerate(lines, 1) if '"name": "amount"' in line)
    return {
        "id": str(uuid4()), "kind": "material", "material_id": material.id,
        "material_sha256": material.sha256,
        "locator": {"line_start": number, "line_end": number},
        "quote": lines[number - 1].strip(),
    }


def test_receipt_reuses_content_across_order_and_date_and_preserves_old_structure(client, monkeypatch):
    connection_id = register(client, ["fiction_orders", "fiction_stores"])
    linked = [link(connection_id, "fiction_stores"), link(connection_id, "fiction_orders")]
    catalog, first = receipt(client, linked)
    content = source(client, first).read_bytes()
    chunk_count = first.chunk_count
    assert first.origin == "table_receipt"
    assert first.name.startswith("表结构收据 · 虚构零售库")
    assert content.startswith(b'{\n  "tables": [\n    {\n      "key": "t1",')
    assert "金额" in content.decode("utf-8") and b"\\u91d1" not in content
    assert hashlib.sha256(content).hexdigest() == first.sha256
    assert "secret_encrypted" not in content.decode() and '"config_json"' not in content.decode()

    from ontofoundry_api.services import modeling_input

    monkeypatch.setattr(modeling_input, "utc_now", lambda: datetime(2030, 1, 2, tzinfo=UTC))
    again_catalog, again = receipt(client, list(reversed(linked)))
    assert (again.id, again.sha256, again.name, again_catalog) == (first.id, first.sha256, first.name, catalog)
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(MaterialRecord)) == 1
        assert db.scalar(select(func.count()).select_from(MaterialChunkRecord)) == chunk_count

    change_column(client, connection_id)
    _, changed = receipt(client, linked)
    assert changed.id != first.id and changed.sha256 != first.sha256
    assert source(client, first).read_bytes() == content
    with client.app.state.session_factory() as db:
        assert db.scalar(select(func.count()).select_from(MaterialRecord)) == 2
        check_material_evidence(
            evidence(first, content.decode()),
            material_lookup(db, client.app.state.settings, WORKSPACE), "虚构属性",
        )


def test_payload_fixes_nested_key_order_and_foreign_key_order(client):
    connection_id = register(client, ["fiction_orders"])
    from ontofoundry_api.services.dataset_sources import linked_table_details

    with client.app.state.session_factory() as db:
        details = linked_table_details(db, WORKSPACE, [link(connection_id, "fiction_orders")])
    table = details[0]["table"]
    table["foreign_keys"] = [
        {"referred_table": name, "referred_columns": ["id"], "constrained_columns": ["store_id"], "referred_schema": "retail", "name": "ignored"}
        for name in ["fiction_stores", "fiction_regions"]
    ]
    _, first = linked_tables_payload(details)
    table["foreign_keys"] = [dict(reversed(list(f.items()))) for f in reversed(table["foreign_keys"])]
    table["columns"] = [dict(reversed(list(c.items()))) for c in table["columns"]]
    _, second = linked_tables_payload(details)
    assert first == second
    payload = json.loads(first)
    assert list(payload["tables"][0]) == [
        "key", "table", "connection_id", "connection", "dialect", "schema_name",
        "table_name", "kind", "comment", "primary_key", "foreign_keys", "columns",
    ]
    assert list(payload["tables"][0]["columns"][0]) == ["name", "type", "nullable", "comment"]


def test_multiple_connections_share_one_named_receipt(client):
    first = register(client, ["fiction_orders"])
    second = register(client, ["fiction_stores"])
    catalog, material = receipt(client, [link(first, "fiction_orders"), link(second, "fiction_stores")])
    assert material.name.startswith("表结构收据 · 多连接（2） · ")
    assert len(catalog) == len(json.loads(source(client, material).read_bytes())["tables"]) == 2


@pytest.mark.parametrize("invalid", ["past_end", "zero", "reversed", "quote", "hash", "workspace"])
def test_receipt_evidence_rejects_invalid_locator_quote_hash_or_workspace(client, invalid):
    connection_id = register(client, ["fiction_orders"])
    _, material = receipt(client, [link(connection_id, "fiction_orders")])
    text = source(client, material).read_text()
    entry = evidence(material, text)
    if invalid == "past_end":
        entry["locator"]["line_end"] = len(text.splitlines()) + 1
    elif invalid == "zero":
        entry["locator"]["line_start"] = 0
    elif invalid == "reversed":
        entry["locator"]["line_end"] = entry["locator"]["line_start"] - 1
    elif invalid == "quote":
        entry["quote"] = "不存在的引文"
    elif invalid == "hash":
        entry["material_sha256"] = "0" * 64
    with client.app.state.session_factory() as db:
        lookup = material_lookup(db, client.app.state.settings, "other-fictional-workspace" if invalid == "workspace" else WORKSPACE)
        with pytest.raises(EvidenceError) as error:
            check_material_evidence(entry, lookup, "虚构属性")
        assert error.value.code == "EVIDENCE_INVALID"


def test_origin_read_contract_and_cited_receipt_usage_archive_and_delete_protection(client):
    uploaded = client.post(ROOT + "/materials", params={"name": "虚构说明.md"}, content="虚构说明").json()
    assert uploaded["origin"] == "upload"
    connection_id = register(client, ["fiction_orders"])
    _, material = receipt(client, [link(connection_id, "fiction_orders")])
    text = source(client, material).read_text()
    session = create_session(client)
    prop = session["draft"]["properties"][0]
    prop["evidence"] = [evidence(material, text)]
    saved = client.put(ROOT + f"/sessions/{session['id']}", json={
        "revision": session["revision"], "draft": session["draft"],
    })
    assert saved.status_code == 200, saved.text
    listed = {item["id"]: item for item in client.get(ROOT + "/materials").json()["items"]}
    assert listed[material.id]["origin"] == "table_receipt"
    assert listed[uploaded["id"]]["origin"] == "upload"
    result = client.get(ROOT + "/materials/overview")
    assert result.status_code == 200, result.text
    Draft202012Validator(json.loads(export_schema.MATERIAL_TARGET.read_text())).validate(result.json())
    managed = {item["id"]: item for item in result.json()["items"]}[material.id]
    assert managed["origin"] == "table_receipt"
    assert managed["usage"]["properties"] == 1
    assert managed["usage"]["can_delete"] is False
    deleted = client.delete(ROOT + f"/materials/{material.id}")
    assert deleted.status_code == 409 and deleted.json()["error"]["code"] == "MATERIAL_IN_USE"
    archived = client.post(ROOT + f"/materials/{material.id}/archive")
    assert archived.status_code == 200 and archived.json()["origin"] == "table_receipt"
    assert material.id not in {m["id"] for m in client.get(ROOT + "/materials").json()["items"]}
    source(client, material).unlink()
    downloaded = client.get(ROOT + f"/materials/{material.id}")
    assert downloaded.status_code == 200 and downloaded.text == text
    with client.app.state.session_factory() as db:
        check_material_evidence(evidence(material, text), material_lookup(db, client.app.state.settings, WORKSPACE), "虚构属性")


def test_run_file_is_pinned_without_a_material_and_survives_background_sync(client, monkeypatch):
    connection_id = register(client, ["fiction_orders"])
    document = client.post(ROOT + "/materials", params={"name": "虚构说明.md"}, content="虚构订单说明").json()
    session = save_links(client, create_session(client), [link(connection_id, "fiction_orders")]).json()
    with client.app.state.session_factory() as db:
        db.get(ModelingSessionRecord, session["id"]).material_ids = [document["id"]]
        db.commit()
    uploads, packs = {}, []

    class Agent:
        async def create_topic(self, *_):
            return {"topic_id": "fictional-topic"}

        async def upload(self, topic_id, name, data, media_type):
            path = "inputs/" + name
            uploads[path] = data
            if name.startswith("ontofoundry-tables-"):
                assert media_type == "application/json"
                with client.app.state.session_factory() as db:
                    row = db.get(ModelingSessionRecord, session["id"])
                    assert row.run_manifest_json["table_snapshot"] == json.loads(data)
                    assert db.scalar(select(MaterialRecord).where(MaterialRecord.origin == "table_receipt")) is None
                change_column(client, connection_id)
            if name.startswith("ontofoundry-work-pack-"):
                packs.append(json.loads(data))
            return {"rel_path": path}

        async def deliver(self, **kwargs):
            return {"task_id": "fictional-task", "task_status": "running"}

    monkeypatch.setattr(agent_conversation, "_client", lambda *_: Agent())
    monkeypatch.setattr(agent_conversation, "_require_configured", lambda _: None)
    response = client.post(ROOT + f"/sessions/{session['id']}/agent-conversation/messages", json={
        "content": "根据虚构表结构建模", "metadata": {"mode": "model"},
    })
    assert response.status_code == 202, response.text
    pack = packs[-1]
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        files = row.run_manifest_json["input_files"]
        assert {m["id"] for m in pack["materials"]} == {document["id"]}
        assert "tables" not in pack and pack["table_scope"]["total"] == 1
        assert pack["tables_file"] == files["tables_file"]
        body = uploads[files["tables_file"]]
        assert files["tables_sha256"] == hashlib.sha256(body).hexdigest()
        assert json.loads(body) == row.run_manifest_json["table_snapshot"]
        assert json.loads(body)["tables"][0]["columns"][1]["type"] == "DECIMAL(12,2)"
        assert db.scalar(select(MaterialRecord).where(MaterialRecord.origin == "table_receipt")) is None


def test_material_origin_alembic_upgrade_backfills_existing_and_defaults_new_rows(client, monkeypatch):
    uploaded = client.post(ROOT + "/materials", params={"name": "虚构旧材料.md"}, content="虚构迁移前材料").json()
    engine = client.app.state.engine
    with engine.begin() as connection:
        connection.exec_driver_sql("ALTER TABLE materials DROP COLUMN origin")
    from ontofoundry_api import config

    monkeypatch.setattr(config, "get_settings", lambda: client.app.state.settings)
    ini = Path(__file__).parents[1] / "src/ontofoundry_api/alembic.ini"
    alembic = Config(str(ini))
    command.stamp(alembic, "20261020_000002")
    command.upgrade(alembic, "20261021_000001")
    column = next(c for c in inspect(engine).get_columns("materials") if c["name"] == "origin")
    assert column["nullable"] is False and column["default"] == "'upload'"
    with engine.begin() as connection:
        assert connection.exec_driver_sql("SELECT origin FROM materials").scalar_one() == "upload"
        connection.exec_driver_sql(
            "INSERT INTO materials (id, workspace_id, name, sha256, byte_size, chunk_count, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid4()), WORKSPACE, "虚构默认值材料", "f" * 64, 10, 0, "2030-01-02 00:00:00"),
        )
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM materials WHERE origin = 'upload'").scalar_one() == 2
    assert client.get(ROOT + f"/materials/{uploaded['id']}").text == "虚构迁移前材料"
    command.downgrade(alembic, "20261020_000002")
    assert "origin" not in {c["name"] for c in inspect(engine).get_columns("materials")}
    command.upgrade(alembic, "20261021_000001")
    assert {m["origin"] for m in client.get(ROOT + "/materials").json()["items"]} == {"upload"}
