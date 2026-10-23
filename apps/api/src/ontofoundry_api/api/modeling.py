from copy import deepcopy
from typing import Any, Literal
from uuid import uuid4

import jsonschema
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, defer

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.contracts.dataset_sources import LinkedTable
from ontofoundry_api.contracts.read_models import AffectedItem, ElementSaveImpact
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import (
    ModelingSessionRecord,
    OntologyVersionRecord,
    WorkspaceRecord,
    utc_now,
)
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.evidence import EvidenceError, reconcile_draft_evidence
from ontofoundry_api.domain.models import OntologyDraft, Strict
from ontofoundry_api.domain.snapshot import (
    draft_sha256,
    empty_snapshot,
)
from ontofoundry_api.services.element_diff import element_changes
from ontofoundry_api.services.element_save import (
    calculate_element_save,
    preview_element_save,
)
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.ontology_query import (
    _all_graph,
    current_version,
    snapshot_of,
    version_summary,
)
from ontofoundry_api.services.proposals import pending_summary, proposal_state
from ontofoundry_api.services.publish_preview import (
    auto_merged,
    element_labels,
    impacts,
    three_way,
)
from ontofoundry_api.services.read_cache import session_reads, version_snapshots
from ontofoundry_api.services.run_status import ACTIVE_RUN_STATUSES
from ontofoundry_api.services.version_diff import compare_snapshots
from ontofoundry_api.services.workspaces import (
    get_workspace,
    membership_role,
    publish_draft,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["modeling"])


class ElementSave(Strict):
    target_kind: Literal["object_type", "link_type", "metric", "dataset", "mapping", "value_type"]
    target_id: str
    expected_current_version_id: str | None
    session_id: str | None = None
    expected_session_revision: int | None = None
    draft: dict
    affected_items: list[AffectedItem] = Field(default_factory=list)
    expected_instance_change_sequence: int | None = None


