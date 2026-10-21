"""Offline acceptance baseline over a publishable fictional procurement ontology."""

import json
from collections import Counter

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from evals.ontology_search.run import (
    QUESTION_TYPES,
    ROOT,
    SEMANTIC_GAP,
    TOP_K,
    evaluate,
    load_inputs,
    main,
)
from ontofoundry_api.contracts.export_core_schema import core_schema
from ontofoundry_api.services.core_validation import validation_report
from ontofoundry_api.services.ontology_search import (
    normalize,
    search_names,
    visible_elements,
)

# Measured on 2026-10-21 with this seed and the real retrieve service: all expected
# elements for all 25 non-gap questions were in the first 10 expanded results.
# Keep the achieved baseline without rounding or allowing a known-good case to regress.
RECALL_BASELINE = 1.0
REGRESSION_TYPES = tuple(kind for kind in QUESTION_TYPES if kind != SEMANTIC_GAP)


@pytest.fixture(scope="module")
def acceptance_inputs():
    return load_inputs()


@pytest.fixture(scope="module")
def acceptance_report(acceptance_inputs):
    return evaluate(*acceptance_inputs)


def test_seed_passes_schema_graph_and_publication_validation(acceptance_inputs):
    raw = json.loads((ROOT / "seed.json").read_text(encoding="utf-8"))
    Draft202012Validator(core_schema(), format_checker=FormatChecker()).validate(raw)
    report = validation_report(raw)
    assert report["publishable"], report
    assert report["schema_status"] == report["semantic_status"] == "passed"
    assert report["instance_status"] == "passed"
    assert report["errors"] == report["warnings"] == []
    draft, questions = acceptance_inputs
    assert {obj.display_name for obj in draft.object_types} >= {
        "供应商",
        "采购订单",
        "采购订单明细",
        "物料",
        "收货",
        "付款",
    }
    assert {metric.kind for metric in draft.metrics} == {"simple", "ratio", "expression"}
    assert all(
        any(p.identifier for p in draft.properties_of(obj.id)) for obj in draft.object_types
    )
    assert {mapping.type_id for mapping in draft.mappings} == {
        obj.id for obj in draft.object_types
    }
    assert Counter(q["type"] for q in questions) == dict.fromkeys(QUESTION_TYPES, 5)


@pytest.mark.parametrize("kind", REGRESSION_TYPES)
def test_expanded_top10_recall_meets_measured_baseline(acceptance_report, kind):
    mode = acceptance_report["modes"]["keyword_expanded"]
    stats = mode["by_type"][kind]
    assert stats["recall_at_10"] >= RECALL_BASELINE, [
        row for row in mode["questions"] if row["type"] == kind and row["missing_ids"]
    ]
    assert mode["regression"]["question_count"] == 25
    assert mode["regression"]["recall_at_10"] >= RECALL_BASELINE


def test_question_labels_exercise_real_retrieval_paths(
    acceptance_inputs, acceptance_report
):
    draft, questions = acceptance_inputs
    elements = {e.id: e for e in visible_elements(draft, mappings=True)}
    direct = {
        row["id"]: row for row in acceptance_report["modes"]["keyword_only"]["questions"]
    }
    expanded = {
        row["id"]: row
        for row in acceptance_report["modes"]["keyword_expanded"]["questions"]
    }
    for question in questions:
        kind = question["type"]
        plain_items = {
            item["id"]: item for item in direct[question["id"]]["response"]["items"]
        }
        expanded_items = {
            item["id"]: item for item in expanded[question["id"]]["response"]["items"]
        }
        if kind == "需要关系扩展才能带出":
            targets = question["expansion_expected_ids"]
            assert targets
            for identity in targets:
                assert identity not in plain_items
                match = expanded_items[identity]["match"]
                assert match["by"] == "expansion"
                assert match["via"]["id"] in plain_items
        elif kind == "只有描述能命中":
            for identity in question["expected_ids"]:
                assert plain_items[identity]["match"]["by"] == "description"
        elif kind == "同义词":
            for identity in question["expected_ids"]:
                assert question["query"] in elements[identity].definition["synonyms"]
                assert plain_items[identity]["match"]["by"] == "name_in_query"
        elif kind == SEMANTIC_GAP:
            # Guard the missing-alias examples without requiring future sources to miss.
            query = normalize(question["query"])
            for identity in question["expected_ids"]:
                assert all(
                    normalize(name) not in query and query not in normalize(name)
                    for name in search_names(elements[identity])
                )
                assert query not in normalize(elements[identity].definition["description"])


def test_metrics_and_byte_counts_match_returned_top10(acceptance_report):
    assert acceptance_report["top_k"] == TOP_K == 10
    assert acceptance_report["mappings"] is True
    for mode in acceptance_report["modes"].values():
        rows = mode["questions"]
        for row in rows:
            payload = row["response"]
            assert len(payload["items"]) <= TOP_K
            assert payload["retrieval"] == {"keyword": True, "vector": False}
            assert row["response_bytes"] == len(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                    "utf-8"
                )
            )
            actual = {item["id"] for item in payload["items"]}
            expected = set(row["expected_ids"])
            assert set(row["matched_ids"]) == expected & actual
            assert set(row["missing_ids"]) == expected - actual
            assert row["all_expected_in_top10"] == (expected <= actual)
            assert row["recall_at_10"] == len(expected & actual) / len(expected)
        assert mode["overall"]["recall_at_10"] == pytest.approx(
            sum(row["recall_at_10"] for row in rows) / len(rows)
        )
        assert mode["overall"]["average_response_bytes"] == pytest.approx(
            sum(row["response_bytes"] for row in rows) / len(rows)
        )
        assert mode["overall"]["micro_recall_at_10"] == pytest.approx(
            sum(len(row["matched_ids"]) for row in rows)
            / sum(len(row["expected_ids"]) for row in rows)
        )
    # A fixed question has three expected elements, only one of which is a direct hit.
    row = next(
        row
        for row in acceptance_report["modes"]["keyword_only"]["questions"]
        if row["id"] == "q21"
    )
    assert row["recall_at_10"] == pytest.approx(1 / 3)
    assert row["all_expected_in_top10"] is False


def test_cli_writes_reusable_json_outside_api_directory(
    tmp_path, monkeypatch, capsys, acceptance_report
):
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "results.json"
    main(["--output", str(output)])
    assert json.loads(output.read_text(encoding="utf-8")) == acceptance_report
    printed = capsys.readouterr().out
    assert "keyword_only" in printed and "keyword_expanded" in printed
    assert all(kind in printed for kind in QUESTION_TYPES)
    assert "q01" in printed and "q30" in printed and "平均返回=" in printed
