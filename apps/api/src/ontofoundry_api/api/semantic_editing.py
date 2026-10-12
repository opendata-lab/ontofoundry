"""Native semantic aggregate saves and compile-only draft metric previews."""

from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import (
    blocks_edits,
    require_member,
    session_draft,
    session_response,
    version_snapshot,
)
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import ModelingSessionRecord, WorkspaceRecord, utc_now
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.semantic_authoring import (
    COLLECTIONS,
    SemanticChange,
    apply_changes,
    copy_scope,
    edit_scope,
    invalid,
    references,
)
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.join_validation import validate_join_columns
from ontofoundry_api.services.metric_query import (
    DIALECTS,
    MetricCompiler,
    connection_for,
    target_dialect,
)
from ontofoundry_api.services.ontology_query import version_summary
from ontofoundry_api.services.publish_preview import three_way
from ontofoundry_api.services.workspaces import publish_draft

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["semantic-editing"])


class SemanticWrite(BaseModel):
    expected_current_version_id: str | None
    session_id: str | None = None
    expected_session_revision: int | None = None
    changes: list[SemanticChange] = Field(min_length=1, max_length=100)


def context(db, workspace_id, body, *, lock=False):
    query = select(WorkspaceRecord).where(WorkspaceRecord.id == workspace_id)
    space = db.scalar(query.with_for_update() if lock else query)
    if space.current_version_id != body.expected_current_version_id:
        raise ServiceError(
            "内容已更新，请重新读取后保存", code="VERSION_CHANGED", status_code=409
        )
    latest = version_snapshot(db, workspace_id, space.current_version_id)
    item = None
    if body.session_id:
        query = select(ModelingSessionRecord).where(
            ModelingSessionRecord.id == body.session_id,
            ModelingSessionRecord.workspace_id == workspace_id,
        )
        item = db.scalar(query.with_for_update() if lock else query)
        if not item:
            raise ServiceError("建模会话不存在", code="SESSION_NOT_FOUND", status_code=404)
        if item.revision != body.expected_session_revision or (lock and blocks_edits(item)):
            raise ServiceError(
                "会话内容已变化，请重新读取",
                code="SESSION_REVISION_CHANGED",
                status_code=409,
            )
    original = session_draft(item) if item else latest
    base = version_snapshot(db, workspace_id, item.base_version_id) if item else latest
    return space, item, original, base, latest


