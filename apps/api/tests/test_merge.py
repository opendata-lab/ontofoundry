"""Strict JSON comparison and missing values in three-way merges."""

from copy import deepcopy

import pytest
from pr23_fixtures import typed_fact_swap

from ontofoundry_api.domain.core import CoreDraft
from ontofoundry_api.domain.dependencies import strict_equal
from ontofoundry_api.domain.validation import validate_core_graph
from ontofoundry_api.services.element_save import calculate_element_save
from ontofoundry_api.services.merge import merge_snapshots


@pytest.mark.parametrize("left,right", [(True, 1), (False, 0), (1, 1.0), (0, 0.0)])
@pytest.mark.parametrize("shape", ["scalar", "list", "dictionary"])
@pytest.mark.parametrize("case", ["draft_change", "latest_change", "both_changed"])
def test_fast_paths_preserve_types_and_conflicts(left, right, shape, case):
    def wrap(value):
        if shape == "list":
            return [value]
        if shape == "dictionary":
            return {"values": [value]}
        return value

    b, c, d = {
        "draft_change": (left, left, right),
        "latest_change": (left, right, "changed"),
        "both_changed": ("before", left, right),
    }[case]
    snapshots = [{"value": wrap(v)} for v in (b, c, d)]
    original = deepcopy(snapshots)
    merged, conflicts = merge_snapshots(*snapshots)
    assert strict_equal(merged, {"value": wrap(d)})
    expected = []
    if case != "draft_change":
        expected = [
            {
                "path": "/value/values" if shape == "dictionary" else "/value",
                "base": [b] if shape == "dictionary" else wrap(b),
                "current": [c] if shape == "dictionary" else wrap(c),
                "draft": [d] if shape == "dictionary" else wrap(d),
            }
        ]
    assert strict_equal(conflicts, expected)
    assert strict_equal(snapshots, original)


@pytest.mark.parametrize("left,right", [(True, 1), (False, 0), (1, 1.0), (0, 0.0)])
def test_keep_both_deduplicates_using_strict_types(left, right):
    merged, conflicts = merge_snapshots(
        {"value": ["before"]},
        {"value": [left]},
        {"value": [right, left]},
        {"/value": {"choice": "both"}},
    )
    assert conflicts == []
    assert strict_equal(merged, {"value": [left, right]})


@pytest.mark.parametrize(
    "base,latest,draft,expected,conflict_count",
    [
        ({}, {}, {"v": None}, {"v": None}, 0),
        ({}, {"v": None}, {}, {"v": None}, 0),
        ({"v": None}, {}, {"v": None}, {}, 0),
        ({"v": None}, {"v": None}, {}, {}, 0),
        ({"v": None}, {}, {}, {}, 0),
        ({"v": 1}, {"v": 2}, {}, {}, 1),
    ],
)
def test_missing_is_distinct_from_null(base, latest, draft, expected, conflict_count):
    merged, conflicts = merge_snapshots(base, latest, draft)
    assert strict_equal(merged, expected)
    assert len(conflicts) == conflict_count


@pytest.mark.parametrize(
    "left_kind,left,right_kind,right",
    [
        ("boolean", True, "integer", 1),
        ("boolean", False, "integer", 0),
        ("integer", 1, "float", 1.0),
        ("integer", 0, "decimal", 0.0),
    ],
)
def test_element_save_merges_typed_rewrites_with_latest_description(
    left_kind, left, right_kind, right
):
    base, candidate, target_id = typed_fact_swap(left_kind, left, right_kind, right)
    latest = deepcopy(base)
    target = next(o for o in latest["object_types"] if o["id"] == target_id)
    target["description"] = "另一会话更新的虚构客户说明"
    inputs = deepcopy([base, latest, candidate])
    result = calculate_element_save(base, latest, base, candidate, "object_type", target_id)
    facts = [f for f in base["material_objects"] if f["type_id"] == target_id]
    assert {i["target_id"] for i in result.affected_items} == {f["id"] for f in facts}
    for raw in (result.merged, result.session_draft):
        graph = validate_core_graph(CoreDraft.model_validate(raw))
        obj = next(o for o in graph.object_types if str(o.id) == target_id)
        assert obj.description == target["description"]
        for fact in graph.material_objects:
            if str(fact.type_id) == target_id:
                assert strict_equal(fact.values["is_vip"], left)
                assert strict_equal(fact.values["name"], right)
    assert strict_equal([base, latest, candidate], inputs)
