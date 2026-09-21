import json
from contextlib import suppress

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import get_modeling_session, require_member, session_data
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import (
    MaterialRecord,
    ModelingSessionRecord,
    WorkspaceRecord,
    utc_now,
)
from ontofoundry_api.services.dataagent import (
    ACTIVE_TASK_STATUSES,
    CANCELLED_TASK_STATUSES,
    SUCCESS_TASK_STATUSES,
    DataAgentClient,
    DataAgentError,
    build_turn_prompt,
    public_answer,
    task_id_from_messages,
    topic_id_from_messages,
    uploaded_material_ids,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/sessions/{session_id}", tags=["agent"]
)


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    mode: str = Field(default="chat", pattern="^(chat|model)$")
    revision: int


def _client(request: Request, workspace_id: str, session_id: str) -> DataAgentClient:
    settings = request.app.state.settings
    return DataAgentClient(
        settings.dataagent_base_url,
        prefix=settings.dataagent_api_prefix,
        website_id=settings.dataagent_website_id,
        access_key=settings.dataagent_access_key,
        session_ref=f"ontofoundry:{workspace_id}:{session_id}",
        timeout_seconds=settings.dataagent_request_timeout_seconds,
    )


def _dataagent_detail(status: str, error: object = None) -> str:
    if status in {"waiting", "queued"}:
        return "等待 DataAgent 调度"
    if status in {"waiting_input", "waiting_permission"}:
        return "DataAgent 正在等待用户确认"
    if status == "running":
        return "DataAgent · Pi 正在处理"
    if status in SUCCESS_TASK_STATUSES:
        return "DataAgent 处理完成"
    if status in CANCELLED_TASK_STATUSES:
        return "已取消，DataAgent 已保留会话记录"
    if isinstance(error, dict):
        return str(error.get("message") or error.get("detail") or error.get("code") or "执行失败")
    return str(error or "DataAgent 执行失败")


async def _sync_dataagent(app, workspace_id: str, session_id: str) -> dict:
    settings = app.state.settings
    client = DataAgentClient(
        settings.dataagent_base_url,
        prefix=settings.dataagent_api_prefix,
        website_id=settings.dataagent_website_id,
        access_key=settings.dataagent_access_key,
        session_ref=f"ontofoundry:{workspace_id}:{session_id}",
        timeout_seconds=settings.dataagent_request_timeout_seconds,
    )
    with app.state.session_factory() as db:
        item = get_modeling_session(db, workspace_id, session_id)
        task_id = task_id_from_messages(item.messages_json)
        if not task_id or item.task_status not in ("queued", "running"):
            return session_data(item)

    task = await client.task(task_id)
    status = str(task.get("task_status") or "").strip().lower()
    assistant: dict | None = None
    if status not in ACTIVE_TASK_STATUSES and status in SUCCESS_TASK_STATUSES:
        try:
            assistant = await client.task_message(task_id)
        except DataAgentError as exc:
            # The coordinator may close the task a fraction before the final
            # assistant row is visible. Keep the projection live and retry.
            if exc.status_code != 404:
                raise
            status = "running"

    with app.state.session_factory() as db:
        item = get_modeling_session(db, workspace_id, session_id)
        if task_id_from_messages(item.messages_json) != task_id:
            return session_data(item)
        messages = [dict(message) for message in item.messages_json]
        terminal_already_projected = any(
            message.get("role") == "assistant"
            and message.get("dataagent_task_id") == task_id
            for message in messages
        )
        for message in reversed(messages):
            if message.get("dataagent_task_id") == task_id:
                message["dataagent_task_status"] = status
                break

        if status in ACTIVE_TASK_STATUSES:
            item.task_status = "queued" if status in {"queued", "waiting"} else "running"
        elif status in SUCCESS_TASK_STATUSES:
            item.task_status = "completed"
            if assistant is not None and not terminal_already_projected:
                messages.append(
                    {
                        "role": "assistant",
                        "content": public_answer(assistant) or "DataAgent 已完成处理。",
                        "dataagent_task_id": task_id,
                        "dataagent_message_id": assistant.get("message_id"),
                        "attachments": assistant.get("attachments") or [],
                    }
                )
                item.revision += 1
        elif status in CANCELLED_TASK_STATUSES:
            item.task_status = "cancelled"
            if not terminal_already_projected:
                item.revision += 1
        else:
            item.task_status = "failed"
            if not terminal_already_projected:
                messages.append(
                    {
                        "role": "assistant",
                        "content": _dataagent_detail(status, task.get("error")),
                        "dataagent_task_id": task_id,
                        "error": task.get("error"),
                    }
                )
                item.revision += 1
        item.messages_json = messages
        item.task_detail = _dataagent_detail(status, task.get("error"))
        item.updated_at = utc_now()
        db.commit()
        db.refresh(item)
        return session_data(item)


