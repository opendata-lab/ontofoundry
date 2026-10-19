"""Material lookup for evidence checks: id -> (sha256, text lines) in one workspace."""

from __future__ import annotations

from ontofoundry_api.db_models import MaterialRecord
from ontofoundry_api.domain.evidence import MaterialLookup
from ontofoundry_api.services.material_source import (
    MaterialSourceMissing,
    material_source_path,
)


def material_lookup(db, settings, workspace_id: str) -> MaterialLookup:
    cache: dict[str, tuple[str, list[str]] | None] = {}

    def look(material_id: str) -> tuple[str, list[str]] | None:
        if material_id not in cache:
            record = db.get(MaterialRecord, material_id)
            if record is None or record.workspace_id != workspace_id:
                cache[material_id] = None
            else:
                try:
                    path = material_source_path(db, settings, record)
                except MaterialSourceMissing:
                    lines = []
                else:
                    lines = path.read_text(encoding="utf-8-sig").splitlines()
                cache[material_id] = (record.sha256, lines)
        return cache[material_id]

    return look
