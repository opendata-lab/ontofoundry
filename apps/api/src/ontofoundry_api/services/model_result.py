"""Consume proposal-only DataAgent results with leases and idempotent storage."""

from __future__ import annotations

import hashlib
import json
import secrets
from contextlib import suppress
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, or_, select, update

from ontofoundry_api.contracts.proposals import (
    ProposalContractError,
    RunContext,
    parse_result,
)
from ontofoundry_api.db_models import ModelingSessionRecord, utc_now
from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.model_review import (
    build_proposal_repair_request,
)
from ontofoundry_api.services.proposals import (
    proposal_header,
    store_batch,
    store_failed_batch,
)

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
    if state == "failed_permanent":
        values["task_status"] = "failed"
    if _guarded_result_values(app, session_id, task_id, claimed_at, **values):
        return state
    return _current_result_state(app, session_id)


async def _request_repair(
    app: Any,
    workspace_id: str,
    session_id: str,
    task_id: str,
    claimed_at,
    *,
    topic_id: str,
    problems: list[str],
    manifest: dict[str, Any] | None = None,
) -> str | None:
    """Hand the complaints back to the agent and let it produce a fix.

    Returns the new result-state on success, or None when the caller should fall
    through to its own ending — no topic, or DataAgent refused the turn. Failing
    to ask must never be worse than not trying: the original outcome still
    applies.

    The claim is released only after DataAgent accepts the follow-up, so a
    refusal leaves the lease exactly as it was.
    """
    if not topic_id or not problems:
        return None

    next_token = secrets.token_hex(16)
    result_path = f"output/ontofoundry-result-{next_token}.json"
    next_manifest = {**manifest, "run_token": next_token} if manifest else None
    if next_manifest is None:
        return None
    content = build_proposal_repair_request(
        problems, proposal_header(next_manifest), result_path
    )
    try:
        submitted = await _client(app, workspace_id, session_id).deliver(
            topic_id=topic_id,
            content=content,
            agent_id=app.state.settings.dataagent_agent_id,
            execution_mode=app.state.settings.dataagent_execution_mode,
        )
    except DataAgentError:
        return None

    next_task_id = str(submitted.get("task_id") or "")
    if not next_task_id:
        return None

    # The new task becomes the session's run. `last_result_task_id` stays on the
    # task being abandoned so this result is never consumed again, and
    # result_state clears so the next reconcile can claim the new one.
    if not _guarded_result_values(
        app,
        session_id,
        task_id,
        claimed_at,
        dataagent_task_id=next_task_id,
        dataagent_run_token=next_token,
        **({"run_manifest_json": next_manifest} if next_manifest else {}),
        result_state="",
        result_claimed_at=None,
        task_status="running",
        task_detail="结果未通过校验，已把问题交回 DataAgent 修正",
    ):
        return _current_result_state(app, session_id)
    return ""


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
            # Only an explicit marker for this run means the agent is waiting.
            needs_input_path = f"output/ontofoundry-needs-input-{run_token}.json"
            marker = None
            try:
                marker_content, _ = await _client(app, workspace_id, session_id).download(
                    topic_id, needs_input_path
                )
            except DataAgentError as marker_exc:
                if _is_retriable_download(marker_exc.status_code):
                    return _finish_failure(
                        app,
                        session_id,
                        task_id,
                        claimed_at,
                        state="failed_retriable",
                        detail=f"建模结果下载暂时失败，等待重试：{marker_exc}",
                    )
                if marker_exc.status_code != 404:
                    return _finish_failure(
                        app,
                        session_id,
                        task_id,
                        claimed_at,
                        state="failed_permanent",
                        detail=_permanent_detail(marker_exc),
                    )
            else:
                with suppress(UnicodeDecodeError, json.JSONDecodeError, TypeError):
                    marker = json.loads(marker_content)

            what = "提案"
            if not (
                isinstance(marker, dict)
                and marker.get("run_token") == run_token
                and isinstance(marker.get("questions"), list)
                and marker["questions"]
                and all(isinstance(question, str) for question in marker["questions"])
            ):
                return _finish_failure(
                    app,
                    session_id,
                    task_id,
                    claimed_at,
                    state="failed_permanent",
                    detail=f"建模没有产出{what}：智能体结束时没有写入结果文件，请重试或换个说法描述需求",
                )
            if _guarded_result_values(
                app,
                session_id,
                task_id,
                claimed_at,
                result_state="awaiting_reply",
                task_detail=f"智能体需要你确认后才能生成{what}，请在对话中回复",
            ):
                return "awaiting_reply"
            return _current_result_state(app, session_id)
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
    """Store an ontofoundry.proposals/v1 result as a batch. Never touches the
    draft: a session edited during the run only makes affected items stale."""
    context = RunContext(
        workspace_id=manifest["workspace_id"],
        session_id=manifest["session_id"],
        run_token=manifest["run_token"],
        base_version_id=manifest.get("base_version_id"),
        base_version_sha256=manifest["base_version_sha256"],
        source_session_revision=manifest["source_session_revision"],
        source_draft_sha256=manifest["source_draft_sha256"],
        draft=manifest["pinned_draft"],
    )
    with app.state.session_factory() as db:
        lookup = material_lookup(db, app.state.settings, workspace_id)
        try:
            parsed = parse_result(content, context, material_lookup=lookup)
        except ProposalContractError as exc:
            parsed, failure = None, exc
    if parsed is None:
        repaired = await _request_repair(
            app,
            workspace_id,
            session_id,
            task_id,
            claimed_at,
            topic_id=topic_id,
            problems=[f"{failure.code}：{failure}"],
            manifest=manifest,
        )
        if repaired is not None:
            return repaired
        with app.state.session_factory() as db:
            current = db.scalar(
                select(ModelingSessionRecord)
                .where(
                    ModelingSessionRecord.id == session_id,
                    ModelingSessionRecord.dataagent_task_id == task_id,
                    ModelingSessionRecord.result_claimed_at == claimed_at,
                )
                .with_for_update()
            )
            if current is None:
                return _current_result_state(app, session_id)
            store_failed_batch(
                db,
                workspace_id=workspace_id,
                session_id=session_id,
                task_id=task_id,
                manifest=manifest,
                result_sha256=hashlib.sha256(content).hexdigest(),
                code=failure.code,
                message=str(failure),
            )
            db.commit()
        return _finish_failure(
            app,
            session_id,
            task_id,
            claimed_at,
            state="failed_permanent",
            detail=f"提案结果被拒收：{failure}",
        )

    with app.state.session_factory() as db:
        current = db.scalar(
            select(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session_id,
                ModelingSessionRecord.dataagent_task_id == task_id,
                ModelingSessionRecord.result_claimed_at == claimed_at,
            )
            .with_for_update()
        )
        if current is None:
            return _current_result_state(app, session_id)
        store_batch(
            db,
            workspace_id=workspace_id,
            session_id=session_id,
            task_id=task_id,
            manifest=manifest,
            parsed=parsed,
        )
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
                task_status="failed",
                task_detail=detail,
                updated_at=utc_now(),
            )
        )
        db.commit()
        if changed.rowcount == 1:
            return "failed_permanent"
    return _current_result_state(app, session_id)
