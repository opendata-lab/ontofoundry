from __future__ import annotations

import json
import secrets
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import get_modeling_session, require_member
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import MaterialRecord, ModelingSessionRecord, utc_now
from ontofoundry_api.services.dataagent import (
    ACTIVE_TASK_STATUSES,
    DataAgentClient,
    DataAgentError,
    build_turn_prompt,
)
from ontofoundry_api.services.run_status import (
    ACTIVE_RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    to_run_status,
)

router = APIRouter(
    prefix=("/api/v1/workspaces/{workspace_id}/sessions/{session_id}/agent-conversation"),
    tags=["agent-conversation"],
)


class ConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CancelRequest(BaseModel):
    task_id: str = Field(min_length=1)


class InteractionRequest(BaseModel):
    task_id: str = Field(min_length=1)
    kind: Literal["permission", "question"]
    request_id: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


async def reconcile_run(*_args: object) -> None:
    """T5 extension point for consuming a completed modeling result."""


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


def _require_configured(request: Request) -> None:
    if not request.app.state.settings.dataagent_base_url:
        raise HTTPException(503, "DataAgent 未配置，无法使用 Agent Conversation")


def _mode(value: object) -> str:
    return value if value in {"chat", "model"} else "chat"


def _detail(status: str, error: object = None) -> str:
    if status in {"waiting", "queued", "submitting"}:
        return "等待 DataAgent 调度"
    if status in {"waiting_input", "waiting_permission"}:
        return "DataAgent 正在等待用户确认"
    if status == "running":
        return "DataAgent 正在处理"
    if status == "finished":
        return "DataAgent 处理完成"
    if status in {"suspended", "cancelled"}:
        return "已取消"
    if isinstance(error, dict):
        return str(
            error.get("message")
            or error.get("detail")
            or error.get("code")
            or "DataAgent 执行失败"
        )
    return str(error or "DataAgent 执行失败")


def _run_ref(
    task_id: str | None,
    status: str,
    *,
    mode: str,
    detail: str,
) -> dict[str, Any]:
    return {
        "task_id": task_id or "",
        "status": status,
        "detail": detail,
        "metadata": {"mode": _mode(mode)},
    }


def _raise_dataagent(exc: DataAgentError) -> None:
    raise HTTPException(exc.status_code, str(exc)) from exc


def _is_stale(updated_at: datetime) -> bool:
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return utc_now() - updated_at > timedelta(seconds=120)


def _persist_task_projection(
    session_factory,
    session_id: str,
    *,
    task_id: str | None,
    upstream_status: str,
    detail: str,
) -> str:
    status = to_run_status(upstream_status)
    with session_factory() as db:
        db.execute(
            update(ModelingSessionRecord)
            .where(ModelingSessionRecord.id == session_id)
            .values(
                dataagent_task_id=task_id,
                task_status=status,
                task_detail=detail,
                updated_at=utc_now(),
            )
        )
        db.commit()
    return status


async def _reconcile_stale_submission(
    request: Request,
    item: ModelingSessionRecord,
    messages: list[dict[str, Any]],
    dataagent: DataAgentClient,
) -> tuple[str | None, dict[str, Any] | None]:
    token = str(item.dataagent_run_token or "")
    task_id = next(
        (
            str(message.get("task_id"))
            for message in reversed(messages)
            if message.get("task_id")
            and token
            and token in str(message.get("content") or "")
        ),
        None,
    )
    if task_id:
        task = await dataagent.task(task_id)
        upstream_status = str(task.get("task_status") or "")
        _persist_task_projection(
            request.app.state.session_factory,
            item.id,
            task_id=task_id,
            upstream_status=upstream_status,
            detail=_detail(upstream_status, task.get("error")),
        )
        return task_id, task

    with request.app.state.session_factory() as db:
        db.execute(
            update(ModelingSessionRecord)
            .where(ModelingSessionRecord.id == item.id)
            .values(
                dataagent_task_id=None,
                task_status="failed",
                task_detail="未找到上次提交对应的 DataAgent 任务，请重试",
                updated_at=utc_now(),
            )
        )
        db.commit()
    return None, None


