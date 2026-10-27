"""Persist previews and atomically turn a confirmed preview into pending proposals."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID, uuid4, uuid5

from sqlalchemy import select, update

from ontofoundry_api.adapters import get_adapter
from ontofoundry_api.adapters.base import ImportContext
from ontofoundry_api.adapters.native.importer import resolve_material_evidence
from ontofoundry_api.contracts.imports import ImportPreview
from ontofoundry_api.db_models import (
    ImportRecord,
    MaterialRecord,
    ModelingSessionRecord,
    OntologyElementIdentityRecord,
    OntologyVersionRecord,
    WorkspaceRecord,
)
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.snapshot import draft_sha256, empty_snapshot, read_snapshot_json
from ontofoundry_api.services.errors import ConflictError, NotFoundError, ServiceError
from ontofoundry_api.services.import_integrity import payload_sha256
from ontofoundry_api.services.import_matching import build_candidate_graph
from ontofoundry_api.services.import_materials import store_import_materials
from ontofoundry_api.services.import_proposals import build_import_batch
from ontofoundry_api.services.material_source import (
    MaterialSourceMissing,
    material_source_path,
)
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.proposals import store_batch


def adapter_for(adapter_id):
    try:
        return get_adapter(adapter_id)
    except ValueError as error:
        raise NotFoundError(str(error), code="IMPORT_ADAPTER_NOT_FOUND") from error


def baseline(db, workspace):
    version = (
        db.get(OntologyVersionRecord, workspace.current_version_id)
        if workspace.current_version_id
        else None
    )
    return (
        read_snapshot_json(version.snapshot_json, workspace.id)
        if version
        else empty_snapshot(workspace.id)
    )


def identities(db, workspace_id):
    return {
        r.element_id: r.kind
        for r in db.scalars(
            select(OntologyElementIdentityRecord).where(
                OntologyElementIdentityRecord.workspace_id == workspace_id
            )
        )
    }


def preview_payload(record):
    return {
        key: getattr(record, key)
        for key in (
            "adapter",
            "filename",
            "raw_sha256",
            "formatted_sha256",
            "material_id",
            "report_json",
            "converted_json",
            "preview_json",
            "base_version_id",
            "base_version_sha256",
        )
    }


def get_import(db, workspace_id, adapter_id, import_id, *, lock=False):
    adapter = adapter_for(adapter_id)
    query = select(ImportRecord).where(
        ImportRecord.id == import_id,
        ImportRecord.workspace_id == workspace_id,
        ImportRecord.adapter == adapter.id,
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    record = db.scalar(query)
    if record is None:
        raise NotFoundError("导入报告不存在", code="IMPORT_NOT_FOUND")
    return record


def preview_import(db, settings, workspace_id, actor_id, adapter_id, filename, raw):
    adapter = adapter_for(adapter_id)
    workspace = db.get(WorkspaceRecord, workspace_id)
    if workspace is None:
        raise NotFoundError("工作空间不存在")
    base = baseline(db, workspace)
    from ontofoundry_api.db_models import ConnectionRecord, MetadataSnapshotRecord
    from ontofoundry_api.services.metadata_sync import normalize_schema

    connections = tuple({"id": c.id, "name": c.name, "kind": c.kind, "default_schema": normalize_schema(c, None) or None} for c in db.scalars(select(ConnectionRecord).where(ConnectionRecord.workspace_id == workspace_id)))
    ids = [c["id"] for c in connections]
    registered = tuple({"connection_id": snap.connection_id, "schema_name": snap.schema_name, **table} for snap in db.scalars(select(MetadataSnapshotRecord).where(MetadataSnapshotRecord.connection_id.in_(ids))) for table in snap.snapshot_json.get("tables", []) if not table.get("missing"))
    result = adapter.import_document(raw, ImportContext(UUID(workspace_id), connections, registered))
    if result.bundled_materials:
        from ontofoundry_api.services.material_store import store_text_material

        for entry in result.bundled_materials:
            store_text_material(
                db, settings, workspace_id, entry["name"], entry["data"].decode("utf-8")
            )
        db.flush()
    if result.pending_material_evidence:
        lookup = material_lookup(db, settings, workspace_id)

        def same_sha(sha):
            material = db.scalar(
                select(MaterialRecord).where(
                    MaterialRecord.workspace_id == workspace_id,
                    MaterialRecord.sha256 == sha,
                )
            )
            found = lookup(material.id) if material else None
            return (UUID(material.id), found[1]) if found else None

        result = resolve_material_evidence(result, same_sha)
    artifact, material = store_import_materials(db, settings, workspace_id, filename, raw)
    candidate = build_candidate_graph(
        CoreDraft.model_validate(base),
        result.model,
        native=adapter.id in {"ontofoundry-core-1", "ontofoundry-core-1-package"},
        registered=identities(db, workspace_id),
    )
    record = ImportRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        created_by=actor_id,
        adapter=adapter.id,
        filename=Path(filename.replace("\\", "/")).name[:240] or "导入.json",
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        raw_artifact=artifact,
        material_id=material.id if material else None,
        formatted_sha256=material.sha256 if material else None,
        report_json=result.report.model_dump(mode="json"),
        converted_json=result.model.model_dump(mode="json"),
        preview_json={
            "id_map": candidate.id_map,
            "changes": candidate.changes,
            "unchanged": candidate.unchanged,
            "blocked": candidate.blocked,
        },
        base_version_id=workspace.current_version_id,
        base_version_sha256=draft_sha256(base),
        content_sha256="",
        completions_json=[],
    )
    record.content_sha256 = payload_sha256(preview_payload(record))
    db.add(record)
    db.commit()
    return import_view(db, record)


def confirmed_view(record):
    return {
        "session_id": record.session_id,
        "batch_id": record.batch_id,
        "report_id": record.id,
    }


def import_view(db, record):
    from ontofoundry_api.services.import_completion import (
        completion_list,
        current_import_blocked,
    )

    if record.preview_json.get("invalidated"):
        raise ServiceError("导入转换结果已失效，请重新导入", code="IMPORT_INVALIDATED", status_code=409)
    changes = record.preview_json["changes"]
    blocked = current_import_blocked(db, record)
    return ImportPreview.model_validate(
        {
            "import_id": record.id,
            "adapter": record.adapter,
            "filename": record.filename,
            "report": record.report_json,
            "content_sha256": record.content_sha256,
            "raw_sha256": record.raw_sha256,
            "formatted_sha256": record.formatted_sha256,
            "material_id": record.material_id,
            "base_version_id": record.base_version_id,
            "proposal_summary": {
                "create": sum(c["operation"] == "create" for c in changes),
                "update": sum(c["operation"] == "update" for c in changes),
                "unchanged": record.preview_json["unchanged"],
                "blocked": record.preview_json["blocked"],
            },
            "id_map": record.preview_json["id_map"],
            "current_blocked": blocked,
            "document_error": any(
                i["outcome"] == "error" and i["construct"] == "document"
                for i in record.report_json["issues"]
            ),
            "completion": completion_list(db, record, blocked=blocked),
            "confirmed": confirmed_view(record) if record.session_id else None,
        }
    )


def check_artifacts(record, settings, *, db):
    if record.content_sha256 != payload_sha256(preview_payload(record)):
        raise ConflictError("预览内容校验失败，请重新上传", code="IMPORT_CONTENT_CHANGED")
    path = settings.data_dir.resolve() / record.raw_artifact
    # A missing upload is not a changed upload: everything needed to confirm is
    # stored in the database, and deployments can lose the data directory. A
    # present file must still match the preview.
    if (
        path.is_file()
        and hashlib.sha256(path.read_bytes()).hexdigest() != record.raw_sha256
    ):
        raise ConflictError("原始文件已失效，请重新上传", code="IMPORT_ARTIFACT_CHANGED")
    if record.formatted_sha256:
        material = (
            db.get(MaterialRecord, record.material_id) if record.material_id else None
        )
        if material is None or material.sha256 != record.formatted_sha256:
            raise ConflictError(
                "引用材料已失效，请重新上传", code="IMPORT_ARTIFACT_CHANGED"
            )
        try:
            path = material_source_path(db, settings, material)
        except MaterialSourceMissing:
            raise ConflictError(
                "引用材料已失效，请重新上传", code="IMPORT_ARTIFACT_CHANGED"
            ) from None
        if hashlib.sha256(path.read_bytes()).hexdigest() != record.formatted_sha256:
            raise ConflictError(
                "引用材料已失效，请重新上传", code="IMPORT_ARTIFACT_CHANGED"
            )


def source_evidence(record, settings, *, changes=None, batch_id=None, db):
    if not record.material_id:
        return {}
    material = db.get(MaterialRecord, record.material_id)
    if material is None or material.sha256 != record.formatted_sha256:
        return {}
    lines = material_source_path(db, settings, material).read_text().splitlines()
    result = {}
    allowed = {c["target_id"] for c in changes or record.preview_json["changes"]}
    for issue in record.report_json["issues"]:
        locator = issue["source_locator"]
        if locator.get("formatted_sha256") != record.formatted_sha256 or not locator.get(
            "line_start"
        ):
            continue
        for original_id in issue["target_element_ids"]:
            target = record.preview_json["id_map"].get(original_id, original_id)
            if target not in allowed or target in result:
                continue
            start, end = locator["line_start"], locator["line_end"]
            result[target] = [
                {
                    "kind": "material",
                    "id": str(uuid5(UUID(batch_id or record.id), "source:" + target)),
                    "material_id": record.material_id,
                    "material_sha256": record.formatted_sha256,
                    "locator": {"line_start": start, "line_end": end},
                    "quote": "\n".join(lines[start - 1 : end])[:2000],
                }
            ]
    return result


def confirm_import(db, settings, workspace_id, actor_id, adapter_id, import_id, body):
    workspace = db.scalar(
        select(WorkspaceRecord)
        .where(WorkspaceRecord.id == workspace_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    record = get_import(db, workspace_id, adapter_id, import_id, lock=True)
    if record.preview_json.get("invalidated"):
        raise ServiceError("导入转换结果已失效，请重新导入", code="IMPORT_INVALIDATED", status_code=409)
    if (
        body.content_sha256 != record.content_sha256
        or (
            str(body.expected_current_version_id)
            if body.expected_current_version_id
            else None
        )
        != record.base_version_id
    ):
        raise ConflictError(
            "确认内容与预览不符，请重新预览", code="IMPORT_PREVIEW_MISMATCH"
        )
    request_hash = payload_sha256(body.model_dump(mode="json"))
    if record.session_id:
        if record.confirmation_sha256 != request_hash:
            raise ConflictError(
                "此预览已确认，请打开已生成会话",
                code="IMPORT_ALREADY_CONFIRMED",
                details=confirmed_view(record),
            )
        return confirmed_view(record)
    check_artifacts(record, settings, db=db)
    if (
        workspace.current_version_id != record.base_version_id
        or draft_sha256(baseline(db, workspace)) != record.base_version_sha256
    ):
        raise ConflictError(
            "已发布版本已变化，请重新预览文件",
            code="IMPORT_BASE_CHANGED",
            details={"current_version_id": workspace.current_version_id},
        )
    if any(
        i["outcome"] == "error" and i["construct"] == "document"
        for i in record.report_json["issues"]
    ):
        raise ServiceError(
            "文件校验失败，请修正后重新上传",
            code="IMPORT_DOCUMENT_INVALID",
            status_code=422,
        )
    # Compare-and-lock the head in the database, including on SQLite.
    guard = (
        WorkspaceRecord.current_version_id == record.base_version_id
        if record.base_version_id
        else WorkspaceRecord.current_version_id.is_(None)
    )
    pinned = db.execute(
        update(WorkspaceRecord)
        .where(WorkspaceRecord.id == workspace_id, guard)
        .values(
            current_version_id=WorkspaceRecord.current_version_id,
            updated_at=WorkspaceRecord.updated_at,
        )
    )
    if pinned.rowcount != 1:
        raise ConflictError("已发布版本已变化，请重新预览文件", code="IMPORT_BASE_CHANGED")
    # Conditional reservation also serializes SQLite confirmations.
    claimed = db.execute(
        update(ImportRecord)
        .where(ImportRecord.id == record.id, ImportRecord.confirmation_sha256.is_(None))
        .values(confirmation_sha256=request_hash)
    )
    if claimed.rowcount != 1:
        db.refresh(record)
        if record.session_id and record.confirmation_sha256 == request_hash:
            return confirmed_view(record)
        raise ConflictError("导入正在确认，请重试同一请求", code="IMPORT_CONFIRMING")
    base = baseline(db, workspace)
    # Recheck registry changes even when the published head is unchanged.
    recomputed = build_candidate_graph(
        CoreDraft.model_validate(base),
        CoreDraft.model_validate(record.converted_json),
        native=record.adapter == "ontofoundry-core-1",
        registered=identities(db, workspace_id),
    )
    if (
        recomputed.changes != record.preview_json["changes"]
        or recomputed.blocked != record.preview_json["blocked"]
    ):
        raise ConflictError("元素身份已变化，请重新预览", code="IMPORT_IDENTITIES_CHANGED")
    session = ModelingSessionRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        created_by=actor_id,
        title=("导入 · " + record.filename)[:120],
        base_version_id=record.base_version_id,
        base_version_sha256=record.base_version_sha256,
        draft_json=base,
        draft_sha256=record.base_version_sha256,
        material_ids=[record.material_id] if record.material_id else [],
    )
    db.add(session)
    db.flush()
    batch_id = str(uuid5(UUID(record.id), "initial-batch"))
    parsed = build_import_batch(
        base,
        record.preview_json["changes"],
        batch_id=batch_id,
        lookup=material_lookup(db, settings, workspace_id),
        evidence_by_target=source_evidence(record, settings, batch_id=batch_id, db=db),
    )
    store_batch(
        db,
        workspace_id=workspace_id,
        session_id=session.id,
        task_id=None,
        manifest={
            "run_token": "import:" + record.id,
            "base_version_id": record.base_version_id,
            "base_version_sha256": record.base_version_sha256,
            "source_session_revision": 0,
            "source_draft_sha256": record.base_version_sha256,
            "materials": [{"id": record.material_id, "sha256": record.formatted_sha256}]
            if record.material_id
            else [],
            "producer": {
                "kind": "import",
                "adapter": record.adapter,
                "report_id": record.id,
            },
        },
        parsed=parsed,
        settings=settings,
    )
    record.session_id, record.batch_id, record.confirmation_sha256 = (
        session.id,
        batch_id,
        request_hash,
    )
    db.commit()
    return confirmed_view(record)
