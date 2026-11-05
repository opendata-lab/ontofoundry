"""The standalone checker uses the supplied schema and pinned input files."""

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "skill_checker", Path(__file__).parents[1] / "shared/scripts/check_result.py"
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
    # SC-08: a result carries only items.
    return {
        "items": [
            {
                "operation": "create",
                "target_kind": "object_type",
                "client_ref": "staff",
                "after": {"display_name": "星港员工", "name": "starport_staff"},
            }
        ],
    }


def test_references_and_context():
    result = payload()
    result["items"][0]["after"]["extends"] = {"client_ref": "missing"}
    errors = checker.check_result(result, SCHEMA)
    assert any("未闭合" in e for e in errors)


def test_duplicates_and_schema():
    result = payload()
    result["items"] *= 2
    assert any("重复" in e for e in checker.check_result(result, SCHEMA))
    result["run_token"] = "round"  # the run is the platform's, not the result's
    assert checker.check_result(result, SCHEMA)


def test_closed_batch_and_literal_values():
    result = payload()
    result["items"].append(
        {
            "operation": "create",
            "target_kind": "material_object",
            "client_ref": "lan",
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
    after = {"display_name": "星港员工", "name": "starport_staff"} if operation == "update" else None
    result["items"] = [
        {"operation": operation, "target_kind": "object_type", "target_id": str(uuid4()), "after": after}
    ]
    return result


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_valid_update_delete_need_no_pinned_copies(operation):
    # before and the target hash are filled and checked by the platform.
    assert checker.check_result(update_payload(operation), SCHEMA) == []


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_update_delete_need_a_target(operation):
    result = update_payload(operation)
    result["items"][0]["target_id"] = None
    assert checker.check_result(result, SCHEMA)


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_update_delete_after_shape(operation):
    result = update_payload(operation)
    result["items"][0]["after"] = (
        None
        if operation == "update"
        else {"display_name": "星港员工", "name": "starport_staff"}
    )
    assert checker.check_result(result, SCHEMA)


def test_one_batch_cannot_change_a_target_twice():
    result = update_payload()
    result["items"] *= 2
    assert checker.check_result(result, SCHEMA)


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
        (Path(__file__).parents[1] / "shared/references/examples/facts.json").read_bytes()
    )
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
