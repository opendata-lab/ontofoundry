"""Shared request-level HTTP JSON-RPC transport for both MCP entry points."""

import base64
import binascii
import json

from fastapi import HTTPException, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import ValidationError as ModelValidationError
from starlette.concurrency import run_in_threadpool

from ontofoundry_api.services.errors import ServiceError

PROTOCOL_VERSION = "2026-07-28"
LEGACY_PROTOCOL_VERSIONS = (
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
)
META = "io.modelcontextprotocol/"


def tool_result(value, *, is_error=False):
    structured = jsonable_encoder(value)
    return {
        "content": [{"type": "text", "text": json.dumps(structured, ensure_ascii=False)}],
        "structuredContent": structured,
        "isError": is_error,
    }


def tool_error(exc, *, all_details=False, validation_message=None):
    if isinstance(exc, ServiceError):
        code = "cursor_invalid" if exc.code == "INVALID_CURSOR" else exc.code.lower()
        structured = {"code": code, "message": str(exc)}
        structured.update({
            key: value for key, value in exc.details.items()
            if key not in {"code", "message"}
            and (all_details or key in {"filtered_count", "warnings", "instance_change_sequence"})
        })
    else:
        structured = {
            "code": "invalid_arguments",
            "message": str(exc) if validation_message is None else validation_message,
        }
    return tool_result(structured, is_error=True)


def execute_tool(invoke, *, all_details=False, validation_message=None):
    try:
        return tool_result(invoke())
    except (ServiceError, ValueError, HTTPException, ModelValidationError) as exc:
        return tool_error(exc, all_details=all_details, validation_message=validation_message)


def rpc_error(rid, code, message, status=400, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    body = {"jsonrpc": "2.0", "error": error}
    if rid is not None:
        body["id"] = rid
    return JSONResponse(body, status_code=status)


def legacy_initialize(rid, params, instructions):
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
            "instructions": instructions,
        },
    }


async def handle_rpc(request, *, tools, inputs, instructions, call_tool):
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
        return legacy_initialize(rid, params, instructions)
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
            "instructions": instructions,
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {
            "tools": [
                {
                    "name": n,
                    "description": d,
                    "inputSchema": inputs[n].model_json_schema(),
                    "annotations": {"readOnlyHint": n != "submit_feedback", "destructiveHint": False},
                }
                for n, d in tools.items()
            ]
        }
    elif method == "tools/call":
        name, args = params.get("name"), params.get("arguments", {})
        if not isinstance(name, str) or name not in tools:
            return rpc_error(rid, -32602, "Unknown tool")
        result = await run_in_threadpool(call_tool, name, args, rid)

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
            "_meta": {META + "serverInfo": {"name": "ontofoundry", "version": "0.1.0"}, **result.get("_meta", {})},
        }
    )
    return {
        "jsonrpc": "2.0",
        "id": rid,
        "result": response_result,
    }
