"""Authorized callers export immutable published snapshots without database writes."""

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from ontofoundry_api.adapters import get_adapter
from ontofoundry_api.adapters.base import ExportContext
from ontofoundry_api.adapters.exporting import json_bytes
from ontofoundry_api.contracts.exports import ExportPreview
from ontofoundry_api.db_models import WorkspaceRecord
from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.services.dataset_sources import resolve_dataset
from ontofoundry_api.services.errors import ConflictError, NotFoundError, ServiceError
from ontofoundry_api.services.import_integrity import payload_sha256
from ontofoundry_api.services.ontology_query import current_version, snapshot_of


def adapter_for(adapter_id):
    try:
        return get_adapter(adapter_id)
    except ValueError as error:
        raise NotFoundError("不支持的导出格式", code="EXPORT_ADAPTER_NOT_FOUND") from error


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def export_root(settings, workspace_id, version_id, adapter):
    return settings.data_dir / workspace_id / "exports" / version_id / adapter


def export_snapshot(db, settings, workspace_id, adapter_id, version_id):
    adapter = adapter_for(adapter_id)
    version = current_version(db, workspace_id, version_id)
    workspace = db.get(WorkspaceRecord, workspace_id)
    model = CoreDraft.model_validate(snapshot_of(version))
    scopes = {}
    for dataset in model.datasets:
        try:
            scopes[dataset.id] = resolve_dataset(db, workspace_id, dataset).connection.id
        except ServiceError:
            continue
    identity = payload_sha256(
        {
            "version_id": version.id,
            "snapshot": model.model_dump(mode="json"),
            "workspace": [workspace.name, workspace.slug, workspace.description],
            "adapter": adapter.id,
            "scopes": {str(k): v for k, v in scopes.items()},
            "compiler": "core-1-export-v1",
        }
    )
    root = export_root(settings, workspace_id, version.id, adapter.id)
    cached = root / ("preview-" + identity + ".json")
    if cached.is_file():
        try:
            preview = ExportPreview.model_validate_json(cached.read_bytes())
            if preview.content_sha256:
                artifact_bytes(
                    settings, workspace_id, adapter.id, version.id, preview.content_sha256
                )
            return preview
        except (ValueError, OSError, ServiceError):
            pass
    ctx = ExportContext(
        workspace_name=workspace.name,
        workspace_slug=workspace.slug,
        workspace_description=workspace.description,
        exported_at=datetime.now(UTC).isoformat(),
        dataset_scopes=scopes,
    )
    result = adapter.export_document(model, ctx)
    digest = (
        hashlib.sha256(result.document).hexdigest() if result.document is not None else None
    )
    url = (
        f"/api/v1/modeling/workspaces/{workspace_id}/exports/{adapter.id}/artifacts/{digest}?version_id={version.id}"
        if digest
        else None
    )
    preview = ExportPreview(
        version_id=version.id,
        adapter=adapter.id,
        report=result.report,
        content_sha256=digest,
        filename=result.filename,
        media_type=result.media_type,
        download_url=url,
    )
    if digest:
        atomic_write(root / (digest + ".json"), result.document)
        atomic_write(
            root / (digest + ".metadata.json"),
            json_bytes(
                {
                    "version_id": version.id,
                    "adapter": adapter.id,
                    "filename": result.filename,
                    "media_type": result.media_type,
                    "content_sha256": digest,
                }
            ),
        )
    atomic_write(cached, preview.model_dump_json().encode())
    return preview


def artifact_bytes(settings, workspace_id, adapter, version_id, digest):
    if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise NotFoundError("导出文件不存在", code="EXPORT_NOT_FOUND")
    root = export_root(settings, workspace_id, version_id, adapter)
    path = root / (digest + ".json")
    metadata = root / (digest + ".metadata.json")
    try:
        data = path.read_bytes()
        description = json.loads(metadata.read_bytes())
    except (OSError, ValueError) as error:
        raise NotFoundError(
            "导出文件不存在或已失效，请重新生成报告", code="EXPORT_NOT_FOUND"
        ) from error
    if (
        hashlib.sha256(data).hexdigest() != digest
        or description.get("content_sha256") != digest
        or description.get("version_id") != version_id
        or description.get("adapter") != adapter
    ):
        raise ConflictError(
            "导出文件完整性校验失败，请重新生成报告", code="EXPORT_ARTIFACT_CHANGED"
        )
    return data, description


def download_export(db, settings, workspace_id, adapter_id, version_id, digest):
    adapter = adapter_for(adapter_id)
    version = current_version(db, workspace_id, version_id)
    return artifact_bytes(settings, workspace_id, adapter.id, version.id, digest)
