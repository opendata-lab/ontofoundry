"""The standalone checker uses the supplied schema and pinned input files."""

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[5]
spec = importlib.util.spec_from_file_location(
    "skill_checker", Path(__file__).parents[1] / "scripts/check_result.py"
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)
SCHEMA = json.loads(
    (
        ROOT
        / "apps/api/src/ontofoundry_api/contracts/ontofoundry.proposals.v1.schema.json"
    ).read_text()
)


def payload():
    return {
        "schema_version": "ontofoundry.proposals/v1",
        "run_token": "round",
        "workspace_id": str(uuid4()),
        "session_id": str(uuid4()),
        "base_version_id": None,
        "base_version_sha256": "a" * 64,
        "source_session_revision": 1,
        "source_draft_sha256": "b" * 64,
        "items": [
            {
                "operation": "create",
                "target_kind": "object_type",
                "client_ref": "staff",
                "before": None,
                "after": {"display_name": "星港员工", "name": "starport_staff"},
            }
        ],
    }


def test_references_and_context():
    result = payload()
    result["items"][0]["after"]["extends"] = {"client_ref": "missing"}
    errors = checker.check_result(result, SCHEMA, {"run_token": "other"})
    assert any("未闭合" in e for e in errors)
    assert any("上下文" in e for e in errors)


def test_duplicates_and_schema():
    result = payload()
    result["items"] *= 2
    assert any("重复" in e for e in checker.check_result(result, SCHEMA))
    del result["run_token"]
    assert checker.check_result(result, SCHEMA)


def test_closed_batch_and_literal_values():
    result = payload()
    result["items"].append(
        {
            "operation": "create",
            "target_kind": "material_object",
            "client_ref": "lan",
            "before": None,
            "after": {
                "type_id": {"client_ref": "staff"},
                "values": {"source_id": "main", "type_id": "literal"},
            },
            "depends_on": ["staff"],
        }
    )
    assert checker.check_result(result, SCHEMA) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_id", str(uuid4())),
        ("before", {}),
        ("after", None),
        (
            "after",
            {
                "id": str(uuid4()),
                "display_name": "星港员工",
                "name": "starport_staff",
            },
        ),
    ],
)
def test_invalid_create_shape(field, value):
    result = payload()
    result["items"][0][field] = value
    assert checker.check_result(result, SCHEMA)


def update_payload(operation="update"):
    result = payload()
    target = str(uuid4())
    before = {"id": target, "display_name": "星港员工", "name": "starport_staff"}
    after = (
        {k: v for k, v in before.items() if k != "id"}
        if operation == "update"
        else None
    )
    result["items"] = [
        {
            "operation": operation,
            "target_kind": "object_type",
            "target_id": target,
            "before": before,
            "after": after,
            "expected_target_hash": "c" * 64,
        }
    ]
    context = {
        "run": {k: v for k, v in result.items() if k != "items"},
        "draft": {"object_types": [deepcopy(before)]},
        "element_hashes": {target: "c" * 64},
    }
    return result, context


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_valid_update_delete_with_pinned_context(operation):
    result, context = update_payload(operation)
    assert checker.check_result(result, SCHEMA, context) == []


@pytest.mark.parametrize("operation", ["update", "delete"])
@pytest.mark.parametrize("field", ["before", "target_id", "expected_target_hash"])
def test_update_delete_need_before_target_and_hash(operation, field):
    result, _ = update_payload(operation)
    result["items"][0][field] = None
    assert checker.check_result(result, SCHEMA)


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_update_delete_after_shape(operation):
    result, _ = update_payload(operation)
    result["items"][0]["after"] = (
        None
        if operation == "update"
        else {"display_name": "星港员工", "name": "starport_staff"}
    )
    assert checker.check_result(result, SCHEMA)


@pytest.mark.parametrize("field", checker.HEADER_FIELDS)
def test_all_header_fields_match_pinned_context(field):
    result = payload()
    context = {"run": {k: v for k, v in result.items() if k != "items"}}
    context["run"][field] = "different"
    assert any(field in e for e in checker.check_result(result, SCHEMA, context))


@pytest.mark.parametrize("mutation", ["before", "hash", "kind", "target", "duplicate"])
def test_pinned_target_consistency(mutation):
    result, context = update_payload()
    item = result["items"][0]
    if mutation == "before":
        item["before"]["name"] = "错误姓名"
    elif mutation == "hash":
        item["expected_target_hash"] = "d" * 64
    elif mutation == "kind":
        context["draft"] = {"properties": context["draft"]["object_types"]}
    elif mutation == "target":
        item["target_id"] = str(uuid4())
    else:
        result["items"] *= 2
    assert checker.check_result(result, SCHEMA, context)


@pytest.mark.parametrize(
    "name,readings",
    [
        ("汇报给", []),
        ("reports_to", ["员工汇报给主管"]),
        ("reports_to", ["{source}汇报给{other}{target}"]),
        ("reports_to", ["{{source}}{target}"]),
        ("reports_to", ["{source}{target}}"]),
    ],
)
def test_relationship_schema_rules(name, readings):
    result = payload()
    result["items"].append(
        {
            "operation": "create",
            "target_kind": "link_type",
            "client_ref": "reports",
            "before": None,
            "after": {
                "name": name,
                "source_type_id": {"client_ref": "staff"},
                "target_type_id": {"client_ref": "staff"},
                "multiplicity": "many_to_one",
                "verbalizes": readings,
            },
        }
    )
    assert checker.check_result(result, SCHEMA)


@pytest.mark.parametrize(
    "readings",
    [
        [],
        ["{source}汇报给{target}", "{target}管理{source}"],
        ["{source}\n{target}与{source}"],
    ],
)
def test_relationship_schema_accepts_complete_readings(readings):
    result = payload()
    result["items"].append(
        {
            "operation": "create",
            "target_kind": "link_type",
            "client_ref": "reports",
            "before": None,
            "after": {
                "name": "reports_to",
                "source_type_id": {"client_ref": "staff"},
                "target_type_id": {"client_ref": "staff"},
                "multiplicity": "many_to_one",
                "verbalizes": readings,
            },
        }
    )
    assert checker.check_result(result, SCHEMA) == []


def test_document_fact_reference_example_is_checkable():
    result = payload()
    result["items"] = json.loads(
        (Path(__file__).parents[1] / "references/examples/facts.json").read_bytes()
    )
    for item in result["items"]:
        item.setdefault("before", None)
    assert checker.check_result(result, SCHEMA) == []


def test_optional_display_name_and_legacy_field_rejection():
    result = payload()
    del result["items"][0]["after"]["display_name"]
    assert checker.check_result(result, SCHEMA) == []
    result["items"][0]["after"]["technical_name"] = "starport_staff"
    assert checker.check_result(result, SCHEMA)
    del result["items"][0]["after"]["technical_name"]
    result["items"][0]["after"]["name"] = "星港员工"
    assert checker.check_result(result, SCHEMA)
