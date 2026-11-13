"""HTTP permission matrix with an exhaustive route inventory.

Read fixtures contain real versions, sessions, imports, materials and instances.
Only external source/agent IMPORT_ROOT/ONTOLOGY_ROOT and unsaved query computations are substituted.
"""

import ast
import inspect
import json
from contextlib import contextmanager
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.routing import APIRoute
from sqlalchemy import create_engine, select

from ontofoundry_api.api.auth import (
    Principal,
    current_principal,
    mcp_principal,
    ontology_directory_principal,
    ontology_principal,
)
from ontofoundry_api.db_models import (
    MetadataSyncJobRecord,
    ModelingSessionRecord,
    ProposalBatchRecord,
    UserRecord,
    WorkspaceMemberRecord,
    WorkspaceRecord,
)
from ontofoundry_api.services.demo import DEMO_CONNECTION_ID, DEMO_WORKSPACE_ID
from ontofoundry_api.services.workspaces import DEV_USER_ID

W = "/api/v1/workspaces/{workspace_id}"
ONTOLOGY_ROOT = "/api/v1/ontology/workspaces/{workspace_id}"
IMPORT_ROOT = "/api/v1/modeling/workspaces/{workspace_id}/imports/{adapter_id}"
E = "/api/v1/modeling/workspaces/{workspace_id}/exports/{adapter_id}"
C = W + "/connections/{connection_id}"
S = W + "/sessions/{session_id}"
A = S + "/agent-conversation"

READS = [
    ("GET", W), ("GET", W + "/overview"), ("GET", W + "/versions"),
    ("GET", W + "/ontology"), ("GET", W + "/published-snapshot"),
    ("GET", W + "/capabilities"), ("GET", W + "/versions/{version_id}/presentation"),
    ("GET", W + "/version-comparison"), ("GET", W + "/sessions"), ("GET", S),
    ("GET", S + "/instances"), ("GET", S + "/instance-baseline"),
    ("GET", S + "/proposal-batches"), ("GET", S + "/proposal-batches/{batch_id}"),
    ("GET", W + "/proposal-metrics"), ("GET", A), ("GET", A + "/events"),
    ("GET", A + "/files/{rel_path:path}"), ("GET", W + "/instances"),
    ("GET", W + "/instances/{kind}/{instance_id}/history"),
    ("GET", W + "/materials"), ("GET", W + "/materials/overview"),
    ("GET", W + "/materials/{material_id}"), ("GET", W + "/connections"),
    ("GET", C + "/tables"), ("GET", C + "/schemas"), ("GET", C + "/assets"),
    ("GET", C + "/assets/synced"), ("GET", C + "/assets/rows"),
    ("GET", C + "/assets/impact"), ("GET", C + "/assets/sync-jobs/{job_id}"),
    ("GET", W + "/registered-tables"), ("GET", IMPORT_ROOT + "/{import_id}"),
    ("GET", E), ("GET", E + "/artifacts/{content_sha256}"),
    ("GET", ONTOLOGY_ROOT + "/version"), ("GET", ONTOLOGY_ROOT + "/types"), ("GET", ONTOLOGY_ROOT + "/types/{type_id}"),
    ("GET", ONTOLOGY_ROOT + "/type-graph/neighborhood"), ("GET", ONTOLOGY_ROOT + "/catalog"),
    ("GET", ONTOLOGY_ROOT + "/types/{type_id}/presentation"),
    ("GET", ONTOLOGY_ROOT + "/types/{type_id}/document-context"), ("GET", ONTOLOGY_ROOT + "/objects"),
    ("GET", ONTOLOGY_ROOT + "/objects/{ref}"), ("GET", ONTOLOGY_ROOT + "/objects/{ref}/neighborhood"),
    ("POST", ONTOLOGY_ROOT + "/search"), ("POST", ONTOLOGY_ROOT + "/entities/resolve"), ("POST", ONTOLOGY_ROOT + "/mcp"),
    ("POST", W + "/instance-neighborhood"), ("POST", C + "/test"),
    ("POST", W + "/mapping-preview"), ("POST", W + "/datasets/validate"),
    ("POST", W + "/datasets/preview"),
    ("POST", "/api/v1/modeling/workspaces/{workspace_id}/metrics/preview"),
    ("POST", W + "/element-saves/preview"), ("POST", S + "/validate"),
    ("POST", S + "/preview"),
]
MANAGE = [("GET", W + "/members"), ("GET", W + "/users/search"),
          ("GET", W + "/settings/dataagent-health"), ("PATCH", W),
          ("POST", W + "/members"), ("PATCH", W + "/members/{member_id}"),
          ("DELETE", W + "/members/{member_id}")]
