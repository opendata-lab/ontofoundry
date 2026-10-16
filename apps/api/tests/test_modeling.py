"""Core session persistence, revision guards and three-way publication."""

from copy import deepcopy

from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"
ONTOLOGY = f"/api/v1/ontology/workspaces/{DEMO_WORKSPACE_ID}"


def create_session(client):
    response = client.post(ROOT + "/sessions", json={"title": "虚构销售建模"})
    assert response.status_code == 201, response.text
    return response.json()


def save(client, session, draft):
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
