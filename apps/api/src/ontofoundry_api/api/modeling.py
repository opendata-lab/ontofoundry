from copy import deepcopy
from typing import Any
from uuid import uuid4

import jsonschema
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import (
    ModelingSessionRecord,
    OntologyVersionRecord,
    WorkspaceRecord,
    utc_now,
)
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.evidence import EvidenceError, reconcile_draft_evidence
from ontofoundry_api.domain.instance_validation import (
    include_instance_validation,
    instance_issues,
)
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.snapshot import (
    as_v2_dict,
    draft_sha256,
    empty_snapshot,
    read_snapshot_json,
)
from ontofoundry_api.ossie.compiler import compile_ossie, validate_ossie
from ontofoundry_api.ossie.importer import OssieImportError, import_ossie
from ontofoundry_api.services.element_diff import element_changes
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.ontology_query import (
    _all_graph,
    _query_view,
    current_version,
    snapshot_of,
    version_summary,
)
from ontofoundry_api.services.proposals import pending_summary
from ontofoundry_api.services.publish_preview import auto_merged, impacts, three_way
from ontofoundry_api.services.run_status import ACTIVE_RUN_STATUSES
from ontofoundry_api.services.version_diff import compare_snapshots
from ontofoundry_api.services.workspaces import (
    get_workspace,
    membership_role,
    publish_draft,
)

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["modeling"])


def require_member(db: Session, workspace_id: str, user_id: str, admin=False):
    role = membership_role(db, workspace_id, user_id)
    if not role or (admin and role != "admin"):
        raise HTTPException(403, "需要空间管理员权限" if admin else "仅空间成员可访问")


def get_modeling_session(db: Session, workspace_id: str, session_id: str):
    item = db.get(ModelingSessionRecord, session_id)
    if not item or item.workspace_id != workspace_id:
        raise HTTPException(404, "建模会话不存在")
    return item


def session_draft(item) -> dict:
    """The session draft as v2 JSON. A session created before v2 still holds a
    v1 draft until its next write; readers never see that difference."""
    return as_v2_dict(item.draft_json, item.workspace_id)


def version_snapshot_sha256(db, workspace_id: str, version_id: str | None) -> str:
    """normalized_snapshot_sha256 of a version, or of the empty snapshot."""
    return snapshot_sha256(version_snapshot(db, workspace_id, version_id))


def version_snapshot(db, workspace_id: str, version_id: str | None) -> dict:
    version = db.get(OntologyVersionRecord, version_id) if version_id else None
    return snapshot_of(version) if version else empty_snapshot(workspace_id)


def session_response(db, item) -> dict:
    """A session as the API returns it: data plus proposal summary and the
    element-level changes relative to its base version."""
    draft = session_draft(item)
    try:
        base_diff = element_changes(
            version_snapshot(db, item.workspace_id, item.base_version_id), draft
        )
    except ValueError:  # an invalid draft field never blocks reading the session
        base_diff = []
    return {
        **session_data(item),
        **pending_summary(db, item.workspace_id, item.id, draft),
        "base_diff": base_diff,
    }


def session_data(item):
    draft = session_draft(item)
    try:
        nodes, edges = _all_graph(_query_view(read_snapshot_json(draft)))
    except (ValidationError, ValueError):
        # A draft may be invalid while being edited; the graph is best effort.
        nodes, edges = [], []
    return {
        "id": item.id,
        "title": item.title,
        "workspace_id": item.workspace_id,
        "base_version_id": item.base_version_id,
        "revision": item.revision,
        "base_version_sha256": item.base_version_sha256,
        "draft_sha256": item.draft_sha256 or draft_sha256(draft),
        "draft": draft,
        "candidates": item.candidates_json,
        "material_ids": item.material_ids,
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
        "graph": {
            "workspace_id": item.workspace_id,
            "version_id": item.base_version_id or "",
            "version_sha256": "",
            "nodes": nodes,
            "edges": edges,
        },
    }


