"""Settle finished modeling runs: report a run that submitted no batch."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, or_, update

from ontofoundry_api.db_models import ModelingSessionRecord, utc_now
from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError
from ontofoundry_api.services.proposals import batch_item_count, submitted_batch

logger = logging.getLogger(__name__)

RESULT_LEASE = timedelta(minutes=5)


def _client(app: Any, workspace_id: str, session_id: str) -> DataAgentClient:
    settings = app.state.settings
    return DataAgentClient(
        settings.dataagent_base_url,
        prefix=settings.dataagent_api_prefix,
        website_id=settings.dataagent_website_id,
        access_key=settings.dataagent_access_key,
        session_ref=f"ontofoundry:{workspace_id}:{session_id}",
        timeout_seconds=settings.dataagent_request_timeout_seconds,
    )


def _guarded_result_values(
    app: Any,
    session_id: str,
    task_id: str,
    claimed_at,
    **values: Any,
) -> bool:
    """Write only while this worker still owns the exact result lease."""
    with app.state.session_factory() as db:
        changed = db.execute(
            update(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session_id,
                ModelingSessionRecord.dataagent_task_id == task_id,
                ModelingSessionRecord.last_result_task_id == task_id,
                ModelingSessionRecord.result_state == "processing",
                ModelingSessionRecord.result_claimed_at == claimed_at,
            )
            .values(**values, updated_at=utc_now())
        )
        db.commit()
        return changed.rowcount == 1


def _current_result_state(app: Any, session_id: str) -> str:
    with app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session_id)
        return str(item.result_state or "") if item is not None else ""


def _finish_failure(
    app: Any,
    session_id: str,
    task_id: str,
    claimed_at,
    *,
    state: str,
    detail: str,
) -> str:
    values: dict[str, Any] = {"result_state": state, "task_detail": detail}
    if _guarded_result_values(app, session_id, task_id, claimed_at, **values):
        return state
    return _current_result_state(app, session_id)


# Stepwise modeling keeps intermediate files in the agent workspace under
# modeling/ (harness design §11 items 14/15).
WORKFLOW_DIR = "modeling/"
PART_FILES = tuple(
    "parts/" + name
    for name in (
        "01-types.json",
        "02-links.json",
        "03-datasets.json",
        "04-metrics-rules.json",
        "05-facts.json",
    )
)
EXCERPT_LIMIT = 4 * 1024


async def _optional_download(client: DataAgentClient, topic_id: str, path: str) -> bytes | None:
    """A workflow file, or None when it is absent or cannot be read now."""
    try:
        content, _ = await client.download(topic_id, path)
    except DataAgentError as exc:
        if exc.status_code != 404:
            logger.info("Workflow file %s unavailable: %s", path, exc)
        return None
    return content


def _text(content: bytes, limit: int) -> str:
    return content[:limit].decode("utf-8", "ignore")


async def workflow_diagnostics(client: DataAgentClient, topic_id: str) -> list[dict[str, Any]]:
    """Which workflow files exist; plan and notes keep a short excerpt."""
    found = []
    for name in ("plan.md", "notes.md", *PART_FILES):
        content = await _optional_download(client, topic_id, WORKFLOW_DIR + name)
        if content is None:
            continue
        entry: dict[str, Any] = {"path": WORKFLOW_DIR + name, "bytes": len(content)}
        if name.endswith(".md"):
            entry["excerpt"] = _text(content, EXCERPT_LIMIT)
        found.append(entry)
    return found


async def _fail_with_workflow(
    app: Any,
    workspace_id: str,
    session_id: str,
    task_id: str,
    claimed_at,
    *,
    topic_id: str,
    manifest: dict[str, Any],
    detail: str,
) -> str:
    """A permanent failure that also keeps the workflow files as diagnostics."""
    found = await workflow_diagnostics(_client(app, workspace_id, session_id), topic_id)
    values: dict[str, Any] = {
        "result_state": "failed_permanent",
        "task_detail": detail
        + ("；已取回中间文件：" + "、".join(f["path"] for f in found) if found else ""),
    }
    if found:
        values["run_manifest_json"] = {**manifest, "workflow_diagnostics": found}
    if _guarded_result_values(app, session_id, task_id, claimed_at, **values):
        return "failed_permanent"
    return _current_result_state(app, session_id)


async def reconcile_run(
    app: Any,
    workspace_id: str,
    session_id: str,
    task_id: str | None = None,
) -> str:
    """Settle one finished model task: its batch was stored when the agent
    submitted it (SC-05), so only the absence of a batch is left to report."""
    with app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session_id)
        if item is None or item.workspace_id != workspace_id:
            return ""
        current_task_id = str(item.dataagent_task_id or "")
        if task_id is not None and current_task_id != task_id:
            return str(item.result_state or "")
        task_id = current_task_id
        if item.task_status != "finished" or not task_id:
            return str(item.result_state or "")
        if item.dataagent_task_mode != "model":
            return str(item.result_state or "")

        claimed_at = utc_now()
        claimed = db.execute(
            update(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session_id,
                ModelingSessionRecord.dataagent_task_id == task_id,
                or_(
                    ModelingSessionRecord.last_result_task_id.is_distinct_from(task_id),
                    and_(
                        ModelingSessionRecord.result_state == "processing",
                        ModelingSessionRecord.result_claimed_at < claimed_at - RESULT_LEASE,
                    ),
                ),
            )
            .values(
                result_state="processing",
                last_result_task_id=task_id,
                result_claimed_at=claimed_at,
                updated_at=claimed_at,
            )
        )
        db.commit()
        if claimed.rowcount != 1:
            db.refresh(item)
            return str(item.result_state or "")

        topic_id = str(item.dataagent_topic_id or "")
        manifest = dict(item.run_manifest_json or {})
        submitted = submitted_batch(db, workspace_id, session_id, item.dataagent_run_token)
        count = batch_item_count(db, submitted) if submitted is not None else 0

    if submitted is not None:
        if _guarded_result_values(
            app, session_id, task_id, claimed_at,
            result_state="done", result_warnings=[], task_status="finished",
            task_detail=f"已生成 {count} 条提案，请在“提案”中审阅",
        ):
            return "done"
        return _current_result_state(app, session_id)
    return await _fail_with_workflow(
        app,
        workspace_id,
        session_id,
        task_id,
        claimed_at,
        topic_id=topic_id,
        manifest=manifest,
        detail="建模没有产出提案：本轮没有提交通过检查的结果，请重试或换个说法描述需求",
    )
