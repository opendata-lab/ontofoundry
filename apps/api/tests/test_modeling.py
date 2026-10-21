"""Core session persistence, revision guards and three-way publication."""

from copy import deepcopy

from dataset_binding import bind_datasets

from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"
ONTOLOGY = f"/api/v1/ontology/workspaces/{DEMO_WORKSPACE_ID}"


def create_session(client):
    response = client.post(ROOT + "/sessions", json={"title": "虚构销售建模"})
    assert response.status_code == 201, response.text
    return response.json()


def save(client, session, draft):
    bind_datasets(client, draft)
    return client.put(
        ROOT + f"/sessions/{session['id']}",
        json={"revision": session["revision"], "draft": draft},
    )


def preview(client, session):
    return client.post(
        ROOT + f"/sessions/{session['id']}/preview",
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


def test_saved_draft_and_cas(client):
    session = create_session(client)
    draft = deepcopy(session["draft"])
    draft["object_types"][0]["description"] = "会话内修改"
    response = save(client, session, draft)
    assert response.status_code == 200, response.text
    assert client.get(ROOT + f"/sessions/{session['id']}").json()["draft"] == draft
    assert client.get(ROOT + "/published-snapshot").json() != draft
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


def test_incomplete_graph_can_be_stashed_but_not_accepted_or_published(client):
    from pr23_fixtures import example_session
    from test_t4_proposal_decisions import decide, seed_batch, update

    session = example_session(client, "01-basic-sales", published=True)
    metric = session["draft"]["metrics"][0]
    batch = seed_batch(
        client, session, [update("metric", metric, description="待接受的口径说明")]
    )
    incomplete = deepcopy(session["draft"])
    incomplete["object_types"][1]["name"] = incomplete["object_types"][0]["name"]
    response = save(client, session, incomplete)
    assert response.status_code == 200, response.text
    stashed = response.json()
    assert stashed["revision"] == session["revision"] + 1
    assert not stashed["validation"]["publishable"]
    assert any("英文标识重复" in e["message"] for e in stashed["validation"]["errors"])
    assert client.get(ROOT + f"/sessions/{session['id']}").json()["draft"] == incomplete
    refused = decide(client, stashed, [(batch["items"][0]["id"], "accept")])
    assert (
        refused.status_code == 422
        and refused.json()["error"]["code"] == "VALIDATION_FAILED"
    )
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


def test_stash_checks_known_source_columns_with_specific_error(client):
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