def blocks_edits(item) -> bool:
    """Only a legacy full-result run blocks edits: its result replaces the
    draft. A proposals run never writes the draft, so edits only make the
    affected proposals stale (design §6.2)."""
    manifest = item.run_manifest_json or {}
    return item.task_status in ACTIVE_RUN_STATUSES and manifest.get("result_contract") != "proposals"


def revise(db, item, revision, **values):
    if "draft_json" in values:
        values["draft_sha256"] = draft_sha256(values["draft_json"], item.workspace_id)
    if "base_version_id" in values:
        values["base_version_sha256"] = version_snapshot_sha256(
            db, item.workspace_id, values["base_version_id"]
        )
    if blocks_edits(item):
        raise HTTPException(409, "当前会话正在生成，请等待完成或取消后编辑")
    guard = [ModelingSessionRecord.id == item.id, ModelingSessionRecord.revision == revision]
    if (item.run_manifest_json or {}).get("result_contract") != "proposals":
        guard.append(ModelingSessionRecord.task_status.not_in(list(ACTIVE_RUN_STATUSES)))
    result = db.execute(
        update(ModelingSessionRecord)
        .where(*guard)
        .values(**values, revision=revision + 1, updated_at=utc_now())
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "此会话已在其他窗口更新，请刷新后重试")
    db.commit()
    db.refresh(item)
    return session_response(db, item)


def validate_draft(draft, workspace):
    try:
        model = OntologyDraft.model_validate(as_v2_dict(draft, workspace.id))
        if str(model.workspace_id) != workspace.id:
            raise ValueError("草稿空间不匹配")
        return include_instance_validation(
            validate_ossie(
                compile_ossie(
                    model,
                    ontology_name=workspace.slug.replace("-", "_"),
                    ontology_description=workspace.description or workspace.name,
                )
            ),
            model,
        )
    except (ValidationError, ValueError) as exc:
        return {
            "publishable": False,
            "schema_status": "failed",
            "semantic_status": "failed",
            "errors": [{"message": str(exc)}],
            "warnings": [],
        }


class SessionCreate(BaseModel):
    title: str = Field(default="新的建模会话", min_length=1, max_length=240)


class DraftSave(BaseModel):
    revision: int
    draft: dict
    title: str | None = Field(default=None, min_length=1, max_length=240)
    material_ids: list[str] | None = None


class CandidateAction(BaseModel):
    revision: int
    ids: list[str]
    action: str = Field(pattern="^(accept|ignore|restore)$")


class SessionPublish(BaseModel):
    """Publish/preview request. `expected_*` fields are the current contract
    (design §9.3); `revision` alone is the legacy form, kept during migration."""

    revision: int | None = None
    expected_session_revision: int | None = None
    expected_current_version_id: str | None = None
    expected_merged_snapshot_sha256: str | None = None
    message: str = Field(default="", max_length=240)

    @property
    def session_revision(self) -> int:
        value = (
            self.expected_session_revision
            if self.expected_session_revision is not None
            else self.revision
        )
        if value is None:
            raise HTTPException(422, "缺少 expected_session_revision")
        return value

    @property
    def strict(self) -> bool:
        return self.expected_merged_snapshot_sha256 is not None


