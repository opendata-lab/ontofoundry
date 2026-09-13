"""Opt-in integration against a disposable MySQL fixture, never a production DB.

ONTOFOUNDRY_TEST_MYSQL_CONFIG must name a JSON file accepted by ConnectionCreate.
It must use a SELECT-only account and contain suppliers(code,name) with S1/S2
and materials(code,name,supplier_code) with M1/M2 -> S1, M3 -> S2.
This test only reads that source; platform writes use the temporary client DB.
"""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import text
from test_modeling import mcp_request
from test_stage_a import ROOT, SERVICE, publish

from ontofoundry_api.api.connections import connect_readonly
from ontofoundry_api.db_models import ConnectionRecord


@pytest.mark.skipif(
    not os.environ.get("ONTOFOUNDRY_TEST_MYSQL_CONFIG"),
    reason="Disposable MySQL configuration not supplied",
)
def test_mysql_metadata_mapping_instance_service_and_readonly_account(client):
    config = json.loads(Path(os.environ["ONTOFOUNDRY_TEST_MYSQL_CONFIG"]).read_text())
    assert config["kind"] == "mysql"
    client.app.state.settings.connection_key = Fernet.generate_key().decode()
    created = client.post(ROOT + "/connections", json=config)
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    assert client.post(ROOT + f"/connections/{cid}/test").status_code == 200
    refreshed = client.post(ROOT + f"/connections/{cid}/assets/refresh").json()
    assert refreshed["status"] == "ready", refreshed
    supplier_table = next(t for t in refreshed["items"] if t["name"] == "suppliers")
    assert next(c for c in supplier_table["columns"] if c["name"] == "code")["primary_key"]
    session = client.post(ROOT + "/sessions", json={"title": "MySQL 实际连接验收"}).json()
    draft = session["draft"]
    supplier = next(t for t in draft["object_types"] if t["technical_name"] == "supplier")
    material = next(t for t in draft["object_types"] if t["technical_name"] == "material")
    draft["mappings"] = [
        {
            "id": str(uuid4()),
            "type_id": supplier["id"],
            "connection_alias": config["name"],
            "table_name": "suppliers",
            "key_column": "code",
            "fields": {"supplier_code": "code", "supplier_name": "name"},
        },
        {
            "id": str(uuid4()),
            "type_id": material["id"],
            "connection_alias": config["name"],
            "table_name": "materials",
            "key_column": "code",
            "fields": {"material_code": "code", "material_name": "name"},
        },
    ]
    relation = next(
        r
        for r in draft["link_types"]
        if r["source_type_id"] == supplier["id"] and r["target_type_id"] == material["id"]
    )
    relation["data_join"] = {"source_column": "code", "target_column": "supplier_code"}
    saved = client.put(
        ROOT + f"/sessions/{session['id']}",
        json={"revision": session["revision"], "draft": draft},
    ).json()
    version = publish(client, saved)["version"]["version_id"]
    listed = client.get(
        SERVICE + "/objects",
        params={"source": "database", "type_id": supplier["id"], "version_id": version},
    )
    assert listed.status_code == 200, listed.text
    data = listed.json()
    assert [row["key"] for row in data["items"]] == ["S1", "S2"]
    assert not data["quality_issues"]
    ref = data["items"][0]["ref"]
    graph = client.get(
        SERVICE + f"/objects/{ref}/neighborhood", params={"version_id": version}
    ).json()
    assert {row["key"] for row in graph["objects"]} == {"S1", "M1", "M2"}
    result = mcp_request(
        client,
        "tools/call",
        {"name": "expand_object_graph", "arguments": {"ref": ref, "version_id": version}},
    ).json()["result"]
    assert not result["isError"]
    assert json.loads(result["content"][0]["text"])["objects"] == graph["objects"]
    assets = client.get(ROOT + f"/connections/{cid}/assets").json()
    assert all(
        t["mappings"][0]["status"] == "valid" for t in assets["items"] if t["mappings"]
    )
    with client.app.state.session_factory() as db:
        connection = db.get(ConnectionRecord, cid)
        with (
            pytest.raises(HTTPException),
            connect_readonly(connection, client.app.state.settings) as sql,
        ):
            sql.execute(text("INSERT INTO suppliers VALUES ('WRITE_PROBE', 'Must fail')"))
        with connect_readonly(connection, client.app.state.settings) as sql:
            assert sql.execute(text("SELECT COUNT(*) FROM suppliers")).scalar() == 2
