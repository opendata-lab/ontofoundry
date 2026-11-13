"""Shared fictional users and request helpers for gateway tests."""

import json
from dataclasses import replace
from uuid import uuid4

from sqlalchemy import select

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.db_models import UserRecord, WorkspaceMemberRecord, WorkspaceRecord
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

GATEWAY = "/api/v1/ontology/mcp"
TOKENS = "/api/v1/auth/tokens"
WID = str(DEMO_WORKSPACE_ID)
VERSIONS = "io.github.opendata-lab.ontofoundry/versions"
META = "io.modelcontextprotocol/"


def user(client, *, role=None, public=False, platform_admin=False):
    identity = str(uuid4())
    with client.app.state.session_factory() as db:
        db.add(UserRecord(id=identity, username="fiction-" + identity, display_name="虚构用户"))
        db.get(WorkspaceRecord, WID).is_public = public
        if role:
            db.add(WorkspaceMemberRecord(workspace_id=WID, user_id=identity, role=role))
        db.commit()
    principal = Principal(identity, "fiction-" + identity, "虚构用户", None, is_platform_admin=platform_admin)
    client.app.dependency_overrides[current_principal] = lambda: principal
    if platform_admin:
        config = client.app.state.auth_config
        client.app.state.auth_config = replace(config, admin_users=(*config.admin_users, principal.username))
    return principal


def token(client, permissions=None):
    response = client.post(TOKENS, json={"name": "虚构客户端", "permissions": permissions or ["ontology:read"]})
    assert response.status_code == 201, response.text
    return response.json()


def rpc(client, credential, method="tools/call", params=None, *, legacy=None, request_id=7):
    params = dict(params or {})
    headers = {"Accept": "application/json, text/event-stream"}
    if credential is not None:
        headers["Authorization"] = "Bearer " + credential
    if legacy:
        headers["MCP-Protocol-Version"] = legacy
    elif method != "initialize":
        headers |= {"MCP-Protocol-Version": "2026-07-28", "Mcp-Method": method}
        params["_meta"] = {META + "protocolVersion": "2026-07-28", META + "clientCapabilities": {}}
        if method == "tools/call":
            headers["Mcp-Name"] = params.get("name", "")
    return client.post(GATEWAY, headers=headers, json={"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})


def call(client, credential, name, arguments=None, **options):
    response = rpc(client, credential, params={"name": name, "arguments": arguments or {}}, **options)
    assert response.status_code == 200, response.text
    result = response.json()["result"]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    return result


def set_role(client, principal, role):
    with client.app.state.session_factory() as db:
        member = db.scalar(select(WorkspaceMemberRecord).where(WorkspaceMemberRecord.workspace_id == WID, WorkspaceMemberRecord.user_id == principal.id))
        if member is not None:
            if role:
                member.role = role
            else:
                db.delete(member)
        elif role:
            db.add(WorkspaceMemberRecord(workspace_id=WID, user_id=principal.id, role=role))
        db.commit()


def principal_admin(client, principal):
    client.app.dependency_overrides[current_principal] = lambda: replace(principal, is_platform_admin=True)


def space(client, name, *, member_id=None, role="viewer", public=False):
    from ontofoundry_api.services.workspaces import DEV_USER_ID

    identity = str(uuid4())
    with client.app.state.session_factory() as db:
        db.add(WorkspaceRecord(id=identity, name=name, slug="fiction-" + identity, created_by=DEV_USER_ID, is_public=public))
        db.flush()
        if member_id:
            db.add(WorkspaceMemberRecord(workspace_id=identity, user_id=member_id, role=role))
        db.commit()
    return identity


def wait_for(check, *, timeout=4):
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.01)
    raise AssertionError("后台记录未在限定时间内完成")


def recorded(client, count=1, *, outcomes=None):
    from ontofoundry_api.db_models import OntologyGatewayCallRecord

    def read():
        with client.app.state.session_factory() as db:
            rows = list(db.scalars(select(OntologyGatewayCallRecord).order_by(OntologyGatewayCallRecord.created_at)))
            if len(rows) >= count and (outcomes is None or [r.outcome for r in rows] == outcomes):
                return rows
    return wait_for(read)