class MergeResolution(BaseModel):
    revision: int | None = None
    expected_session_revision: int | None = None
    current_version_id: str | None = None
    expected_current_version_id: str | None = None
    # key -> "current"/"draft" (legacy) or {"choice", "value"}
    resolutions: dict[str, Any]


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
        choice = "latest" if choice == "current" else choice
        if choice not in conflict["allowed"]:
            raise refuse(f"{conflict['element_label']} / {conflict['path']} 不允许选择 {choice}")
        if choice == "custom":
            if not isinstance(answer, dict) or "value" not in answer:
                raise refuse(f"{conflict['element_label']} / {conflict['path']} 的自定义值缺失")
            expected = {
                _json_type(v) for v in (conflict["latest"], conflict["draft"]) if v is not None
            }
            if expected and _json_type(answer["value"]) not in expected:
                raise refuse(
                    f"{conflict['element_label']} / {conflict['path']} 的自定义值类型应为 "
                    + "、".join(sorted(expected))
                )


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
    expected_current = body.expected_current_version_id or body.current_version_id
    revision = body.expected_session_revision if body.expected_session_revision is not None else body.revision
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
    check_resolutions(three_way(base, latest, draft, workspace_id).conflicts, body.resolutions)
    merge = three_way(base, latest, draft, workspace_id, body.resolutions)
    try:
        jsonschema.validate(merge.merged, OntologyDraft.model_json_schema())
    except jsonschema.ValidationError as exc:
        raise ServiceError(
            "合并结果结构无效：" + exc.message, code="RESOLUTION_INVALID", status_code=422
        ) from exc
    if merge.conflicts:
        raise ServiceError(
            "仍有未解决的冲突",
            code="CONFLICTS_UNRESOLVED",
            status_code=422,
            details={"conflicts": merge.conflicts, "current_version_id": space.current_version_id},
        )
    # The draft now starts from the current version: resolved conflicts are
    # its content, and the base moves so they are never asked again.
    return revise(
        db, item, revision, draft_json=merge.merged, base_version_id=space.current_version_id
    )


