"""Generated schema, registered array policy and cross-language contract drift."""

import json
from uuid import uuid4

import pytest
from core1_fixtures import example_draft, example_draft_json, example_names
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from ontofoundry_api.contracts.export_core_schema import TARGET, core_schema, schema_text
from ontofoundry_api.domain.core import COLLECTIONS, MaterialObject, Operator
from ontofoundry_api.domain.core_canonical import draft_sha256, element_sha256


def test_generated_schema_matches_authoritative_models():
    assert TARGET.read_text(encoding="utf-8") == schema_text()
    Draft202012Validator.check_schema(core_schema())


@pytest.mark.parametrize("name", example_names())
def test_shared_examples_match_schema(name):
    Draft202012Validator(core_schema(), format_checker=FormatChecker()).validate(
        example_draft_json(name)
    )


@pytest.mark.parametrize("field", ["dataset_id", "time_field", "value_kind"])
def test_schema_rejects_ratio_read_projections(field):
    raw = example_draft_json("13-dataset-metrics")
    ratio = next(m for m in raw["metrics"] if m["kind"] == "ratio")
    ratio[field] = None
    assert list(Draft202012Validator(core_schema()).iter_errors(raw))


@pytest.mark.parametrize("name", example_names())
def test_hash_is_independent_of_collection_evidence_source_column_and_set_order(name):
    draft = example_draft(name)
    candidate = draft.model_copy(deep=True)
    for collection in COLLECTIONS:
        getattr(candidate, collection).reverse()
        for item in getattr(candidate, collection):
            if hasattr(item, "evidence"):
                item.evidence.reverse()
            for field in ("tags", "synonyms"):
                if hasattr(item, field):
                    setattr(item, field, ["乙", "甲", "乙"])
                    original = next(
                        i for i in getattr(draft, collection) if i.id == item.id
                    )
                    setattr(original, field, ["甲", "乙"])
    for dataset in candidate.datasets:
        if dataset.columns:
            dataset.columns.reverse()
    for mapping in candidate.mappings:
        mapping.sources.reverse()
    assert draft_sha256(draft) == draft_sha256(candidate)


def test_ordered_key_and_join_arrays_change_hash():
    draft = example_draft("04-composite-key")
    candidate = draft.model_copy(deep=True)
    main = next(s for m in candidate.mappings for s in m.sources if len(s.key_columns) > 1)
    main.key_columns.reverse()
    assert draft_sha256(draft) != draft_sha256(candidate)
    candidate = draft.model_copy(deep=True)
    join = next(
        link.data_join
        for link in candidate.link_types
        if link.data_join
        and link.data_join.kind == "mapping_table"
        and len(link.data_join.source_columns) > 1
    )
    join.source_columns.reverse()
    assert draft_sha256(draft) != draft_sha256(candidate)


def test_condition_order_and_between_bounds_are_preserved():
    draft = example_draft("13-dataset-metrics")
    metric = next(m for m in draft.metrics if getattr(m, "filters", None))
    metric.filters[0].operator = Operator.BETWEEN
    metric.filters[0].values = ["a", "z"]
    first = draft_sha256(draft)
    metric.filters[0].values.reverse()
    assert first != draft_sha256(draft)


def test_user_null_false_zero_and_literal_bytes_survive_canonicalization():
    fact = MaterialObject(
        id=uuid4(),
        type_id=uuid4(),
        values={"null": None, "zero": 0, "false": False, "name": "e\u0301"},
    )
    from ontofoundry_api.domain.canonical import canonical as content_canonical
    normalized = json.loads(content_canonical(fact))
    assert normalized["values"] == fact.values
    assert '"null":null' in content_canonical(fact)
    assert '"false":false' in content_canonical(fact)


def test_hash_fills_model_defaults_and_is_deterministic():
    draft = example_draft("09-empty")
    minimal = {"workspace_id": str(draft.workspace_id)}
    assert draft_sha256(minimal) == draft_sha256(draft)
    assert len(draft_sha256(draft)) == 64


def test_element_hash_and_new_field_rejection():
    draft = example_draft("01-basic-sales")
    prop = draft.properties[0]
    assert element_sha256(prop, "properties") == element_sha256(
        prop.model_dump(mode="json"), "properties"
    )
    with pytest.raises(ValidationError):
        draft_sha256({**draft.model_dump(mode="json"), "new_array": []})


def test_nonfinite_scalars_are_rejected_at_storage_boundary():
    with pytest.raises(ValidationError):
        MaterialObject(id=uuid4(), type_id=uuid4(), values={"amount": float("nan")})
