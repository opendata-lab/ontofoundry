"""Modeling run lifecycle and idempotent result settlement."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import update

from ontofoundry_api.db_models import ModelingSessionRecord, utc_now
from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError
from ontofoundry_api.services.model_result import exhaust_retriable_result, reconcile_run
from ontofoundry_api.services.run_status import (
    ACTIVE_RUN_STATUSES,
    TERMINAL_RUN_STATUSES,
    to_run_status,
)

logger = logging.getLogger(__name__)

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


def _is_stale(updated_at: datetime) -> bool:
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return utc_now() - updated_at > timedelta(seconds=120)


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
                result_state="failed_permanent",
                run_manifest_json={**(item.run_manifest_json or {}), "invalidated": True},
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
        values = {"dataagent_task_id": task_id, "task_status": status, "task_detail": detail}
        if status in {"failed", "cancelled"}:
            current = db.get(ModelingSessionRecord, session_id)
            values.update(result_state="failed_permanent", last_result_task_id=task_id)
            if status == "cancelled" and current is not None:
                values["run_manifest_json"] = {**(current.run_manifest_json or {}), "invalidated": True}
        changed = db.execute(
            update(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session_id,
                ModelingSessionRecord.dataagent_task_id == task_id,
            )
            .values(**values, updated_at=utc_now())
        )
        db.commit()
    return status if changed.rowcount == 1 else None


def replacement_task_id(messages: list[dict[str, Any]], task_id: str) -> str | None:
    """The task DataAgent started to continue `task_id`'s turn, if any: the
    latest assistant message after it that belongs to another task."""
    seen = False
    found = None
    for message in messages:
        current = str(message.get("task_id") or "")
        if current == task_id:
            seen = True
        elif seen and current and message.get("sender_type") == "assistant":
            found = current
    return found


def _adopt_replacement(session_factory, session_id: str, old: str, new: str) -> bool:
    with session_factory() as db:
        changed = db.execute(
            update(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session_id,
                ModelingSessionRecord.dataagent_task_id == old,
            )
            .values(
                dataagent_task_id=new,
                task_status="running",
                task_detail="DataAgent 恢复了中断的任务，继续处理",
                updated_at=utc_now(),
            )
        )
        db.commit()
    return changed.rowcount == 1


async def _reconcile_stale_submission(
    app,
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
        with app.state.session_factory() as db:
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
        app.state.session_factory,
        item,
        detail="未找到上次提交对应的 DataAgent 任务，请重试",
    )
    return None, None


SYNCABLE_RUN_STATUSES = ACTIVE_RUN_STATUSES
_SYNC_INTERVAL_SECONDS = 3.0
_sync_lock = threading.Lock()
_syncing: set[str] = set()
_last_sync: dict[str, float] = {}


def needs_run_sync(app, item: ModelingSessionRecord) -> bool:
    """Whether a session's stored run state may lag DataAgent: a live task, or a
    finished model run whose result has not been claimed (or awaits a retry)."""
    if not app.state.settings.dataagent_base_url:
        return False
    if item.task_status == "submitting":
        return _is_stale(item.updated_at)
    if not item.dataagent_task_id:
        return False
    if item.task_status in SYNCABLE_RUN_STATUSES:
        return True
    return (
        item.task_status == "finished"
        and item.dataagent_task_mode == "model"
        and (
            item.last_result_task_id != item.dataagent_task_id
            or item.result_state in {"failed_retriable", "processing"}
        )
    )


async def sync_session_run(app, workspace_id: str, session_id: str) -> None:
    """Bring one session's run up to date without a conversation view open.

    Session reads schedule this after responding, so a run that finished while
    nobody watched still gets its status and its proposal batch. It reuses the
    view's guarded writes: a projection only lands on the task that still owns
    the session, and results are claimed under the result lease, so concurrent
    reads, views and workers converge on one outcome. Throttled per session.
    """
    now = time.monotonic()
    with _sync_lock:
        if (
            session_id in _syncing
            or now - _last_sync.get(session_id, -1e9) < _SYNC_INTERVAL_SECONDS
        ):
            return
        if len(_last_sync) > 1024:  # forget sessions no longer throttled
            for key in [
                k for k, at in _last_sync.items() if now - at >= _SYNC_INTERVAL_SECONDS
            ]:
                del _last_sync[key]
        _syncing.add(session_id)
        _last_sync[session_id] = now
    try:
        await _sync_session_run(app, workspace_id, session_id)
    except DataAgentError as exc:
        logger.warning("同步会话 %s 的 DataAgent 任务失败：%s", session_id, exc)
    finally:
        with _sync_lock:
            _syncing.discard(session_id)


async def settle_session_run(app, workspace_id: str, session_id: str) -> None:
    """Sync one session's run now, for a reader that needs its outcome.

    Unthrottled: the result lease keeps concurrent settlement to one writer,
    and a DataAgent outage leaves the stored state as it was."""
    try:
        await _sync_session_run(app, workspace_id, session_id)
    except DataAgentError as exc:
        logger.warning("同步会话 %s 的 DataAgent 任务失败：%s", session_id, exc)


async def _sync_session_run(app, workspace_id: str, session_id: str) -> None:
    with app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session_id)
        if (
            item is None
            or item.workspace_id != workspace_id
            or not needs_run_sync(app, item)
        ):
            return
        task_id = str(item.dataagent_task_id or "")
        topic_id = str(item.dataagent_topic_id or "")
        status = str(item.task_status or "")

    dataagent = _app_client(app, workspace_id, session_id)
    if status == "submitting":
        if not topic_id:
            _fail_stale_submission(app.state.session_factory, item, detail="上次提交未创建可对账的 DataAgent Topic，请重试")
            return
        try:
            recovered, task = await _reconcile_stale_submission(app, item, await dataagent.messages(topic_id), dataagent)
        except DataAgentError:
            _fail_stale_submission(app.state.session_factory, item, detail="上次提交超时，无法确认 DataAgent 任务，请重新发起")
            return
        if not recovered:
            return
        task_id = recovered
        status = to_run_status(str(task.get("task_status") or ""))
    if status in SYNCABLE_RUN_STATUSES:
        task = await dataagent.task(task_id)
        if (
            str(task.get("task_status") or "") == "suspended"
            and not task.get("cancel_requested_at")
            and topic_id
            and (
                replacement := replacement_task_id(
                    await dataagent.messages(topic_id), task_id
                )
            )
            and _adopt_replacement(
                app.state.session_factory, session_id, task_id, replacement
            )
        ):
            task_id = replacement
            task = await dataagent.task(replacement)
        upstream_status = str(task.get("task_status") or "")
        projected = _persist_task_projection(
            app.state.session_factory,
            session_id,
            task_id=task_id,
            upstream_status=upstream_status,
            detail=_detail(upstream_status, task.get("error")),
        )
        if projected is None or projected not in TERMINAL_RUN_STATUSES:
            return
    await settle_result(app, workspace_id, session_id, task_id)


async def settle_result(app, workspace_id: str, session_id: str, task_id: str) -> str:
    """Claim a finished run's result, retrying a transient download failure
    with backoff and failing visibly once the retries are spent."""
    result_state = await reconcile_run(app, workspace_id, session_id, task_id)
    if result_state in {"failed_retriable", "processing"}:
        for delay in (2, 4, 8):
            await asyncio.sleep(delay)
            result_state = await reconcile_run(app, workspace_id, session_id, task_id)
            if result_state not in {"failed_retriable", "processing"}:
                break
        if result_state == "failed_retriable":
            result_state = exhaust_retriable_result(app, session_id, task_id)
    return result_state


