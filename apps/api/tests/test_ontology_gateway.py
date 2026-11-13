"""Cross-workspace tools, live permissions, limits, pagination and version metadata."""

import json
from uuid import uuid4

import pytest
from gateway_helpers import (
    GATEWAY,
    META,
    TOKENS,
    VERSIONS,
    WID,
    call,
    rpc,
    set_role,
    space,
    token,
    user,
)
from sqlalchemy import event
from test_modeling import create_session, publish, save

from ontofoundry_api.db_models import OntologyVersionRecord, WorkspaceRecord
from ontofoundry_api.services import ontology_gateway
from ontofoundry_api.services.errors import ServiceError


def test_tools_schemas_instructions_and_annotations(client):
    credential = token(client)["token"]
    result = rpc(client, credential, "tools/list").json()["result"]
    assert {tool["name"] for tool in result["tools"]} == set(ontology_gateway.INPUTS)
    for tool in result["tools"]:
        assert tool["inputSchema"] == ontology_gateway.INPUTS[tool["name"]].model_json_schema()
        assert tool["annotations"] == {"readOnlyHint": tool["name"] != "submit_feedback", "destructiveHint": False}
    init = rpc(client, credential, "initialize", {"protocolVersion": "2025-06-18", "clientInfo": {}, "capabilities": {}})
    assert init.json()["result"]["protocolVersion"] == "2025-06-18"
    assert "DataAgent" not in init.text
    assert "客户端自己的查询工具" in init.json()["result"]["instructions"]
    discover = rpc(client, credential, "server/discover").json()["result"]
    assert discover["instructions"] == init.json()["result"]["instructions"]


@pytest.mark.parametrize("role", ["admin", "member", "viewer"])
def test_members_all_read_and_list_role(client, role):
    user(client, role=role)
    credential = token(client)["token"]
    listed = call(client, credential, "list_spaces")
    spaces = listed["structuredContent"]["spaces"]
    assert len(spaces) == 1 and spaces[0]["role"] == role
    assert spaces[0]["workspace_id"] == WID
    assert listed["structuredContent"]["permissions"] == ["ontology:read"]
    assert listed["_meta"][VERSIONS] == [{"workspace_id": WID, "version_id": spaces[0]["version_id"], "version_number": 1}]
    result = call(client, credential, "search_ontology", {"query": "订单"})
    assert not result["isError"]
    assert result["structuredContent"]["groups"][0]["workspace_id"] == WID


def test_public_reader_and_default_membership_scope(client):
    principal = user(client, public=True)
    credential = token(client)["token"]
    result = call(client, credential, "list_spaces")["structuredContent"]
    assert result["spaces"][0]["role"] == "public"
    assert call(client, credential, "search_ontology", {"query": "订单"})["structuredContent"] == {"groups": []}
    explicit = call(client, credential, "search_ontology", {"query": "订单", "workspace_ids": [WID]})
    assert explicit["structuredContent"]["groups"][0]["items"]
    assert not call(client, credential, "get_ontology", {"workspace_id": WID})["isError"]
    set_role(client, principal, "viewer")
    assert call(client, credential, "list_spaces")["structuredContent"]["spaces"][0]["role"] == "viewer"
    set_role(client, principal, None)
    with client.app.state.session_factory() as db:
        db.get(WorkspaceRecord, WID).is_public = False
        db.commit()
    assert call(client, credential, "list_spaces")["structuredContent"]["spaces"] == []
    assert call(client, credential, "get_ontology", {"workspace_id": WID})["structuredContent"]["code"] == "workspace_unavailable"


def test_platform_admin_without_membership_is_listed_but_not_default_searched(client):
    user(client, platform_admin=True)
    credential = token(client)["token"]
    listed = call(client, credential, "list_spaces")["structuredContent"]["spaces"]
    assert listed[0]["role"] == "admin"
    assert call(client, credential, "search_ontology", {"query": "订单"})["structuredContent"] == {"groups": []}
    assert not call(client, credential, "get_ontology", {"workspace_id": WID})["isError"]


def test_multiple_workspaces_sorted_and_live_membership_changes(client):
    principal = user(client, role="viewer")
    credential = token(client)["token"]
    other = space(client, "云帆采购", member_id=principal.id)
    space(client, "远星公开", public=True)
    result = call(client, credential, "search_ontology", {"query": "订单"})
    assert [g["workspace_id"] for g in result["structuredContent"]["groups"]] == [other, WID]
    assert len(result["_meta"][VERSIONS]) == 2
    set_role(client, principal, None)
    assert [g["workspace_id"] for g in call(client, credential, "search_ontology", {"query": "订单"})["structuredContent"]["groups"]] == [other]
    assert len(call(client, credential, "list_spaces")["structuredContent"]["spaces"]) == 2


