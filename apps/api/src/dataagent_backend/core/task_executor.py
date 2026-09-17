from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx
from dataagent_backend.config import get_settings, resolve_workspace_scratch_dirs

from dataagent_backend.core.agent_profile_service import normalize_agent_snapshot
from dataagent_backend.core.context_governance import build_governance_settings
from dataagent_backend.core.provider_runtime import build_provider_env, normalize_api_format
from dataagent_backend.core.runtime_support import (
    build_mcp_servers,
    build_runtime_env,
    build_system_prompt,
    default_model_for_provider,
    resolve_agent_skill_runtime,
    resolve_max_turns,
)
from dataagent_backend.core.skill_admin_service import (
    resolve_enabled_skill_runtime,
    resolve_runtime_provider_selection,
)
from dataagent_backend.core.task_control import PARKED_TASK_STATUSES, CancelReason
from dataagent_backend.core.task_status import from_engine_outcome as task_status_from_engine_outcome
from dataagent_backend.core.topic_task_store import get_topic_task_store
from dataagent_backend.core.topic_workspace import prepare_topic_workspace

logger = logging.getLogger(__name__)


@dataclass
class TaskExecutionInput:
    """One DataAgent run assembled by the coordinator."""

    task_id: str
    topic_id: str
    question: str
    history: list[dict[str, str]]
    resume_session_id: str | None
    provider_id: str
    model: str
    database_hint: str | None
    debug: bool = False
    timeout_seconds: int | None = None
    sql_read_timeout_seconds: int | None = None
    sql_write_timeout_seconds: int | None = None
    execution_mode: str = "background"
    agent_snapshot: dict[str, Any] | None = None
    permission_mode: str | None = None


@dataclass
class TaskExecutionResult:
    task_status: str
    content: str
    usage: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    provider_id: str = ""
    model: str = ""
    session_id: str = ""


async def execute_task_stream(
    params: TaskExecutionInput,
    *,
    emit: Callable[[dict[str, Any]], Awaitable[None] | None],
    is_cancel_requested: Callable[[], Awaitable[Any] | Any] | None = None,
) -> TaskExecutionResult:
    """Execute a run through the only supported engine: the Pi Cell."""
    cfg = get_settings()
    if _should_use_sandbox_runner(cfg):
        return await _execute_task_stream_via_runner(
            params,
            emit=emit,
            is_cancel_requested=is_cancel_requested,
        )
    return await _execute_task_stream_local(
        params,
        emit=emit,
        is_cancel_requested=is_cancel_requested,
    )


def _should_use_sandbox_runner(cfg: Any) -> bool:
    return bool(str(getattr(cfg, "dataagent_sandbox_mode", "") or "").strip())


def _normalize_cancel_reason(value: Any) -> CancelReason | None:
    if isinstance(value, str):
        reason = value.strip()
        return reason if reason in {"user_cancel", "runner_stop"} else None  # type: ignore[return-value]
    return "user_cancel" if bool(value) else None


def _task_is_parked(task_id: str) -> bool:
    try:
        task = get_topic_task_store().get_task(task_id)
    except Exception:
        logger.warning("task.cancel_watch: failed to read task status task_id=%s", task_id, exc_info=True)
        return False
    return str((task or {}).get("task_status") or "") in PARKED_TASK_STATUSES


