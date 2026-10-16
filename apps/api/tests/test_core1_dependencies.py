"""Impact, stable references and atomic rename regressions."""

import pytest
from core1_fixtures import example_draft

from ontofoundry_api.domain.core import Aggregation, ExpressionMetric
from ontofoundry_api.domain.dependencies import (
    affected_metrics,
    reference_index,
    reverse_dependencies,
    validate_candidate_graph,
)
from ontofoundry_api.domain.expressions import rule_context


def test_dataset_impact_contains_direct_and_ratio_but_no_ontology():
    before = example_draft("13-dataset-metrics")
    candidate = before.model_copy(deep=True)
    candidate.datasets[0].snapshot_date_column = "stat_date"
    assert affected_metrics(before, candidate) == {m.id for m in before.metrics}
    reverse = reverse_dependencies(before, {before.datasets[0].id})
    assert reverse == {m.id for m in before.metrics}


def test_object_edits_do_not_affect_metrics():
    before = example_draft("06-inheritance")
    candidate = before.model_copy(deep=True)
    candidate.object_types[0].technical_name = "renamed"
    candidate.object_types[0].derived_by = []
    candidate.link_types.clear()
    assert affected_metrics(before, candidate) == set()


def test_column_index_includes_expression_filter_measure_and_time():
    draft = example_draft("13-dataset-metrics")
    refs = reference_index(draft)
    columns = {r.column for items in refs.values() for r in items if r.column}
    assert {"repo", "commit_count", "stat_date"} <= columns
    ratio = next(m for m in draft.metrics if m.kind == "ratio")
    assert {r.target_id for r in refs[ratio.id]} == {
        ratio.numerator_id,
        ratio.denominator_id,
    }


def test_atomic_dataset_name_swap_preserves_uuid_and_literals():
    before = example_draft("01-basic-sales")
    candidate = before.model_copy(deep=True)
    first, second = candidate.datasets
    first.name, second.name = second.name, first.name
    result = validate_candidate_graph(before, candidate)
    for previous in before.metrics:
        if isinstance(previous, ExpressionMetric):
            current = next(m for m in result.metrics if m.id == previous.id)
            ds = next(d for d in result.datasets if d.id == current.dataset_id)
            assert ds.name + "." in current.expression
            assert current.dataset_id == previous.dataset_id
    assert candidate != result  # The caller's candidate is never mutated.


def test_property_rename_rewrites_rules_binding_keys_and_fact_values():
    before = example_draft("06-inheritance")
    candidate = before.model_copy(deep=True)
    prop = next(p for p in candidate.properties if p.technical_name == "phone")
    prop.technical_name = "telephone"
    result = validate_candidate_graph(before, candidate)
    assert "party.telephone" in result.rules[0].expression
    assert any("telephone" in m.fields for m in result.mappings)
    assert all("phone" not in f.values for f in result.material_objects)
    assert before.rules[0].expression != result.rules[0].expression


def test_atomic_property_name_swap_does_not_merge_values():
    before = example_draft("07-instances-and-evidence")
    candidate = before.model_copy(deep=True)
    fact = next(f for f in before.material_objects if len(f.values) > 1)
    names = list(fact.values)[:2]
    props = [
        next(
            p
            for p in candidate.properties
            if p.technical_name == name and p.owner_type_id == fact.type_id
        )
        for name in names
    ]
    # Same scalar kinds make the swap a pure rename.
    same_kind = [
        p
        for p in candidate.properties
        if p.owner_type_id == fact.type_id and p.value_kind == props[0].value_kind
    ]
    assert len(same_kind) >= 2
    p1, p2 = same_kind[:2]
    a, b = p1.technical_name, p2.technical_name
    p1.technical_name, p2.technical_name = b, a
    result = validate_candidate_graph(before, candidate)
    for original in before.material_objects:
        current = next(f for f in result.material_objects if f.id == original.id)
        if a in original.values:
            assert current.values[b] == original.values[a]
        if b in original.values:
            assert current.values[a] == original.values[b]


def test_deleted_reference_must_be_revised_together():
    before = example_draft("08-rules")
    candidate = before.model_copy(deep=True)
    candidate.properties = [p for p in candidate.properties if p.technical_name != "amount"]
    with pytest.raises(ValueError, match="删除|无效"):
        validate_candidate_graph(before, candidate)


def test_explicit_expression_revision_resolves_in_final_namespace():
    before = example_draft("01-basic-sales")
    candidate = before.model_copy(deep=True)
    rule = candidate.rules[0]
    target = next(
        p
        for p in candidate.properties
        if p.owner_type_id == rule_context(candidate, rule) and p.technical_name == "amount"
    )
    target.technical_name = "total_amount"
    rule.expression = "sales_order.total_amount >= 100"
    result = validate_candidate_graph(before, candidate)
    assert result.rules[0].expression == rule.expression


def test_inherited_link_binding_dictionary_key_is_a_dependency():
    draft = example_draft("06-inheritance")
    mapping = next(m for m in draft.mappings if m.inherited_link_bindings)
    refs = reference_index(draft)[mapping.id]
    assert set(mapping.inherited_link_bindings) <= {r.target_id for r in refs}


def test_reverse_dependency_cycle_terminates():
    draft = example_draft("01-basic-sales")
    prop = draft.properties[0]
    owners = reverse_dependencies(draft, {prop.owner_type_id})
    assert prop.id in owners
    assert prop.owner_type_id not in owners


def test_dataset_column_deletion_affects_count_and_ratio_even_without_column_use():
    before = example_draft("13-dataset-metrics")
    candidate = before.model_copy(deep=True)
    candidate.datasets[0].columns.pop()
    assert affected_metrics(before, candidate) == {m.id for m in before.metrics}
    with pytest.raises(ValueError):
        validate_candidate_graph(before, candidate)


def test_simple_definition_change_affects_its_ratio_without_dataset_edits():
    before = example_draft("13-dataset-metrics")
    ratio = next(m for m in before.metrics if m.kind == "ratio")
    candidate = before.model_copy(deep=True)
    component = next(m for m in candidate.metrics if m.id == ratio.numerator_id)
    component.aggregation = Aggregation.AVG
    assert affected_metrics(before, candidate) == {component.id, ratio.id}
