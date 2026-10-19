"""Shared text-material storage; the caller owns its database transaction."""

import hashlib
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from ontofoundry_api.db_models import MaterialChunkRecord, MaterialRecord


def store_text_material(db, settings, workspace_id, name, text):
    data = text.encode("utf-8")
    sha = hashlib.sha256(data).hexdigest()
    existing = db.scalar(
        select(MaterialRecord).where(
            MaterialRecord.workspace_id == workspace_id, MaterialRecord.sha256 == sha
        )
    )
    if existing:
        # Re-uploading identical content must restore a source file that a
        # deployment without a persistent data directory lost.
        destination = settings.data_dir.resolve() / workspace_id / (sha + ".md")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return existing
    item = MaterialRecord(
        id=str(uuid4()),
        workspace_id=workspace_id,
        name=Path(name).name[:240],
        sha256=sha,
        byte_size=len(data),
    )
    db.add(item)
    db.flush()
    count, line = 0, 1
    for start in range(0, len(text), 12000):
        chunk = text[start : start + 12000]
        end = line + chunk.count("\n")
        db.add(
            MaterialChunkRecord(
                material_id=item.id,
                ordinal=count,
                line_start=line,
                line_end=end,
                text=chunk,
            )
        )
        count, line = count + 1, end
    item.chunk_count = count
    destination = settings.data_dir.resolve() / workspace_id / (sha + ".md")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return item
