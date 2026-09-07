import hashlib
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import require_member
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import MaterialChunkRecord, MaterialRecord

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/materials", tags=["materials"])


def describe(item):
    return {
        "id": item.id,
        "name": item.name,
        "sha256": item.sha256,
        "byte_size": item.byte_size,
        "chunk_count": item.chunk_count,
        "created_at": item.created_at,
    }


@router.get("")
def list_materials(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    return {
        "items": [
            describe(m)
            for m in db.scalars(
                select(MaterialRecord)
                .where(MaterialRecord.workspace_id == workspace_id)
                .order_by(MaterialRecord.created_at.desc())
            ).all()
        ]
    }


@router.post("", status_code=201)
async def upload(
    workspace_id: str,
    request: Request,
    name: str = Query(min_length=1, max_length=240),
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_member(db, workspace_id, user.id)
    if Path(name).suffix.lower() not in (".md", ".markdown"):
        raise HTTPException(422, "当前仅支持 UTF-8 Markdown 文件")
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
        raise HTTPException(404, "源文件缺失，请联系管理员恢复备份")
    return FileResponse(path, filename=item.name, media_type="text/markdown")
