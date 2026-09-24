import base64
import binascii
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from jsonschema import ValidationError, validate
from pydantic import ValidationError as ModelValidationError
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, ontology_principal
from ontofoundry_api.database import get_db
from ontofoundry_api.services.access import (
    can_read_instances,
    can_read_mappings,
    require_instances,
)
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.instance_query import (
    ObjectSearch,
    get_object,
    object_neighborhood,
    search_objects,
)
from ontofoundry_api.services.ontology_query import (
    current_version,
    get_type,
    search_types,
    type_graph,
    version_summary,
)

router = APIRouter(prefix="/api/v1/ontology/workspaces/{workspace_id}/mcp", tags=["mcp"])
PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
)
META = "io.modelcontextprotocol/"
INSTRUCTIONS = (
    "Read published ontology versions. Mapping metadata requires mappings:read or "
    "instances:read; instance tools require instances:read. Both require workspace "
    "membership. Database rows are live; modeling and raw materials are not exposed."
)
TOOLS = [
    ("get_ontology_version", "读取当前已发布本体版本", {}),
    ("search_ontology_types", "搜索已发布业务对象和关系", {"query": {"type": "string"}}),
    ("get_ontology_type", "读取业务对象或关系定义", {"type_id": {"type": "string"}}),
    (
        "get_ontology_graph",
        "读取已发布的语义图谱",
        {
            "focus_id": {"type": "string"},
            "depth": {"type": "integer", "minimum": 1, "maximum": 3},
        },
    ),
    ("export_ontology", "读取官方 Ossie JSON", {}),
    (
        "search_objects",
        "搜索已发布文档实例或按已发布映射查询数据库实例",
        {
            "type_id": {"type": "string", "format": "uuid"},
            "source": {"type": "string", "enum": ["document", "database"]},
            "q": {"type": "string", "maxLength": 240},
            "cursor": {"type": "string", "maxLength": 4000},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        },
    ),
    (
        "get_object",
        "读取实例属性、来源与证据",
        {"ref": {"type": "string", "maxLength": 4000}},
    ),
    (
        "expand_object_graph",
        "展开实例关系邻域（最多三跳）",
        {
            "ref": {"type": "string", "maxLength": 4000},
            "depth": {"type": "integer", "minimum": 1, "maximum": 3},
        },
    ),
]
INSTANCE_TOOLS = {"search_objects", "get_object", "expand_object_graph"}


def rpc_error(rid, code, message, status=400, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    body = {"jsonrpc": "2.0", "error": error}
    if rid is not None:
        body["id"] = rid
    return JSONResponse(body, status_code=status)


def tool_schema(name, properties):
    return {
        "type": "object",
        "properties": {**properties, "version_id": {"type": "string"}},
        "required": ["type_id"]
        if name == "get_ontology_type"
        else ["ref"]
        if name in ("get_object", "expand_object_graph")
        else [],
        "additionalProperties": False,
    }


def legacy_initialize(rid, params):
    requested = params.get("protocolVersion")
    if (
        not isinstance(requested, str)
        or not isinstance(params.get("capabilities"), dict)
        or not isinstance(params.get("clientInfo"), dict)
    ):
        return rpc_error(rid, -32602, "Invalid initialize params")
    negotiated = (
        requested
        if requested in LEGACY_PROTOCOL_VERSIONS
        else LEGACY_PROTOCOL_VERSIONS[0]
    )
    return {
        "jsonrpc": "2.0",
        "id": rid,
        "result": {
            "protocolVersion": negotiated,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "ontofoundry", "version": "0.1.0"},
            "instructions": INSTRUCTIONS,
        },
    }


