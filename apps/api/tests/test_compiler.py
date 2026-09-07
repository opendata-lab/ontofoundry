from copy import deepcopy

import pytest
from pydantic import ValidationError

from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.ossie.compiler import compile_ossie, sha256_json, validate_ossie
from ontofoundry_api.services.demo import build_demo_draft


def test_compiler_is_deterministic_and_publishable():
    draft = build_demo_draft()

    first = compile_ossie(
        draft,
        ontology_name="manufacturing_supply_chain",
        ontology_description="制造供应链",
    )
    second = compile_ossie(
        draft,
        ontology_name="manufacturing_supply_chain",
        ontology_description="制造供应链",
    )
    report = validate_ossie(first)

    assert first == second
    assert sha256_json(first) == sha256_json(second)
    assert report["schema_status"] == "passed"
    assert report["semantic_status"] == "passed"
    assert report["publishable"] is True


def test_compiler_uses_only_supported_multiplicity_values():
    document = compile_ossie(
        build_demo_draft(),
        ontology_name="manufacturing_supply_chain",
        ontology_description="制造供应链",
    )
    multiplicities = {
        relationship["multiplicity"]
        for component in document["ontology"]
        for relationship in component.get("relationships", [])
        if "multiplicity" in relationship
    }

    assert multiplicities <= {"OneToOne", "ManyToOne"}
    assert "OneToMany" not in multiplicities


def test_internal_model_rejects_duplicate_names():
    payload = build_demo_draft().model_dump(mode="json")
    duplicate = deepcopy(payload["object_types"][0])
    duplicate["id"] = "20375c4d-64e2-4ddf-a6e6-f3fc36d23101"
    duplicate["technical_name"] = "supplier_copy"
    duplicate["attributes"] = []
    payload["object_types"].append(duplicate)

    with pytest.raises(ValidationError, match="同名业务对象"):
        OntologyDraft.model_validate(payload)


def test_ablation_ordinary_attributes_share_builtins_without_losing_identifiers():
    draft = build_demo_draft()
    result = compile_ossie(draft, ontology_name="test", ontology_description="")
    values = [c for c in result["ontology"] if c["type"] == "ValueType"]
    assert len(values) == sum(
        a.identifier for t in draft.object_types for a in t.attributes
    )
    assert (
        len(result["ontology"]) == 10
    )  # Previously 17: five entities + twelve value wrappers.
    assert validate_ossie(result)["publishable"]
    draft.object_types.reverse()
    draft.link_types.reverse()
    assert result == compile_ossie(draft, ontology_name="test", ontology_description="")


@pytest.mark.parametrize(
    "multiplicity", ["one_to_many", "many_to_many", "many_to_one", "one_to_one"]
)
def test_all_cardinalities_and_self_relationship_are_official_schema_valid(multiplicity):
    draft = build_demo_draft()
    relation = draft.link_types[0]
    relation.multiplicity = multiplicity
    relation.target_type_id = relation.source_type_id
    result = compile_ossie(draft, ontology_name="test", ontology_description="")
    assert validate_ossie(result)["publishable"], validate_ossie(result)