@router.post("/messages", status_code=202)
async def chat(
    workspace_id: str,
    session_id: str,
    body: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    workspace = db.get(WorkspaceRecord, workspace_id)
    if workspace is None:
        raise HTTPException(404, "空间不存在")

    item = get_modeling_session(db, workspace_id, session_id)
    size = sum(db.get(MaterialRecord, mid).byte_size for mid in item.material_ids)
    if size > 2 * 1024**3:
        raise HTTPException(422, "所选材料总量超过 2 GB，请分批建模")

    config = request.app.state.settings
    if not config.dataagent_base_url:
        raise HTTPException(503, "DataAgent 未配置，无法启动 Agent 任务")
    if item.revision != body.revision or item.task_status in ("queued", "running"):
        raise HTTPException(409, "会话正在处理或已更新，请刷新后重试")
    dataagent = _client(request, workspace_id, session_id)
    topic_id = topic_id_from_messages(item.messages_json)
    created_topic = False
    try:
        if not topic_id:
            topic = await dataagent.create_topic(item.title, config.dataagent_agent_id)
            topic_id = str(topic.get("topic_id") or "")
            if not topic_id:
                raise DataAgentError("DataAgent 未返回 topic_id")
            created_topic = True

        already_uploaded = uploaded_material_ids(item.messages_json)
        material_paths: list[str] = []
        newly_uploaded: list[str] = []
        for material_id in item.material_ids:
            if material_id in already_uploaded:
                continue
            material = db.get(MaterialRecord, material_id)
            if material is None:
                continue
            path = config.data_dir / workspace_id / (material.sha256 + ".md")
            if not path.is_file():
                raise DataAgentError(f"建模材料源文件缺失: {material.name}", status_code=422)
            uploaded = await dataagent.upload(
                topic_id,
                f"{material.id}-{material.name}",
                path.read_bytes(),
                "text/markdown",
            )
            material_paths.append(str(uploaded.get("rel_path") or material.name))
            newly_uploaded.append(material.id)

        context = await dataagent.upload(
            topic_id,
            f"ontofoundry-context-r{item.revision}.json",
            json.dumps(item.draft_json, ensure_ascii=False, indent=2).encode(),
            "application/json",
        )
        submitted = await dataagent.deliver(
            topic_id=topic_id,
            content=build_turn_prompt(
                body.content,
                mode=body.mode,
                workspace_id=workspace_id,
                session_id=session_id,
                context_file=str(context.get("rel_path") or ""),
                material_files=material_paths,
            ),
            agent_id=config.dataagent_agent_id,
            execution_mode=config.dataagent_execution_mode,
        )
        task_id = str(submitted.get("task_id") or "")
        if not task_id:
            raise DataAgentError("DataAgent 未返回 task_id")
    except DataAgentError as exc:
        # A topic created for a request that DataAgent never accepted is not
        # referenced by the local session. Remove it (including uploaded
        # context files) so retries cannot accumulate orphan runtime state.
        if created_topic and topic_id:
            with suppress(DataAgentError):
                await dataagent.delete_topic(topic_id)
        raise HTTPException(exc.status_code, str(exc)) from exc
    changed = db.execute(
        update(ModelingSessionRecord)
        .where(
            ModelingSessionRecord.id == item.id,
            ModelingSessionRecord.revision == body.revision,
            ModelingSessionRecord.task_status.not_in(["queued", "running"]),
        )
        .values(
            task_status="queued",
            task_detail="等待 DataAgent 调度",
            dataagent_topic_id=topic_id,
            dataagent_task_id=task_id,
            dataagent_task_mode=body.mode,
            uploaded_material_ids=sorted(already_uploaded | set(newly_uploaded)),
            revision=body.revision + 1,
            messages_json=[
                *item.messages_json,
                {
                    "role": "user",
                    "content": body.content,
                    "mode": body.mode,
                    "dataagent_topic_id": topic_id,
                    "dataagent_task_id": task_id,
                    "dataagent_material_ids": newly_uploaded,
                },
            ],
            updated_at=utc_now(),
        )
    )
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "会话已在 DataAgent 接受任务后发生变化，请刷新查看")
    db.commit()
    db.refresh(item)
    return session_data(item)


@router.post("/sync")
async def sync(
    workspace_id: str,
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    get_modeling_session(db, workspace_id, session_id)
    if not request.app.state.settings.dataagent_base_url:
        raise HTTPException(409, "当前未启用 DataAgent")
    try:
        return await _sync_dataagent(request.app, workspace_id, session_id)
    except DataAgentError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.get("/events")
async def events(
    workspace_id: str,
    session_id: str,
    request: Request,
    after_id: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    if not request.app.state.settings.dataagent_base_url:
        raise HTTPException(409, "当前未启用 DataAgent")
    task_id = task_id_from_messages(item.messages_json)
    if not task_id:
        raise HTTPException(404, "当前会话没有 DataAgent 任务")
    dataagent = _client(request, workspace_id, session_id)
    try:
        await dataagent.task(task_id)
    except DataAgentError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc

    async def proxy():
        completed = False
        try:
            async for chunk in dataagent.stream(task_id, after_id):
                yield chunk
            completed = True
        finally:
            if completed:
                with suppress(DataAgentError):
                    await _sync_dataagent(request.app, workspace_id, session_id)
                    # The session polling fallback retries reconciliation; an
                    # already completed SSE response must not become malformed.

    return StreamingResponse(
        proxy(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/cancel")
async def cancel(
    workspace_id: str,
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    settings = request.app.state.settings
    dataagent_task_id = task_id_from_messages(item.messages_json)
    if not settings.dataagent_base_url:
        raise HTTPException(409, "当前未启用 DataAgent")
    if item.task_status not in ("running", "queued"):
        return session_data(item)
    if not dataagent_task_id:
        raise HTTPException(409, "当前运行中的会话缺少 DataAgent task_id")
    try:
        result = await _client(request, workspace_id, session_id).cancel(dataagent_task_id)
    except DataAgentError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc
    item.task_status = "cancelled"
    item.task_detail = _dataagent_detail(
        str(result.get("task_status") or "cancelled").lower()
    )
    item.revision += 1
    item.updated_at = utc_now()
    db.commit()
    db.refresh(item)
    return session_data(item)
