"""Consume completed DataAgent modeling results as reviewable candidates.

The agent output is deliberately kept on the proposal side of the boundary:
this module never writes ``draft_json`` and never publishes an ontology.
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, or_, update

from ontofoundry_api.db_models import ModelingSessionRecord, utc_now
from ontofoundry_api.ossie.importer import OssieImportError, import_ossie
from ontofoundry_api.ossie.validator import validate_schema
from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError

RESULT_SCHEMA_VERSION = "ontofoundry.model-result/v1"
RESULT_LEASE = timedelta(minutes=5)
TOP_LEVEL_WARNING = (
    "本轮结果包含顶层本体约束变更，v1 不生成候选，"
    "如需应用请手工编辑或导入 Ossie 文件"
)
_CANDIDATE_COLLECTIONS = {
    "object_type": "object_types",
    "link_type": "link_types",
    "mapping": "mappings",
}
AnnotationIndex = dict[tuple[str, str], tuple[str, list[dict[str, Any]]]]


def _annotation_index(
    annotations: object, imported_draft: dict[str, Any]
) -> AnnotationIndex:
    result: AnnotationIndex = {}
    if not isinstance(annotations, list):
        return result
    object_keys = {
        str(item.get("id")): {
            str(item.get("technical_name") or ""),
            str(item.get("name") or ""),
        }
        for item in imported_draft.get("object_types", [])
        if isinstance(item, dict)
    }
    for annotation in annotations:
        if not isinstance(annotation, dict):
            continue
        target = annotation.get("target")
        if not isinstance(target, dict):
            continue
        kind = str(target.get("kind") or "")
        key = str(target.get("key") or "")
        if kind not in _CANDIDATE_COLLECTIONS or not key:
            continue
        evidence = annotation.get("evidence")
        if not isinstance(evidence, list) or any(
            not isinstance(item, dict) for item in evidence
        ):
            evidence = []
        result[(kind, key)] = (
            str(annotation.get("reason") or ""),
            deepcopy(evidence),
        )
        # Mappings are addressed by their owning Ossie concept, not an
        # implementation UUID. Keep the regular key above for forward
        # compatibility, and resolve the current mapping keys below.
        if kind == "mapping":
            for mapping in imported_draft.get("mappings", []):
                if not isinstance(mapping, dict):
                    continue
                if key in object_keys.get(str(mapping.get("type_id")), set()):
                    result[(kind, str(mapping.get("id") or ""))] = result[(kind, key)]
    return result


def build_candidates(
    before_draft: dict[str, Any],
    imported_draft: dict[str, Any],
    annotations: object,
    task_id: str,
) -> list[dict[str, Any]]:
    """Build deterministic type-level proposals from an imported merge result."""
    annotation_by_target = _annotation_index(annotations, imported_draft)
    candidates: list[dict[str, Any]] = []
    for kind, collection in _CANDIDATE_COLLECTIONS.items():
        before_by_id = {
            str(item.get("id")): item
            for item in before_draft.get(collection, [])
            if isinstance(item, dict) and item.get("id")
        }
        for value in imported_draft.get(collection, []):
            if not isinstance(value, dict) or not value.get("id"):
                continue
            value_id = str(value["id"])
            before = before_by_id.get(value_id)
            if before is not None and (kind == "mapping" or before == value):
                continue
            annotation_keys = (
                [value_id]
                if kind == "mapping"
                else [
                    str(value.get("technical_name") or ""),
                    str(value.get("name") or ""),
                ]
            )
            reason, evidence = next(
                (
                    annotation_by_target[(kind, key)]
                    for key in annotation_keys
                    if (kind, key) in annotation_by_target
                ),
                ("", []),
            )
            candidates.append(
                {
                    "id": f"{task_id}:{kind}:{value_id}",
                    "kind": kind,
                    "status": "pending",
                    "value": deepcopy(value),
                    "before": deepcopy(before),
                    "reason": reason,
                    "evidence": evidence,
                    "source_task_id": task_id,
                }
            )
    return candidates


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
    if _guarded_result_values(
        app, session_id, task_id, claimed_at, **values
    ):
        return state
    return _current_result_state(app, session_id)


def _permanent_detail(exc: DataAgentError, result_path: str) -> str:
    if exc.status_code == 404:
        return f"建模任务没有产出 `{result_path}`"
    return f"建模结果下载失败：{exc}"


def _top_level_changed(
    before_draft: dict[str, Any], imported_draft: dict[str, Any]
) -> bool:
    collections = set(_CANDIDATE_COLLECTIONS.values())
    before = {key: value for key, value in before_draft.items() if key not in collections}
    imported = {
        key: value for key, value in imported_draft.items() if key not in collections
    }
    return before != imported


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
        before_draft = deepcopy(item.draft_json)
        old_candidates = deepcopy(item.candidates_json or [])
        old_warnings = deepcopy(item.result_warnings or [])
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
        imported_draft, _report = import_ossie(
            payload["ontology"],
            workspace_id=workspace_id,
            base=before_draft,
            mode="merge",
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

    candidates = build_candidates(
        before_draft,
        imported_draft,
        payload.get("annotations", []),
        task_id,
    )
    retained = []
    for candidate in old_candidates:
        candidate = deepcopy(candidate)
        if candidate.get("status") == "pending":
            candidate["status"] = "superseded"
        retained.append(candidate)
    warnings = old_warnings
    if _top_level_changed(before_draft, imported_draft):
        warnings = [*warnings, TOP_LEVEL_WARNING]

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
                candidates_json=[*retained, *candidates],
                result_warnings=warnings,
                result_state="done",
                task_status="finished",
                task_detail="DataAgent 处理完成",
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
                    state="failed_retriable",
                    detail="候选写入前草稿已更新，正在基于最新草稿重试",
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
