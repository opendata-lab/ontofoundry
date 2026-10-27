"""Consume proposal-only DataAgent results with leases and idempotent storage."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, or_, update

from ontofoundry_api.contracts.proposals import (
    ProposalContractError,
    RunContext,
)
from ontofoundry_api.db_models import ModelingSessionRecord, utc_now
from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.proposal_apply import parse_agent
from ontofoundry_api.services.proposals import store_batch

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


def _permanent_detail(exc: DataAgentError) -> str:
    return f"建模结果下载失败：{exc}"


# Transient by status code. 429 matters most: a rate-limited file service is the
# one case where the result exists and is correct, and calling that permanent
# throws away a model the agent already produced. 408 and 425 are the same
# shape. Everything else — 404, a malformed body, a contract violation — is a
# statement about the result itself and will not improve by asking again.
_RETRIABLE_DOWNLOAD_STATUSES = frozenset({408, 425, 429})


def _is_retriable_download(status_code: int) -> bool:
    return status_code >= 500 or status_code in _RETRIABLE_DOWNLOAD_STATUSES


async def reconcile_run(
    app: Any,
    workspace_id: str,
    session_id: str,
    task_id: str | None = None,
) -> str:
    """Consume one successful model task, returning its result-state projection."""
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
                    ModelingSessionRecord.result_state == "failed_retriable",
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
        run_token = str(item.dataagent_run_token or "")
        manifest = dict(item.run_manifest_json or {})

    result_path = f"output/ontofoundry-result-{run_token}.json"
    try:
        content, _content_type = await _client(app, workspace_id, session_id).download(
            topic_id, result_path
        )
    except DataAgentError as exc:
        if exc.status_code == 404:
            # Questions and plan approval happen inside the run (DataAgent's
            # cards), so a finished run without a result produced nothing.
            return await _fail_with_workflow(
                app,
                workspace_id,
                session_id,
                task_id,
                claimed_at,
                topic_id=topic_id,
                manifest=manifest,
                detail="建模没有产出提案：智能体结束时没有写入结果文件，请重试或换个说法描述需求",
            )
        if _is_retriable_download(exc.status_code):
            return _finish_failure(
                app,
                session_id,
                task_id,
                claimed_at,
                state="failed_retriable",
                detail=f"建模结果下载暂时失败，等待重试：{exc}",
            )
        return _finish_failure(
            app,
            session_id,
            task_id,
            claimed_at,
            state="failed_permanent",
            detail=_permanent_detail(exc),
        )

    return await _consume_proposals(
        app,
        workspace_id,
        session_id,
        task_id,
        claimed_at,
        topic_id=topic_id,
        manifest=manifest,
        content=content,
    )


async def _consume_proposals(
    app: Any,
    workspace_id: str,
    session_id: str,
    task_id: str,
    claimed_at,
    *,
    topic_id: str,
    manifest: dict[str, Any],
    content: bytes,
) -> str:
    """Validate and store a complete batch within the result lease transaction."""
    if manifest.get("invalidated") or "pinned_draft" not in manifest:
        return _finish_failure(app, session_id, task_id, claimed_at,
            state="failed_permanent", detail="运行固定上下文已失效，请重新运行")
    context = RunContext(
        workspace_id=manifest["workspace_id"],
        session_id=manifest["session_id"],
        run_token=manifest["run_token"],
        base_version_id=manifest.get("base_version_id"),
        base_version_sha256=manifest["base_version_sha256"],
        source_session_revision=manifest["source_session_revision"],
        source_draft_sha256=manifest["source_draft_sha256"],
        draft=manifest["pinned_draft"],
        instance_baseline=manifest.get("instance_baseline", {}),
    )
    try:
        with app.state.session_factory() as db:
            from ontofoundry_api.services.session_gate import lock_session
            current = lock_session(db, workspace_id, session_id)
            if (current.dataagent_task_id != task_id
                or current.result_claimed_at is None
                or current.result_claimed_at.replace(tzinfo=claimed_at.tzinfo) != claimed_at
                or current.result_state != "processing"
                or (current.run_manifest_json or {}).get("invalidated")):
                return str(current.result_state or "")
            parsed = parse_agent(db, app.state.settings, current, content, context)
            store_batch(db, workspace_id=workspace_id, session_id=session_id,
                        task_id=task_id, manifest=manifest, parsed=parsed,
                        settings=app.state.settings)
            changed = db.execute(
                update(ModelingSessionRecord)
                .where(
                    ModelingSessionRecord.id == session_id,
                    ModelingSessionRecord.dataagent_task_id == task_id,
                    ModelingSessionRecord.last_result_task_id == task_id,
                    ModelingSessionRecord.result_state == "processing",
                    ModelingSessionRecord.result_claimed_at == claimed_at,
                )
                .values(
                    result_state="done",
                    result_warnings=[],
                    task_status="finished",
                    task_detail=f"已生成 {len(parsed.items)} 条提案，请在“提案”中审阅",
                    updated_at=utc_now(),
                )
            )
            if changed.rowcount != 1:
                db.rollback()
                return _current_result_state(app, session_id)
            db.commit()
    except (ServiceError, ProposalContractError) as exc:
        return await _fail_with_workflow(app, workspace_id, session_id, task_id, claimed_at,
            topic_id=topic_id, manifest=manifest, detail=f"提案结果被拒收：{exc}")
    except Exception:
        logger.exception("Unexpected proposal result validation failure")
        return _finish_failure(app, session_id, task_id, claimed_at,
            state="failed_permanent", detail="建模结果校验异常，请按本轮契约重新生成")
    return "done"


def exhaust_retriable_result(app: Any, session_id: str, task_id: str) -> str:
    """Turn an exhausted download retry loop into a visible terminal failure."""
    with app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session_id)
        if item is None:
            return ""
        detail = str(item.task_detail or "建模结果下载失败").replace(
            "等待重试", "重试三次后仍失败"
        )
        changed = db.execute(
            update(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session_id,
                ModelingSessionRecord.dataagent_task_id == task_id,
                ModelingSessionRecord.last_result_task_id == task_id,
                ModelingSessionRecord.result_state == "failed_retriable",
            )
            .values(
                result_state="failed_permanent",
                task_detail=detail,
                updated_at=utc_now(),
            )
        )
        db.commit()
        if changed.rowcount == 1:
            return "failed_permanent"
    return _current_result_state(app, session_id)
