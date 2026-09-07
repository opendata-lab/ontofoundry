import base64
import binascii
import json

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from jsonschema import ValidationError, validate
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, ontology_principal
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import OntologyVersionRecord
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.ontology_query import (
    current_version,
    get_type,
    search_types,
    type_graph,
    version_summary,
)

router = APIRouter(prefix="/api/v1/ontology/workspaces/{workspace_id}/mcp", tags=["mcp"])
PROTOCOL_VERSION = "2026-07-28"
META = "io.modelcontextprotocol/"
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
]


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
        "required": ["type_id"] if name == "get_ontology_type" else [],
        "additionalProperties": False,
    }


@router.post("")
async def rpc(
    workspace_id: str,
    request: Request,
    db: Session = Depends(get_db),
    _: Principal = Depends(ontology_principal),
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
    metadata = params.get("_meta", {})
    if not isinstance(metadata, dict):
        return rpc_error(rid, -32602, "Invalid request metadata")
    header_version = request.headers.get("mcp-protocol-version")
    if not header_version or request.headers.get("mcp-method") != method:
        return rpc_error(rid, -32020, "Missing or mismatched protocol/method headers")
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
        return rpc_error(rid, -32602, "Required clientCapabilities metadata is missing")
    accept = request.headers.get("accept", "")
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
        if not header_name or header_name != params.get("name"):
            return rpc_error(rid, -32020, "Mcp-Name does not match tool name")
    if method == "server/discover":
        result = {
            "supportedVersions": [PROTOCOL_VERSION],
            "capabilities": {"tools": {}},
            "instructions": "Read published ontology only. Modeling, materials and database instances are not exposed by these tools.",
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
            version = (
                db.get(OntologyVersionRecord, args["version_id"])
                if args.get("version_id")
                else current_version(db, workspace_id)
            )
            if not version or version.workspace_id != workspace_id:
                raise ValueError("Published version not found in this workspace")
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
            else:
                value = version.ossie_json
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(value, ensure_ascii=False, default=str),
                    }
                ],
                "isError": False,
            }
        except (ServiceError, ValueError) as exc:
            result = {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    else:
        return rpc_error(
            rid, -32601, "Method not found; supported protocol: " + PROTOCOL_VERSION, 404
        )
    return {
        "jsonrpc": "2.0",
        "id": rid,
        "result": {
            **result,
            "resultType": "complete",
            "_meta": {META + "serverInfo": {"name": "ontofoundry", "version": "0.1.0"}},
        },
    }


@router.get("", status_code=405)
def no_sse():
    return {"detail": "此服务使用 MCP 2026-07-28 请求级 HTTP JSON，不提供独立 SSE 流"}
