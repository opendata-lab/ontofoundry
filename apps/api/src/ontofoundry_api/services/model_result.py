"""Consume a completed DataAgent result as a complete version draft.

The generated ontology replaces the modeling session's draft as one atomic
snapshot.  Publishing remains a separate, explicit user action.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import and_, or_, update

from ontofoundry_api.db_models import ModelingSessionRecord, utc_now
from ontofoundry_api.ossie.importer import OssieImportError, import_ossie
from ontofoundry_api.ossie.validator import validate_schema
from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError

RESULT_SCHEMA_VERSION = "ontofoundry.model-result/v1"
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


def _result_warnings(import_report: dict[str, Any]) -> list[str]:
    """Everything the import could not carry over, in one list for the user.

    Only `notes` used to be kept, which dropped exactly the actionable half:
    `skipped` is where "this relation has no data join because that concept has
    no mapping" lives. Without it the draft silently came back smaller than the
    agent described and nothing said why.
    """
    warnings = [str(note) for note in import_report.get("notes") or []]
    for item in import_report.get("skipped") or []:
        reason = str(item.get("reason") or "").strip()
        path = str(item.get("path") or "").strip()
        text = f"{path}：{reason}" if path and reason else reason or path
        if text and text not in warnings:
            warnings.append(text)
    return warnings


def _first_validation_message(exc: ValidationError) -> str:
    """The one line worth showing a user out of a pydantic error report.

    The raw report repeats the whole rejected document, which for an ontology is
    thousands of characters of noise around a one-sentence reason.
    """
    for error in exc.errors():
        message = str(error.get("msg") or "").removeprefix("Value error, ").strip()
        if message:
            return message
    return "草稿校验未通过"


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
    if _guarded_result_values(
        app, session_id, task_id, claimed_at, **values
    ):
        return state
    return _current_result_state(app, session_id)


def _permanent_detail(exc: DataAgentError, result_path: str) -> str:
    if exc.status_code == 404:
        return f"建模任务没有产出 `{result_path}`"
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
                        ModelingSessionRecord.result_claimed_at
                        < claimed_at - RESULT_LEASE,
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
        revision = item.revision

    result_path = f"output/ontofoundry-result-{run_token}.json"
    try:
        content, _content_type = await _client(
            app, workspace_id, session_id
        ).download(topic_id, result_path)
    except DataAgentError as exc:
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
            detail=_permanent_detail(exc, result_path),
        )

    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
        return _finish_failure(
            app,
            session_id,
            task_id,
            claimed_at,
            state="failed_permanent",
            detail="建模结果不是有效的 JSON 文件",
        )

    detail = ""
    if not isinstance(payload, dict):
        detail = "建模结果 JSON 顶层必须是对象"
    elif payload.get("schema_version") != RESULT_SCHEMA_VERSION:
        detail = f"建模结果 schema_version 必须是 {RESULT_SCHEMA_VERSION}"
    elif payload.get("run_token") != run_token:
        detail = "建模结果 run_token 与当前会话不符"
    elif not isinstance(payload.get("ontology"), dict):
        detail = "建模结果缺少完整的 Apache Ossie ontology 对象"
    if detail:
        return _finish_failure(
            app,
            session_id,
            task_id,
            claimed_at,
            state="failed_permanent",
            detail=detail,
        )

    schema_issues = validate_schema(payload["ontology"])
    if schema_issues:
        first = schema_issues[0]
        return _finish_failure(
            app,
            session_id,
            task_id,
            claimed_at,
            state="failed_permanent",
            detail=(
                "建模结果不符合 Apache Ossie 0.2.0.dev0 schema："
                + str(first.get("message") or first)
            ),
        )

    try:
        version_draft, import_report = import_ossie(
            payload["ontology"],
            workspace_id=workspace_id,
            mode="replace",
        )
    except OssieImportError as exc:
        return _finish_failure(
            app,
            session_id,
            task_id,
            claimed_at,
            state="failed_permanent",
            detail=f"建模结果无法导入：{exc}",
        )
    except ValidationError as exc:
        # The document passed the Ossie schema but breaks a draft invariant of
        # ours — an agent may, for instance, map a link whose endpoint objects
        # have no data mapping. Only OssieImportError was caught here, so this
        # escaped as a 500 out of whichever request happened to be reconciling,
        # and the lease stayed held with result_state parked on "processing":
        # the conversation became unreadable and the run never resolved.
        #
        # Re-running the same file cannot change the outcome, so it is
        # permanent: the agent has to produce a different model.
        return _finish_failure(
            app,
            session_id,
            task_id,
            claimed_at,
            state="failed_permanent",
            detail=f"建模结果不满足草稿约束：{_first_validation_message(exc)}",
        )

    with app.state.session_factory() as db:
        changed = db.execute(
            update(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == session_id,
                ModelingSessionRecord.dataagent_task_id == task_id,
                ModelingSessionRecord.last_result_task_id == task_id,
                ModelingSessionRecord.result_state == "processing",
                ModelingSessionRecord.result_claimed_at == claimed_at,
                ModelingSessionRecord.revision == revision,
            )
            .values(
                draft_json=version_draft,
                candidates_json=[],
                result_warnings=_result_warnings(import_report),
                result_state="done",
                task_status="finished",
                task_detail="完整建模结果已生成，请预览差异后发布新版本",
                revision=revision + 1,
                updated_at=utc_now(),
            )
        )
        db.commit()
        if changed.rowcount != 1:
            state = _current_result_state(app, session_id)
            if state == "processing":
                return _finish_failure(
                    app,
                    session_id,
                    task_id,
                    claimed_at,
                    state="failed_permanent",
                    detail="新版本草稿写入前会话已更新，请重新运行建模",
                )
            return state
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