def test_unavailable_workspace_aborts_entire_search(client):
    user(client, role="viewer")
    credential = token(client)["token"]
    private = space(client, "虚构私有")
    for unavailable in (private, str(uuid4()), "fiction-missing"):
        denied = call(client, credential, "get_ontology", {"workspace_id": unavailable})
        assert denied["structuredContent"]["code"] == "workspace_unavailable"
        result = call(client, credential, "search_ontology", {"query": "订单", "workspace_ids": [WID, unavailable]})
        assert result["isError"] and result["structuredContent"] == {"code": "workspace_unavailable", "message": "空间不存在或不可阅读"}
        assert "groups" not in result["structuredContent"]
        assert result["_meta"][VERSIONS][0]["workspace_id"] == WID


def test_workspace_limit_default_and_explicit(client):
    principal = user(client, role="viewer")
    credential = token(client)["token"]
    ids = [WID, *[space(client, f"虚构采购{i}", member_id=principal.id) for i in range(10)]]
    for options in ({}, {"workspace_ids": ids}):
        result = call(client, credential, "search_ontology", {"query": "订单", **options})
        assert result["structuredContent"] == {"code": "search_limit_exceeded", "message": "检索空间超过上限，请缩小空间范围", "reason": "workspace_count", "limit": 10}
    allowed = call(client, credential, "search_ontology", {"query": "订单", "workspace_ids": ids[:10]})
    assert len(allowed["structuredContent"]["groups"]) == 10


def test_aggregate_response_budget_and_single_workspace_failure(client, monkeypatch):
    credential = token(client)["token"]
    other = space(client, "虚构采购")
    def big(db, wid, principal, name, args, settings):
        return {"workspace_id": wid, "items": [{"summary": "x" * 55_000}]}
    monkeypatch.setattr(ontology_gateway, "read_tool", big)
    result = call(client, credential, "search_ontology", {"query": "", "workspace_ids": [WID, other]})
    assert result["isError"] and result["structuredContent"]["reason"] == "response_size"
    assert "groups" not in result["structuredContent"]
    def fail(*args):
        raise ServiceError("单页超过预算", code="response_too_large")
    monkeypatch.setattr(ontology_gateway, "read_tool", fail)
    result = call(client, credential, "search_ontology", {"query": "", "workspace_ids": [WID]})
    assert result["structuredContent"]["code"] == "response_too_large"
    assert result["_meta"][VERSIONS][0]["workspace_id"] == WID


def test_search_continuation_uses_one_group_and_original_parameters(client):
    credential = token(client)["token"]
    other = space(client, "虚构采购")
    args = {"query": "", "limit": 1, "expand": False}
    first = call(client, credential, "search_ontology", {**args, "workspace_ids": [WID, other]})
    group = next(g for g in first["structuredContent"]["groups"] if g["workspace_id"] == WID)
    assert group["next_cursor"]
    second = call(client, credential, "search_ontology", {**args, "workspace_ids": [WID], "cursor": group["next_cursor"]})
    assert not second["isError"] and second["structuredContent"]["groups"][0]["items"] != group["items"]
    bad = call(client, credential, "search_ontology", {**args, "workspace_ids": [WID, other], "cursor": group["next_cursor"]})
    assert bad["structuredContent"]["code"] == "invalid_arguments"


@pytest.mark.parametrize("name,args,key", [
    ("get_ontology", {"workspace_id": WID, "limit": 1}, "elements"),
    ("search_ontology", {"workspace_ids": [WID], "query": "", "limit": 1}, "items"),
])
def test_cursor_invalidated_by_token_permissions_membership_and_other_token(client, name, args, key):
    principal = user(client, role="viewer")
    item = token(client, ["ontology:read", "mappings:read"])
    first = call(client, item["token"], name, args)["structuredContent"]
    page = first["groups"][0] if name == "search_ontology" else first
    cursor = page["next_cursor"]
    assert cursor and page[key]
    other = token(client, ["ontology:read", "mappings:read"])
    assert call(client, other["token"], name, {**args, "cursor": cursor})["structuredContent"]["code"] == "cursor_invalid"
    set_role(client, principal, "member")
    assert call(client, item["token"], name, {**args, "cursor": cursor})["structuredContent"]["code"] == "cursor_invalid"
    set_role(client, principal, "viewer")
    assert client.patch(TOKENS + "/" + item["id"], json={"permissions": ["ontology:read"]}).status_code == 200
    assert call(client, item["token"], name, {**args, "cursor": cursor})["structuredContent"]["code"] == "cursor_invalid"
    assert not call(client, item["token"], name, args)["isError"]


