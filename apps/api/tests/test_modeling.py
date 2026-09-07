from copy import deepcopy
from uuid import uuid4

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"
ONTOLOGY = f"/api/v1/ontology/workspaces/{DEMO_WORKSPACE_ID}"


def create_session(client):
    response = client.post(ROOT + "/sessions", json={"title": "集成测试草稿"})
    assert response.status_code == 201, response.text
    return response.json()


def save(client, session, draft):
    return client.put(
        ROOT + "/sessions/" + session["id"],
        json={"revision": session["revision"], "draft": draft},
    )


def publish(client, session):
    return client.post(
        ROOT + "/sessions/" + session["id"] + "/publish",
        json={"revision": session["revision"], "message": "测试发布"},
    )


def test_saved_draft_survives_reload_and_does_not_mutate_published(client):
    s = create_session(client)
    s["draft"]["object_types"][0]["description"] = "只修改草稿"
    response = save(client, s, s["draft"])
    assert response.status_code == 200, response.text
    assert (
        client.get(ROOT + "/sessions/" + s["id"]).json()["draft"]["object_types"][0][
            "description"
        ]
        == "只修改草稿"
    )
    assert (
        client.get(ROOT + "/published-snapshot").json()["object_types"][0]["description"]
        != "只修改草稿"
    )
    assert save(client, s, s["draft"]).status_code == 409


def test_two_sessions_merge_independent_fields_and_publish_atomically(client):
    a, b = create_session(client), create_session(client)
    a["draft"]["object_types"][0]["description"] = "新的供应商定义"
    b["draft"]["object_types"][1]["description"] = "新的物料定义"
    a = save(client, a, a["draft"]).json()
    b = save(client, b, b["draft"]).json()
    assert publish(client, a).status_code == 200
    response = publish(client, b)
    assert response.status_code == 200, response.text
    snapshot = client.get(ROOT + "/published-snapshot").json()
    descriptions = {t["description"] for t in snapshot["object_types"]}
    assert {"新的供应商定义", "新的物料定义"} <= descriptions
    assert response.json()["version"]["version"] == 3
    assert (
        client.get(ONTOLOGY + "/version").json()["version_sha256"]
        == response.json()["version"]["version_sha256"]
    )


def test_same_field_conflict_can_be_resolved_without_overwriting_other_changes(client):
    a, b = create_session(client), create_session(client)
    a["draft"]["object_types"][0]["description"] = "A 修改"
    b["draft"]["object_types"][0]["description"] = "B 修改"
    a = save(client, a, a["draft"]).json()
    b = save(client, b, b["draft"]).json()
    assert publish(client, a).status_code == 200
    response = publish(client, b)
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert client.get(ONTOLOGY + "/version").json()["version"] == 2
    resolution = client.post(
        ROOT + "/sessions/" + b["id"] + "/resolve-merge",
        json={
            "revision": b["revision"],
            "current_version_id": detail["current_version_id"],
            "resolutions": {c["path"]: "draft" for c in detail["conflicts"]},
        },
    )
    assert resolution.status_code == 200, resolution.text
    assert publish(client, resolution.json()).status_code == 200


def test_invalid_names_save_as_draft_but_cannot_publish(client):
    s = create_session(client)
    s["draft"]["object_types"][1]["name"] = s["draft"]["object_types"][0]["name"]
    result = save(client, s, s["draft"])
    assert result.status_code == 200
    assert not result.json()["validation"]["publishable"]
    assert publish(client, result.json()).status_code == 422
    assert client.get(ONTOLOGY + "/version").json()["version"] == 1


def test_markdown_upload_dedup_download_and_encoding(client):
    content = "# 供应链\n供应商向客户提供物料。".encode()
    first = client.post(ROOT + "/materials?name=business.md", content=content)
    second = client.post(ROOT + "/materials?name=renamed.md", content=content)
    assert first.status_code == 201, first.text
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["chunk_count"] == 1
    assert client.get(ROOT + "/materials/" + first.json()["id"]).content == content
    assert client.post(ROOT + "/materials?name=x.pdf", content=b"pdf").status_code == 422
    assert client.post(ROOT + "/materials?name=x.md", content=b"\xff").status_code == 422


