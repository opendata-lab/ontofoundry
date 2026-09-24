"""Publication, access, version and source-data contracts; no external DB claimed."""

import json
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from test_instance_queries import mapped_session as mapped_session_fixture
from test_modeling import mcp_request

from ontofoundry_api.api import assets, connections
from ontofoundry_api.api.auth import Principal, current_principal, ontology_principal
from ontofoundry_api.db_models import (
    MetadataSnapshotRecord,
    OntologyVersionRecord,
)
from ontofoundry_api.domain.instance_validation import valid_value
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

mapped_session = mapped_session_fixture

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"
SERVICE = f"/api/v1/ontology/workspaces/{DEMO_WORKSPACE_ID}"


def publish(client, session):
    response = client.post(
        ROOT + f"/sessions/{session['id']}/publish",
        json={"revision": session["revision"], "message": "契约验证"},
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def document_session(client):
    session = client.post(ROOT + "/sessions", json={}).json()
    kind = session["draft"]["object_types"][0]
    attrs = {
        a["technical_name"]: f"code-{i}"
        for i, a in enumerate(kind["attributes"])
        if a["required"]
    }
    session["draft"]["objects"] = [
        {
            "id": str(uuid4()),
            "type_id": kind["id"],
            "name": f"实例 {i}",
            "values": {k: f"{v}-{i}" for k, v in attrs.items()},
            "evidence": [],
        }
        for i in range(3)
    ]
    result = client.put(
        ROOT + f"/sessions/{session['id']}",
        json={"revision": session["revision"], "draft": session["draft"]},
    )
    assert result.status_code == 200, result.text
    return result.json(), kind


@pytest.mark.parametrize(
    ("kind", "value", "valid"),
    [
        ("integer", True, False),
        ("integer", 3, True),
        ("integer", "3", False),
        ("boolean", 1, False),
        ("boolean", False, True),
        ("string", 3, False),
        ("decimal", 1.5, True),
        ("float", float("inf"), False),
        ("date", "2024-02-29", True),
        ("date", "2025-02-29", False),
        ("date", "20260201", False),
        ("datetime", "2026-02-01", False),
        ("datetime", "2026-02-01T08:30:00+08:00", True),
    ],
)
def test_fact_value_semantics(kind, value, valid):
    assert valid_value(kind, value) is valid


def test_incomplete_values_can_save_but_cannot_publish(client, document_session):
    session, kind = document_session
    before = client.get(SERVICE + "/version").json()["version_id"]
    required = next(a for a in kind["attributes"] if a["required"])
    session["draft"]["objects"][0]["values"][required["technical_name"]] = " "
    saved = client.put(
        ROOT + f"/sessions/{session['id']}",
        json={"revision": session["revision"], "draft": session["draft"]},
    )
    assert saved.status_code == 200
    report = saved.json()["validation"]
    assert not report["publishable"]
    assert report["errors"][0]["code"] == "INSTANCE_REQUIRED"
    assert report["errors"][0]["path"].startswith("$.objects[0].values.")
    rejected = client.post(
        ROOT + f"/sessions/{session['id']}/publish",
        json={"revision": saved.json()["revision"]},
    )
    assert rejected.status_code == 422
    assert client.get(SERVICE + "/version").json()["version_id"] == before
    with client.app.state.session_factory() as db:
        assert len(db.scalars(select(OntologyVersionRecord)).all()) == 1


def test_pinned_rest_and_mcp_instances_and_cursor(client, document_session):
    session, kind = document_session
    first = publish(client, session)
    assert client.get(SERVICE + "/version").json()["published_at"].endswith(("Z", "+00:00"))
    vid = first["version"]["version_id"]
    session = first["session"]
    session["draft"]["object_types"][0]["description"] = "新版本说明"
    saved = client.put(
        ROOT + f"/sessions/{session['id']}",
        json={"revision": session["revision"], "draft": session["draft"]},
    ).json()
    second = publish(client, saved)["version"]["version_id"]
    for endpoint in ("version", "types", "types/" + kind["id"], "type-graph/neighborhood"):
        response = client.get(SERVICE + "/" + endpoint, params={"version_id": vid})
        assert response.status_code == 200, response.text
        assert response.json()["version_id"] == vid
    page = client.get(SERVICE + "/objects", params={"version_id": vid, "limit": 1}).json()
    assert page["next_cursor"] and len(page["items"]) == 1
    next_page = client.get(
        SERVICE + "/objects",
        params={"version_id": vid, "limit": 1, "cursor": page["next_cursor"]},
    ).json()
    assert next_page["items"][0]["id"] != page["items"][0]["id"]
    assert (
        client.get(
            SERVICE + "/objects",
            params={"version_id": second, "cursor": page["next_cursor"]},
        ).status_code
        == 422
    )
    ref = page["items"][0]["ref"]
    rest = client.get(SERVICE + "/objects/" + ref, params={"version_id": vid}).json()
    mcp = mcp_request(
        client,
        "tools/call",
        {"name": "get_object", "arguments": {"ref": ref, "version_id": vid}},
    ).json()["result"]
    assert not mcp["isError"]
    assert json.loads(mcp["content"][0]["text"])["item"] == rest["item"]
    assert (
        client.get(
            SERVICE + "/objects/" + ref + "/neighborhood", params={"depth": 4}
        ).status_code
        == 422
    )
    assert (
        client.get(SERVICE + "/types", params={"version_id": str(uuid4())}).status_code
        == 404
    )


def test_tokens_do_not_gain_instances_implicitly_and_can_be_revoked(
    client, document_session
):
    publish(client, document_session[0])
    legacy = client.post(
        ROOT + "/service-tokens",
        json={"name": "本体调用方", "scopes": ["ontology:read"]},
    ).json()
    legacy_headers = {"Authorization": "Bearer " + legacy["token"]}
    assert client.get(SERVICE + "/types", headers=legacy_headers).status_code == 200
    assert client.get(SERVICE + "/objects", headers=legacy_headers).status_code == 403
    assert (
        len(
            mcp_request(client, "tools/list", headers=legacy_headers).json()["result"][
                "tools"
            ]
        )
        == 5
    )
    denied = mcp_request(
        client,
        "tools/call",
        {"name": "search_objects", "arguments": {}},
        headers=legacy_headers,
    ).json()["result"]
    assert denied["isError"]
    granted = client.post(
        ROOT + "/service-tokens", json={"name": "实例调用方", "scopes": ["instances:read"]}
    ).json()
    headers = {"Authorization": "Bearer " + granted["token"]}
    assert len(client.get(SERVICE + "/objects", headers=headers).json()["items"]) == 3
    assert client.get(ROOT + "/sessions", headers=headers).status_code == 401
    assert client.delete(ROOT + "/service-tokens/" + granted["id"]).status_code == 200
    assert client.get(SERVICE + "/objects", headers=headers).status_code == 401


def test_nonmember_cannot_read_instances_or_private_presentation(client, document_session):
    version = publish(client, document_session[0])["version"]["version_id"]
    client.app.dependency_overrides[current_principal] = lambda: Principal(
        "not-member", "other", "其他用户", None
    )
    client.app.dependency_overrides[ontology_principal] = client.app.dependency_overrides[
        current_principal
    ]
    try:
        assert client.get(SERVICE + "/objects").status_code == 403
        assert client.get(SERVICE + "/types").status_code == 200
        public = client.get(ROOT + f"/versions/{version}/presentation").json()["model"]
        assert public["objects"] == public["links"] == public["mappings"] == []
        assert all("data_join" not in relation for relation in public["link_types"])
    finally:
        client.app.dependency_overrides.clear()


def test_database_services_share_actual_rows_and_protect_mapping_export(
    client, mapped_session
):
    session, supplier, _ = mapped_session
    vid = publish(client, session)["version"]["version_id"]
    assert client.get(SERVICE + "/version").json()["counts"]["mappings"] > 0
    page = client.get(
        SERVICE + "/objects",
        params={"source": "database", "type_id": supplier["id"], "version_id": vid},
    ).json()
    assert [obj["key"] for obj in page["items"]] == ["S1", "S2"]
    ref = page["items"][0]["ref"]
    graph = client.get(SERVICE + "/objects/" + ref + "/neighborhood").json()
    assert {obj["key"] for obj in graph["objects"]} == {"S1", "M1", "M2"}
    assert graph["data_mode"] == "live"
    assert any(issue["code"] == "INSTANCE_REQUIRED" for issue in graph["quality_issues"])
    mcp = mcp_request(
        client, "tools/call", {"name": "expand_object_graph", "arguments": {"ref": ref}}
    ).json()["result"]
    assert json.loads(mcp["content"][0]["text"])["objects"] == graph["objects"]
    legacy = client.post(
        ROOT + "/service-tokens",
        json={"name": "语义", "scopes": ["ontology:read"]},
    ).json()
    definition = client.get(
        SERVICE + f"/versions/{vid}/export",
        headers={"Authorization": "Bearer " + legacy["token"]},
    ).json()
    assert "ontology_mappings" not in definition
    redacted = mcp_request(
        client,
        "tools/call",
        {"name": "export_ontology", "arguments": {"version_id": vid}},
        headers={"Authorization": "Bearer " + legacy["token"]},
    ).json()["result"]
    assert redacted["structuredContent"]["redacted_fields"] == [
        "ontology_mappings"
    ]
    assert "ontology_mappings" not in redacted["structuredContent"]

    mapping_token = client.post(
        ROOT + "/service-tokens",
        json={"name": "映射", "scopes": ["mappings:read"]},
    ).json()
    mapping_headers = {"Authorization": "Bearer " + mapping_token["token"]}
    complete = mcp_request(
        client,
        "tools/call",
        {"name": "export_ontology", "arguments": {"version_id": vid}},
        headers=mapping_headers,
    ).json()["result"]["structuredContent"]
    assert complete["ontology_mappings"]
    assert "redacted_fields" not in complete
    assert client.get(SERVICE + "/objects", headers=mapping_headers).status_code == 403


def test_assets_detect_schema_drift_and_keep_last_success(
    client, mapped_session, monkeypatch
):
    session, _, _ = mapped_session
    publish(client, session)
    cid = client.get(ROOT + "/connections").json()["items"][0]["id"]
    monkeypatch.setattr(assets, "connect_readonly", connections.connect_readonly)
    path = ROOT + f"/connections/{cid}/assets"
    initial = client.post(path + "/refresh").json()
    assert initial["status"] == "ready"
    assert initial["changes"] == []
    assert {t["name"] for t in initial["items"]} == {"suppliers", "materials"}
    with connections.connect_readonly(None, None) as conn:
        conn.execute(text("ALTER TABLE materials RENAME COLUMN name TO renamed"))
        conn.commit()
    updated = client.post(path + "/refresh").json()
    material = next(t for t in updated["items"] if t["name"] == "materials")
    assert material["mappings"][0]["status"] == "invalid"
    assert material["mappings"][0]["missing_columns"] == ["name"]

    def offline(*_):
        raise HTTPException(422, "源库不可用")

    monkeypatch.setattr(assets, "connect_readonly", offline)
    stale = client.post(path + "/refresh").json()
    assert stale["status"] == "stale" and stale["observed_at"] == updated["observed_at"]
    assert stale["items"] == updated["items"]
    with client.app.state.session_factory() as db:
        record = db.get(MetadataSnapshotRecord, (cid, ""))
        assert record.error == "源库不可用"


def test_preview_and_history_diff_use_saved_revision_without_publication(client):
    before = client.get(SERVICE + "/version").json()
    session = client.post(ROOT + "/sessions", json={}).json()
    draft = deepcopy(session["draft"])
    target = draft["object_types"][0]
    target["name"] = "供应商新名称"
    saved = client.put(
        ROOT + f"/sessions/{session['id']}",
        json={"revision": session["revision"], "draft": draft},
    ).json()
    preview = client.post(
        ROOT + f"/sessions/{session['id']}/preview", json={"revision": saved["revision"]}
    ).json()
    assert preview["validation"]["publishable"] and preview["ossie"]
    assert any(
        c["path"] == f"$.object_types[{target['id']}].name" for c in preview["changes"]
    )
    assert client.get(SERVICE + "/version").json()["version_id"] == before["version_id"]
    assert (
        client.post(
            ROOT + f"/sessions/{session['id']}/preview",
            json={"revision": session["revision"]},
        ).status_code
        == 409
    )
    after = publish(client, saved)["version"]
    compared = client.get(
        ROOT + "/version-comparison",
        params={"left_id": after["version_id"], "right_id": before["version_id"]},
    ).json()
    assert compared["left"]["version_id"] == before["version_id"]
    assert compared["changes"] == preview["changes"]
    assert (
        client.get(
            ROOT + "/version-comparison",
            params={"left_id": after["version_id"], "right_id": after["version_id"]},
        ).status_code
        == 422
    )
