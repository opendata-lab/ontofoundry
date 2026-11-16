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