@router.get("")
async def snapshot(
    workspace_id: str,
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    if not item.dataagent_topic_id:
        return {"messages": [], "run": None}

    _require_configured(request)
    dataagent = _client(request, workspace_id, session_id)
    try:
        messages = await dataagent.messages(item.dataagent_topic_id)
        task_id = item.dataagent_task_id
        task: dict[str, Any] | None = None
        local_status = item.task_status
        local_detail = item.task_detail

        if local_status == "submitting" and _is_stale(item.updated_at):
            task_id, task = await _reconcile_stale_submission(
                request, item, messages, dataagent
            )
            if task is None:
                local_status = "failed"
                local_detail = "未找到上次提交对应的 DataAgent 任务，请重试"

        if task_id and task is None:
            task = await dataagent.task(task_id)

        if task is not None:
            upstream_status = str(task.get("task_status") or "")
            local_status = _persist_task_projection(
                request.app.state.session_factory,
                item.id,
                task_id=task_id,
                upstream_status=upstream_status,
                detail=_detail(upstream_status, task.get("error")),
            )
            local_detail = _detail(upstream_status, task.get("error"))
            if local_status in TERMINAL_RUN_STATUSES:
                await reconcile_run(request.app, workspace_id, session_id, task_id)

        run = None
        if task_id or local_status in ACTIVE_RUN_STATUSES | TERMINAL_RUN_STATUSES:
            visible_status = "queued" if local_status == "submitting" else local_status
            run = _run_ref(
                task_id,
                visible_status,
                mode=item.dataagent_task_mode,
                detail=local_detail,
            )
        return {"messages": messages, "run": run}
    except DataAgentError as exc:
        _raise_dataagent(exc)


@router.post("/messages", status_code=202)
async def send_message(
    workspace_id: str,
    session_id: str,
    body: ConversationMessageRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    _require_configured(request)

    materials = [
        material
        for material_id in item.material_ids
        if (material := db.get(MaterialRecord, material_id)) is not None
    ]
    if sum(material.byte_size for material in materials) > 2 * 1024**3:
        raise HTTPException(422, "所选材料总量超过 2 GB，请分批建模")

    mode = _mode(body.metadata.get("mode"))
    expected_revision = item.revision
    run_token = secrets.token_hex(16)
    topic_id = item.dataagent_topic_id
    title = item.title
    draft = item.draft_json
    uploaded_ids = set(item.uploaded_material_ids or [])

    changed = db.execute(
        update(ModelingSessionRecord)
        .where(
            ModelingSessionRecord.id == item.id,
            ModelingSessionRecord.revision == expected_revision,
            ModelingSessionRecord.task_status.not_in(ACTIVE_RUN_STATUSES),
        )
        .values(
            task_status="submitting",
            task_detail="正在提交到 DataAgent",
            dataagent_task_mode=mode,
            dataagent_run_token=run_token,
            revision=expected_revision + 1,
            updated_at=utc_now(),
        )
    )
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "会话正在处理或已更新，请刷新后重试")
    db.commit()

    dataagent = _client(request, workspace_id, session_id)
    created_topic = False
    task_id: str | None = None
    newly_uploaded: list[str] = []
    try:
        if not topic_id:
            topic = await dataagent.create_topic(
                title, request.app.state.settings.dataagent_agent_id
            )
            topic_id = str(topic.get("topic_id") or "")
            if not topic_id:
                raise DataAgentError("DataAgent 未返回 topic_id")
            created_topic = True

        material_paths: list[str] = []
        for material in materials:
            if material.id in uploaded_ids:
                continue
            path = (
                request.app.state.settings.data_dir / workspace_id / f"{material.sha256}.md"
            )
            if not path.is_file():
                raise DataAgentError(
                    f"建模材料源文件缺失: {material.name}", status_code=422
                )
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
            f"ontofoundry-context-r{expected_revision}.json",
            json.dumps(draft, ensure_ascii=False, indent=2).encode(),
            "application/json",
        )
        prompt = build_turn_prompt(
            body.content,
            mode=mode,
            workspace_id=workspace_id,
            session_id=session_id,
            context_file=str(context.get("rel_path") or ""),
            material_files=material_paths,
            run_token=run_token,
        )
        submitted = await dataagent.deliver(
            topic_id=topic_id,
            content=prompt,
            agent_id=request.app.state.settings.dataagent_agent_id,
            execution_mode=request.app.state.settings.dataagent_execution_mode,
        )
        task_id = str(submitted.get("task_id") or "")
        if not task_id:
            raise DataAgentError("DataAgent 未返回 task_id")
        upstream_status = str(submitted.get("task_status") or "waiting")
    except DataAgentError as exc:
        with request.app.state.session_factory() as failed_db:
            failed_db.execute(
                update(ModelingSessionRecord)
                .where(ModelingSessionRecord.id == item.id)
                .values(
                    task_status="failed",
                    task_detail=str(exc),
                    dataagent_task_id=None,
                    updated_at=utc_now(),
                )
            )
            failed_db.commit()
        if created_topic and topic_id:
            with suppress(DataAgentError):
                await dataagent.delete_topic(topic_id)
        _raise_dataagent(exc)

    status = to_run_status(upstream_status)
    try:
        with request.app.state.session_factory() as success_db:
            success_db.execute(
                update(ModelingSessionRecord)
                .where(ModelingSessionRecord.id == item.id)
                .values(
                    task_status=status,
                    task_detail=_detail(upstream_status),
                    dataagent_topic_id=topic_id,
                    dataagent_task_id=task_id,
                    dataagent_task_mode=mode,
                    uploaded_material_ids=sorted(uploaded_ids | set(newly_uploaded)),
                    updated_at=utc_now(),
                )
            )
            success_db.commit()
    except Exception:
        if task_id:
            with suppress(DataAgentError):
                await dataagent.cancel(task_id)
        raise

    return _run_ref(
        task_id,
        status,
        mode=mode,
        detail=_detail(upstream_status),
    )


