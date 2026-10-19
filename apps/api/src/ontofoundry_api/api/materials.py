import hashlib
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import require_member
from ontofoundry_api.contracts.materials import MaterialOverview
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import (
    MaterialChunkRecord,
    MaterialRecord,
    utc_now,
)
from ontofoundry_api.services.errors import ConflictError
from ontofoundry_api.services.material_source import (
    MaterialSourceMissing,
    material_source_path,
)
from ontofoundry_api.services.material_types import is_material_name, material_media_type
from ontofoundry_api.services.material_usage import material_references, material_usage

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/materials", tags=["materials"])


def describe(item):
    return {
        "id": item.id,
        "name": item.name,
        "sha256": item.sha256,
        "byte_size": item.byte_size,
        "chunk_count": item.chunk_count,
        "created_at": item.created_at,
        "archived_at": item.archived_at,
    }


def store_text_material(db: Session, settings, workspace_id: str, name: str, text: str):
    from ontofoundry_api.services.material_store import store_text_material as store

    item = store(db, settings, workspace_id, name, text)
    db.commit()
    return item


@router.get("")
def list_materials(
    workspace_id: str,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    query = select(MaterialRecord).where(MaterialRecord.workspace_id == workspace_id)
    if not include_archived:
        # Archived material stays readable as evidence but is not offered for
        # new modeling runs.
        query = query.where(MaterialRecord.archived_at.is_(None))
    return {
        "items": [
            describe(m)
            for m in db.scalars(query.order_by(MaterialRecord.created_at.desc())).all()
        ]
    }


@router.get("/overview", response_model=MaterialOverview)
def overview(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    materials = db.scalars(select(MaterialRecord).where(
        MaterialRecord.workspace_id == workspace_id
    ).order_by(MaterialRecord.created_at.desc())).all()
    usage = material_usage(db, workspace_id, {item.id for item in materials})
    return {"items": [{**describe(item), "usage": usage[item.id]} for item in materials]}


@router.post("", status_code=201)
async def upload(
    workspace_id: str,
    request: Request,
    name: str = Query(min_length=1, max_length=240),
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    if not is_material_name(name):
        raise HTTPException(422, "仅支持 UTF-8 文本材料：Markdown、TXT、JSON、YAML、CSV")
    root = request.app.state.settings.data_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    digest, size = hashlib.sha256(), 0
    temporary = tempfile.NamedTemporaryFile(dir=root, prefix="upload-", delete=False)  # noqa: SIM115 - entered below; path needed for cleanup after streaming
    path = Path(temporary.name)
    try:
        with temporary:
            async for block in request.stream():
                size += len(block)
                if size > request.app.state.settings.max_file_mb * 1024 * 1024:
                    raise HTTPException(413, "文件超过上传限制")
                digest.update(block)
                temporary.write(block)
        if not size:
            raise HTTPException(422, "文件为空")
        sha = digest.hexdigest()
        existing = db.scalar(
            select(MaterialRecord).where(
                MaterialRecord.workspace_id == workspace_id, MaterialRecord.sha256 == sha
            )
        )
        if existing:
            # Identical content still restores a source file lost by a
            # deployment whose data directory was not persisted.
            destination = root / workspace_id / (sha + ".md")
            if not destination.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                path.replace(destination)
            return describe(existing)
        item = MaterialRecord(
            id=str(uuid4()),
            workspace_id=workspace_id,
            name=Path(name).name,
            sha256=sha,
            byte_size=size,
        )
        db.add(item)
        db.flush()
        count, line = 0, 1
        try:
            with path.open(encoding="utf-8-sig") as source:
                while text := source.read(12000):
                    end = line + text.count("\n")
                    db.add(
                        MaterialChunkRecord(
                            material_id=item.id,
                            ordinal=count,
                            line_start=line,
                            line_end=end,
                            text=text,
                        )
                    )
                    count, line = count + 1, end
                    if count % 100 == 0:
                        db.flush()
        except UnicodeError as exc:
            db.rollback()
            raise HTTPException(422, "文件编码须为 UTF-8") from exc
        item.chunk_count = count
        destination = root / workspace_id / (sha + ".md")
        destination.parent.mkdir(parents=True, exist_ok=True)
        path.replace(destination)
        db.commit()
        return describe(item)
    finally:
        # Only the random temporary upload is removed; immutable source files remain.
        path.unlink(missing_ok=True)


@router.get("/{material_id}")
def download(
    workspace_id: str,
    material_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    item = db.get(MaterialRecord, material_id)
    if not item or item.workspace_id != workspace_id:
        raise HTTPException(404, "材料不存在")
    path = request.app.state.settings.data_dir / workspace_id / (item.sha256 + ".md")
    if not path.is_file():
        try:
            path = material_source_path(db, request.app.state.settings, item)
        except MaterialSourceMissing:
            raise HTTPException(404, "源文件缺失，请联系管理员恢复备份") from None
    return FileResponse(path, filename=item.name, media_type=material_media_type(item.name))


def _material(db: Session, workspace_id: str, material_id: str) -> MaterialRecord:
    item = db.get(MaterialRecord, material_id)
    if not item or item.workspace_id != workspace_id:
        raise HTTPException(404, "材料不存在")
    return item


@router.post("/{material_id}/archive")
def archive(
    workspace_id: str,
    material_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    item = _material(db, workspace_id, material_id)
    if item.archived_at is None:
        item.archived_at, item.archived_by = utc_now(), user.id
        db.commit()
    return describe(item)


@router.post("/{material_id}/restore")
def restore(
    workspace_id: str,
    material_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    item = _material(db, workspace_id, material_id)
    item.archived_at, item.archived_by = None, None
    db.commit()
    return describe(item)


@router.delete("/{material_id}", status_code=204)
def delete_material(
    workspace_id: str,
    material_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    """Physically remove material that nothing cites; cited material is archived."""
    require_member(db, workspace_id, user.id, admin=True)
    item = _material(db, workspace_id, material_id)
    references = material_references(db, workspace_id, material_id)
    if references:
        raise ConflictError(
            "材料已被引用，不能删除，只能归档：" + "、".join(references),
            code="MATERIAL_IN_USE",
            details={"references": references},
        )
    sha = item.sha256
    db.execute(
        sql_delete(MaterialChunkRecord).where(
            MaterialChunkRecord.material_id == material_id
        )
    )
    db.delete(item)
    db.commit()
    still_used = db.scalar(
        select(MaterialRecord).where(
            MaterialRecord.workspace_id == workspace_id, MaterialRecord.sha256 == sha
        )
    )
    if still_used is None:
        (request.app.state.settings.data_dir / workspace_id / (sha + ".md")).unlink(
            missing_ok=True
        )