def test_non_member_cannot_read_materials_drafts_connections_or_instances(client):
    s = create_session(client)
    client.app.dependency_overrides[current_principal] = lambda: Principal(
        "not-a-member", "test:visitor", "visitor", None
    )
    for path in (
        "/materials",
        "/sessions",
        "/sessions/" + s["id"],
        "/connections",
        "/published-snapshot",
    ):
        assert client.get(ROOT + path).status_code == 403
    client.app.dependency_overrides.clear()


def test_service_token_is_workspace_scoped_revocable_and_read_only(client):
    token = client.post(ROOT + "/service-tokens", json={"name": "测试调用方"}).json()
    headers = {"Authorization": "Bearer " + token["token"]}
    assert client.get(ONTOLOGY + "/types", headers=headers).status_code == 200
    assert client.post(ROOT + "/sessions", json={}, headers=headers).status_code == 401
    assert (
        client.get("/api/v1/ontology/workspaces/other/types", headers=headers).status_code
        == 401
    )
    assert "token" not in client.get(ROOT + "/service-tokens").text.replace(
        "service-tokens", ""
    )
    client.delete(ROOT + "/service-tokens/" + token["id"])
    assert client.get(ONTOLOGY + "/types", headers=headers).status_code == 401


def mcp_request(client, method, params=None, headers=None):
    values = params or {}
    values = {
        **values,
        "_meta": {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {},
        },
    }
    actual_headers = {
        "MCP-Protocol-Version": "2026-07-28",
        "Mcp-Method": method,
        "Accept": "application/json, text/event-stream",
    }
    if "name" in values:
        actual_headers["Mcp-Name"] = values["name"]
    return client.post(
        ONTOLOGY + "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": values},
        headers={**actual_headers, **(headers or {})},
    )


def test_mcp_discover_list_call_and_notification(client):
    discover = mcp_request(client, "server/discover")
    assert discover.json()["result"]["supportedVersions"] == ["2026-07-28"]
    assert discover.json()["result"]["resultType"] == "complete"
    tools = mcp_request(client, "tools/list").json()["result"]["tools"]
    assert len(tools) == 5
    result = mcp_request(client, "tools/call", {"name": "get_ontology_version"}).json()
    assert result["result"]["isError"] is False
    assert (
        client.post(
            ONTOLOGY + "/mcp", json={"jsonrpc": "2.0", "method": "notifications/example"}
        ).status_code
        == 202
    )
    assert (
        mcp_request(
            client, "ping", headers={"Origin": "https://untrusted.example"}
        ).status_code
        == 403
    )
    assert client.get(ONTOLOGY + "/mcp").status_code == 405


def test_mcp_rejects_mismatched_headers_and_invalid_arguments(client):
    response = mcp_request(
        client, "tools/call", {"name": "get_ontology_type"}, {"Mcp-Name": "wrong"}
    )
    assert response.status_code == 400 and response.json()["error"]["code"] == -32020
    response = mcp_request(client, "tools/call", {"name": "get_ontology_type"})
    assert response.json()["error"]["code"] == -32602
    assert (
        mcp_request(
            client,
            "tools/call",
            {"name": "get_ontology_graph", "arguments": {"depth": 100}},
        ).status_code
        == 400
    )
    assert mcp_request(client, "unknown").status_code == 404
    assert mcp_request(client, "initialize").status_code == 404


