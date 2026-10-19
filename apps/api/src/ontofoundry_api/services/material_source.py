"""Resolve a material's source file, rebuilding it from database chunks if lost.

Chunks are written in the same transaction as the material row, so they are the
durable copy. A deployment whose data directory was not persisted can recover
uploaded text without asking people to upload everything again.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from sqlalchemy import select

from ontofoundry_api.db_models import MaterialChunkRecord, MaterialRecord


class MaterialSourceMissing(FileNotFoundError):
    """Neither the source file nor any stored chunk is available."""


def material_source_path(db, settings, material: MaterialRecord) -> Path:
    path = settings.data_dir.resolve() / material.workspace_id / (material.sha256 + ".md")
    if path.is_file():
        return path
    chunks = db.scalars(
        select(MaterialChunkRecord)
        .where(MaterialChunkRecord.material_id == material.id)
        .order_by(MaterialChunkRecord.ordinal)
    ).all()
    if not chunks:
        raise MaterialSourceMissing(material.name)
    data = "".join(chunk.text for chunk in chunks).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix="repair-")
    try:
        with os.fdopen(handle, "wb") as target:
            target.write(data)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return path
