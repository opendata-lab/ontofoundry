"""Keep uploaded bytes and an independently hashed, line-addressable JSON material."""

import hashlib
from pathlib import Path

from ontofoundry_api.adapters.archive import read_ossie
from ontofoundry_api.adapters.documents import SourceDocument
from ontofoundry_api.services.material_store import store_text_material


def store_import_materials(db, settings, workspace_id, filename, raw):
    digest = hashlib.sha256(raw).hexdigest()
    relative = Path(workspace_id) / "imports" / (digest + ".json")
    path = settings.data_dir.resolve() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    try:
        if raw.startswith(b"PK"):
            from ontofoundry_api.adapters.archive import read_archive
            from ontofoundry_api.adapters.native.package import unpack

            members = read_archive(raw)
            document_raw = (
                unpack(raw)[0] if "manifest.json" in members else read_ossie(raw)[0]
            )
        else:
            document_raw = raw
        document = SourceDocument.parse(document_raw)
    except (ValueError, UnicodeError, RecursionError, KeyError, TypeError, AttributeError):
        return str(relative), None
    material = store_text_material(db, settings, workspace_id, filename, document.formatted)
    return str(relative), material