@router.post("")
async def rpc(
    workspace_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(ontology_principal),
):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 262144:
            return rpc_error(None, -32600, "Request exceeds 256 KB", 413)
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError):
        return rpc_error(None, -32700, "Parse error")
    if (
        not isinstance(body, dict)
        or body.get("jsonrpc") != "2.0"
        or not isinstance(body.get("method"), str)
    ):
        return rpc_error(None, -32600, "Invalid Request")
    if "id" not in body:
        return Response(status_code=202)
    rid, method, params = body["id"], body["method"], body.get("params", {})
    if isinstance(rid, bool) or not isinstance(rid, (str, int)):
        return rpc_error(None, -32600, "Request ID must be a string or integer")
    if not isinstance(params, dict):
        return rpc_error(rid, -32602, "Invalid params")
    header_version = request.headers.get("mcp-protocol-version")
    accept = request.headers.get("accept", "")
    legacy = header_version in LEGACY_PROTOCOL_VERSIONS
    if (
        method == "initialize"
        and header_version != PROTOCOL_VERSION
        and request.headers.get("mcp-method") is None
    ):
        if "application/json" not in accept or "text/event-stream" not in accept:
            return rpc_error(
                rid,
                -32600,
                "Accept must include application/json and text/event-stream",
                406,
            )
        return legacy_initialize(rid, params)
    if legacy:
        if request.headers.get("mcp-method") not in (None, method):
            return rpc_error(rid, -32020, "Mcp-Method does not match request method")
    else:
        metadata = params.get("_meta", {})
        if not isinstance(metadata, dict):
            return rpc_error(rid, -32602, "Invalid request metadata")
        if not header_version or request.headers.get("mcp-method") != method:
            return rpc_error(
                rid, -32020, "Missing or mismatched protocol/method headers"
            )
        if header_version != metadata.get(META + "protocolVersion"):
            return rpc_error(
                rid, -32020, "Protocol version header does not match request metadata"
            )
        if header_version != PROTOCOL_VERSION:
            return rpc_error(
                rid,
                -32022,
                "Unsupported protocol version",
                data={"supported": [PROTOCOL_VERSION], "requested": header_version},
            )
        if not isinstance(metadata.get(META + "clientCapabilities"), dict):
            return rpc_error(
                rid, -32602, "Required clientCapabilities metadata is missing"
            )
    if "application/json" not in accept or "text/event-stream" not in accept:
        return rpc_error(
            rid, -32600, "Accept must include application/json and text/event-stream", 406
        )
    if method == "tools/call":
        header_name = request.headers.get("mcp-name", "")
        if header_name.startswith("=?base64?") and header_name.endswith("?="):
            try:
                header_name = base64.b64decode(header_name[9:-2], validate=True).decode(
                    "utf-8"
                )
            except (ValueError, UnicodeError, binascii.Error):
                return rpc_error(rid, -32020, "Malformed Mcp-Name header")
        if (not legacy and not header_name) or (
            header_name and header_name != params.get("name")
        ):
            return rpc_error(rid, -32020, "Mcp-Name does not match tool name")
    if method == "server/discover":
        result = {
            "supportedVersions": [PROTOCOL_VERSION],
            "capabilities": {"tools": {}},
            "instructions": INSTRUCTIONS,
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": n,
                    "description": d,
                    "inputSchema": tool_schema(n, p),
                    "annotations": {"readOnlyHint": True, "destructiveHint": False},
                }
                for n, d, p in TOOLS
                if n not in INSTANCE_TOOLS
                or can_read_instances(db, workspace_id, principal)
            ]
        }
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {})
        schema = next((tool_schema(n, p) for n, _, p in TOOLS if n == name), None)
        if schema is None:
            return rpc_error(rid, -32602, "Unknown tool")
        try:
            validate(args, schema)
        except ValidationError as exc:
            return rpc_error(rid, -32602, exc.message)
        try:
            if name in INSTANCE_TOOLS:
                require_instances(db, workspace_id, principal)
            version = current_version(db, workspace_id, args.get("version_id"))
            if name == "get_ontology_version":
                value = version_summary(version)
            elif name == "search_ontology_types":
                value = search_types(version, query=args.get("query", ""))
            elif name == "get_ontology_type":
                value = get_type(version, args["type_id"])
            elif name == "get_ontology_graph":
                value = type_graph(
                    version, focus_id=args.get("focus_id"), depth=args.get("depth", 1)
                )
            elif name == "search_objects":
                value = search_objects(
                    db,
                    version,
                    ObjectSearch(**{k: v for k, v in args.items() if k != "version_id"}),
                    request.app.state.settings,
                )
            elif name == "get_object":
                value = get_object(db, version, args["ref"], request.app.state.settings)
            elif name == "expand_object_graph":
                value = object_neighborhood(
                    db,
                    version,
                    args["ref"],
                    args.get("depth", 1),
                    request.app.state.settings,
                )
            else:
                mappings_allowed = can_read_mappings(db, workspace_id, principal)
                value = {
                    key: value
                    for key, value in version.ossie_json.items()
                    if key != "ontology_mappings"
                    or mappings_allowed
                }
                if not mappings_allowed and "ontology_mappings" in version.ossie_json:
                    value["redacted_fields"] = ["ontology_mappings"]
            structured = jsonable_encoder(value)
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(structured, ensure_ascii=False),
                    }
                ],
                "structuredContent": structured,
                "isError": False,
            }
        except (ServiceError, ValueError, HTTPException, ModelValidationError) as exc:
            detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
            result = {
                "content": [
                    {"type": "text", "text": json.dumps(detail, ensure_ascii=False)}
                ],
                "isError": True,
            }
    else:
        return rpc_error(
            rid, -32601, "Method not found; supported protocol: " + PROTOCOL_VERSION, 404
        )
    response_result = result if legacy else {
        **result,
        "resultType": "complete",
        "_meta": {META + "serverInfo": {"name": "ontofoundry", "version": "0.1.0"}},
    }
    return {
        "jsonrpc": "2.0",
        "id": rid,
        "result": response_result,
    }


@router.get("", status_code=405)
def no_sse():
    return {"detail": "此服务使用 MCP 2026-07-28 请求级 HTTP JSON，不提供独立 SSE 流"}
