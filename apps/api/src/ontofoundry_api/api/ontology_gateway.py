"""Personal-token MCP gateway and session-authenticated history endpoints."""

from datetime import datetime
from time import perf_counter
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal, gateway_principal
from ontofoundry_api.api.mcp_rpc import META, execute_tool, handle_rpc, tool_error
from ontofoundry_api.api.service_validation import ServiceValidationRoute
from ontofoundry_api.contracts.gateway import (
    FeedbackList,
    GatewayCallDetail,
    GatewayCallList,
)
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import utc_now
from ontofoundry_api.services import gateway_records, ontology_gateway
from ontofoundry_api.services.access import require_manage
from ontofoundry_api.services.errors import ForbiddenError

router = APIRouter(prefix="/api/v1/ontology/mcp", tags=["ontology-gateway"])
history_router = APIRouter(
    prefix="/api/v1", tags=["gateway-history"], route_class=ServiceValidationRoute
)
INSTRUCTIONS = (
    "从 OntoFoundry 读取已发布的本体定义，业务数据由客户端自己的查询工具按权限查询。"
    "先用 list_spaces 确认空间与版本，再检索和读取相关定义。跨空间结果分别说明口径。"
    "元素 name 是英文标识，display_name 是可选显示名称，空时显示 name。"
)
TOOLS = {
    "list_spaces": "列出当前可阅读空间、角色、发布版本和令牌权限",
    "search_ontology": "按原问题检索已发布语义，默认搜索成员空间。可用 workspace_ids 显式选择空间。每组单独分页，续页时只指定该组空间",
    "get_ontology": "读取指定空间的已发布定义、继承和授权物理投影，支持分页和字段分段",
    "submit_feedback": "记录用户对口径的纠正或建议，保留用户原话与智能体说明",
}


@router.post("")
async def rpc(
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(gateway_principal),
):
    return await handle_rpc(
        request,
        tools=TOOLS,
        inputs=ontology_gateway.INPUTS,
        instructions=INSTRUCTIONS,
        call_tool=lambda name, args, rid: call_tool(
            db, principal, name, args, request.app.state.settings,
            request.app.state.gateway_recorder, rid,
        ),
    )


@router.get("", status_code=405)
def no_sse():
    return {"detail": "此服务使用 MCP 2026-07-28 请求级 HTTP JSON，不提供独立 SSE 流"}


def audit_principal(request: Request, db: Session = Depends(get_db)):
    try:
        principal = current_principal(request, db)
    except HTTPException:
        raise ForbiddenError("需要平台管理员登录会话", code="PLATFORM_ADMIN_REQUIRED") from None
    if not principal.is_platform_admin:
        raise ForbiddenError("需要平台管理员权限", code="PLATFORM_ADMIN_REQUIRED")
    return principal


@history_router.get(
    "/workspaces/{workspace_id}/feedback",
    response_model=FeedbackList,
    response_model_exclude_unset=True,
)
def feedback(
    workspace_id: str,
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    require_manage(db, workspace_id, principal)
    return gateway_records.list_feedback(
        db, workspace_id, principal, request.app.state.settings, cursor=cursor, limit=limit
    )


@history_router.get("/admin/gateway-calls", response_model=GatewayCallList)
def gateway_calls(
    request: Request,
    user_id: str | None = None,
    workspace_id: str | None = None,
    tool: str | None = None,
    outcome: Literal["started", "ok", "error"] | None = None,
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(audit_principal),
):
    return gateway_records.list_calls(
        db, principal, request.app.state.settings,
        user_id=user_id, workspace_id=workspace_id, tool=tool, outcome=outcome,
        from_time=from_time, to_time=to_time, cursor=cursor, limit=limit,
    )


@history_router.get("/admin/gateway-calls/{call_id}", response_model=GatewayCallDetail)
def gateway_call(
    call_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(audit_principal),
):
    return gateway_records.get_call(db, call_id)


def call_tool(db, principal, name, arguments, settings, recorder, request_id):
    context = ontology_gateway.GatewayContext()
    started = perf_counter()
    call = {
        "id": str(uuid4()),
        "created_at": utc_now(),
        "user_id": principal.id,
        "token_id": principal.service_token_id.removeprefix("pat:"),
        "request_id": str(request_id),
        "tool": name,
        "arguments": {},
        "outcome": "started",
    }
    try:
        args = ontology_gateway.INPUTS[name].model_validate(arguments)
    except ValueError as exc:
        recorder.started(call, [])
        result = tool_error(exc, validation_message="工具参数无效，请核对输入")
    else:
        call["arguments"] = args.model_dump(mode="json", exclude={"cursor"})
        if hasattr(args, "cursor"):
            call["arguments"]["pagination"] = bool(args.cursor)
        targets = ontology_gateway.prepare_targets(db, principal, name, args, context)
        recorder.started(call, targets)
        result = execute_tool(
            lambda: ontology_gateway.invoke(db, principal, name, args, settings, context),
            all_details=True,
            validation_message="工具参数无效，请核对输入",
        )
    result["_meta"] = {
        META + "serverInfo": {"name": "ontofoundry", "version": "0.1.0"},
        ontology_gateway.VERSIONS_META: context.versions,
    }
    response = result["structuredContent"]
    recorder.finished(
        {
            **call,
            "response": response,
            "outcome": "error" if result["isError"] else "ok",
            "error_code": response.get("code") if result["isError"] else None,
            "error_message": response.get("message") if result["isError"] else None,
            "duration_ms": int((perf_counter() - started) * 1000),
        },
        ontology_gateway.audit_workspaces(context),
    )
    return result