async def _execute_task_stream_via_runner(
    params: TaskExecutionInput,
    *,
    emit: Callable[[dict[str, Any]], Awaitable[None] | None],
    is_cancel_requested: Callable[[], Awaitable[Any] | Any] | None = None,
) -> TaskExecutionResult:
    cfg = get_settings()
    runner_url = str(getattr(cfg, "dataagent_sandbox_runner_url", "") or "").strip().rstrip("/")
    if not runner_url:
        raise RuntimeError("DATAAGENT_SANDBOX_RUNNER_URL is required when DATAAGENT_SANDBOX_MODE is enabled")

    endpoint = f"{runner_url}/internal/sandbox/runs"
    request_payload = asdict(params)
    cancel_sent = False
    stream_done = False

    async def _cancel_reason() -> CancelReason | None:
        if is_cancel_requested is None:
            return None
        result = is_cancel_requested()
        if inspect.isawaitable(result):
            result = await result
        return _normalize_cancel_reason(result)

    async def _emit(record: dict[str, Any]) -> None:
        result = emit(record)
        if inspect.isawaitable(result):
            await result

    async with httpx.AsyncClient(timeout=None) as client:

        async def _watch_cancel() -> None:
            nonlocal cancel_sent
            while not stream_done:
                reason = await _cancel_reason()
                if not cancel_sent and reason:
                    cancel_sent = True
                    cancel_payload: dict[str, Any] = {"task_id": params.task_id, "reason": reason}
                    if reason == "user_cancel" and _task_is_parked(params.task_id):
                        cancel_payload["kill"] = False
                    await client.post(
                        f"{runner_url}/internal/sandbox/runs/{params.task_id}/cancel",
                        json=cancel_payload,
                    )
                    return
                await asyncio.sleep(0.25)

        cancel_task = asyncio.create_task(_watch_cancel())
        try:
            async with client.stream("POST", endpoint, json=request_payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not str(line or "").strip():
                        continue
                    message = json.loads(line)
                    message_type = str(message.get("type") or "")
                    if message_type == "record":
                        record = message.get("record") or {}
                        if isinstance(record, dict):
                            await _emit(record)
                    elif message_type == "result":
                        value = message.get("result") or {}
                        if not isinstance(value, dict):
                            break
                        return TaskExecutionResult(
                            task_status=str(value.get("task_status") or "error"),
                            content=str(value.get("content") or ""),
                            usage=value.get("usage") if isinstance(value.get("usage"), dict) else None,
                            error=value.get("error") if isinstance(value.get("error"), dict) else None,
                            provider_id=str(value.get("provider_id") or ""),
                            model=str(value.get("model") or ""),
                            session_id=str(value.get("session_id") or ""),
                        )
        finally:
            stream_done = True
            cancel_task.cancel()
            try:
                await cancel_task
            except asyncio.CancelledError:
                pass

    return TaskExecutionResult(
        task_status="error",
        content="sandbox runner stream ended without a result",
        error={"code": "sandbox_runner_no_result", "message": "sandbox runner stream ended without a result"},
        provider_id=params.provider_id,
        model=params.model,
    )


async def _execute_pi(
    params: TaskExecutionInput,
    *,
    provider_id: str,
    model: str,
    system_prompt: str,
    skill_runtime: dict[str, Any],
    project_cwd: Path,
    runtime_env: dict[str, str],
    provider_env: dict[str, str],
    agent_snapshot: dict[str, Any] | None,
    cancel_reason: Callable[[], Awaitable[CancelReason | None]],
) -> TaskExecutionResult:
    from dataagent_backend.core.agent_event_writer import AgentEventWriter
    from dataagent_backend.core.boundary_policy import build_boundary_policy
    from dataagent_backend.core.pi_runtime import (
        PiRunContext,
        PiRuntimeUnavailable,
        execute_pi_run,
        resolve_cell_command,
    )

    cfg = get_settings()
    writer = AgentEventWriter(get_topic_task_store(), params.task_id, params.topic_id)

    history: list[dict[str, str]] = []
    messages: list[dict[str, str]] = []
    for item in params.history or []:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        entry = {"role": "user" if item.get("role") == "user" else "assistant", "content": content}
        messages.append(entry)
        history.append(entry)
    question = str(params.question or "").strip()
    messages.append({"role": "user", "content": question})

    raw_mcp_servers = build_mcp_servers(
        (agent_snapshot or {}).get("mcp_server_ids") if agent_snapshot else None,
    )
    mcp_servers = [
        {
            "name": name,
            "url": conf.get("url"),
            "type": conf.get("type", "http"),
            "headers": conf.get("headers", {}),
            "command": conf.get("command"),
            "args": conf.get("args", []),
            "env": conf.get("env", {}),
        }
        for name, conf in (raw_mcp_servers or {}).items()
    ]

    try:
        cell_command = resolve_cell_command(cfg)
    except PiRuntimeUnavailable as exc:
        reason = str(exc)
        writer.append_error(code="pi_runtime_missing", message=reason)
        return TaskExecutionResult(
            task_status="error",
            content=reason,
            error={"code": "pi_runtime_missing", "message": reason},
            provider_id=provider_id,
            model=model,
        )

    ctx = PiRunContext(
        task_id=params.task_id,
        topic_id=params.topic_id,
        provider_id=provider_id,
        model=model,
        system_prompt=system_prompt,
        messages=messages,
        history=history,
        prompt=question,
        project_cwd=project_cwd,
        boundary_policy=build_boundary_policy(
            project_cwd,
            skill_runtime,
            resolve_workspace_scratch_dirs(cfg),
            runtime_env,
        ),
        runtime_env=dict(runtime_env),
        provider_env=dict(provider_env),
        skills=[
            {"name": name, "root_path": str(root)}
            for name, root in dict((skill_runtime or {}).get("enabled_roots") or {}).items()
        ],
        mcp_servers=mcp_servers,
        total_timeout_seconds=int(params.timeout_seconds or 0)
        or int(getattr(cfg, "dataagent_run_total_timeout_seconds", 600)),
        idle_timeout_seconds=int(getattr(cfg, "dataagent_run_idle_timeout_seconds", 300)),
        governance_settings=build_governance_settings(cfg),
        max_turns=resolve_max_turns(
            cfg,
            params.execution_mode,
            int((agent_snapshot or {}).get("max_turns") or 0),
        ),
    )
    outcome = await execute_pi_run(
        ctx,
        writer=writer,
        cancel_reason=cancel_reason,
        cell_command=cell_command,
    )
    session_id = f"pi-{params.topic_id}-{params.task_id}"
    if outcome.terminal_status in {"success", "cancelled"}:
        return TaskExecutionResult(
            task_status=task_status_from_engine_outcome(outcome.terminal_status),
            content=outcome.answer,
            usage=outcome.usage,
            provider_id=provider_id,
            model=model,
            session_id=session_id,
        )
    return TaskExecutionResult(
        task_status="error",
        content=outcome.answer or outcome.error_message,
        usage=outcome.usage,
        error={"code": outcome.error_code or "pi_runtime_error", "message": outcome.error_message},
        provider_id=provider_id,
        model=model,
        session_id=session_id,
    )


async def _execute_task_stream_local(
    params: TaskExecutionInput,
    *,
    emit: Callable[[dict[str, Any]], Awaitable[None] | None],
    is_cancel_requested: Callable[[], Awaitable[Any] | Any] | None = None,
    prepared_workspace_dir: str | Path | None = None,
) -> TaskExecutionResult:
    del emit
    cfg = get_settings()
    runtime_target = resolve_runtime_provider_selection(params.provider_id, params.model)
    # provider_id still names the vendor, which is all it is used for below
    # (default model, telemetry). It no longer decides the wire protocol —
    # api_format does, and it is stored rather than guessed from the base URL.
    provider_id = str(runtime_target.get("provider_id") or "").strip()
    api_format = normalize_api_format(runtime_target.get("api_format"))
    model = str(runtime_target.get("model") or cfg.claude_model or "").strip()
    if not model:
        model = default_model_for_provider(provider_id)

    async def _cancel_reason() -> CancelReason | None:
        if is_cancel_requested is None:
            return None
        result = is_cancel_requested()
        if inspect.isawaitable(result):
            result = await result
        return _normalize_cancel_reason(result)

    agent_snapshot = normalize_agent_snapshot(params.agent_snapshot) if params.agent_snapshot else None
    skill_runtime = resolve_agent_skill_runtime(agent_snapshot, resolve_enabled_skill_runtime())
    system_prompt = build_system_prompt(params.database_hint, skill_runtime, agent_snapshot)
    provider_env = build_provider_env(
        api_format,
        api_key=str(runtime_target.get("api_key") or ""),
        auth_token=str(runtime_target.get("auth_token") or ""),
        base_url=str(runtime_target.get("base_url") or ""),
    )
    runtime_env = build_runtime_env(cfg, provider_env, params, skill_runtime)
    for key, value in runtime_env.items():
        os.environ[key] = value

    enabled_folders = skill_runtime.get("enabled_folders") or []
    workspace_dir = str(prepared_workspace_dir or "").strip()
    project_cwd = prepare_topic_workspace(
        params.topic_id,
        enabled_folders,
        allow_empty=bool(agent_snapshot) or not enabled_folders,
        workspace_dir=workspace_dir or None,
    )
    runtime_env.pop("DATAAGENT_WORKSPACE_DIR", None)
    runtime_env.pop("DATAAGENT_WORKSPACE_PREPARED", None)
    runtime_env["PWD"] = str(project_cwd)
    os.environ["PWD"] = str(project_cwd)

    logger.info(
        "task.start task_id=%s topic_id=%s engine=pi_agent_core provider=%s model=%s cwd=%s",
        params.task_id,
        params.topic_id,
        provider_id,
        model,
        project_cwd,
    )
    return await _execute_pi(
        params,
        provider_id=provider_id,
        model=model,
        system_prompt=system_prompt,
        skill_runtime=skill_runtime,
        project_cwd=project_cwd,
        runtime_env=runtime_env,
        provider_env=provider_env,
        agent_snapshot=agent_snapshot,
        cancel_reason=_cancel_reason,
    )
