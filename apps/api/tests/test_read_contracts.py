"""Check the interface schema against DTO serialization and actual projections."""

import json
from copy import deepcopy

import pytest
from core1_fixtures import example_draft, example_names
from jsonschema import Draft202012Validator, FormatChecker

from ontofoundry_api.contracts import export_schema
from ontofoundry_api.contracts.read_models import read_models_schema
from ontofoundry_api.services.element_save import calculate_element_save
from ontofoundry_api.services.physical_projection import physical_projection


def validator(name):
    schema = read_models_schema()
    return Draft202012Validator(
        {"$ref": f"#/$defs/{name}", "$defs": schema["$defs"]},
        format_checker=FormatChecker(),
    )


def test_read_schema_artifact_and_check_detect_drift(tmp_path, monkeypatch):
    schema = read_models_schema()
    Draft202012Validator.check_schema(schema)
    assert json.loads(export_schema.READ_TARGET.read_text()) == schema
    assert {ref["$ref"] for ref in schema["anyOf"]} == {
        f"#/$defs/{name}"
        for name in (
            "MembershipRead",
            "EffectiveLinkRead",
            "EffectiveBindingRead",
            "ElementSaveImpact",
            "TableRowsRead",
        )
    }
    export_schema.export(check=True)
    changed = tmp_path / "read.schema.json"
    changed.write_text("{}\n")
    monkeypatch.setattr(export_schema, "READ_TARGET", changed)
    with pytest.raises(SystemExit, match="接口读模型 schema"):
        export_schema.export(check=True)


@pytest.mark.parametrize("name", example_names())
def test_effective_read_schema_accepts_actual_example_projections(name):
    draft = example_draft(name)
    for obj in draft.object_types:
        projection = physical_projection(draft, "object_type", obj.id, [])
        for binding in projection["effective_bindings"]:
            validator("EffectiveBindingRead").validate(binding)
            for membership in binding["memberships"]:
                validator("MembershipRead").validate(membership)
            for link in binding["links"]:
                validator("EffectiveLinkRead").validate(link)


def test_save_impact_schema_accepts_server_result_and_rejects_missing_hash():
    raw = example_draft("13-dataset-metrics").model_dump(mode="json")
    edited = deepcopy(raw)
    edited["datasets"][0]["snapshot_date_column"] = "stat_date"
    calculation = calculate_element_save(
        raw, raw, raw, edited, "dataset", edited["datasets"][0]["id"]
    )
    response = {
        "current_version_id": None,
        "session_revision": 3,
        "affected_items": calculation.affected_items,
    }
    assert len(response["affected_items"]) == 6
    validator("ElementSaveImpact").validate(response)
    del response["affected_items"][0]["expected_target_hash"]
    assert list(validator("ElementSaveImpact").iter_errors(response))
