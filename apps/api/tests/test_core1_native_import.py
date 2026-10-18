"""Native single files keep definitions and UUIDs; absent materials only lose evidence."""

import json
from pathlib import Path
from uuid import UUID

import pytest

from ontofoundry_api.adapters.base import ImportContext
from ontofoundry_api.adapters.native.importer import (
    NativeAdapter,
    resolve_material_evidence,
)
from ontofoundry_api.domain.core import COLLECTIONS
from ontofoundry_api.domain.validation import validate_core_graph

ROOT = Path(__file__).resolve().parents[3]
EXAMPLES = ROOT / "docs/design/core-1-examples"
CTX = ImportContext(UUID("22222222-2222-4222-8222-222222222222"))


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("[0-9]*.json")), ids=lambda p: p.stem)
def test_all_thirteen_examples_preserve_every_definition_and_identity(path):
    raw = path.read_bytes()
    original = json.loads(raw)
    result = NativeAdapter().import_document(raw, CTX)
    assert not [i for i in result.report.issues if i.outcome == "error"]
    validate_core_graph(result.model)
    assert result.model.workspace_id == CTX.workspace_id
    for collection in COLLECTIONS:
        actual = getattr(result.model, collection)
        assert [str(e.id) for e in actual] == [
            e["id"] for e in original["draft"][collection]
        ]
        for element, source in zip(actual, original["draft"][collection], strict=True):
            got = element.model_dump(mode="json")
            expected = dict(source)
            if "evidence" in expected:
                expected["evidence"] = [
                    e for e in expected["evidence"] if e["kind"] == "manual"
                ]
                assert got["evidence"] == expected["evidence"]
            # Compare normalized core shapes; optional/default fields may be absent.
            for key, value in expected.items():
                assert got[key] == value
    again = NativeAdapter().import_document(raw, CTX)
    assert again.report == result.report
    assert again.model == result.model


def test_material_resolution_rewrites_by_sha_and_checks_quote_without_mutating_report():
    path = EXAMPLES / "07-instances-and-evidence.json"
    result = NativeAdapter().import_document(path.read_bytes(), CTX)
    assert result.pending_material_evidence
    first = result.pending_material_evidence[0]
    original = result.report.model_dump_json()
    destination = UUID("33333333-3333-4333-8333-333333333333")

    def lookup(sha):
        if sha != first.evidence.material_sha256:
            return None
        lines = [""] * first.evidence.locator.line_end
        lines[first.evidence.locator.line_start - 1] = first.evidence.quote or ""
        return destination, lines

    resolved = resolve_material_evidence(result, lookup)
    evidence = [
        e
        for c in COLLECTIONS
        for item in getattr(resolved.model, c)
        for e in getattr(item, "evidence", [])
        if e.id == first.evidence.id
    ]
    assert len(evidence) == 1
    assert evidence[0].material_id == str(destination)
    assert evidence[0].locator == first.evidence.locator
    assert evidence[0].quote == first.evidence.quote
    assert result.report.model_dump_json() == original
    assert resolved.report.content_sha256 != result.report.content_sha256
    bad = resolve_material_evidence(result, lambda sha: (destination, ["wrong quote"]))
    assert all(
        e.kind == "manual"
        for c in COLLECTIONS
        for item in getattr(bad.model, c)
        for e in getattr(item, "evidence", [])
    )


@pytest.mark.parametrize(
    "change",
    [
        {"extra": 1},
        {"schema_version": "3"},
        {"format": "zip"},
        {"exported_at": "not-a-date"},
    ],
)
def test_invalid_envelope_is_file_error(change):
    value = json.loads((EXAMPLES / "01-basic-sales.json").read_bytes())
    value.update(change)
    result = NativeAdapter().import_document(json.dumps(value).encode(), CTX)
    assert not result.model.object_types
    assert result.report.issues[0].outcome == "error"
