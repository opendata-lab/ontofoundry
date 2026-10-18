"""Report integrity and adapter isolation, independently of any database."""

import hashlib
import json
from uuid import UUID

import pytest

from ontofoundry_api.adapters import get_adapter
from ontofoundry_api.adapters.base import ImportContext
from ontofoundry_api.adapters.documents import SourceDocument

CTX = ImportContext(UUID("11111111-1111-4111-8111-111111111111"))


def test_formatted_source_spans_and_escaped_pointers_are_real():
    raw = b'{"a/b":{"~name":[1,{"x":"test"}]}}'
    source = SourceDocument.parse(raw)
    assert json.loads(source.formatted) == json.loads(raw)
    for pointer, (start, end) in source.spans.items():
        assert source.get(pointer) is not None
        locator = source.locator(pointer)
        assert locator["sha256"] == hashlib.sha256(raw).hexdigest()
        assert (
            locator["formatted_sha256"]
            == hashlib.sha256(source.formatted.encode()).hexdigest()
        )
        assert locator["line_start"] == start and locator["line_end"] == end
    assert source.get("/a~1b/~0name/1/x") == "test"


@pytest.mark.parametrize("adapter_id", ["ossie-0.2", "ontofoundry-core-1"])
@pytest.mark.parametrize("raw", [b'{\n"broken":', b"\xff", b'{"x":NaN}', b'{"x":1,"x":2}'])
def test_parse_errors_never_invent_json_pointers(adapter_id, raw):
    result = get_adapter(adapter_id).import_document(raw, CTX)
    assert not result.model.object_types
    issue = result.report.issues[0]
    assert issue.outcome == "error"
    assert "json_pointer" not in issue.source_locator
    if raw.startswith(b"{\n"):
        assert issue.source_locator["line"] == 2


def test_explicit_selection_does_not_guess_formats_or_enable_generic_diff():
    adapter = get_adapter("ossie")
    assert adapter.id == "ossie-0.2"
    with pytest.raises(ValueError):
        get_adapter("automatic")
    assert callable(adapter.export_document)
    with pytest.raises(NotImplementedError):
        adapter.diff_roundtrip(b"", b"")
