"""Native standalone files preserve definitions and UUIDs, with explicit material loss."""

import hashlib
import json
from uuid import UUID

import pytest
from core1_fixtures import example_draft, example_names

from ontofoundry_api.adapters.base import ExportContext, ImportContext
from ontofoundry_api.adapters.native.importer import NativeAdapter

CTX = ExportContext(
    "虚构往返", "fictional-roundtrip", "虚构验收", exported_at="2026-10-18T00:00:00+00:00"
)


@pytest.mark.parametrize("name", example_names())
def test_thirteen_native_exports_preserve_every_core_definition_and_uuid(name):
    model = example_draft(name)
    result = NativeAdapter().export_document(model, CTX)
    assert result.document is not None
    assert hashlib.sha256(result.document).hexdigest() == result.report.content_sha256
    document = json.loads(result.document)
    assert set(document) == {"format", "schema_version", "exported_at", "draft"}
    assert document["draft"] == model.model_dump(mode="json")
    assert result.report.direction == "export"
    restored = NativeAdapter().import_document(
        result.document, ImportContext(model.workspace_id)
    )
    expected = model.model_dump(mode="json")
    for collection in (
        "object_types",
        "properties",
        "link_types",
        "rules",
        "metrics",
        "material_objects",
        "material_links",
    ):
        for item in expected[collection]:
            item["evidence"] = [
                e for e in item.get("evidence", []) if e["kind"] == "manual"
            ]
    assert restored.model.model_dump(mode="json") == expected
    assert NativeAdapter().export_document(model, CTX) == result


def test_native_import_applies_only_explicit_destination_workspace():
    source = example_draft("07-instances-and-evidence")
    exported = NativeAdapter().export_document(source, CTX)
    destination = UUID("33333333-3333-4333-8333-333333333333")
    result = NativeAdapter().import_document(exported.document, ImportContext(destination))
    assert result.model.workspace_id == destination
    assert [o.id for o in result.model.material_objects] == [
        o.id for o in source.material_objects
    ]
