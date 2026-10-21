"""Strict JSON comparison and missing values in three-way merges."""

from copy import deepcopy

import pytest

from ontofoundry_api.domain.dependencies import strict_equal
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