@router.post("/semantic-change-preview")
def preview(
    workspace_id: str,
    body: SemanticWrite,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    _, _, original, base, latest = context(db, workspace_id, body)
    impacts = []
    for change in body.changes:
        collection = COLLECTIONS.get(change.kind)
        target = next(
            (n for n in original.get(collection, []) if n["id"] == str(change.id)), None
        )
        if target and (change.operation == "delete" or "name" in change.values):
            impacts.extend(references(original, change.kind, target))
    try:
        edited = apply_changes(original, body.changes)
    except (ValidationError, ValueError) as exc:
        raise invalid("语义模型校验失败：" + str(exc)) from exc
    from ontofoundry_api.api.modeling import validate_draft

    scope = edit_scope(original, edited, body.changes)
    merged = three_way(base, latest, copy_scope(base, edited, scope), workspace_id)
    if merged.conflicts:
        raise ServiceError(
            "语义模型与最新版本存在冲突，请重新读取",
            code="MERGE_CONFLICTS",
            status_code=409,
            details={"conflicts": merged.conflicts},
        )
    return {
        "references": impacts,
        "validation": validate_draft(merged.merged, db.get(WorkspaceRecord, workspace_id)),
    }


@router.post("/semantic-saves")
def save(
    workspace_id: str,
    body: SemanticWrite,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    try:
        _, item, original, base, latest = context(db, workspace_id, body, lock=True)
        revision = item.revision if item else None
        edited = apply_changes(original, body.changes)
        scope = edit_scope(original, edited, body.changes)
        scoped = copy_scope(base, edited, scope)
        merge = three_way(base, latest, scoped, workspace_id)
        if merge.conflicts:
            raise ServiceError(
                "语义模型与最新版本存在冲突，请重新读取后核对",
                code="MERGE_CONFLICTS",
                status_code=409,
                details={"conflicts": merge.conflicts},
            )
        model = OntologyDraft.model_validate(merge.merged)
        validate_join_columns(
            db,
            workspace_id,
            original,
            model.model_dump(mode="json"),
            request.app.state.settings,
        )
        version = publish_draft(
            db,
            workspace_id=workspace_id,
            draft=model,
            user_id=user.id,
            message="保存语义模型元素",
            commit=False,
        )
        if item:
            updated = copy_scope(edited, model.model_dump(mode="json"), scope)
            changed = db.execute(
                update(ModelingSessionRecord)
                .where(
                    ModelingSessionRecord.id == item.id,
                    ModelingSessionRecord.revision == revision,
                )
                .values(
                    draft_json=updated,
                    draft_sha256=snapshot_sha256(updated),
                    revision=revision + 1,
                    updated_at=utc_now(),
                )
            )
            if changed.rowcount != 1:
                raise ServiceError(
                    "会话内容已变化，请重新读取",
                    code="SESSION_REVISION_CHANGED",
                    status_code=409,
                )
        db.commit()
        if item:
            db.refresh(item)
        return {
            "version": version_summary(version),
            "session": session_response(db, item) if item else None,
        }
    except (ValidationError, ValueError) as exc:
        db.rollback()
        raise invalid("语义模型校验失败：" + str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        raise ServiceError(
            "内容已被其他人更新，请重新读取", code="VERSION_CHANGED", status_code=409
        ) from exc
    except ServiceError:
        db.rollback()
        raise


class SQLPreview(BaseModel):
    session_id: str | None = None
    expected_session_revision: int | None = None
    expected_current_version_id: str | None = None
    dialect: Literal["ANSI_SQL", "POSTGRES", "POSTGRESQL", "MYSQL"] | None = None
    group_by: list[str] = Field(default_factory=list, max_length=100)
    filters: list[dict] = Field(default_factory=list, max_length=100)
    as_of: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    changes: list[SemanticChange] = Field(default_factory=list, max_length=100)


@router.post("/metrics/{metric_id}/sql-preview")
def sql_preview(
    workspace_id: str,
    metric_id: str,
    body: SQLPreview,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    _, item, original, _, _ = context(db, workspace_id, body)
    try:
        draft = OntologyDraft.model_validate(
            apply_changes(original, body.changes) if body.changes else original
        )
    except (ValidationError, ValueError) as exc:
        raise invalid("草稿结构无效：" + str(exc)) from exc
    metric = next((m for m in draft.metrics if str(m.id) == metric_id), None)
    if not metric:
        raise ServiceError("当前内容中没有此指标", code="METRIC_NOT_FOUND", status_code=404)
    model = next(m for m in draft.semantic_models if m.id == metric.semantic_model_id)
    connection = connection_for(db, workspace_id, model)
    dialect = DIALECTS[body.dialect] if body.dialect else target_dialect(connection)
    compiler = MetricCompiler(draft, metric, dialect)
    result = {
        "metric_id": metric_id,
        "session_revision": item.revision if item else None,
        "dialect": body.dialect or (dialect.upper() if dialect else "ANSI_SQL"),
        "executed": False,
        "executable": False,
        "sql": None,
        "parameters": {},
        "columns": [],
        "warnings": [],
        **compiler.explanation(),
    }
    if compiler.dataset is None:
        return result
    plan = compiler.compile(
        group_by=body.group_by, filters=body.filters, as_of=body.as_of, limit=body.limit
    )
    result.update(
        sql=plan.sql,
        parameters=plan.parameters,
        columns=plan.columns,
        executable=connection is not None,
        reason=None,
        time_semantics=compiler.time_semantics,
        time_field=compiler.time_field,
    )
    if connection is None:
        result["reason"] = "未绑定数据连接，已生成 SQL"
    # Deliberately never open a data connection or enter the execution service.
    return result
