"""T2: a modeling run reads only its own workspace and pinned version."""

import json
from uuid import uuid4

from test_modeling import ONTOLOGY, ROOT, create_session, mcp_request, publish, save

from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.services.run_credentials import RunGrant, issue


def start_run(client, session: dict) -> str:
    """Put the session into a running state and mint its run credential."""
    run_token = uuid4().hex
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session["id"])
        item.task_status = "running"
        item.dataagent_run_token = run_token
        created_by = item.created_by
        db.commit()
    return issue(
        client.app.state.settings.session_secret,
        RunGrant(
            workspace_id=session["workspace_id"],
            session_id=session["id"],
            run_token=run_token,
            version_id=session["base_version_id"],
            user_id=created_by,
        ),
    )


def call(client, credential, tool, **arguments):
    return mcp_request(
        client,
        "tools/call",
        {"name": tool, "arguments": arguments},
        headers={"Authorization": "Bearer " + credential},
    )


def test_session_pins_base_version_and_hashes(client):
    session = create_session(client)
    version = client.get(ONTOLOGY + "/version").json()
    assert session["base_version_id"] == version["version_id"]
    assert session["base_version_sha256"] == version["normalized_snapshot_sha256"]
    assert session["draft_sha256"] == snapshot_sha256(session["draft"])
    session["draft"]["object_types"][0]["description"] = "改动"
    saved = save(client, session, session["draft"]).json()
    assert saved["draft_sha256"] == snapshot_sha256(saved["draft"])
    assert saved["base_version_sha256"] == session["base_version_sha256"]


def test_run_credential_reads_the_pinned_version_only(client):
    pinned = create_session(client)
    # The workspace moves on after the session was created.
    other = create_session(client)
    other["draft"]["object_types"][0]["description"] = "新版本"
    publish(client, save(client, other, other["draft"]).json())
    latest = client.get(ONTOLOGY + "/version").json()["version_id"]
    assert latest != pinned["base_version_id"]

    credential = start_run(client, pinned)
    result = call(client, credential, "get_ontology_version").json()["result"]
    body = result["structuredContent"]
    assert body["version_id"] == pinned["base_version_id"]
    assert body["normalized_snapshot_sha256"] == pinned["base_version_sha256"]
    assert body["version_content_sha256"]

    explicit = call(client, credential, "get_ontology_graph", version_id=pinned["base_version_id"])
    assert "result" in explicit.json()
    refused = call(client, credential, "get_ontology_graph", version_id=latest).json()
    assert refused["error"]["code"] == -32602


def test_run_credential_has_no_mapping_or_instance_access(client):
    session = create_session(client)
    credential = start_run(client, session)
    tools = mcp_request(
        client, "tools/list", headers={"Authorization": "Bearer " + credential}
    ).json()["result"]["tools"]
    names = {tool["name"] for tool in tools}
    assert "search_objects" not in names
    export = call(client, credential, "export_ontology").json()["result"]
    assert "ontology_mappings" not in export["structuredContent"]


def test_run_credential_is_refused_elsewhere_and_after_the_run(client):
    session = create_session(client)
    credential = start_run(client, session)
    header = {"Authorization": "Bearer " + credential}

    # Not a REST credential.
    assert client.get(ONTOLOGY + "/version", headers=header).status_code == 401
    # Not for another workspace.
    other = client.post(
        "/api/v1/workspaces", json={"name": "另一个空间", "slug": "another-space"}
    )
    assert other.status_code in (200, 201), other.text
    foreign = mcp_request(client, "tools/list", headers=header)
    assert foreign.status_code == 200
    response = client.post(
        f"/api/v1/ontology/workspaces/{other.json()['id']}/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        headers=header,
    )
    assert response.status_code == 401
    # A tampered credential.
    assert (
        mcp_request(client, "tools/list", headers={"Authorization": "Bearer " + credential + "x"}).status_code
        == 401
    )
    # The run ends: the credential dies with it.
    with client.app.state.session_factory() as db:
        db.get(ModelingSessionRecord, session["id"]).task_status = "finished"
        db.commit()
    assert mcp_request(client, "tools/list", headers=header).status_code == 401


def test_run_manifest_is_recorded_when_a_run_is_claimed(client, monkeypatch):
    from ontofoundry_api.api import agent_conversation

    class FakeAgent:
        async def create_topic(self, *_):
            return {"topic_id": "topic-1"}

        async def upload(self, *_args, **_kwargs):
            return {"rel_path": "ctx.json"}

        async def deliver(self, **_):
            return {"task_id": "task-1", "task_status": "running"}

    monkeypatch.setattr(agent_conversation, "_client", lambda *_: FakeAgent())
    monkeypatch.setattr(agent_conversation, "_require_configured", lambda _r: None)
    session = create_session(client)
    response = client.post(
        ROOT + f"/sessions/{session['id']}/agent-conversation/messages",
        json={"content": "建模", "metadata": {"mode": "model"}},
    )
    assert response.status_code in (200, 201, 202), response.text
    with client.app.state.session_factory() as db:
        manifest = db.get(ModelingSessionRecord, session["id"]).run_manifest_json
    assert manifest["base_version_id"] == session["base_version_id"]
    assert manifest["base_version_sha256"] == session["base_version_sha256"]
    assert manifest["source_session_revision"] == session["revision"] + 1
    assert manifest["source_draft_sha256"] == session["draft_sha256"]
    assert manifest["materials"] == []
    assert json.dumps(manifest)  # plain JSON


def test_cited_material_can_only_be_archived(client):
    material = client.post(ROOT + "/materials?name=a.md", content="# a\n供应商\n".encode()).json()
    unused = client.post(ROOT + "/materials?name=b.md", content="# b\n别的\n".encode()).json()
    session = create_session(client)
    session["material_ids"] = [material["id"]]
    saved = client.put(
        ROOT + "/sessions/" + session["id"],
        json={"revision": session["revision"], "draft": session["draft"], "material_ids": [material["id"]]},
    )
    assert saved.status_code == 200, saved.text

    refused = client.delete(ROOT + "/materials/" + material["id"])
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "MATERIAL_IN_USE"

    archived = client.post(ROOT + "/materials/" + material["id"] + "/archive").json()
    assert archived["archived_at"]
    listed = {m["id"] for m in client.get(ROOT + "/materials").json()["items"]}
    assert material["id"] not in listed
    everything = client.get(ROOT + "/materials?include_archived=true").json()["items"]
    assert material["id"] in {m["id"] for m in everything}
    assert client.get(ROOT + "/materials/" + material["id"]).status_code == 200  # still readable

    assert client.delete(ROOT + "/materials/" + unused["id"]).status_code == 204


def test_duplicate_evidence_ids_are_refused_on_save(client):
    session = create_session(client)
    entry = {
        "kind": "manual",
        "id": str(uuid4()),
        "note": "x",
        "created_by": "u",
        "created_at": "2026-09-01T00:00:00Z",
    }
    session["draft"]["object_types"][0]["evidence"] = [entry, dict(entry)]
    response = save(client, session, session["draft"])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EVIDENCE_ID_DUPLICATE"


def test_after_publish_the_session_draft_is_the_published_form(client):
    session = create_session(client)
    session["draft"]["object_types"][0]["description"] = "发布"
    published = publish(client, save(client, session, session["draft"]).json()).json()
    after = published["session"]
    assert after["draft_sha256"] == after["base_version_sha256"]
    assert after["draft_sha256"] == snapshot_sha256(after["draft"])