# Writes that stay admin-only as before this change: connection maintenance
# and material deletion (design UM-08).
MANAGE_WRITES = [("POST", W + "/connections"), ("PATCH", W + "/connections/{connection_id}"),
                 ("DELETE", W + "/connections/{connection_id}"), ("DELETE", W + "/materials/{material_id}")]
# The run endpoint uses a separately signed write credential; no browser session
# can submit through it. GET MCP is a protocol-level 405, not a data read.
SPECIAL = [("POST", ONTOLOGY_ROOT + "/runs/{run_token}/proposals"), ("GET", ONTOLOGY_ROOT + "/mcp")]


def route_key(route):
    return next(iter(route.methods)), route.path


def workspace_routes(client):
    def walk(routes):
        for route in routes:
            if isinstance(route, APIRoute):
                yield route
            elif hasattr(route, "original_router"):
                yield from walk(route.original_router.routes)
    return [r for r in walk(client.app.routes) if "{workspace_id}" in r.path and not r.path.startswith("/api/v1/admin/")]


@pytest.fixture
def matrix(client, monkeypatch):
    wid = str(DEMO_WORKSPACE_ID)
    root = f"/api/v1/workspaces/{wid}"
    draft = client.get(root + "/published-snapshot").json()
    version = client.get(f"/api/v1/ontology/workspaces/{wid}/version").json()["version_id"]
    session = client.post(root + "/sessions", json={"title": "虚构权限矩阵"}).json()
    material = client.post(root + "/materials?name=fiction.txt", content=b"fictional material").json()
    export = client.get(f"/api/v1/modeling/workspaces/{wid}/exports/ontofoundry-core-1?version_id={version}").json()
    raw = client.get(export["download_url"]).content
    imported = client.post(f"/api/v1/modeling/workspaces/{wid}/imports/ontofoundry-core-1?name=fiction.json", content=raw).json()
    bid, job, uid = str(uuid4()), str(uuid4()), str(uuid4())
    with client.app.state.session_factory() as db:
        db.add(UserRecord(id=uid, username="fiction-visitor", display_name="虚构访客"))
        db.add(MetadataSyncJobRecord(id=job, workspace_id=wid, connection_id=DEMO_CONNECTION_ID, scope="all", state="succeeded", schema_name="public", created_by=DEV_USER_ID))
        db.add(ProposalBatchRecord(id=bid, workspace_id=wid, session_id=session["id"], run_token="fiction-run", schema_version="ontofoundry.proposals/v1", base_version_id=version, base_version_sha256="a" * 64, source_session_revision=1, source_draft_sha256="b" * 64, material_manifest_json=[], producer_json={}, result_sha256="c" * 64, status="available"))
        item = db.get(ModelingSessionRecord, session["id"])
        item.dataagent_topic_id = "fiction-topic"
        item.dataagent_task_id = "fiction-task"
        # The terminal task avoids triggering background reconciliation writes.
        item.task_status = "idle"
        db.commit()
    client.app.state.settings.dataagent_base_url = "http://agent.invalid"

    class Agent:
        async def messages(self, *args):
            return []
        async def task(self, *args):
            return {"task_status": "completed"}
        async def stream(self, *args):
            yield b'data: {"seq_id":1}\n\n'
        async def download(self, *args):
            return b"fictional output", "text/plain"

    monkeypatch.setattr("ontofoundry_api.api.agent_conversation._client", lambda *args: Agent())
    source = create_engine("sqlite://")

    @contextmanager
    def connect(*args, **kwargs):
        with source.connect() as conn:
            yield conn

    for module in ("api.assets", "api.connections"):
        monkeypatch.setattr(f"ontofoundry_api.{module}.connect_readonly", connect)
    monkeypatch.setattr("ontofoundry_api.services.metadata_catalog.list_tables", lambda *args: ["fictional_sales"])
    monkeypatch.setattr("ontofoundry_api.api.assets.visible_schemas", lambda *args: ["public"])
    monkeypatch.setattr("ontofoundry_api.services.table_preview.preview_table", lambda *args: {"columns": [], "items": [], "limit": 100})
    # Compute-only endpoints keep their route guards and scope checks; query
    # execution is covered in the existing dataset, metric and instance suites.
    monkeypatch.setattr("ontofoundry_api.api.datasets.check_dataset", lambda *a, **k: {})
    monkeypatch.setattr("ontofoundry_api.api.datasets.preview_dataset", lambda *a, **k: {})
    monkeypatch.setattr("ontofoundry_api.api.metrics.preview_metric", lambda *a, **k: {})
    monkeypatch.setattr("ontofoundry_api.api.connections.query_mapping", lambda *a, **k: {})
    monkeypatch.setattr("ontofoundry_api.api.instances.database_neighborhood", lambda *a, **k: {})
    monkeypatch.setattr("ontofoundry_api.services.entity_resolution.resolve_entity", lambda *a, **k: {})
    instance = client.get(root + "/instances").json()["items"][0]
    objects = client.get(f"/api/v1/ontology/workspaces/{wid}/objects").json()["items"]
    ref = objects[0]["ref"]
    ids = dict(workspace_id=wid, connection_id=DEMO_CONNECTION_ID, version_id=version,
               session_id=session["id"], material_id=material["id"], import_id=imported["import_id"],
               adapter_id="ontofoundry-core-1", content_sha256=export["content_sha256"], batch_id=bid,
               job_id=job, type_id=draft["object_types"][0]["id"], instance_id=instance["target_id"],
               kind="material_object", ref=ref, member_id=99999, user_id=uid, proposal_id=str(uuid4()))
    yield dict(client=client, ids=ids, draft=draft, session=session, uid=uid)
    source.dispose()


