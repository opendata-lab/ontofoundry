from __future__ import annotations

import asyncio
import codecs
import json
import logging
import re
import secrets
from contextlib import suppress
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import update
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import (
    get_modeling_session,
    require_member,
    session_draft,
    version_snapshot_sha256,
)
from ontofoundry_api.contracts.proposals import result_schema
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import MaterialRecord, ModelingSessionRecord, utc_now
from ontofoundry_api.domain.snapshot import draft_sha256
from ontofoundry_api.services.dataagent import (
    ACTIVE_TASK_STATUSES,
    DataAgentClient,
    DataAgentError,
    build_turn_prompt,
    proposal_instructions,
    require_dataagent_configuration,
)
from ontofoundry_api.services.material_source import (
    MaterialSourceMissing,
    material_source_path,
)
from ontofoundry_api.services.material_types import material_media_type
from ontofoundry_api.services.modeling_input import (
    build_work_pack,
    encode,
    execution_input,
    material_index,
    scenario_facts,
    store_linked_tables_receipt,
    upload_work_pack,
)
from ontofoundry_api.services.modeling_runs import _persist_task_projection
from ontofoundry_api.services.proposals import proposal_context, proposal_header
from ontofoundry_api.services.request_material import store_request_material
from ontofoundry_api.services.run_credentials import RunGrant
from ontofoundry_api.services.run_credentials import access_file as mcp_access_file
from ontofoundry_api.services.run_credentials import issue as issue_run_credential
from ontofoundry_api.services.run_status import (
    ACTIVE_RUN_STATUSES,
    to_run_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=("/api/v1/workspaces/{workspace_id}/sessions/{session_id}/agent-conversation"),
    tags=["agent-conversation"],
)


class ConversationSettings(BaseModel):
    # The composer's plan switch. Other composer settings (model, provider)
    # are DataAgent's to choose and are ignored here.
    permission_mode: Literal["plan", "default"] | None = None


class ConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    settings: ConversationSettings = Field(default_factory=ConversationSettings)


class CancelRequest(BaseModel):
    task_id: str = Field(min_length=1)


class InteractionRequest(BaseModel):
    task_id: str = Field(min_length=1)
    kind: Literal["permission", "question"]
    request_id: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


def run_mcp_access(
    request, workspace_id, session_id, run_token, item, user_id
) -> dict[str, Any]:
    settings = request.app.state.settings
    base = (settings.public_base_url or str(request.base_url)).rstrip("/")
    return {
        "url": f"{base}/api/v1/ontology/workspaces/{workspace_id}/mcp",
        "version_id": item.base_version_id,
        "credential": issue_run_credential(
            settings.session_secret,
            RunGrant(
                workspace_id=workspace_id,
                session_id=session_id,
                run_token=run_token,
                version_id=item.base_version_id,
                user_id=user_id,
            ),
        ),
    }


# What reaches DataAgent is the turn prompt: run context, contract and the
# user's words. The chat shows only the words; a run credential never shows,
# including in messages stored before it moved into an uploaded file.
USER_MESSAGE_MARK = "[用户消息]\n"
_RUN_CREDENTIAL = re.compile(r"ofrun\.[A-Za-z0-9_.\-]+")


def redact_credentials(text: str) -> str:
    return _RUN_CREDENTIAL.sub("ofrun.***", text)


def present_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return json.loads(redact_credentials(json.dumps(messages, ensure_ascii=False)))


def _client(request: Request, workspace_id: str, session_id: str) -> DataAgentClient:
    return _app_client(request.app, workspace_id, session_id)


def _app_client(app, workspace_id: str, session_id: str) -> DataAgentClient:
    settings = app.state.settings
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
    require_dataagent_configuration(settings.dataagent_base_url)


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


