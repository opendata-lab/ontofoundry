"""Validate preview contexts and execute without writing a session or version."""

from datetime import datetime

from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.domain.canonical import domain_sha256
from ontofoundry_api.domain.core import CoreDraft, RatioMetric
from ontofoundry_api.domain.snapshot import empty_snapshot
from ontofoundry_api.domain.validation import validate_core_graph
from ontofoundry_api.services.access import can_read_instances, can_read_mappings
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.metric_query import (
    execute_metric_preview,
    value_kind,
)
from ontofoundry_api.services.ontology_query import current_version, snapshot_of
from ontofoundry_api.services.workspaces import get_workspace, membership_role


def preview_metric(db, workspace_id, user, body, settings):
    space = get_workspace(db, workspace_id)
    if not membership_role(db, workspace_id, user.id):
        raise ServiceError(
            "仅空间成员可预览指标", code="MAPPINGS_FORBIDDEN", status_code=403
        )
    if (
        "expected_current_version_id" in body.model_fields_set
        and body.expected_current_version_id != space.current_version_id
    ):
        raise ServiceError("发布版已更新", code="VERSION_CHANGED", status_code=409)
    revision = None
    if body.session_id:
        session = db.get(ModelingSessionRecord, body.session_id)
        if not session or session.workspace_id != workspace_id:
            raise ServiceError("会话不存在", code="SESSION_NOT_FOUND", status_code=404)
        if session.revision != body.expected_session_revision:
            raise ServiceError(
                "草稿已更新", code="SESSION_REVISION_CHANGED", status_code=409
            )
        raw, revision = session.draft_json, session.revision
    else:
        if "expected_current_version_id" not in body.model_fields_set:
            raise ServiceError(
                "缺少发布版本确认", code="VALIDATION_FAILED", status_code=422
            )
        raw = (
            snapshot_of(current_version(db, workspace_id))
            if space.current_version_id
            else empty_snapshot(workspace_id)
        )
    candidate = CoreDraft.model_validate(raw)
    components = body.components or []
    if isinstance(body.metric, RatioMetric):
        required = {body.metric.numerator_id, body.metric.denominator_id}
        if {c.id for c in components} != required or len(components) != len(required):
            raise ServiceError(
                "预览分量必须完整且只覆盖比率引用",
                code="VALIDATION_FAILED",
                status_code=422,
            )
    elif components:
        raise ServiceError(
            "只有比率预览允许提供分量", code="VALIDATION_FAILED", status_code=422
        )
    ids = {body.metric.id, *(c.id for c in components)}
    candidate.metrics = [m for m in candidate.metrics if m.id not in ids] + [
        *components,
        body.metric,
    ]
    time_range = body.time_range.model_dump() if body.time_range else None
    try:
        if time_range:
            start = datetime.fromisoformat(time_range["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(time_range["end"].replace("Z", "+00:00"))
            if start >= end:
                raise ValueError("开始时间必须早于结束时间")
        validate_core_graph(candidate)
    except (ValueError, TypeError) as exc:
        raise ServiceError(
            "预览定义无效：" + str(exc), code="VALIDATION_FAILED", status_code=422
        ) from exc
    context = {
        "definition_hash": domain_sha256(
            {
                "draft": candidate.model_dump(mode="json"),
                "metric": str(body.metric.id),
                "time_range": time_range,
                "trend_grain": body.trend_grain,
                "version": space.current_version_id,
                "revision": revision,
            }
        ),
        "context_version": space.current_version_id,
        "session_revision": revision,
    }
    unable = {
        **context,
        "status": "unable",
        "value": None,
        "value_kind": None,
        "total_query": None,
        "trend_query": None,
        "snapshot_dates": [],
        "warnings": [],
    }
    if not can_read_instances(db, workspace_id, user) or not can_read_mappings(
        db, workspace_id, user
    ):
        return {**unable, "reason_code": "forbidden", "reason": "没有映射或实例读取授权"}
    kind = value_kind(candidate, body.metric)
    if kind is None:
        return {
            **unable,
            "reason_code": "binding_not_ready",
            "reason": "指标结果类型待补全",
        }
    metric_components = components if components else [body.metric]
    trend = body.trend_grain is not None
    warnings = []
    if trend and any(not c.time_field for c in metric_components):
        trend = False
        warnings.append("缺少时间字段，仅返回总值，无法生成月趋势")
    try:
        result = execute_metric_preview(
            db,
            workspace_id,
            candidate,
            body.metric,
            settings,
            time_range=time_range,
            trend=trend,
        )
        result["warnings"].extend(warnings)
        return {**context, **result}
    except ServiceError as exc:
        codes = {
            "SOURCE_AMBIGUOUS": "source_ambiguous",
            "BINDING_NOT_READY": "binding_not_ready",
            "QUERY_TIMEOUT": "query_timeout",
            "QUERY_FAILED": "query_failed",
            "METRIC_EXPRESSION_UNSUPPORTED": "expression_not_supported",
            "METRIC_FIELD_INVALID": "binding_not_ready",
            "METRIC_DIALECT_UNSUPPORTED": "engine_not_supported",
            "expression_unsupported": "expression_not_supported",
            "dialect_unsupported": "engine_not_supported",
            "time_field_required": "binding_not_ready",
        }
        return {
            **unable,
            "value_kind": kind,
            "reason_code": codes.get(exc.code, exc.code.lower()),
            "reason": exc.message,
        }
