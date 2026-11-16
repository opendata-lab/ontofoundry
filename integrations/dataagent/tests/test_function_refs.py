"""Platform-rejected functions found locally, from lists generated off the platform code."""

import importlib
import json
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import test_workflow  # noqa: F401 - puts the skill scripts on sys.path
from generate_output_schemas import FUNCTIONS_FILE, function_lists

function_refs = importlib.import_module("function_refs")


def item(kind, after, ref="x"):
    return {"operation": "create", "target_kind": kind, "client_ref": ref, "after": after}


def test_lists_match_the_platform_code():
    # A platform change to SCALAR_FUNCTIONS or QUERY_NODES must be regenerated (make schemas).
    stored = json.loads(FUNCTIONS_FILE.read_bytes())
    assert {k: stored[k] for k in ("expression", "query_sql")} == function_lists()


def test_lists_agree_with_the_platform_checks():
    pytest.importorskip("ontofoundry_api")
    from ontofoundry_api.services.dataset_sql import parse_query
    from ontofoundry_api.services.errors import DatasetSourceError

    def platform_rejects(sql, dialect):
        try:
            parse_query(sql, dialect)
        except DatasetSourceError:
            return True
        return False

    for name in ("GREATEST", "LEAST"):
        assert name in function_refs.REJECTED["query_sql"]
        assert platform_rejects(f"SELECT {name}(a, b) FROM t", "mysql")
    for name in ("COALESCE", "IFNULL", "CURDATE", "DATE_ADD", "ROUND"):
        assert name not in function_refs.REJECTED["query_sql"]
    assert not platform_rejects("SELECT COALESCE(a, 0), CURDATE(), ROUND(b, 2) FROM t", "mysql")


@pytest.mark.parametrize("kind, after, expected", [
    ("dataset", {"source_kind": "query", "query_sql": "SELECT GREATEST(a, b) AS n FROM t"}, [("x", "query_sql", "GREATEST")]),
    ("rule", {"expression": "order.order_date <= CURDATE()"}, [("x", "expression", "CURDATE")]),
    ("rule", {"expression": "now ( ) > 1 AND ROUND(a, 1) > 0"}, [("x", "expression", "NOW")]),
    ("mapping", {"fields": {"n": {"kind": "expression", "expression": "GREATEST(s.a, s.b)"}}}, [("x", "expression", "GREATEST")]),
    # Allowed calls, literals, quoted names, comments and aggregate metrics are left alone.
    ("rule", {"expression": "COALESCE(a, 0) >= 0 AND IF(b IN (1, 2), 1, 0) = 1 AND REGEXP_LIKE(c, '^x')"}, []),
    ("rule", {"expression": "note <> 'GREATEST(1, 2)' AND \"now\" (1) IS NULL -- NOW()"}, []),
    ("dataset", {"source_kind": "query", "query_sql": "SELECT COALESCE(a, 0), CURDATE() FROM t"}, []),
    ("metric", {"kind": "expression", "expression": "SUM(o.a) / COUNT(*)"}, []),
    ("object_type", {"derived_by": [{"kind": "expression", "expression": "NOW() > 1"}]}, [("x", "expression", "NOW")]),
    # A literal instance value that happens to sit under a property named expression is data.
    ("material_object", {"values": {"expression": "NOW()"}}, []),
])
def test_rejected_calls(kind, after, expected):
    assert function_refs.function_errors([item(kind, after)]) == expected


def test_examples_have_no_rejected_calls():
    for example in (BASE / "shared/references/examples").rglob("*.json"):
        items = json.loads(example.read_bytes())
        if isinstance(items, list):
            assert function_refs.function_errors(items) == [], example


materials = importlib.import_module("materials")
check_part = importlib.import_module("check_part")


def test_quotes_are_filled_from_cited_lines_and_written_quotes_kept():
    texts = {"m1": ["第一行", "  第二行 ", "第三行"]}
    items = [item("rule", {"evidence": [
        {"kind": "material", "material_id": "m1", "locator": {"line_start": 2, "line_end": 3}},
        {"kind": "material", "material_id": "m1", "locator": {"line_start": 1, "line_end": 1}, "quote": "第一"},
        {"kind": "material", "material_id": "m1", "locator": {"line_start": 3, "line_end": 9}},
        {"kind": "table", "ref": "t1", "quote": "表"}]})]
    materials.fill_quotes(items, texts)
    evidence = items[0]["after"]["evidence"]
    assert evidence[0]["quote"] == "第二行 第三行"
    assert evidence[1]["quote"] == "第一"
    assert "quote" not in evidence[2]  # out of range: left for the platform to report


def test_a_malformed_mapping_is_reported_not_crashed():
    schema = json.loads((BASE / "skills/ontology-discovery/output-schema.json").read_bytes())
    context = json.loads((BASE / "tests/fixtures/extract-retail/context.json").read_bytes())
    report = check_part.check_fragment([item("mapping", {"sources": [{}]})], context, schema)
    assert report["errors"] and all("/items/0" in e for e in report["errors"])


def test_metrics_and_rules_without_material_evidence_are_hinted():
    cited = {"kind": "material", "material_id": "m1", "locator": {"line_start": 3, "line_end": 3}}
    items = [
        item("metric", {"name": "sales", "evidence": [cited]}, "a"),
        item("metric", {"name": "repeat_rate"}, "b"),
        item("rule", {"name": "rejected_not_stocked", "owner_kind": "property", "evidence": [{"kind": "table", "ref": "t1", "quote": "x"}]}, "c"),
        item("rule", {"name": "level_values", "owner_kind": "value_type"}, "d"),
        {"operation": "update", "target_kind": "metric", "target_id": "x", "after": {"name": "old"}},
    ]
    assert check_part.uncited_definitions(items) == ["repeat_rate", "rejected_not_stocked"]