def request_options(data, key):
    method, path = key
    ids, draft = data["ids"], data["draft"]
    params = {}
    if path.startswith(E):
        params["version_id"] = ids["version_id"]
    if path.endswith("/version-comparison"):
        params.update(right_id=ids["version_id"])
    if path.endswith(("/presentation", "/document-context")) and "/types/" in path:
        params["kind"] = "object_type"
    if "/connections/" in path:
        params.update(schema_name="public", table_name="fictional_sales")
    bodies = {
        ("POST", ONTOLOGY_ROOT + "/search"): {"query": "销售"},
        ("POST", ONTOLOGY_ROOT + "/entities/resolve"): {"mention": "虚构", "object_type_id": ids["type_id"]},
        ("POST", ONTOLOGY_ROOT + "/mcp"): {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        ("POST", W + "/instance-neighborhood"): {"type_id": ids["type_id"], "key": []},
        ("POST", W + "/datasets/validate"): {"dataset": draft["datasets"][0]},
        ("POST", W + "/datasets/preview"): {"dataset": draft["datasets"][0]},
        ("POST", W + "/mapping-preview"): {"mapping": {"id": str(uuid4()), "type_id": ids["type_id"], "binding_mode": "shared_parent"}},
        ("POST", "/api/v1/modeling/workspaces/{workspace_id}/metrics/preview"): {"metric": draft["metrics"][0]},
        ("POST", W + "/element-saves/preview"): {"target_kind": "object_type", "target_id": ids["type_id"], "expected_current_version_id": ids["version_id"], "draft": draft},
        ("POST", S + "/preview"): {"expected_session_revision": data["session"]["revision"]},
    }
    options = {"params": params}
    if key in bodies:
        options["json"] = bodies[key]
    if path.endswith("/mcp"):
        options["headers"] = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25"}
    return options


def actor(data, role=None, *, admin=False, public=True):
    client, uid, wid = data["client"], data["uid"], data["ids"]["workspace_id"]
    with client.app.state.session_factory() as db:
        db.get(WorkspaceRecord, wid).is_public = public
        member = db.scalar(select(WorkspaceMemberRecord).where(WorkspaceMemberRecord.workspace_id == wid, WorkspaceMemberRecord.user_id == uid))
        if role:
            if member:
                member.role = role
            else:
                db.add(WorkspaceMemberRecord(workspace_id=wid, user_id=uid, role=role))
        elif member:
            db.delete(member)
        db.commit()
    for dependency in (current_principal, ontology_principal, mcp_principal, ontology_directory_principal):
        client.app.dependency_overrides[dependency] = lambda: Principal(uid, "fiction-visitor", "虚构访客", None, is_platform_admin=admin)


def test_every_read_route_public_200_private_denied_and_viewer_200(matrix):
    data = matrix
    for role, public in [(None, True), (None, False), ("viewer", False)]:
        actor(data, role, public=public)
        for key in READS:
            path = key[1].replace("{rel_path:path}", "output/fiction.txt").format(**data["ids"])
            response = data["client"].request(key[0], path, **request_options(data, key))
            if public or role:
                assert response.status_code == 200, (role, key, response.text)
            else:
                assert response.status_code in {403, 404}, (key, response.text)


def minimal(schema, definitions):
    if "$ref" in schema:
        return minimal(definitions[schema["$ref"].split("/")[-1]], definitions)
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if "anyOf" in schema:
        variant = next((s for s in schema["anyOf"] if s.get("type") == "null"), schema["anyOf"][0])
        return minimal(variant, definitions)
    if "oneOf" in schema:
        return minimal(schema["oneOf"][0], definitions)
    kind = schema.get("type")
    if kind == "object":
        value = {name: minimal(schema.get("properties", {}).get(name, {}), definitions) for name in schema.get("required", [])}
        if schema.get("minProperties") and not value:
            value["name"] = "fictional"
        return value
    if kind == "array":
        return [minimal(schema["items"], definitions) for _ in range(schema.get("minItems", 0))]
    if kind in {"integer", "number"}:
        return schema.get("minimum", 0)
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    if schema.get("format") == "uuid":
        return str(uuid4())
    if schema.get("pattern") == "^[0-9a-f]{64}$":
        return "a" * 64
    return "fictional" + "a" * schema.get("minLength", 0)


def test_every_write_route_denies_nonmembers_and_viewers_allows_editors_and_platform_admins(matrix, monkeypatch):
    data, client = matrix, matrix["client"]
    routes = workspace_routes(client)
    writes = [r for r in routes if route_key(r) not in READS + MANAGE + SPECIAL]
    assert writes
    for role, admin in [(None, False), ("viewer", False), ("member", False), (None, True)]:
        actor(data, role, admin=admin)
        for route in writes:
            key = route_key(route)
            # Missing resource ids let allowed requests reach normal business
            # validation without mutating the fixtures used by later routes.
            ids = {**data["ids"], "session_id": str(uuid4()), "connection_id": str(uuid4()), "material_id": str(uuid4()), "import_id": str(uuid4())}
            path = route.path.format(**ids)
            options = {"params": {"name": "fiction.txt", "schema_name": "public", "table_name": "fictional_sales"}}
            if route.body_field:
                schema = route.body_field._type_adapter.json_schema()
                options["json"] = minimal(schema, schema.get("$defs", {}))
                if key[1].endswith("/dataset"):
                    options["json"]["dataset"] = data["draft"]["datasets"][0]
                if key == ("POST", W + "/connections"):
                    options["json"].update(kind="postgresql", database="fictional", port=5432)
                if key[1].startswith(IMPORT_ROOT):
                    options["params"] = {"name": "fiction.json"}
            response = client.request(key[0], path, **options)
            if (role in {None, "viewer"} or (role == "member" and key in MANAGE_WRITES)) and not admin:
                assert response.status_code == 403, (role, key, response.text)
            else:
                assert response.status_code not in {401, 403}, (role, admin, key, response.text)


def test_route_inventory_cannot_silently_omit_new_workspace_endpoints(client):
    actual = {route_key(r) for r in workspace_routes(client)}
    assert set(READS + MANAGE + MANAGE_WRITES + SPECIAL) <= actual
    # Every non-special route must declare a shared gate as its first statement.
    for route in workspace_routes(client):
        key = route_key(route)
        if key in SPECIAL:
            continue
        node = ast.parse(inspect.getsource(route.endpoint)).body[0]
        statements = [s for s in node.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str))]
        call = statements[0].value
        assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
        expected = "require_manage" if key in MANAGE + MANAGE_WRITES else "require_read" if key in READS else "require_edit"
        assert call.func.id == expected, (key, call.func.id, expected)


