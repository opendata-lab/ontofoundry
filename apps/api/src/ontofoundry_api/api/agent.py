from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import get_modeling_session, require_member, session_data
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import MaterialRecord, ModelingSessionRecord, utc_now
from ontofoundry_api.services.agent import run_agent

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/sessions/{session_id}", tags=["agent"]
)


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    mode: str = Field(default="chat", pattern="^(chat|model)$")
    revision: int


@router.post("/messages", status_code=202)
def chat(
    workspace_id: str,
    session_id: str,
    body: ChatRequest,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    config = request.app.state.settings
    if not config.anthropic_base_url or not config.anthropic_model:
        raise HTTPException(
            503,
            "尚未配置内网大模型。请在服务器设置 Anthropic 接口地址和模型名称；仍可手工建模。",
        )
    item = get_modeling_session(db, workspace_id, session_id)
    run_id = str(uuid4())
    size = sum(db.get(MaterialRecord, mid).byte_size for mid in item.material_ids)
    if size > 2 * 1024**3:
        raise HTTPException(422, "所选材料总量超过 2 GB，请分批建模")
    changed = db.execute(
        update(ModelingSessionRecord)
        .where(
            ModelingSessionRecord.id == item.id,
            ModelingSessionRecord.revision == body.revision,
            ModelingSessionRecord.task_status.not_in(["queued", "running"]),
        )
        .values(
            task_status="queued",
            task_detail="等待模型处理",
            revision=body.revision + 1,
            messages_json=[
                *item.messages_json,
                {
                    "role": "user",
                    "content": body.content,
                    "mode": body.mode,
                    "run_id": run_id,
                },
            ],
            updated_at=utc_now(),
        )
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "会话正在处理或已更新，请刷新后重试")
    db.commit()
    db.refresh(item)
    result = session_data(item)
    background.add_task(
        run_agent, request.app, item.id, body.content, body.mode == "model", run_id
    )
    return result


@router.post("/cancel")
def cancel(
    workspace_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    db.refresh(item, with_for_update=True)
    if item.task_status in ("running", "queued"):
        item.task_status, item.task_detail = "cancelled", "已取消，已生成候选保留"
        item.revision += 1
        db.commit()
    return session_data(item)
