"""Pinned modeling grants, including empty baselines, never follow a new head."""

from uuid import uuid4

from test_modeling import create_session, mcp_request, publish, save

from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.services.run_credentials import RunGrant, issue


def start_run(client, s):
    run = uuid4().hex
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, s["id"])
        item.task_status = "running"
        item.dataagent_run_token = run
        user = item.created_by
        db.commit()
    return issue(
        client.app.state.settings.session_secret,
        RunGrant(
            workspace_id=s["workspace_id"],
            session_id=s["id"],
            run_token=run,
            version_id=s["base_version_id"],
            user_id=user,
        ),
    )


def call(client, credential, **args):
    return mcp_request(
        client,
        "tools/call",
        {"name": "get_ontology", "arguments": args},
        headers={"Authorization": "Bearer " + credential},
    )


def test_run_pinned_while_head_moves(client):
    s = create_session(client)
    credential = start_run(client, s)
    other = create_session(client)
    other["draft"]["object_types"][0]["description"] = "新版本"
    assert publish(client, save(client, other, other["draft"]).json()).status_code == 200
    result = call(client, credential).json()["result"]
    assert result["structuredContent"]["version_id"] == s["base_version_id"]
    assert call(client, credential, version_id=s["base_version_id"]).json()["result"][
        "isError"
    ]


def test_empty_pin_returns_empty_directory_and_deleted_grant_fails(client):
    wid = client.post(
        "/api/v1/workspaces", json={"name": "空白星湾", "slug": "empty-starbay"}
    ).json()["id"]
    s = client.post(f"/api/v1/workspaces/{wid}/sessions", json={}).json()
    credential = start_run(client, s)
    path = f"/api/v1/ontology/workspaces/{wid}/mcp"
    response = client.post(
        path,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_ontology", "arguments": {}},
        },
        headers={
            "Authorization": "Bearer " + credential,
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25",
        },
    )
    assert response.json()["result"]["structuredContent"]["total"] == 0, response.text
    with client.app.state.session_factory() as db:
        db.delete(db.get(ModelingSessionRecord, s["id"]))
        db.commit()
    assert (
        client.post(
            path, json={}, headers={"Authorization": "Bearer " + credential}
        ).status_code
        == 401
    )