@router.post("/element-saves/preview", response_model=ElementSaveImpact)
def preview_element(
    workspace_id: str,
    body: ElementSave,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    return preview_element_save(db, workspace_id, body)


@router.post("/element-saves")
def save_element(
    workspace_id: str,
    body: ElementSave,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    """One Save action validates and commits an immutable, immediately active version."""
    require_member(db, workspace_id, user.id)
    space = db.scalar(
        select(WorkspaceRecord).where(WorkspaceRecord.id == workspace_id).with_for_update()
    )
    if space.current_version_id != body.expected_current_version_id:
        raise ServiceError(
            "内容已被其他人更新，请重新打开后再保存",
            code="VERSION_CHANGED",
            status_code=409,
        )
    if body.expected_instance_change_sequence is not None:
        from ontofoundry_api.services.instance_store import change_sequence
        if body.expected_instance_change_sequence != change_sequence(db, workspace_id):
            raise ServiceError("实例集合在预览后已变化，请重新预览", code="PREVIEW_OUTDATED", status_code=409)
    latest = version_snapshot(db, workspace_id, space.current_version_id)
    item = None
    if body.session_id:
        item = db.scalar(
            select(ModelingSessionRecord)
            .where(
                ModelingSessionRecord.id == body.session_id,
                ModelingSessionRecord.workspace_id == workspace_id,
            )
            .with_for_update()
        )
        if not item:
            raise HTTPException(404, "建模会话不存在")
        if item.revision != body.expected_session_revision or blocks_edits(item):
            raise ServiceError(
                "内容已变化，请重新打开后再保存",
                code="SESSION_REVISION_CHANGED",
                status_code=409,
            )
    if bool(body.session_id) != (body.expected_session_revision is not None):
        raise ServiceError(
            "会话和 revision 必须同时给出", code="ELEMENT_SCOPE_INVALID", status_code=422
        )
    write_revision = item.revision if item else None
    original = session_draft(item) if item else latest
    try:
        if body.draft.get("schema_version") != "core-1":
            raise ValueError("只接受 core-1 草稿")
        edited = CoreDraft.model_validate(body.draft).model_dump(mode="json")
        edited = reconcile_draft_evidence(
            original,
            edited,
            lookup=material_lookup(db, request.app.state.settings, workspace_id),
            actor_id=user.id,
            now=utc_now(),
        )
        base = version_snapshot(db, workspace_id, item.base_version_id) if item else latest
        calculation = calculate_element_save(
            base,
            latest,
            original,
            edited,
            body.target_kind,
            body.target_id,
            affected_items=body.affected_items,
        )
        model = OntologyDraft.model_validate(calculation.merged)
        from ontofoundry_api.services.join_validation import validate_join_columns

        checked_draft = model.model_dump(mode="json")
        validate_join_columns(
            db,
            workspace_id,
            original,
            checked_draft,
            request.app.state.settings,
        )
        model = OntologyDraft.model_validate(checked_draft)
        version = publish_draft(
            db,
            workspace_id=workspace_id,
            draft=model,
            user_id=user.id,
            message="保存本体元素",
            session_id=item.id if item else None,
            commit=False,
        )
        if item:
            updated_draft = deepcopy(calculation.session_draft)
            # Server-probed dataset columns go to the session too, so it matches
            # exactly what was published.
            probed = {d["id"]: d for d in checked_draft["datasets"]}
            updated_draft["datasets"] = [
                {**d, "columns": probed[d["id"]]["columns"]} if d["id"] in probed else d
                for d in updated_draft["datasets"]
            ]
            # CAS also protects SQLite and a proposal decision racing this request.
            changed = db.execute(
                update(ModelingSessionRecord)
                .where(
                    ModelingSessionRecord.id == item.id,
                    ModelingSessionRecord.revision == write_revision,
                )
                .values(
                    draft_json=updated_draft,
                    draft_sha256=snapshot_sha256(updated_draft),
                    revision=item.revision + 1,
                    updated_at=utc_now(),
                )
            )
            if changed.rowcount != 1:
                db.rollback()
                raise ServiceError(
                    "内容已变化，请重新打开后再保存",
                    code="SESSION_REVISION_CHANGED",
                    status_code=409,
                )
        db.commit()
        if item:
            db.refresh(item)
    except (jsonschema.ValidationError, ValidationError, ValueError) as exc:
        db.rollback()
        raise ServiceError(
            "内容校验失败：" + str(exc), code="ELEMENT_VALIDATION_FAILED", status_code=422
        ) from exc
    except EvidenceError as exc:
        db.rollback()
        raise ServiceError(str(exc), code=exc.code, status_code=422) from exc
    except IntegrityError as exc:
        db.rollback()
        raise ServiceError(
            "内容已被其他人更新，请重新打开后再保存",
            code="VERSION_CHANGED",
            status_code=409,
        ) from exc
    return {
        "version": version_summary(version),
        "draft": model.model_dump(mode="json"),
        "session": session_response(db, item) if item else None,
    }


def require_member(db: Session, workspace_id: str, user_id: str, admin=False):
    role = membership_role(db, workspace_id, user_id)
    if not role or (admin and role != "admin"):
        raise HTTPException(403, "需要空间管理员权限" if admin else "仅空间成员可访问")


def get_modeling_session(db: Session, workspace_id: str, session_id: str):
    item = db.get(ModelingSessionRecord, session_id)
    if (
        not item
        or item.workspace_id != workspace_id
        or item.draft_json.get("schema_version") != "core-1"
    ):
        raise HTTPException(404, "建模会话不存在")
    return item


def session_draft(item) -> dict:
    """Read the current draft without rewriting session history."""
    if item.draft_json.get("schema_version") != "core-1":
        raise HTTPException(404, "旧建模会话已停用，请新建会话")
    draft = deepcopy(item.draft_json)
    return draft


def version_snapshot_sha256(db, workspace_id: str, version_id: str | None) -> str:
    """normalized_snapshot_sha256 of a version, or of the empty snapshot."""
    return snapshot_sha256(version_snapshot(db, workspace_id, version_id))


def version_snapshot(db, workspace_id: str, version_id: str | None) -> dict:
    version = db.get(OntologyVersionRecord, version_id) if version_id else None
    return snapshot_of(version) if version else empty_snapshot(workspace_id)


def session_response(db, item) -> dict:
    """A session as the API returns it: data plus proposal summary and the
    element-level changes relative to its base version."""
    data = session_data(item)
    data["import_source"] = import_source(db, item.workspace_id, item.id)
    key = _read_key(item)

    def base_diff():
        try:
            return element_changes(_base_snapshot(db, item), session_draft(item))
        except ValueError:  # an invalid draft field never blocks reading the session
            return []

    def summary():
        return pending_summary(db, item.workspace_id, item.id, item.draft_json)

    if key is None:
        return {**data, **summary(), "base_diff": base_diff()}
    return {
        **data,
        **session_reads.get(
            (*key, "pending", proposal_state(db, item.workspace_id, item.id)), summary
        ),
        "base_diff": session_reads.get(
            (*key, "base_diff", item.base_version_id, item.base_version_sha256), base_diff
        ),
    }


def import_source(db, workspace_id, session_id):
    from ontofoundry_api.db_models import ImportRecord

    record = db.scalar(
        select(ImportRecord).where(
            ImportRecord.workspace_id == workspace_id, ImportRecord.session_id == session_id
        )
    )
    return {"adapter": record.adapter, "report_id": record.id} if record else None


def _read_key(item) -> tuple | None:
    """Derived parts of a session only change with its revision and draft hash."""
    if not item.draft_sha256:
        return None
    return ("session", item.id, item.revision, item.draft_sha256)


def _base_snapshot(db, item) -> dict:
    """The base version's snapshot; published versions never change."""
    if not item.base_version_id or not item.base_version_sha256:
        return version_snapshot(db, item.workspace_id, item.base_version_id)
    return version_snapshots.get(
        (item.base_version_id, item.base_version_sha256),
        lambda: version_snapshot(db, item.workspace_id, item.base_version_id),
    )


def _derived_views(draft):
    return _all_graph(draft)


def session_data(item):
    draft = session_draft(item)
    key = _read_key(item)
    if key is None:
        nodes, edges = _derived_views(draft)
    else:
        nodes, edges = session_reads.get((*key, "views"), lambda: _derived_views(draft))
    return {
        "id": item.id,
        "title": item.title,
        "workspace_id": item.workspace_id,
        "base_version_id": item.base_version_id,
        "revision": item.revision,
        "base_version_sha256": item.base_version_sha256,
        "draft_sha256": item.draft_sha256 or draft_sha256(draft),
        "draft": draft,
        "material_ids": item.material_ids,
        "linked_tables": item.linked_tables or [],
        "task_status": item.task_status,
        "task_detail": item.task_detail,
        "dataagent_topic_id": item.dataagent_topic_id,
        "dataagent_task_id": (
            item.dataagent_task_id
            if item.task_status
            in (
                "submitting",
                "queued",
                "running",
                "waiting_input",
                "waiting_permission",
            )
            else None
        ),
        "dataagent_task_mode": item.dataagent_task_mode,
        "dataagent_run_token": item.dataagent_run_token,
        "uploaded_material_ids": item.uploaded_material_ids,
        "last_result_task_id": item.last_result_task_id,
        "result_state": item.result_state,
        "result_warnings": item.result_warnings,
        "result_claimed_at": item.result_claimed_at,
        "updated_at": item.updated_at,
        "abandoned_at": item.abandoned_at,
        "abandoned_by": item.abandoned_by,
        "graph": {
            "workspace_id": item.workspace_id,
            "version_id": item.base_version_id or "",
            "version_sha256": "",
            "nodes": nodes,
            "edges": edges,
        },
    }


def blocks_edits(item):
    if item.abandoned_at is not None:
        raise ServiceError("会话已放弃", code="SESSION_ABANDONED", status_code=409)
    return False


def revise(db, item, revision, **values):
    if "draft_json" in values:
        if values["draft_json"].get("schema_version") != "core-1":
            raise ServiceError(
                "只接受 core-1 草稿", code="VALIDATION_FAILED", status_code=422
            )
        values["draft_json"] = CoreDraft.model_validate(values["draft_json"]).model_dump(
            mode="json"
        )
        values["draft_sha256"] = draft_sha256(values["draft_json"])
    if "base_version_id" in values:
        values["base_version_sha256"] = version_snapshot_sha256(
            db, item.workspace_id, values["base_version_id"]
        )
    if blocks_edits(item):
        raise HTTPException(409, "当前会话正在生成，请等待完成或取消后编辑")
    guard = [
        ModelingSessionRecord.id == item.id,
        ModelingSessionRecord.revision == revision,
    ]
    result = db.execute(
        update(ModelingSessionRecord)
        .where(*guard)
        .values(**values, revision=revision + 1, updated_at=utc_now())
    )
    if result.rowcount != 1:
        db.rollback()
        raise ServiceError(
            "此会话已在其他窗口更新，请刷新后重试",
            code="SESSION_REVISION_CHANGED",
            status_code=409,
        )
    db.commit()
    db.refresh(item)
    return session_response(db, item)


def validate_draft(draft, workspace):
    from ontofoundry_api.services.core_validation import validation_report

    return validation_report(draft)


class SessionCreate(BaseModel):
    title: str = Field(default="新的建模会话", min_length=1, max_length=240)


class DraftSave(Strict):
    revision: int
    draft: dict
    title: str | None = Field(default=None, min_length=1, max_length=240)
    material_ids: list[str] | None = None
    linked_tables: list[LinkedTable] | None = Field(default=None, max_length=200)


class SessionPublish(Strict):
    expected_session_revision: int
    expected_current_version_id: str | None = None
    expected_merged_snapshot_sha256: str | None = None
    expected_instance_change_sequence: int | None = None
    message: str = Field(default="", max_length=240)

    @property
    def session_revision(self):
        return self.expected_session_revision

    @property
    def strict(self):
        return True


class MergeResolution(Strict):
    expected_session_revision: int
    expected_current_version_id: str | None
    resolutions: dict[str, dict[str, Any]]


def _json_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def check_resolutions(conflicts: list[dict], resolutions: dict[str, Any]) -> None:
    def refuse(message: str) -> ServiceError:
        return ServiceError(message, code="RESOLUTION_INVALID", status_code=422)

    by_key = {c["key"]: c for c in conflicts}
    if set(resolutions) != set(by_key):
        missing = sorted(set(by_key) - set(resolutions))
        extra = sorted(set(resolutions) - set(by_key))
        raise refuse(
            "解决方案必须恰好对应当前的冲突"
            + (f"；缺少 {missing}" if missing else "")
            + (f"；多余 {extra}" if extra else "")
        )
    for key, answer in resolutions.items():
        conflict = by_key[key]
        choice = answer.get("choice") if isinstance(answer, dict) else answer
        if choice not in conflict["allowed"]:
            raise refuse(
                f"{conflict['element_label']} / {conflict['path']} 不允许选择 {choice}"
            )
        if choice == "custom":
            if not isinstance(answer, dict) or "value" not in answer:
                raise refuse(
                    f"{conflict['element_label']} / {conflict['path']} 的自定义值缺失"
                )
            expected = {
                _json_type(v)
                for v in (conflict["latest"], conflict["draft"])
                if v is not None
            }
            if expected and _json_type(answer["value"]) not in expected:
                raise refuse(
                    f"{conflict['element_label']} / {conflict['path']} 的自定义值类型应为 "
                    + "、".join(sorted(expected))
                )


def revised_material_bookkeeping(item, material_ids):
    """Release unselected upload bookkeeping once no run is using it.

    A terminal run's proposal batch keeps its own material manifest, so this
    session-level copy only blocks deletion of documents the user unchecked.
    """
    if item.task_status in ACTIVE_RUN_STATUSES:
        return {}
    selected = set(material_ids)
    values = {}
    uploaded = item.uploaded_material_ids or []
    if any(material_id not in selected for material_id in uploaded):
        values["uploaded_material_ids"] = [
            material_id for material_id in uploaded if material_id in selected
        ]
    manifest = item.run_manifest_json
    if manifest:
        materials = manifest.get("materials") or []
        kept = [entry for entry in materials if entry.get("id") in selected]
        if len(kept) != len(materials):
            values["run_manifest_json"] = {**manifest, "materials": kept}
    return values


@router.post("/sessions/{session_id}/resolve-merge")
def resolve_merge(
    workspace_id: str,
    session_id: str,
    body: MergeResolution,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    space = get_workspace(db, workspace_id)
    item = get_modeling_session(db, workspace_id, session_id)
    expected_current = body.expected_current_version_id
    revision = body.expected_session_revision
    if space.current_version_id != expected_current:
        raise ServiceError(
            "最新版本又有变化，请重新预览",
            code="PREVIEW_OUTDATED",
            status_code=409,
            details={"current_version_id": space.current_version_id},
        )
    base = version_snapshot(db, workspace_id, item.base_version_id)
    latest = version_snapshot(db, workspace_id, space.current_version_id)
    draft = session_draft(item)
    # Resolutions must answer exactly the current conflicts, each with an
    # allowed choice and, for custom, a value of the field's own type.
    check_resolutions(
        three_way(base, latest, draft, workspace_id).conflicts, body.resolutions
    )
    merge = three_way(base, latest, draft, workspace_id, body.resolutions)
    try:
        jsonschema.validate(merge.merged, CoreDraft.model_json_schema())
    except jsonschema.ValidationError as exc:
        raise ServiceError(
            "合并结果结构无效：" + exc.message, code="RESOLUTION_INVALID", status_code=422
        ) from exc
    if merge.conflicts:
        raise ServiceError(
            "仍有未解决的冲突",
            code="CONFLICTS_UNRESOLVED",
            status_code=422,
            details={
                "conflicts": merge.conflicts,
                "current_version_id": space.current_version_id,
            },
        )
    # The draft now starts from the current version: resolved conflicts are
    # its content, and the base moves so they are never asked again.
    return revise(
        db,
        item,
        revision,
        draft_json=merge.merged,
        base_version_id=space.current_version_id,
    )


def schedule_run_sync(request: Request, background: BackgroundTasks, items) -> None:
    """Let reads converge a run nobody is watching: after the response, sync
    each session whose stored run state may lag DataAgent."""
    from ontofoundry_api.api.agent_conversation import needs_run_sync, sync_session_run

    for item in items:
        if needs_run_sync(request.app, item):
            background.add_task(sync_session_run, request.app, item.workspace_id, item.id)


@router.get("/sessions")
def sessions(
    workspace_id: str,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    # Polled while a run is live: never load the drafts.
    rows = db.scalars(
        select(ModelingSessionRecord)
        .options(
            defer(ModelingSessionRecord.draft_json),
            defer(ModelingSessionRecord.candidates_json),
            defer(ModelingSessionRecord.run_manifest_json),
        )
        .where(ModelingSessionRecord.workspace_id == workspace_id)
        .order_by(ModelingSessionRecord.updated_at.desc())
    ).all()
    schedule_run_sync(request, background, rows)
    from ontofoundry_api.db_models import ImportRecord

    sources = {
        r.session_id: {"adapter": r.adapter, "report_id": r.id}
        for r in db.scalars(
            select(ImportRecord).where(
                ImportRecord.workspace_id == workspace_id,
                ImportRecord.session_id.is_not(None),
            )
        )
    }
    return {
        "items": [
            {
                "id": r.id,
                "title": r.title,
                "import_source": sources.get(r.id),
                "updated_at": r.updated_at,
                "task_status": r.task_status,
                "base_version_id": r.base_version_id,
                # Both hashes are stored on every write, so this costs no
                # draft read: the draft differs from the version it started from.
                "has_unpublished_changes": bool(
                    r.draft_sha256 and r.draft_sha256 != r.base_version_sha256
                ),
            }
            for r in rows
        ]
    }


@router.post("/sessions", status_code=201)
def create_session(
    workspace_id: str,
    body: SessionCreate,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    space = get_workspace(db, workspace_id)
    version = (
        db.get(OntologyVersionRecord, space.current_version_id)
        if space.current_version_id
        else None
    )
    draft = snapshot_of(version) if version else empty_snapshot(workspace_id)
    item = ModelingSessionRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        created_by=user.id,
        title=body.title,
        base_version_id=space.current_version_id,
        base_version_sha256=snapshot_sha256(draft),
        draft_json=draft,
        draft_sha256=snapshot_sha256(draft),
    )
    db.add(item)
    db.commit()
    return session_response(db, item)


@router.get("/sessions/{session_id}")
def read_session(
    workspace_id: str,
    session_id: str,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    schedule_run_sync(request, background, [item])
    return session_response(db, item)


@router.put("/sessions/{session_id}")
def save_session(
    workspace_id: str,
    session_id: str,
    body: DraftSave,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    if body.draft.get("workspace_id") != workspace_id:
        raise ServiceError("草稿空间不匹配", code="WORKSPACE_MISMATCH", status_code=422)
    if body.draft.get("schema_version") != "core-1":
        raise ServiceError("只接受 core-1 草稿", code="VALIDATION_FAILED", status_code=422)
    # Structural schema permits duplicate names/references during editing; publication
    # applies the domain validators as well. UI readers always get a traversable shape.
    try:
        jsonschema.validate(body.draft, CoreDraft.model_json_schema())
    except jsonschema.ValidationError as exc:
        raise ServiceError(
            "草稿结构无效：" + exc.message, code="VALIDATION_FAILED", status_code=422
        ) from exc
    try:
        draft = reconcile_draft_evidence(
            session_draft(item),
            deepcopy(body.draft),
            lookup=material_lookup(db, request.app.state.settings, workspace_id),
            actor_id=user.id,
            now=utc_now(),
        )
    except EvidenceError as exc:
        raise ServiceError(str(exc), code=exc.code, status_code=422) from exc
    from ontofoundry_api.services.join_validation import validate_source_columns

    validate_source_columns(draft)
    values = {"draft_json": draft}
    if body.title is not None:
        values["title"] = body.title
    if body.material_ids is not None:
        from ontofoundry_api.db_models import MaterialRecord

        for material_id in body.material_ids:
            material = db.get(MaterialRecord, material_id)
            if not material or material.workspace_id != workspace_id:
                raise HTTPException(422, "材料不属于当前空间")
        values["material_ids"] = body.material_ids
        values.update(revised_material_bookkeeping(item, body.material_ids))
    if body.linked_tables is not None:
        from ontofoundry_api.services.dataset_sources import linked_table_details

        linked = [t.model_dump() for t in body.linked_tables]
        linked_table_details(db, workspace_id, linked)
        values["linked_tables"] = linked
    result = revise(db, item, body.revision, **values)
    result["validation"] = validate_draft(draft, get_workspace(db, workspace_id))
    return result


@router.post("/sessions/{session_id}/validate")
def validate_session(
    workspace_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    return validate_draft(item.draft_json, get_workspace(db, workspace_id))


@router.post("/sessions/{session_id}/publish")
def publish_session(
    workspace_id: str,
    session_id: str,
    body: SessionPublish,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    space = db.scalar(
        select(WorkspaceRecord).where(WorkspaceRecord.id == workspace_id).with_for_update()
    )
    item = db.scalar(
        select(ModelingSessionRecord)
        .where(
            ModelingSessionRecord.id == session_id,
            ModelingSessionRecord.workspace_id == workspace_id,
        )
        .with_for_update()
    )
    if not item:
        raise ServiceError("建模会话不存在", code="SESSION_NOT_FOUND", status_code=404)
    if (
        body.expected_merged_snapshot_sha256 is None
        or "expected_current_version_id" not in body.model_fields_set
    ):
        raise ServiceError(
            "发布需要最新预览的版本和内容哈希", code="PREVIEW_OUTDATED", status_code=409
        )
    # All five active states, not just the two obvious ones: a run parked on
    # waiting_input or waiting_permission is still live, and publishing a draft
    # the agent is mid-way through rewriting would capture a half-applied model.
    if item.revision != body.session_revision or item.task_status in ACTIVE_RUN_STATUSES:
        if body.strict:
            raise ServiceError(
                "会话已变化或仍在生成，请重新预览",
                code="PREVIEW_OUTDATED",
                status_code=409,
                details={"current_version_id": space.current_version_id},
            )
        raise HTTPException(409, "会话已变化或仍在生成，请刷新后发布")
    from ontofoundry_api.services.instance_store import change_sequence
    if body.expected_instance_change_sequence != change_sequence(db, workspace_id):
        raise ServiceError("实例集合在预览后已变化，请重新预览", code="PREVIEW_OUTDATED", status_code=409)
    if item.abandoned_at is not None:
        raise ServiceError("会话已放弃", code="SESSION_ABANDONED", status_code=409)
    if body.strict and space.current_version_id != body.expected_current_version_id:
        # Even a change that would merge cleanly is content the user has not
        # seen: never publish it silently (design §9.3).
        raise ServiceError(
            "最新版本在你预览后已变化，请重新预览",
            code="PREVIEW_OUTDATED",
            status_code=409,
            details={"current_version_id": space.current_version_id},
        )
    merge = three_way(
        version_snapshot(db, workspace_id, item.base_version_id),
        version_snapshot(db, workspace_id, space.current_version_id),
        session_draft(item),
        workspace_id,
    )
    merged = merge.merged
    if merge.conflicts:
        if body.strict:
            raise ServiceError(
                "当前版本与草稿存在冲突，请先解决",
                code="MERGE_CONFLICTS",
                status_code=409,
                details={
                    "conflicts": merge.conflicts,
                    "current_version_id": space.current_version_id,
                },
            )
        raise HTTPException(
            409,
            {
                "message": "当前版本与草稿存在冲突，请在编辑页合并后重试",
                "conflicts": [
                    {
                        "path": c["key"],
                        "base": c["base"],
                        "current": c["latest"],
                        "draft": c["draft"],
                    }
                    for c in merge.conflicts
                ],
                "current_version_id": space.current_version_id,
                "merged": merged,
            },
        )
    if body.strict and merge.merged_sha256 != body.expected_merged_snapshot_sha256:
        raise ServiceError(
            "待发布内容与预览不一致，请重新预览",
            code="PREVIEW_OUTDATED",
            status_code=409,
            details={"current_version_id": space.current_version_id},
        )
    # Session drafts can be edited directly, so publishing re-checks every new or
    # changed dataset: registered source and safe read-only SQL.
    from ontofoundry_api.services.join_validation import validate_join_columns

    validate_join_columns(
        db,
        workspace_id,
        version_snapshot(db, workspace_id, space.current_version_id),
        merged,
        request.app.state.settings,
    )
    try:
        model = OntologyDraft.model_validate(merged)
    except ValidationError as exc:
        raise ServiceError(
            "发布草稿校验失败：" + str(exc), code="VALIDATION_FAILED", status_code=422
        ) from exc
    try:
        version = publish_draft(
            db,
            workspace_id=workspace_id,
            draft=model,
            user_id=user.id,
            message=body.message,
            session_id=session_id,
            commit=False,
        )
        item.base_version_id = version.id
        item.base_version_sha256 = snapshot_sha256(model.model_dump(mode="json"))
        # The session continues from exactly what was published: same
        # normalized form, so its draft hash equals the new base hash.
        item.draft_json = model.model_dump(mode="json")
        item.draft_sha256 = item.base_version_sha256
        item.revision += 1
        item.updated_at = utc_now()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "另一会话刚刚发布，请重新比较后重试") from exc
    return {"version": version_summary(version), "session": session_response(db, item)}


@router.get("/versions")
def versions(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    from ontofoundry_api.services.access import can_read_instances, can_read_mappings

    return {
        "items": [
            version_summary(
                v,
                include_mappings=can_read_mappings(db, workspace_id, user),
                include_instances=can_read_instances(db, workspace_id, user),
            )
            for v in db.scalars(
                select(OntologyVersionRecord)
                .where(OntologyVersionRecord.workspace_id == workspace_id)
                .order_by(OntologyVersionRecord.version_number.desc())
            ).all()
        ]
    }


@router.get("/ontology")
@router.get("/published-snapshot")
def published_snapshot(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    space = get_workspace(db, workspace_id)
    version = (
        db.get(OntologyVersionRecord, space.current_version_id)
        if space.current_version_id
        else None
    )
    return snapshot_of(version) if version else empty_snapshot(workspace_id)


@router.get("/capabilities")
def capabilities(
    workspace_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    config = request.app.state.settings
    configured = bool(config.dataagent_base_url)
    return {
        "agent_configured": configured,
        "model": f"DataAgent · {config.dataagent_agent_id}" if configured else "",
        "max_file_mb": config.max_file_mb,
        "connections_configured": True,
        "skills": ["ontology-discovery", "entity-extraction"],
    }


@router.get("/versions/{version_id}/presentation")
def presentation(
    workspace_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    from ontofoundry_api.services.access import can_read_instances, can_read_mappings
    from ontofoundry_api.services.public_projection import authorized_snapshot

    version = current_version(db, workspace_id, version_id)
    return {
        "version": version_summary(
            version,
            include_mappings=can_read_mappings(db, workspace_id, user),
            include_instances=can_read_instances(db, workspace_id, user),
        ),
        "model": authorized_snapshot(
            snapshot_of(version),
            mappings=can_read_mappings(db, workspace_id, user),
            instances=can_read_instances(db, workspace_id, user),
        ),
    }


@router.post("/sessions/{session_id}/preview")
def preview_definition(
    workspace_id: str,
    session_id: str,
    body: SessionPublish,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    """Exactly what publishing now would produce: the B/L/D merge of base,
    latest and draft, validated and compiled, with the values publish checks."""
    from ontofoundry_api.services.join_validation import dataset_checks

    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    if item.revision != body.session_revision:
        raise ServiceError(
            "草稿已更新，请重新预览", code="SESSION_REVISION_CHANGED", status_code=409
        )
    space = get_workspace(db, workspace_id)
    merge = three_way(
        version_snapshot(db, workspace_id, item.base_version_id),
        version_snapshot(db, workspace_id, space.current_version_id),
        session_draft(item),
        workspace_id,
    )
    if merge.conflicts:
        raise ServiceError(
            f"与最新版本存在 {len(merge.conflicts)} 处冲突，请先解决",
            code="MERGE_CONFLICTS",
            status_code=409,
            details={
                "conflicts": merge.conflicts,
                "current_version_id": space.current_version_id,
            },
        )
    report = validate_draft(merge.merged, space)
    from ontofoundry_api.services.instance_store import publish_impact
    instance_impact = {"instance_change_sequence": 0, "affected_instances": []}
    if report["publishable"]:
        instance_impact = publish_impact(db, workspace_id, merge.merged, session_id)
        if instance_impact["affected_instances"]:
            report = {**report, "publishable": False}
    else:
        from ontofoundry_api.services.instance_store import change_sequence
        instance_impact["instance_change_sequence"] = change_sequence(db, workspace_id)
    current = current_version(db, workspace_id) if space.current_version_id else None
    changes = element_changes(merge.latest, merge.merged)
    base = (
        db.get(OntologyVersionRecord, item.base_version_id)
        if item.base_version_id
        else None
    )
    return {
        "revision": item.revision,
        "session_revision": item.revision,
        "base_version_id": item.base_version_id,
        "base_version_number": base.version_number if base else None,
        "current_version_id": space.current_version_id,
        "current_version_number": current.version_number if current else None,
        "next_version_number": (
            db.scalar(
                select(func.max(OntologyVersionRecord.version_number)).where(
                    OntologyVersionRecord.workspace_id == workspace_id
                )
            )
            or 0
        )
        + 1,
        "current_version_sha256": snapshot_sha256(merge.latest),
        "merged_snapshot_sha256": merge.merged_sha256,
        **instance_impact,
        "merged_model": merge.merged,
        "validation": report,
        "changes": changes,
        "labels": element_labels(merge.latest, merge.merged),
        "impacts": impacts(changes, merge.merged),
        "auto_merged": auto_merged(merge),
        "dataset_checks": dataset_checks(
            db, workspace_id, merge.latest, merge.merged, request.app.state.settings
        ),
    }


@router.get("/version-comparison")
def compare_versions(
    workspace_id: str,
    right_id: str,
    left_id: str | None = None,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    left = current_version(db, workspace_id, left_id) if left_id else None
    right = current_version(db, workspace_id, right_id)
    if left and left.id == right.id:
        raise HTTPException(422, "请选择不同的版本进行比较")
    if left and left.version_number > right.version_number:
        left, right = right, left
    return {
        "left": version_summary(left) if left else None,
        "right": version_summary(right),
        **compare_snapshots(snapshot_of(left) if left else {}, snapshot_of(right)),
    }