def _delivery_outcome_is_unknown(exc: DataAgentError) -> bool:
    """Whether deliver may have reached DataAgent before failing locally."""
    if exc.status_code == 408:
        return True
    if 400 <= exc.status_code < 500:
        return False
    return not isinstance(exc.__cause__, httpx.ConnectError)


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
    messages = await dataagent.messages(item.dataagent_topic_id)
    run = None
    if item.dataagent_task_id:
        task = await dataagent.task(item.dataagent_task_id)
        upstream_status = str(task.get("task_status") or "")
        run = _run_ref(item.dataagent_task_id, to_run_status(upstream_status),
                       mode=item.dataagent_task_mode, detail=_detail(upstream_status, task.get("error")))
    return {"messages": present_messages(messages), "run": run}


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
    from ontofoundry_api.services.session_gate import lock_session, require_draft_edit
    item = lock_session(db, workspace_id, session_id)
    require_draft_edit(db, item)
    _require_configured(request)

    # The session's mode is fixed; a message cannot switch it.
    mode = _mode(item.mode)
    request_material = store_request_material(
        db, request.app.state.settings, workspace_id, body.content, mode
    )
    selected_material_ids = list(item.material_ids)
    if request_material is not None and request_material.id not in selected_material_ids:
        selected_material_ids.append(request_material.id)
    materials = [
        material
        for material_id in selected_material_ids
        if (material := db.get(MaterialRecord, material_id)) is not None
    ]
    if sum(material.byte_size for material in materials) > 2 * 1024**3:
        raise HTTPException(422, "所选材料总量超过 2 GB，请分批建模")

    expected_revision = item.revision
    run_token = secrets.token_hex(16)
    topic_id = item.dataagent_topic_id
    title = (
        _session_title(body.content, materials)
        if item.title in {"新的建模会话", "未命名建模会话"}
        else item.title
    )
    # Modeling sessions and new runs use core-1.
    draft = session_draft(item)
    uploaded_ids = set(item.uploaded_material_ids or [])
    # Where earlier runs put material in this topic, read before the claim
    # below replaces the manifest: a proposals prompt must name every
    # material's file, not only this turn's uploads.
    known_paths: dict[str, str] = {
        str(entry["id"]): str(entry["path"])
        for entry in (item.run_manifest_json or {}).get("materials") or []
        if entry.get("path")
    }
    # The previous run, read before the claim replaces its manifest: its
    # inputs are the baseline for this run's facts.
    previous_manifest = dict(item.run_manifest_json or {})
    # Everything this run is pinned to. The claim below bumps the revision,
    # so the run's source revision is the one after it.
    manifest = {
        "run_token": run_token,
        "draft_schema_version": "core-1",
        "workspace_id": workspace_id,
        "session_id": session_id,
        "base_version_id": item.base_version_id,
        "base_version_sha256": item.base_version_sha256
        or version_snapshot_sha256(db, workspace_id, item.base_version_id),
        "source_session_revision": expected_revision + 1,
        "source_draft_sha256": draft_sha256(draft),
        "materials": [{"id": m.id, "sha256": m.sha256} for m in materials],
        "producer": {
            "agent_id": request.app.state.settings.dataagent_agent_id,
            # The agent picks among its mounted skills per task.
            "skill": "ontology-discovery+entity-extraction",
            "mode": mode,
        },
        "result_contract": request.app.state.settings.modeling_result_contract
        if mode == "model"
        else None,
    }
    proposals = manifest["result_contract"] == "proposals"
    if proposals:
        # Results are parsed against exactly the draft this run was given.
        manifest["pinned_draft"] = draft
        from ontofoundry_api.services.instance_store import baseline
        manifest["instance_baseline"] = baseline(db, workspace_id, session_id)

    table_catalog, table_receipt = None, None
    if proposals and item.linked_tables:
        table_catalog, table_receipt = store_linked_tables_receipt(
            db, request.app.state.settings, workspace_id, item.linked_tables
        )
        if all(material.id != table_receipt.id for material in materials):
            materials.append(table_receipt)
        manifest["materials"] = [{"id": m.id, "sha256": m.sha256} for m in materials]

    changed = db.execute(
        update(ModelingSessionRecord)
        .where(
            ModelingSessionRecord.id == item.id,
            ModelingSessionRecord.revision == expected_revision,
            ModelingSessionRecord.task_status.not_in(ACTIVE_RUN_STATUSES),
        )
        .values(
            title=title,
            material_ids=selected_material_ids,
            task_status="submitting",
            task_detail="正在提交到 DataAgent",
            dataagent_task_id=None,
            dataagent_task_mode=mode,
            dataagent_run_token=run_token,
            run_manifest_json=manifest,
            result_state="",
            last_result_task_id=None,
            result_claimed_at=None,
            result_warnings=[],
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

        material_paths: list[dict[str, Any]] = []
        material_path_by_id: dict[str, str] = dict(known_paths)
        material_indices = []
        for material in materials:
            known_path = material_path_by_id.get(material.id)
            if material.id in uploaded_ids and known_path and not proposals:
                material_indices.append(
                    {"id": material.id, "sha256": material.sha256, "path": known_path}
                )
                continue
            try:
                path = material_source_path(db, request.app.state.settings, material)
            except MaterialSourceMissing:
                raise DataAgentError(
                    f"建模材料源文件缺失: {material.name}", status_code=422
                ) from None
            source_bytes = path.read_bytes()
            if material.id in uploaded_ids and known_path:
                path_in_topic = known_path
            else:
                uploaded = await dataagent.upload(
                    topic_id,
                    f"ontofoundry-tables-{run_token}.json"
                    if table_receipt is not None and material.id == table_receipt.id
                    else f"{material.id}-{material.name}",
                    source_bytes,
                    "application/json"
                    if table_receipt is not None and material.id == table_receipt.id
                    else material_media_type(material.name),
                )
                path_in_topic = str(uploaded.get("rel_path") or material.name)
                material_paths.append({"path": path_in_topic, "bytes": material.byte_size})
                material_path_by_id[material.id] = path_in_topic
                newly_uploaded.append(material.id)
            metadata = {"id": material.id, "sha256": material.sha256}
            material_indices.append(
                material_index(metadata, source_bytes, path_in_topic)
                if proposals
                else {**metadata, "path": path_in_topic}
            )

        proposal_prompt = None
        if proposals:
            fixed_context = proposal_context(manifest, draft)
            fixed_context["execution"] = execution_input(run_token)
            context_body = encode(fixed_context)
            context = await dataagent.upload(
                topic_id,
                f"ontofoundry-context-{run_token}.json",
                context_body,
                "application/json",
            )
            schema = await dataagent.upload(
                topic_id,
                "ontofoundry.proposals.v1.schema.json",
                json.dumps(result_schema(), ensure_ascii=False).encode(),
                "application/json",
            )
            # Every run gets its credential: the merge script's platform check
            # needs it even before anything is published. The MCP config (which
            # reads the published ontology) is only offered once a version exists.
            access = run_mcp_access(
                request, workspace_id, session_id, run_token, item, user.id
            )
            uploaded_access = await dataagent.upload(
                topic_id,
                f"ontofoundry-mcp-{run_token}.json",
                json.dumps(mcp_access_file(access), indent=2).encode(),
                "application/json",
            )
            access_path = str(uploaded_access.get("rel_path") or "")
            mcp = (
                {"url": access["url"], "version_id": access["version_id"], "file": access_path}
                if item.base_version_id
                else None
            )
            tables_file = material_path_by_id[table_receipt.id] if table_receipt is not None else None
            facts = scenario_facts(draft, manifest, previous_manifest, table_catalog)
            pack, pages = build_work_pack(
                fixed_context,
                material_indices,
                context_file=str(context.get("rel_path") or ""),
                schema_file=str(schema.get("rel_path") or ""),
                mcp_config_file=mcp["file"] if mcp else None,
                platform_check_file=access_path,
                tables=table_catalog,
                tables_file=tables_file,
                scenario_facts=facts,
            )
            work_pack_file = await upload_work_pack(
                dataagent, topic_id, run_token, pack, pages
            )
            manifest["input_files"] = {
                "context": str(context.get("rel_path") or ""),
                "schema": str(schema.get("rel_path") or ""),
                "work_pack": work_pack_file,
                "materials": material_indices,
                "mcp": mcp["file"] if mcp else None,
                "run_access": access_path,
                "mcp_access": {"url": access["url"], "user_id": user.id},
                # Fixed for the run: the repair round reuses the same table structure.
                "tables": table_catalog,
                "tables_file": tables_file,
                "scenario_facts": facts,
            }
            proposal_prompt = proposal_instructions(
                work_pack_file=manifest["input_files"]["work_pack"],
                run_token=run_token,
                header=proposal_header(manifest),
                materials=material_indices,
                schema_file=str(schema.get("rel_path") or ""),
                mcp=mcp,
            )
        else:
            context_body = json.dumps(draft, ensure_ascii=False, indent=2).encode()
            context = await dataagent.upload(
                topic_id,
                f"ontofoundry-context-r{expected_revision}.json",
                context_body,
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
            proposal_prompt=proposal_prompt,
            context_bytes=len(context_body),
        )
        delivery_started = True
        submitted = await dataagent.deliver(
            topic_id=topic_id,
            content=prompt,
            agent_id=request.app.state.settings.dataagent_agent_id,
            execution_mode=request.app.state.settings.dataagent_execution_mode,
            # Plan mode is a modeling choice: the agent submits its plan and
            # waits for approval inside the same run.
            permission_mode=(body.settings.permission_mode or "default") if mode == "model" else None,
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
                    ModelingSessionRecord.task_status == "submitting",
                )
                .values(
                    task_status=status,
                    task_detail=_detail(upstream_status),
                    dataagent_topic_id=topic_id,
                    dataagent_task_id=task_id,
                    dataagent_task_mode=mode,
                    uploaded_material_ids=sorted(uploaded_ids | set(newly_uploaded)),
                    run_manifest_json={
                        **manifest,
                        "materials": [m for m in material_indices],
                    },
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


def _done_frame(run: dict[str, Any]) -> str:
    return "event: done\ndata: " + json.dumps(run, ensure_ascii=False, separators=(",", ":")) + "\n\n"


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
            decoder = codecs.getincrementaldecoder("utf-8")()
            saw_event = False
            async for chunk in dataagent.stream(task_id, cursor):
                buffer += decoder.decode(chunk)
                frames, buffer = _event_frames(buffer)
                for frame in frames:
                    payload = _data_payload(frame)
                    if payload is None:
                        continue
                    saw_event = True
                    with suppress(ValueError, TypeError):
                        event = json.loads(payload)
                        cursor = max(cursor, int(event.get("seq_id") or cursor))
                    yield f"event: agent-event\ndata: {redact_credentials(payload)}\n\n"

            buffer += decoder.decode(b"", final=True)
            payload = _data_payload(buffer)
            if payload is not None:
                saw_event = True
                with suppress(ValueError, TypeError):
                    event = json.loads(payload)
                    cursor = max(cursor, int(event.get("seq_id") or cursor))
                yield f"event: agent-event\ndata: {redact_credentials(payload)}\n\n"

            yield ": ping\n\n"
            # A pass-through of DataAgent's run: when its stream closes on a
            # live task, reconnect; once the task ends, say so. Turning the
            # result into proposals is the session's business, settled when
            # the session is read, never part of the conversation stream.
            task = await dataagent.task(task_id)
            upstream_status = str(task.get("task_status") or "")
            if upstream_status in ACTIVE_TASK_STATUSES:
                delay = 0.25 if saw_event else reconnect_delay
                await asyncio.sleep(delay)
                reconnect_delay = 0.25 if saw_event else min(delay * 2, 5.0)
                continue
            yield _done_frame(
                _run_ref(
                    task_id,
                    to_run_status(upstream_status),
                    mode=mode,
                    detail=_detail(upstream_status, task.get("error")),
                )
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