def _event_frames(buffer: str) -> tuple[list[str], str]:
    normalized = buffer.replace("\r\n", "\n")
    parts = normalized.split("\n\n")
    return parts[:-1], parts[-1]


def _data_payload(frame: str) -> str | None:
    lines = [line[5:].lstrip() for line in frame.splitlines() if line.startswith("data:")]
    return "\n".join(lines) if lines else None


@router.get("/events")
async def events(
    workspace_id: str,
    session_id: str,
    request: Request,
    after_id: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
) -> StreamingResponse:
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    _require_configured(request)
    if not item.dataagent_task_id:
        raise HTTPException(404, "当前会话没有 DataAgent 任务")

    task_id = item.dataagent_task_id
    mode = _mode(item.dataagent_task_mode)
    dataagent = _client(request, workspace_id, session_id)

    async def stream_events():
        cursor = after_id
        while True:
            buffer = ""
            async for chunk in dataagent.stream(task_id, cursor):
                buffer += chunk.decode("utf-8", errors="replace")
                frames, buffer = _event_frames(buffer)
                for frame in frames:
                    payload = _data_payload(frame)
                    if payload is None:
                        continue
                    with suppress(ValueError, TypeError):
                        event = json.loads(payload)
                        cursor = max(cursor, int(event.get("seq_id") or cursor))
                    yield f"event: agent-event\ndata: {payload}\n\n"

            payload = _data_payload(buffer)
            if payload is not None:
                with suppress(ValueError, TypeError):
                    event = json.loads(payload)
                    cursor = max(cursor, int(event.get("seq_id") or cursor))
                yield f"event: agent-event\ndata: {payload}\n\n"

            yield ": ping\n\n"
            task = await dataagent.task(task_id)
            upstream_status = str(task.get("task_status") or "")
            status = _persist_task_projection(
                request.app.state.session_factory,
                session_id,
                task_id=task_id,
                upstream_status=upstream_status,
                detail=_detail(upstream_status, task.get("error")),
            )
            if upstream_status in ACTIVE_TASK_STATUSES:
                continue

            await reconcile_run(request.app, workspace_id, session_id, task_id)
            run = _run_ref(
                task_id,
                status,
                mode=mode,
                detail=_detail(upstream_status, task.get("error")),
            )
            yield (
                "event: done\ndata: "
                + json.dumps(run, ensure_ascii=False, separators=(",", ":"))
                + "\n\n"
            )
            return

    return StreamingResponse(
        stream_events(),
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
    body: CancelRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    _require_configured(request)
    if item.dataagent_task_id and body.task_id != item.dataagent_task_id:
        raise HTTPException(409, "任务不属于当前会话")
    try:
        result = await _client(request, workspace_id, session_id).cancel(body.task_id)
    except DataAgentError as exc:
        _raise_dataagent(exc)
    upstream_status = str(result.get("task_status") or "suspended")
    status = _persist_task_projection(
        request.app.state.session_factory,
        item.id,
        task_id=body.task_id,
        upstream_status=upstream_status,
        detail=_detail(upstream_status, result.get("error")),
    )
    return _run_ref(
        body.task_id,
        status,
        mode=item.dataagent_task_mode,
        detail=_detail(upstream_status, result.get("error")),
    )


@router.post("/interactions")
async def interact(
    workspace_id: str,
    session_id: str,
    body: InteractionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
) -> dict[str, Any]:
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    _require_configured(request)
    if item.dataagent_task_id and body.task_id != item.dataagent_task_id:
        raise HTTPException(409, "任务不属于当前会话")
    dataagent = _client(request, workspace_id, session_id)
    try:
        if body.kind == "permission":
            return await dataagent.permission_decision(
                body.task_id, body.request_id, body.payload
            )
        return await dataagent.question_answer(body.task_id, body.request_id, body.payload)
    except DataAgentError as exc:
        _raise_dataagent(exc)


@router.get("/files/{rel_path:path}")
async def download_file(
    workspace_id: str,
    session_id: str,
    rel_path: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
) -> Response:
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    _require_configured(request)
    if not item.dataagent_topic_id:
        raise HTTPException(404, "当前会话没有 DataAgent Topic")
    try:
        content, content_type = await _client(request, workspace_id, session_id).download(
            item.dataagent_topic_id, rel_path
        )
    except DataAgentError as exc:
        _raise_dataagent(exc)
    return Response(content=content, media_type=content_type)
