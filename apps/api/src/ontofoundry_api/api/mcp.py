from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, mcp_principal
from ontofoundry_api.api.mcp_rpc import execute_tool, handle_rpc
from ontofoundry_api.database import get_db
from ontofoundry_api.services.access import require_read
from ontofoundry_api.services.mcp_ontology import INPUTS, invoke

router = APIRouter(prefix="/api/v1/ontology/workspaces/{workspace_id}/mcp", tags=["mcp"])
INSTRUCTIONS = (
    "只读核心本体和已接受的文档事实；数据库聚合由 DataAgent 自有查询工具执行。"
    "元素 name 是必填英文标识，display_name 是可选中文名称，空时显示 name；"
    "写提案以 definition 和本轮 proposal Schema 为准。"
)
TOOLS = {
    "search_ontology": "按问题中的名称、英文标识、同义词和描述检索核心语义，按相关程度排序；expand 默认 true，只扩展一层关系并用 match.via 标明来源；返回 retrieval 与未覆盖原文 unmatched_terms；kinds 在扩展排序后过滤，可选 object_type、property、link_type、rule、metric、dataset、value_type；limit/cursor 分页，空间与版本由令牌绑定",
    "get_ontology": "读取核心定义、继承及授权物理投影；数据集含来源方式、表位置或 SQL、列和被引用元素，值类型含基础类型、约束和使用属性",
    "search_objects": "按事实 UUID 分页搜索已接受的文档事实",
    "resolve_entity": "把实体提及解析到指定实体类型（UUID）的实例：业务标识或名称精确、名称包含三级判定，返回 MATCHED／AMBIGUOUS／NOT_FOUND 与候选；AMBIGUOUS 必须追问，不得任选",
    "get_object": "读取文档事实、证据与直接邻接",
}



@router.post("")
async def rpc(
    workspace_id: str,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(mcp_principal),
):
    require_read(db, workspace_id, principal)
    return await handle_rpc(
        request, tools=TOOLS, inputs=INPUTS, instructions=INSTRUCTIONS,
        call_tool=lambda name, args, rid: execute_tool(
            lambda: invoke(db, workspace_id, principal, name, args, request.app.state.settings)
        ),
    )


@router.get("", status_code=405)
def no_sse():
    return {"detail": "此服务使用 MCP 2026-07-28 请求级 HTTP JSON，不提供独立 SSE 流"}