def test_visibility_directory_cache_revocation_and_platform_superuser(matrix):
    data, client = matrix, matrix["client"]
    wid = data["ids"]["workspace_id"]
    path = W.format(workspace_id=wid)
    actor(data, public=True)
    summary = client.get(path)
    assert summary.json()["role"] is None and summary.json()["visibility"] == "public"
    actor(data, public=False)
    denied = client.get(path, headers={"If-None-Match": summary.headers["etag"]})
    assert denied.status_code == 404 and denied.json()["error"]["code"] == "WORKSPACE_NOT_FOUND"
    # A configured admin's access derives from current config, not membership.
    client.app.dependency_overrides.clear()
    with client.app.state.session_factory() as db:
        member = db.scalar(select(WorkspaceMemberRecord).where(WorkspaceMemberRecord.workspace_id == wid, WorkspaceMemberRecord.user_id == DEV_USER_ID))
        db.delete(member)
        db.commit()
    assert any(s["id"] == wid for s in client.get("/api/v1/workspaces").json()["items"])
    assert any(s["id"] == wid for s in client.get("/api/v1/ontology/workspaces").json()["items"])
    assert client.get(path).json()["role"] == "admin"
    assert client.patch(path, json={"is_public": True}).status_code == 200
    actor(data, public=True)
    assert any(s["id"] == wid for s in client.get("/api/v1/ontology/workspaces").json()["items"])


