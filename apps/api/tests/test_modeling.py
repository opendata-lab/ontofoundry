"""Core session persistence, revision guards and three-way publication."""

from copy import deepcopy

from dataset_binding import bind_datasets

from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"
ONTOLOGY = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"


def published_snapshot(client, root=ROOT):
    version = client.get(root + "/version").json()["version_id"]
    response = client.get(root + f"/versions/{version}/presentation")
    assert response.status_code == 200, response.text
    return response.json()["model"]


def create_session(client):
    response = client.post(ROOT + "/sessions", json={"title": "虚构销售建模"})
    assert response.status_code == 201, response.text
    return response.json()


def save(client, session, draft):
    """Seed a legacy stored draft for publish/read/agent regression fixtures.

    Human-save endpoint behavior is exercised in test_element_save instead.
    Some fixtures intentionally contain incomplete graphs predating AI-09.
    """
    from fastapi.encoders import jsonable_encoder
    from httpx import Response

    from ontofoundry_api.db_models import ModelingSessionRecord, utc_now
    from ontofoundry_api.domain.evidence import EvidenceError, reconcile_draft_evidence
    from ontofoundry_api.services.errors import ServiceError
    from ontofoundry_api.services.join_validation import validate_source_columns
    from ontofoundry_api.services.materials_lookup import material_lookup
    from ontofoundry_api.services.sessions import revise, validate_draft
    from ontofoundry_api.services.workspaces import get_workspace

    bind_datasets(client, draft, session["workspace_id"])
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session["id"])
        try:
            reconciled = reconcile_draft_evidence(
                item.draft_json, draft,
                lookup=material_lookup(db, client.app.state.settings, session["workspace_id"]),
                actor_id="00000000-0000-0000-0000-000000000001", now=utc_now(),
            )
            validate_source_columns(reconciled)
            data = revise(db, item, session["revision"], draft_json=reconciled)
            data["validation"] = validate_draft(reconciled, get_workspace(db, session["workspace_id"]))
            return Response(200, json=jsonable_encoder(data))
        except (EvidenceError, ServiceError) as exc:
            return Response(getattr(exc, "status_code", 422), json={"error": {"code": exc.code, "message": str(exc)}})


def preview(client, session):
    return client.post(
        ROOT + f"/sessions/{session['id']}/publish-preview",
        json={"expected_session_revision": session["revision"]},
    )


def publish(client, session):
    response = preview(client, session)
    if response.status_code != 200:
        return response
    body = response.json()
    return client.post(
        ROOT + f"/sessions/{session['id']}/publish",
        json={
            "expected_session_revision": session["revision"],
            "expected_current_version_id": body["current_version_id"],
            "expected_merged_snapshot_sha256": body["merged_snapshot_sha256"],
            "expected_instance_change_sequence": body["instance_change_sequence"],
        },
    )


def mcp_request(client, method, params=None, headers=None):
    return client.post(
        ONTOLOGY + "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers={
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25",
            **(headers or {}),
        },
    )


def test_legacy_draft_revision_guard(client):
    session = create_session(client)
    draft = deepcopy(session["draft"])
    draft["object_types"][0]["description"] = "会话内修改"
    response = save(client, session, draft)
    assert response.status_code == 200, response.text
    assert client.get(ROOT + f"/sessions/{session['id']}").json()["draft"] == draft
    assert published_snapshot(client, ROOT) != draft
    assert save(client, session, draft).status_code == 409


def test_two_sessions_merge_and_conflict(client):
    a, b = create_session(client), create_session(client)
    a["draft"]["object_types"][0]["description"] = "甲"
    b["draft"]["object_types"][1]["description"] = "乙"
    a, b = save(client, a, a["draft"]).json(), save(client, b, b["draft"]).json()
    assert publish(client, a).status_code == 200
    assert publish(client, b).status_code == 200
    a, b = create_session(client), create_session(client)
    a["draft"]["object_types"][0]["description"] = "并发甲"
    b["draft"]["object_types"][0]["description"] = "并发乙"
    a, b = save(client, a, a["draft"]).json(), save(client, b, b["draft"]).json()
    assert publish(client, a).status_code == 200
    conflict = preview(client, b)
    assert conflict.status_code == 409
    error = conflict.json()["error"]
    resolved = client.post(
        ROOT + f"/sessions/{b['id']}/resolve-merge",
        json={
            "expected_session_revision": b["revision"],
            "expected_current_version_id": error["current_version_id"],
            "resolutions": {c["key"]: {"choice": "draft"} for c in error["conflicts"]},
        },
    )
    assert resolved.status_code == 200, resolved.text
    assert publish(client, resolved.json()).status_code == 200


def test_legacy_incomplete_graph_reads_and_refuses_publication(client):
    from pr23_fixtures import example_session

    session = example_session(client, "01-basic-sales", published=True)
    incomplete = deepcopy(session["draft"])
    incomplete["object_types"][1]["name"] = incomplete["object_types"][0]["name"]
    response = save(client, session, incomplete)
    assert response.status_code == 200, response.text
    stashed = response.json()
    assert stashed["revision"] == session["revision"] + 1
    assert not stashed["validation"]["publishable"]
    assert any("英文标识重复" in e["message"] for e in stashed["validation"]["errors"])
    assert client.get(ROOT + f"/sessions/{session['id']}").json()["draft"] == incomplete
    version = client.get(ONTOLOGY + "/version").json()["version_id"]
    invalid_preview = preview(client, stashed)
    assert invalid_preview.status_code == 200, invalid_preview.text
    assert not invalid_preview.json()["validation"]["publishable"]
    refused = publish(client, stashed)
    assert (
        refused.status_code == 422
        and refused.json()["error"]["code"] == "VALIDATION_FAILED"
    )
    assert client.get(ONTOLOGY + "/version").json()["version_id"] == version
    fixed = save(client, stashed, session["draft"])
    assert fixed.status_code == 200 and fixed.json()["validation"]["publishable"]
    assert publish(client, fixed.json()).status_code == 200


def test_legacy_fixture_checks_source_columns(client):
    from pr23_fixtures import example_session

    session = example_session(client, "01-basic-sales")
    invalid = deepcopy(session["draft"])
    invalid["mappings"][0]["sources"][0]["key_columns"] = ["missing_customer_key"]
    response = save(client, session, invalid)
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "JOIN_COLUMN_NOT_FOUND"
    assert (
        client.get(ROOT + f"/sessions/{session['id']}").json()["revision"]
        == session["revision"]
    )
    # A dangling semantic reference is reportable, not a structural/source error.
    invalid = deepcopy(session["draft"])
    invalid["link_types"][0]["target_type_id"] = "00000000-0000-4000-8000-000000099999"
    response = save(client, session, invalid)
    assert response.status_code == 200, response.text
    assert not response.json()["validation"]["publishable"]
