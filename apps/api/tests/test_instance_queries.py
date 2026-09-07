"""SQL/query contracts against real SQLite tables; not external PG/MySQL/Doris integration."""

from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from ontofoundry_api.api import connections, instances
from ontofoundry_api.db_models import ConnectionRecord
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"


@pytest.fixture
def mapped_session(client, monkeypatch):
    engine = create_engine(
        "sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE suppliers (code TEXT PRIMARY KEY, name TEXT)"))
        conn.execute(
            text(
                "CREATE TABLE materials (code TEXT PRIMARY KEY, name TEXT, supplier_code TEXT)"
            )
        )
        conn.execute(
            text("INSERT INTO suppliers VALUES ('S1', '供应商一'), ('S2', '供应商二')")
        )
        conn.execute(
            text(
                "INSERT INTO materials VALUES ('M1', '物料一', 'S1'), ('M2', '物料二', 'S1'), ('M3', '物料三', 'S2')"
            )
        )

    @contextmanager
    def local_readonly(item, settings):
        with engine.connect() as conn:
            yield conn

    monkeypatch.setattr(connections, "connect_readonly", local_readonly)
    monkeypatch.setattr(instances, "connect_readonly", local_readonly)
    cid = str(uuid4())
    with client.app.state.session_factory() as db:
        db.add(
            ConnectionRecord(
                id=cid,
                workspace_id=str(DEMO_WORKSPACE_ID),
                name="测试连接",
                kind="postgresql",
                config_json={},
                secret_encrypted="not-used",
            )
        )
        db.commit()
    session = client.post(ROOT + "/sessions", json={"title": "SQL 契约测试"}).json()
    draft = session["draft"]
    supplier = next(t for t in draft["object_types"] if t["technical_name"] == "supplier")
    material = next(t for t in draft["object_types"] if t["technical_name"] == "material")
    draft["mappings"] = [
        {
            "id": str(uuid4()),
            "type_id": supplier["id"],
            "connection_id": cid,
            "table_name": "suppliers",
            "key_column": "code",
            "fields": {"supplier_code": "code"},
        },
        {
            "id": str(uuid4()),
            "type_id": material["id"],
            "connection_id": cid,
            "table_name": "materials",
            "key_column": "code",
            "fields": {"material_name": "name"},
        },
    ]
    relation = next(
        r
        for r in draft["link_types"]
        if r["source_type_id"] == supplier["id"] and r["target_type_id"] == material["id"]
    )
    relation["data_join"] = {"source_column": "code", "target_column": "supplier_code"}
    response = client.put(
        ROOT + "/sessions/" + session["id"],
        json={"revision": session["revision"], "draft": draft},
    )
    assert response.status_code == 200, response.text
    assert response.json()["validation"]["publishable"], response.text
    yield response.json(), supplier, material
    engine.dispose()


def test_join_neighborhood_matches_expected_rows_in_both_directions(client, mapped_session):
    session, supplier, material = mapped_session

    def query(tid, key, depth=1):
        response = client.post(
            ROOT + "/instance-neighborhood",
            json={"session_id": session["id"], "type_id": tid, "key": key, "depth": depth},
        )
        assert response.status_code == 200, response.text
        return response.json()

    first = query(supplier["id"], "S1")
    assert {o["key"] for o in first["objects"]} == {"S1", "M1", "M2"}
    assert len(first["links"]) == 2
    inverse = query(material["id"], "M1")
    assert {o["key"] for o in inverse["objects"]} == {"S1", "M1"}
    assert inverse["links"][0]["source_id"].endswith(":S1")
    assert {o["key"] for o in query(material["id"], "M1", 2)["objects"]} == {
        "S1",
        "M1",
        "M2",
    }
    assert not first["truncated"]


def test_mapping_preview_parameterizes_keys_and_reports_missing_columns(
    client, mapped_session
):
    session, supplier, _ = mapped_session
    mapping = session["draft"]["mappings"][0]
    attack = client.post(
        ROOT + "/mapping-preview", json={"mapping": mapping, "key": "S1' OR 1=1 --"}
    )
    assert attack.status_code == 200
    assert attack.json()["items"] == []
    page = client.post(
        ROOT + "/mapping-preview", json={"mapping": mapping, "limit": 1}
    ).json()
    assert len(page["items"]) == 1 and page["has_more"]
    missing = {**mapping, "key_column": "missing"}
    assert (
        client.post(ROOT + "/mapping-preview", json={"mapping": missing}).status_code == 422
    )
    assert (
        client.post(
            ROOT + "/instance-neighborhood",
            json={"type_id": supplier["id"], "session_id": session["id"], "key": "missing"},
        ).status_code
        == 404
    )


def test_cross_connection_is_not_federated(client, mapped_session):
    session, supplier, _ = mapped_session
    session["draft"]["mappings"][1]["connection_id"] = str(uuid4())
    saved = client.put(
        ROOT + "/sessions/" + session["id"],
        json={"revision": session["revision"], "draft": session["draft"]},
    )
    assert saved.status_code == 200
    result = client.post(
        ROOT + "/instance-neighborhood",
        json={"session_id": session["id"], "type_id": supplier["id"], "key": "S1"},
    ).json()
    assert len(result["objects"]) == 1
    assert any("跨连接" in warning for warning in result["warnings"])


def test_published_public_type_service_does_not_leak_database_join_columns(
    client, mapped_session
):
    session, _, _ = mapped_session
    result = client.post(
        ROOT + "/sessions/" + session["id"] + "/publish",
        json={"revision": session["revision"], "message": "测试"},
    )
    assert result.status_code == 200, result.text
    public = client.get(f"/api/v1/ontology/workspaces/{DEMO_WORKSPACE_ID}/types").json()
    assert all("data_join" not in item for item in public["items"])
