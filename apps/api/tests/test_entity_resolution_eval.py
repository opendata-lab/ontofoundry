"""Offline entity-resolution eval: implemented levels stay exact; known gaps are only reported."""

from evals.entity_resolution.run import GAPS, evaluate, load


def test_implemented_levels_are_all_correct_and_gaps_are_measured():
    report = evaluate(*load())
    assert report["accuracy_excluding_gaps"] == 1.0
    assert all(name in report["by_type"] for name in GAPS)
    assert sum(v["total"] for v in report["by_type"].values()) == 20
