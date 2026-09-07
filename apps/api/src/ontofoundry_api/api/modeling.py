from copy import deepcopy
from uuid import uuid4

import jsonschema
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select, update
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
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.ossie.compiler import compile_ossie, validate_ossie
from ontofoundry_api.ossie.importer import OssieImportError, import_ossie
from ontofoundry_api.services.merge import merge_snapshots
from ontofoundry_api.services.ontology_query import _all_graph, version_summary
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


def session_data(item):
    nodes, edges = _all_graph(item.draft_json)
    return {
        "id": item.id,
        "title": item.title,
        "workspace_id": item.workspace_id,
        "base_version_id": item.base_version_id,
        "revision": item.revision,
        "draft": item.draft_json,
        "candidates": item.candidates_json,
        "messages": item.messages_json,
        "material_ids": item.material_ids,
        "task_status": item.task_status,
        "task_detail": item.task_detail,
        "updated_at": item.updated_at,
        "graph": {
            "workspace_id": item.workspace_id,
            "version_id": item.base_version_id or "",
            "version_sha256": "",
            "nodes": nodes,
            "edges": edges,
        },
    }


def revise(db, item, revision, **values):
    if item.task_status in ("queued", "running"):
        raise HTTPException(409, "当前会话正在生成，请等待完成或取消后编辑")
    result = db.execute(
        update(ModelingSessionRecord)
        .where(
            ModelingSessionRecord.id == item.id,
            ModelingSessionRecord.revision == revision,
            ModelingSessionRecord.task_status.not_in(["queued", "running"]),
        )
        .values(**values, revision=revision + 1, updated_at=utc_now())
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "此会话已在其他窗口更新，请刷新后重试")
    db.commit()
    db.refresh(item)
    return session_data(item)


def validate_draft(draft, workspace):
    try:
        model = OntologyDraft.model_validate(draft)
        if str(model.workspace_id) != workspace.id:
            raise ValueError("草稿空间不匹配")
        return validate_ossie(
            compile_ossie(
                model,
                ontology_name=workspace.slug.replace("-", "_"),
                ontology_description=workspace.description or workspace.name,
            )
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
    revision: int
    message: str = Field(default="", max_length=240)


class MergeResolution(BaseModel):
    revision: int
    current_version_id: str
    resolutions: dict[str, str]


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
    if space.current_version_id != body.current_version_id:
        raise HTTPException(409, "最新版本又有变化，请重新比较")

    def snapshot(vid):
        v = db.get(OntologyVersionRecord, vid) if vid else None
        return (
            OntologyDraft.model_validate(v.snapshot_json).model_dump(mode="json")
            if v
            else OntologyDraft(workspace_id=workspace_id).model_dump(mode="json")
        )

    merged, conflicts = merge_snapshots(
        snapshot(item.base_version_id),
        snapshot(space.current_version_id),
        item.draft_json,
        body.resolutions,
    )
    if conflicts:
        raise HTTPException(422, "仍有未解决的字段冲突")
    return revise(
        db, item, body.revision, draft_json=merged, base_version_id=space.current_version_id
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
    draft = (
        OntologyDraft.model_validate(version.snapshot_json).model_dump(mode="json")
        if version
        else OntologyDraft(workspace_id=workspace_id).model_dump(mode="json")
    )
    item = ModelingSessionRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        created_by=user.id,
        title=body.title,
        base_version_id=space.current_version_id,
        draft_json=draft,
    )
    db.add(item)
    db.commit()
    return session_data(item)


@router.get("/sessions/{session_id}")
def read_session(
    workspace_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    return session_data(get_modeling_session(db, workspace_id, session_id))


@router.put("/sessions/{session_id}")
def save_session(
    workspace_id: str,
    session_id: str,
    body: DraftSave,
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
    values = {"draft_json": body.draft}
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
    result["validation"] = validate_draft(body.draft, get_workspace(db, workspace_id))
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
    draft, candidates = deepcopy(item.draft_json), deepcopy(item.candidates_json)
    collection = {
        "object_type": "object_types",
        "link_type": "link_types",
        "object": "objects",
        "link": "links",
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
        OntologyDraft.model_validate(draft)
    except ValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
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
    if item.revision != body.revision or item.task_status in ("queued", "running"):
        raise HTTPException(409, "会话已变化或仍在生成，请刷新后发布")
    empty = OntologyDraft(workspace_id=workspace_id).model_dump(mode="json")

    def snapshot(version_id):
        version = db.get(OntologyVersionRecord, version_id) if version_id else None
        return (
            OntologyDraft.model_validate(version.snapshot_json).model_dump(mode="json")
            if version
            else empty
        )

    merged, conflicts = merge_snapshots(
        snapshot(item.base_version_id), snapshot(space.current_version_id), item.draft_json
    )
    if conflicts:
        raise HTTPException(
            409,
            {
                "message": "当前版本与草稿存在冲突，请在编辑页合并后重试",
                "conflicts": conflicts,
                "current_version_id": space.current_version_id,
                "merged": merged,
            },
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
        item.draft_json = merged
        item.revision += 1
        item.updated_at = utc_now()
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "另一会话刚刚发布，请重新比较后重试") from exc
    return {"version": version_summary(version), "session": session_data(item)}


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
    return (
        OntologyDraft.model_validate(version.snapshot_json).model_dump(mode="json")
        if version
        else OntologyDraft(workspace_id=workspace_id).model_dump(mode="json")
    )


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
            base=version.snapshot_json if version else None,
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
        draft_json=draft,
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
    return {
        "agent_configured": bool(config.anthropic_base_url and config.anthropic_model),
        "model": config.anthropic_model,
        "max_file_mb": config.max_file_mb,
        "connections_configured": bool(config.connection_key),
        "skills": ["md2ossie", "ontology-clarifier"],
    }