def test_manage_routes_deny_editors_viewers_and_public_readers(matrix, monkeypatch):
    data, client = matrix, matrix["client"]

    async def health(*args):
        return {"status": "ok"}

    monkeypatch.setattr("ontofoundry_api.api.settings.dataagent_health", health)
    for role, admin in [(None, False), ("viewer", False), ("member", False), ("admin", False), (None, True)]:
        actor(data, role, admin=admin)
        for method, template in MANAGE:
            path = template.format(**data["ids"])
            body = {"name": "星港销售"} if method == "PATCH" and template == W else {"role": "viewer", "user_id": data["uid"]} if method == "POST" else {"role": "viewer"} if method == "PATCH" else None
            response = client.request(method, path, json=body)
            if admin or role == "admin":
                assert response.status_code not in {401, 403}, (method, template, response.text)
            else:
                assert response.status_code == 403, (role, method, template, response.text)


def test_public_workspace_does_not_override_service_token_scopes(matrix):
    from ontofoundry_api.services.access import can_read_instances, can_read_mappings
    from ontofoundry_api.services.mcp_ontology import invoke

    data, client = matrix, matrix["client"]
    actor(data, public=True)
    wid = data["ids"]["workspace_id"]
    low = Principal(data["uid"], "fiction-visitor", "虚构访客", None, service_token_id="fiction-token", scopes=frozenset({"ontology:read"}))
    with client.app.state.session_factory() as db:
        assert not can_read_mappings(db, wid, low)
        assert not can_read_instances(db, wid, low)
        semantic = invoke(db, wid, low, "get_ontology", {"include": ["semantic", "physical"]}, client.app.state.settings)
        assert "fictional_sales" not in json.dumps(semantic)
        high = replace(low, scopes=frozenset({"ontology:read", "mappings:read", "instances:read"}))
        assert can_read_mappings(db, wid, high) and can_read_instances(db, wid, high)
        physical = invoke(db, wid, high, "get_ontology", {"ids": [e["id"] for e in semantic["elements"]], "include": ["semantic", "physical"]}, client.app.state.settings)
        assert "fictional_sales" in json.dumps(physical)
