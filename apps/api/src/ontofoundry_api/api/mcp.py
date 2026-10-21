import base64
import binascii
import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError as ModelValidationError
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, mcp_principal
from ontofoundry_api.database import get_db
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.mcp_ontology import INPUTS, invoke

router = APIRouter(prefix="/api/v1/ontology/workspaces/{workspace_id}/mcp", tags=["mcp"])
PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
)
META = "io.modelcontextprotocol/"
INSTRUCTIONS = (
    "只读核心本体和已接受的文档事实；数据库聚合由 DataAgent 自有查询工具执行。"
    "元素 name 是必填英文标识，display_name 是可选中文名称，空时显示 name；"
    "写提案以 definition 和本轮 proposal Schema 为准。"
)
TOOLS = {
    "search_ontology": "按名称、英文标识和同义词搜索核心语义；kinds 可选 object_type、property、link_type、rule、metric、dataset、value_type",
    "get_ontology": "读取核心定义、继承及授权物理投影；数据集含来源方式、表位置或 SQL、列和被引用元素，值类型含基础类型、约束和使用属性",
    "search_objects": "按事实 UUID 分页搜索已接受的文档事实",
    "get_object": "读取文档事实、证据与直接邻接",
}


def rpc_error(rid, code, message, status=400, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    body = {"jsonrpc": "2.0", "error": error}
    if rid is not None:
        body["id"] = rid
    return JSONResponse(body, status_code=status)


def tool_schema(name):
    return INPUTS[name].model_json_schema()


def legacy_initialize(rid, params):
    requested = params.get("protocolVersion")
    if (
        not isinstance(requested, str)
        or not isinstance(params.get("capabilities"), dict)
        or not isinstance(params.get("clientInfo"), dict)
    ):
        return rpc_error(rid, -32602, "Invalid initialize params")
    negotiated = (
        requested if requested in LEGACY_PROTOCOL_VERSIONS else LEGACY_PROTOCOL_VERSIONS[0]
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
    principal: Principal = Depends(mcp_principal),
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
                    "inputSchema": tool_schema(n),
                    "annotations": {"readOnlyHint": True, "destructiveHint": False},
                }
                for n, d in TOOLS.items()
            ]
        }
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {})
        if name not in TOOLS:
            return rpc_error(rid, -32602, "Unknown tool")
        try:
            value = invoke(
                db, workspace_id, principal, name, args, request.app.state.settings
            )
            structured = jsonable_encoder(value)
            result = {
                "content": [
                    {"type": "text", "text": json.dumps(structured, ensure_ascii=False)}
                ],
                "structuredContent": structured,
                "isError": False,
            }
        except (ServiceError, ValueError, HTTPException, ModelValidationError) as exc:
            code = (
                "cursor_invalid"
                if isinstance(exc, ServiceError) and exc.code == "INVALID_CURSOR"
                else exc.code.lower()
                if isinstance(exc, ServiceError)
                else "invalid_arguments"
            )
            structured = {"code": code, "message": str(exc)}
            result = {
                "content": [
                    {"type": "text", "text": json.dumps(structured, ensure_ascii=False)}
                ],
                "structuredContent": structured,
                "isError": True,
            }

    else:
        return rpc_error(
            rid, -32601, "Method not found; supported protocol: " + PROTOCOL_VERSION, 404
        )
    response_result = (
        result
        if legacy
        else {
            **result,
            "resultType": "complete",
            "_meta": {META + "serverInfo": {"name": "ontofoundry", "version": "0.1.0"}},
        }
    )
    return {
        "jsonrpc": "2.0",
        "id": rid,
        "result": response_result,
    }


@router.get("", status_code=405)
def no_sse():
    return {"detail": "此服务使用 MCP 2026-07-28 请求级 HTTP JSON，不提供独立 SSE 流"}
