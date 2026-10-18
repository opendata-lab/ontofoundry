"""Keep uploaded bytes and an independently hashed, line-addressable JSON material."""

import hashlib
from pathlib import Path

from ontofoundry_api.adapters.documents import SourceDocument
from ontofoundry_api.services.material_store import store_text_material


def store_import_materials(db, settings, workspace_id, filename, raw):
    digest = hashlib.sha256(raw).hexdigest()
    relative = Path(workspace_id) / "imports" / (digest + ".json")
    path = settings.data_dir.resolve() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    try:
        document = SourceDocument.parse(raw)
    except (ValueError, UnicodeError, RecursionError):
        return str(relative), None
    material = store_text_material(db, settings, workspace_id, filename, document.formatted)
    return str(relative), material
