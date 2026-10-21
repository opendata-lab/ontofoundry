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
    candidate.object_types[0].name = "renamed"
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
    prop = next(p for p in candidate.properties if p.name == "phone")
    prop.name = "telephone"
    result = validate_candidate_graph(before, candidate)
    assert "party.telephone" in result.rules[0].expression
    assert any("telephone" in m.fields for m in result.mappings)
    assert before.rules[0].expression != result.rules[0].expression




def test_deleted_reference_must_be_revised_together():
    before = example_draft("08-rules")
    candidate = before.model_copy(deep=True)
    candidate.properties = [p for p in candidate.properties if p.name != "amount"]
    with pytest.raises(ValueError, match="删除|无效"):
        validate_candidate_graph(before, candidate)


def test_explicit_expression_revision_resolves_in_final_namespace():
    before = example_draft("01-basic-sales")
    candidate = before.model_copy(deep=True)
    rule = candidate.rules[0]
    target = next(
        p
        for p in candidate.properties
        if p.owner_type_id == rule_context(candidate, rule) and p.name == "amount"
    )
    target.name = "total_amount"
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


def test_exact_final_property_swap_rewrite_is_not_interpreted_again():
    from ontofoundry_api.domain.dependencies import rewrite_references

    before = example_draft("07-instances-and-evidence")
    candidate = before.model_copy(deep=True)
    first, second = [p for p in candidate.properties if p.name in {"customer_no", "name"}][
        :2
    ]
    first.name, second.name = (
        second.name,
        first.name,
    )
    final = validate_candidate_graph(before, candidate)
    saved = final.model_copy(deep=True)
    assert rewrite_references(before, final) == final
    assert validate_candidate_graph(before, final) == final
    assert final == saved





def test_ambiguous_binding_swap_is_accepted_as_exact_final_form_first():
    before = example_draft("01-basic-sales")
    candidate = before.model_copy(deep=True)
    first, second = [
        p for p in candidate.properties if p.owner_type_id == candidate.object_types[0].id
    ][:2]
    first.name, second.name = (
        second.name,
        first.name,
    )
    final = validate_candidate_graph(before, candidate)
    # These same submitted fields could mean a manual binding swap in the old
    # namespace. The contract deliberately gives the exact final form priority.
    submitted = final.model_copy(deep=True)
    result = validate_candidate_graph(before, submitted)
    assert result.mappings == final.mappings
    # A binding revision after the rename is an unambiguous second save.
    mapping = next(m for m in submitted.mappings if m.type_id == first.owner_type_id)
    mapping.fields[first.name], mapping.fields[second.name] = (
        mapping.fields[second.name],
        mapping.fields[first.name],
    )
    assert validate_candidate_graph(final, submitted).mappings == submitted.mappings