@router.get("/sessions")
def sessions(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    rows = db.scalars(
        select(ModelingSessionRecord)
        .where(ModelingSessionRecord.workspace_id == workspace_id)
        .order_by(ModelingSessionRecord.updated_at.desc())
    ).all()
    return {
        "items": [
            {
                "id": r.id,
                "title": r.title,
                "updated_at": r.updated_at,
                "task_status": r.task_status,
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
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    return session_response(db, get_modeling_session(db, workspace_id, session_id))


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
        raise HTTPException(422, "草稿空间不匹配")
    # Structural schema permits duplicate names/references during editing; publication
    # applies the domain validators as well. UI readers always get a traversable shape.
    try:
        jsonschema.validate(body.draft, OntologyDraft.model_json_schema())
    except jsonschema.ValidationError as exc:
        raise HTTPException(422, "草稿结构无效：" + exc.message) from exc
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
    result = revise(db, item, body.revision, **values)
    result["validation"] = validate_draft(draft, get_workspace(db, workspace_id))
    return result


@router.post("/sessions/{session_id}/candidates")
def accept_candidates(
    workspace_id: str,
    session_id: str,
    body: CandidateAction,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    draft, candidates = deepcopy(session_draft(item)), deepcopy(item.candidates_json)
    collection = {
        "object_type": "object_types",
        "link_type": "link_types",
        "object": "material_objects",
        "link": "material_links",
        "mapping": "mappings",
    }
    for candidate in candidates:
        if candidate["id"] not in body.ids:
            continue
        if body.action == "accept":
            key = collection.get(candidate["kind"])
            if not key:
                continue
            value = candidate["value"]
            # The proposal remembers the value it was based on; manual edits win.
            current = next((v for v in draft.get(key, []) if v["id"] == value["id"]), None)
            if current != candidate.get("before") and current != value:
                candidate["conflict"] = "模型已手工修改，请重新建模或手工合并"
                continue
            draft[key] = [v for v in draft.get(key, []) if v["id"] != value["id"]] + [value]
            candidate["status"] = "accepted"
        else:
            candidate["status"] = "ignored" if body.action == "ignore" else "pending"
    # An accept-all operation stays atomic: type/ref/name errors never reach the draft.
    try:
        model = OntologyDraft.model_validate(draft)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    issues = instance_issues(model)
    if body.action == "accept" and issues:
        raise HTTPException(422, {"code": "INSTANCE_VALIDATION_FAILED", "errors": issues})
    return revise(db, item, body.revision, draft_json=draft, candidates_json=candidates)


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
        raise HTTPException(404, "建模会话不存在")
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
                details={"conflicts": merge.conflicts, "current_version_id": space.current_version_id},
            )
        raise HTTPException(
            409,
            {
                "message": "当前版本与草稿存在冲突，请在编辑页合并后重试",
                "conflicts": [
                    {"path": c["key"], "base": c["base"], "current": c["latest"], "draft": c["draft"]}
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
    try:
        model = OntologyDraft.model_validate(merged)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    try:
        version = publish_draft(
            db,
            workspace_id=workspace_id,
            draft=model,
            user_id=user.id,
            message=body.message,
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
    _: Principal = Depends(current_principal),
):
    return {
        "items": [
            version_summary(v)
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


class OssieImport(BaseModel):
    document: dict
    mode: str = Field(default="merge", pattern="^(merge|replace)$")
    title: str | None = Field(default=None, min_length=1, max_length=240)


@router.post("/imports/ossie", status_code=201)
def import_ossie_document(
    workspace_id: str,
    body: OssieImport,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    """Read an Ossie file into a new modeling session. Publishing stays explicit."""
    require_member(db, workspace_id, user.id)
    space = get_workspace(db, workspace_id)
    version = (
        db.get(OntologyVersionRecord, space.current_version_id)
        if space.current_version_id
        else None
    )
    try:
        draft, report = import_ossie(
            body.document,
            workspace_id=workspace_id,
            base=snapshot_of(version) if version else None,
            mode=body.mode,
        )
    except (OssieImportError, ValidationError, ValueError) as exc:
        raise HTTPException(422, f"导入失败：{exc}") from exc
    item = ModelingSessionRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        created_by=user.id,
        title=body.title or f"导入 {report['name'] or 'Ossie 本体'}",
        base_version_id=space.current_version_id,
        base_version_sha256=version_snapshot_sha256(db, workspace_id, space.current_version_id),
        draft_json=draft,
        draft_sha256=draft_sha256(draft, workspace_id),
    )
    db.add(item)
    db.commit()
    result = session_data(item)
    result["import_report"] = report
    result["validation"] = validate_draft(draft, space)
    return result


@router.get("/capabilities")
def capabilities(
    workspace_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    config = request.app.state.settings
    configured = bool(config.dataagent_base_url and config.dataagent_access_key)
    return {
        "agent_configured": configured,
        "model": f"DataAgent · {config.dataagent_agent_id}" if configured else "",
        "max_file_mb": config.max_file_mb,
        "connections_configured": bool(config.connection_key),
        "skills": ["md2ossie"],
    }


@router.get("/versions/{version_id}/presentation")
def presentation(
    workspace_id: str,
    version_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    version = current_version(db, workspace_id, version_id)
    model = deepcopy(snapshot_of(version))
    from ontofoundry_api.services.workspaces import membership_role

    if not membership_role(db, workspace_id, user.id):
        # Instances carry evidence quotes; mappings name tables. Members only.
        model.update(material_objects=[], material_links=[], mappings=[])
        for item in model["object_types"] + model["properties"] + model["link_types"] + model[
            "rules"
        ] + model["actions"]:
            item["evidence"] = []
        for link in model.get("link_types", []):
            link.pop("data_join", None)
    return {"version": version_summary(version), "model": model}


@router.post("/sessions/{session_id}/preview")
def preview_definition(
    workspace_id: str,
    session_id: str,
    body: SessionPublish,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    """Exactly what publishing now would produce: the B/L/D merge of base,
    latest and draft, validated and compiled, with the values publish checks."""
    require_member(db, workspace_id, user.id)
    item = get_modeling_session(db, workspace_id, session_id)
    if item.revision != body.session_revision:
        raise ServiceError("草稿已更新，请重新预览", code="SESSION_REVISION_CHANGED", status_code=409)
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
            details={"conflicts": merge.conflicts, "current_version_id": space.current_version_id},
        )
    report = validate_draft(merge.merged, space)
    current = current_version(db, workspace_id) if space.current_version_id else None
    changes = element_changes(merge.latest, merge.merged)
    return {
        "revision": item.revision,
        "session_revision": item.revision,
        "base_version_id": item.base_version_id,
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
        "validation": report,
        "changes": changes,
        "impacts": impacts(changes, merge.merged),
        "auto_merged": auto_merged(merge),
        "ossie": compile_ossie(
            OntologyDraft.model_validate(merge.merged),
            ontology_name=space.slug.replace("-", "_"),
            ontology_description=space.description or space.name,
        )
        if report["publishable"]
        else None,
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