def test_new_publication_invalidates_cursor_and_updates_meta(client):
    credential = token(client)["token"]
    first = call(client, credential, "get_ontology", {"workspace_id": WID, "limit": 1})
    cursor = first["structuredContent"]["next_cursor"]
    session = create_session(client)
    session["draft"]["object_types"][0]["description"] = "虚构新版定义"
    assert publish(client, save(client, session, session["draft"]).json()).status_code == 200
    result = call(client, credential, "get_ontology", {"workspace_id": WID, "limit": 1, "cursor": cursor})
    assert result["structuredContent"]["code"] == "cursor_invalid"
    assert result["_meta"][VERSIONS][0]["version_number"] == 2
    assert result["_meta"][VERSIONS][0]["version_id"] != first["_meta"][VERSIONS][0]["version_id"]


def test_mapping_projections_follow_current_token_permissions(client):
    user(client, role="viewer")
    item = token(client, ["ontology:read", "mappings:read"])
    with client.app.state.session_factory() as db:
        version = db.get(OntologyVersionRecord, db.get(WorkspaceRecord, WID).current_version_id)
        ids = [e["id"] for e in version.snapshot_json["datasets"] + version.snapshot_json["metrics"]]
    args = {"workspace_id": WID, "ids": ids, "include": ["semantic", "physical"]}
    allowed = call(client, item["token"], "get_ontology", args)["structuredContent"]
    assert any(e.get("sql_reference") for e in allowed["elements"])
    assert any(e["kind"] == "dataset" and e.get("definition") for e in allowed["elements"])
    assert client.patch(TOKENS + "/" + item["id"], json={"permissions": ["ontology:read"]}).status_code == 200
    denied = call(client, item["token"], "get_ontology", args)["structuredContent"]
    assert all("sql_reference" not in e and "definition" not in e for e in denied["elements"])
    assert not any(e["kind"] == "dataset" for e in denied["elements"])
    assert "connection_id" not in json.dumps(allowed)


@pytest.mark.parametrize("legacy", ["2025-03-26", "2025-06-18", "2025-11-25", None])
def test_meta_on_success_unpublished_and_errors_for_all_protocols(client, legacy):
    credential = token(client)["token"]
    unpublished = space(client, "虚构未发布")
    for name, args in [
        ("list_spaces", {}), ("search_ontology", {"query": ""}),
        ("get_ontology", {"workspace_id": unpublished}),
        ("get_ontology", {"workspace_id": WID, "cursor": "invalid"}),
        ("get_ontology", {"workspace_id": str(uuid4())}),
        ("submit_feedback", {"workspace_id": unpublished, "kind": "suggestion", "user_text": "增加定义", "agent_text": "建议补充定义"}),
    ]:
        result = call(client, credential, name, args, legacy=legacy)
        assert META + "serverInfo" in result["_meta"]
        assert VERSIONS in result["_meta"]
        if args.get("workspace_id") == unpublished:
            assert result["_meta"][VERSIONS] == [{"workspace_id": unpublished, "version_id": None, "version_number": None}]


def test_directory_never_reads_version_snapshots(client):
    credential = token(client)["token"]
    statements = []
    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)
    event.listen(client.app.state.engine, "before_cursor_execute", capture)
    try:
        assert not call(client, credential, "list_spaces")["isError"]
    finally:
        event.remove(client.app.state.engine, "before_cursor_execute", capture)
    assert not any("snapshot_json" in statement for statement in statements)


def test_gateway_reuses_rpc_header_and_size_validation(client):
    credential = token(client)["token"]
    headers = {"Authorization": "Bearer " + credential, "Accept": "application/json, text/event-stream"}
    assert client.post(GATEWAY, headers=headers, content=b"x" * 262145).status_code == 413
    assert client.post(GATEWAY, headers=headers, content=b"{").json()["error"]["code"] == -32700
    assert client.post(GATEWAY, headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).json()["error"]["code"] == -32020
    result = rpc(client, credential, params={"name": "unknown", "arguments": {}})
    assert result.json()["error"]["code"] == -32602
    assert client.post(GATEWAY, headers=headers, json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
