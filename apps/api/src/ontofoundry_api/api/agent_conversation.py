from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
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
    require_dataagent_configuration,
)
from ontofoundry_api.services.model_result import (
    exhaust_retriable_result,
    reconcile_run,
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
    settings = request.app.state.settings
    require_dataagent_configuration(
        settings.dataagent_base_url, settings.dataagent_access_key
    )


def _mode(value: object) -> str:
    return value if value in {"chat", "model"} else "chat"


def _session_title(content: str, materials: list[MaterialRecord]) -> str:
    """Name a first turn without another model call or remote dependency."""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    candidates: list[str] = []
    for prefix in ("业务场景：", "业务场景:", "本次需求：", "本次需求:"):
        candidates.extend(
            line.removeprefix(prefix).strip() for line in lines if line.startswith(prefix)
        )
    candidates.extend(lines)
    title = next((value for value in candidates if value), "")
    if title == "基于已选材料开始建模" and materials:
        material_name = materials[0].name.rsplit("/", 1)[-1]
        title = material_name.rsplit(".", 1)[0] + "建模"
    title = " ".join(title.split()).strip("#*- ")
    if not title:
        return "未命名建模会话"
    return title if len(title) <= 36 else title[:35].rstrip() + "…"


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
    raise exc


def _is_stale(updated_at: datetime) -> bool:
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return utc_now() - updated_at > timedelta(seconds=120)


def _delivery_outcome_is_unknown(exc: DataAgentError) -> bool:
    """Whether deliver may have reached DataAgent before failing locally."""
    if exc.status_code == 408:
        return True
    if 400 <= exc.status_code < 500:
        return False
    return not isinstance(exc.__cause__, httpx.ConnectError)


def _fail_stale_submission(
    session_factory,
    item: ModelingSessionRecord,
    *,
    detail: str,
) -> bool:
    """Release only the stale submitting generation observed by this request."""
    with session_factory() as db:
        changed = db.execute(
            update(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == item.id,
                ModelingSessionRecord.task_status == "submitting",
                ModelingSessionRecord.dataagent_run_token
                == str(item.dataagent_run_token or ""),
                ModelingSessionRecord.dataagent_task_id.is_(None),
            )
            .values(
                dataagent_task_id=None,
                task_status="failed",
                task_detail=detail,
                updated_at=utc_now(),
            )
        )
        db.commit()
        return changed.rowcount == 1


def _persist_task_projection(
    session_factory,
    session_id: str,
    *,
    task_id: str | None,
    upstream_status: str,
    detail: str,
) -> str | None:
    status = to_run_status(upstream_status)
    with session_factory() as db:
        changed = db.execute(
            update(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session_id,
                ModelingSessionRecord.dataagent_task_id == task_id,
            )
            .values(
                dataagent_task_id=task_id,
                task_status=status,
                task_detail=detail,
                updated_at=utc_now(),
            )
        )
        db.commit()
    return status if changed.rowcount == 1 else None


def _current_run_projection(
    session_factory,
    session_id: str,
) -> tuple[str | None, str, str, str, str]:
    """Read the generation that currently owns the session."""
    with session_factory() as db:
        item = db.get(ModelingSessionRecord, session_id)
        if item is None:  # pragma: no cover - the request already owns this row
            return None, "", "", "chat", ""
        return (
            item.dataagent_task_id,
            str(item.task_status or ""),
            str(item.task_detail or ""),
            _mode(item.dataagent_task_mode),
            str(item.dataagent_run_token or ""),
        )


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
        with request.app.state.session_factory() as db:
            claimed = db.execute(
                update(ModelingSessionRecord)
                .where(
                    ModelingSessionRecord.id == item.id,
                    ModelingSessionRecord.task_status == "submitting",
                    ModelingSessionRecord.dataagent_run_token == token,
                    ModelingSessionRecord.dataagent_task_id.is_(None),
                )
                .values(
                    dataagent_task_id=task_id,
                    task_status=to_run_status(upstream_status),
                    task_detail=_detail(upstream_status, task.get("error")),
                    updated_at=utc_now(),
                )
            )
            db.commit()
        if claimed.rowcount == 1:
            return task_id, task
        return None, None

    _fail_stale_submission(
        request.app.state.session_factory,
        item,
        detail="未找到上次提交对应的 DataAgent 任务，请重试",
    )
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
        if item.task_status == "submitting" and _is_stale(item.updated_at):
            detail = "上次提交未创建可对账的 DataAgent Topic，请重试"
            if _fail_stale_submission(
                request.app.state.session_factory,
                item,
                detail=detail,
            ):
                return {
                    "messages": [],
                    "run": _run_ref(
                        None,
                        "failed",
                        mode=item.dataagent_task_mode,
                        detail=detail,
                    ),
                }
            task_id, status, detail, mode, _token = _current_run_projection(
                request.app.state.session_factory,
                item.id,
            )
            if task_id or status in ACTIVE_RUN_STATUSES | TERMINAL_RUN_STATUSES:
                return {
                    "messages": [],
                    "run": _run_ref(
                        task_id,
                        "queued" if status == "submitting" else status,
                        mode=mode,
                        detail=detail,
                    ),
                }
        return {"messages": [], "run": None}

    _require_configured(request)
    dataagent = _client(request, workspace_id, session_id)
    try:
        messages = await dataagent.messages(item.dataagent_topic_id)
        task_id = item.dataagent_task_id
        task: dict[str, Any] | None = None
        local_status = item.task_status
        local_detail = item.task_detail
        local_mode = _mode(item.dataagent_task_mode)
        ownership_lost = False

        if local_status == "submitting" and _is_stale(item.updated_at):
            task_id, task = await _reconcile_stale_submission(
                request, item, messages, dataagent
            )
            if task is None:
                task_id, local_status, local_detail, local_mode, current_token = (
                    _current_run_projection(
                        request.app.state.session_factory,
                        item.id,
                    )
                )
                ownership_lost = current_token != str(item.dataagent_run_token or "")

        if task_id and task is None and not ownership_lost:
            task = await dataagent.task(task_id)

        if task is not None:
            upstream_status = str(task.get("task_status") or "")
            projected_status = _persist_task_projection(
                request.app.state.session_factory,
                item.id,
                task_id=task_id,
                upstream_status=upstream_status,
                detail=_detail(upstream_status, task.get("error")),
            )
            if projected_status is None:
                task_id, local_status, local_detail, local_mode, _current_token = (
                    _current_run_projection(
                        request.app.state.session_factory,
                        item.id,
                    )
                )
                ownership_lost = True
            else:
                local_status = projected_status
                local_detail = _detail(upstream_status, task.get("error"))
            if not ownership_lost and local_status in TERMINAL_RUN_STATUSES:
                result_state = await reconcile_run(
                    request.app, workspace_id, session_id, task_id
                )
                with request.app.state.session_factory() as current_db:
                    current = current_db.get(ModelingSessionRecord, item.id)
                    if current is not None:
                        task_id = current.dataagent_task_id
                        local_status = current.task_status
                        local_detail = current.task_detail
                        local_mode = _mode(current.dataagent_task_mode)
                if result_state in {"failed_retriable", "processing"}:
                    # Keep the SDK run reconnectable; only /events owns the
                    # bounded automatic retry and eventual terminal event.
                    local_status = "running"

        run = None
        if task_id or local_status in ACTIVE_RUN_STATUSES | TERMINAL_RUN_STATUSES:
            visible_status = "queued" if local_status == "submitting" else local_status
            run = _run_ref(
                task_id,
                visible_status,
                mode=local_mode,
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
    title = (
        _session_title(body.content, materials)
        if item.title in {"新的建模会话", "未命名建模会话"}
        else item.title
    )
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
            title=title,
            task_status="submitting",
            task_detail="正在提交到 DataAgent",
            dataagent_task_id=None,
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
    delivery_started = False
    try:
        if not topic_id:
            topic = await dataagent.create_topic(
                title, request.app.state.settings.dataagent_agent_id
            )
            topic_id = str(topic.get("topic_id") or "")
            if not topic_id:
                raise DataAgentError("DataAgent 未返回 topic_id")
            created_topic = True
            with request.app.state.session_factory() as topic_db:
                persisted_topic = topic_db.execute(
                    update(ModelingSessionRecord)
                    .where(
                        ModelingSessionRecord.id == item.id,
                        ModelingSessionRecord.task_status == "submitting",
                        ModelingSessionRecord.dataagent_run_token == run_token,
                        ModelingSessionRecord.dataagent_task_id.is_(None),
                    )
                    .values(
                        dataagent_topic_id=topic_id,
                        updated_at=utc_now(),
                    )
                )
                topic_db.commit()
            if persisted_topic.rowcount != 1:
                with suppress(DataAgentError):
                    await dataagent.delete_topic(topic_id)
                raise HTTPException(
                    409,
                    "会话已在创建 Topic 期间被其他请求接管，请刷新后重试",
                )

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
        delivery_started = True
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
        outcome_unknown = delivery_started and _delivery_outcome_is_unknown(exc)
        released = False
        if not outcome_unknown:
            with request.app.state.session_factory() as failed_db:
                # Only release the slot we are still holding. A submission slow
                # enough for the stale-submitting reconciler to have released it
                # can find another turn already running; writing unconditionally
                # would mark that one failed and orphan its remote task.
                failed = failed_db.execute(
                    update(ModelingSessionRecord)
                    .where(
                        ModelingSessionRecord.id == item.id,
                        ModelingSessionRecord.dataagent_run_token == run_token,
                    )
                    .values(
                        task_status="failed",
                        task_detail=str(exc),
                        dataagent_task_id=None,
                        dataagent_topic_id=None if created_topic else topic_id,
                        updated_at=utc_now(),
                    )
                )
                failed_db.commit()
                released = failed.rowcount == 1
        if released and created_topic and topic_id:
            with suppress(DataAgentError):
                await dataagent.delete_topic(topic_id)
        _raise_dataagent(exc)

    status = to_run_status(upstream_status)
    try:
        with request.app.state.session_factory() as success_db:
            claimed = success_db.execute(
                update(ModelingSessionRecord)
                .where(
                    ModelingSessionRecord.id == item.id,
                    ModelingSessionRecord.dataagent_run_token == run_token,
                )
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
        if claimed.rowcount != 1:
            # Another turn owns the session now. The task we just created is
            # real and running, and nothing local will ever reference it, so
            # cancel it rather than leave it burning budget unobserved.
            with suppress(DataAgentError):
                await dataagent.cancel(task_id)
            raise HTTPException(409, "会话已在提交期间被其他请求接管，请刷新后重试")
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
    dataagent = _client(request, workspace_id, session_id)

    async def stream_events():
        cursor = after_id
        mode = _mode(item.dataagent_task_mode)
        reconnect_delay = 0.25
        while True:
            buffer = ""
            saw_event = False
            async for chunk in dataagent.stream(task_id, cursor):
                buffer += chunk.decode("utf-8", errors="replace")
                frames, buffer = _event_frames(buffer)
                for frame in frames:
                    payload = _data_payload(frame)
                    if payload is None:
                        continue
                    saw_event = True
                    with suppress(ValueError, TypeError):
                        event = json.loads(payload)
                        cursor = max(cursor, int(event.get("seq_id") or cursor))
                    yield f"event: agent-event\ndata: {payload}\n\n"

            payload = _data_payload(buffer)
            if payload is not None:
                saw_event = True
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
            if status is None:
                # This stream belongs to an older generation. Closing it without
                # a terminal event prevents the SDK from completing the new run
                # with the old task id/status.
                return
            if upstream_status in ACTIVE_TASK_STATUSES:
                delay = 0.25 if saw_event else reconnect_delay
                await asyncio.sleep(delay)
                reconnect_delay = 0.25 if saw_event else min(delay * 2, 5.0)
                continue

            result_state = await reconcile_run(
                request.app, workspace_id, session_id, task_id
            )
            if result_state in {"failed_retriable", "processing"}:
                for delay in (2, 4, 8):
                    await asyncio.sleep(delay)
                    result_state = await reconcile_run(
                        request.app, workspace_id, session_id, task_id
                    )
                    if result_state not in {"failed_retriable", "processing"}:
                        break
                if result_state == "failed_retriable":
                    result_state = exhaust_retriable_result(
                        request.app, session_id, task_id
                    )
                if result_state == "processing":
                    # Another request still owns a valid lease. It must be the
                    # one to commit or fail the result before any terminal SDK
                    # event is emitted.
                    continue

            with request.app.state.session_factory() as current_db:
                current = current_db.get(ModelingSessionRecord, session_id)
                if current is not None:
                    if current.dataagent_task_id != task_id:
                        # Result reconciliation can outlive the generation it
                        # started on. Never complete its successor from this
                        # old task's event stream.
                        return
                    status = current.task_status
                    detail = current.task_detail
                    mode = _mode(current.dataagent_task_mode)
                else:  # pragma: no cover - a live request owns this session
                    detail = _detail(upstream_status, task.get("error"))
            run = _run_ref(
                task_id,
                status,
                mode=mode,
                detail=detail,
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
    if status is None:
        raise HTTPException(409, "会话任务已变化，请刷新后重试")
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