def test_mcp_invalid_ids_do_not_emit_a_null_response_id(client):
    for rid in [None, True, {}, []]:
        response = client.post(
            ONTOLOGY + "/mcp",
            json={"jsonrpc": "2.0", "id": rid, "method": "ping"},
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == -32600
        assert "id" not in response.json()


def test_mcp_version_negotiation_and_required_metadata(client):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "ping",
        "params": {
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": "1900-01-01",
                "io.modelcontextprotocol/clientCapabilities": {},
            }
        },
    }
    response = client.post(
        ONTOLOGY + "/mcp",
        json=payload,
        headers={"MCP-Protocol-Version": "1900-01-01", "Mcp-Method": "ping"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == -32022
    assert response.json()["error"]["data"]["supported"] == ["2026-07-28"]
    payload["params"]["_meta"] = {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}
    response = client.post(
        ONTOLOGY + "/mcp",
        json=payload,
        headers={"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "ping"},
    )
    assert response.json()["error"]["code"] == -32602


def test_agent_contract_returns_candidates_before_accepting(client, monkeypatch):
    from ontofoundry_api.services import agent

    client.app.state.settings.anthropic_base_url = "https://model.example.invalid"
    client.app.state.settings.anthropic_model = "contract-test"
    s = create_session(client)
    original = deepcopy(s["draft"])
    proposal = {
        "id": str(uuid4()),
        "name": "仓库",
        "technical_name": "warehouse",
        "description": "保管物料的设施",
        "tags": [],
        "attributes": [],
    }

    async def fake_model(settings, messages, modeling):
        assert modeling is True
        assert "user_request" in messages[-1]["content"]
        return {
            "content": [
                {
                    "type": "tool_use",
                    "name": "propose_ontology",
                    "input": {
                        "summary": "识别仓库概念",
                        "candidates": [
                            {
                                "kind": "object_type",
                                "value": proposal,
                                "reason": "用户明确描述了仓库",
                            }
                        ],
                    },
                }
            ]
        }

    monkeypatch.setattr(agent, "call_model", fake_model)
    response = client.post(
        ROOT + "/sessions/" + s["id"] + "/messages",
        json={
            "revision": s["revision"],
            "content": "开始建模：仓库保管物料",
            "mode": "model",
        },
    )
    assert response.status_code == 202, response.text
    ready = client.get(ROOT + "/sessions/" + s["id"]).json()
    assert ready["task_status"] == "completed", ready
    assert ready["draft"] == original
    accepted = client.post(
        ROOT + "/sessions/" + s["id"] + "/candidates",
        json={
            "revision": ready["revision"],
            "ids": [ready["candidates"][0]["id"]],
            "action": "accept",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert len(accepted.json()["draft"]["object_types"]) == 6
    assert client.get(ONTOLOGY + "/version").json()["version"] == 1


def test_candidate_cannot_overwrite_later_manual_edit(client):
    s = create_session(client)
    before = deepcopy(s["draft"]["object_types"][0])
    candidate = {**before, "description": "Agent 的建议"}
    cid = str(uuid4())
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, s["id"])
        item.candidates_json = [
            {
                "id": cid,
                "kind": "object_type",
                "value": candidate,
                "before": before,
                "status": "pending",
            }
        ]
        db.commit()
    s["draft"]["object_types"][0]["description"] = "人工修改"
    saved = save(client, s, s["draft"]).json()
    result = client.post(
        ROOT + "/sessions/" + s["id"] + "/candidates",
        json={"revision": saved["revision"], "ids": [cid], "action": "accept"},
    )
    assert result.status_code == 200
    assert result.json()["draft"]["object_types"][0]["description"] == "人工修改"
    assert result.json()["candidates"][0]["conflict"]


def test_late_cancelled_run_cannot_overwrite_a_new_run(client, monkeypatch):
    import asyncio

    from ontofoundry_api.services import agent

    s = create_session(client)
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, s["id"])
        item.messages_json = [{"role": "user", "content": "旧请求", "run_id": "old"}]
        item.task_status = "queued"
        db.commit()

    async def late_response(*args):
        with client.app.state.session_factory() as db:
            item = db.get(ModelingSessionRecord, s["id"])
            item.messages_json = [
                *item.messages_json,
                {"role": "user", "content": "新请求", "run_id": "new"},
            ]
            item.task_status, item.task_detail = "running", "新请求处理中"
            db.commit()
        return {"content": [{"type": "text", "text": "旧回复"}]}

    monkeypatch.setattr(agent, "call_model", late_response)
    asyncio.run(agent.run_agent(client.app, s["id"], "旧请求", False, "old"))
    result = client.get(ROOT + "/sessions/" + s["id"]).json()
    assert result["task_status"] == "running"
    assert result["task_detail"] == "新请求处理中"
    assert not any(m["content"] == "旧回复" for m in result["messages"])


def test_candidate_evidence_is_an_exact_source_span():
    from types import SimpleNamespace

    import pytest

    from ontofoundry_api.services.agent import quote_evidence

    chunk = SimpleNamespace(
        material_id="m", line_start=12, text="标题\n供应商交付物料。\n下一行"
    )
    assert quote_evidence(chunk, "供应商交付物料。")[0] == {
        "material_id": "m",
        "line_start": 13,
        "line_end": 13,
        "quote": "供应商交付物料。",
    }
    with pytest.raises(ValueError, match="不在当前材料"):
        quote_evidence(chunk, "虚构引用")
