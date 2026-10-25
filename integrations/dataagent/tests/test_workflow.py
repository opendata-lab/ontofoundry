"""Executable examples, final-graph checks, bounded diagnostics and atomic output."""

import hashlib
import json
import re
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from ontofoundry_api.contracts.proposals import (
    ProposalContractError,
    RunContext,
    parse_result,
)
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.snapshot import empty_snapshot

BASE = Path(__file__).resolve().parents[1]
SKILL = BASE / "shared"
sys.path.insert(0, str(BASE / "scripts"))
sys.path.insert(0, str(SKILL / "scripts"))
import check_result as checker
import offline_budget as budget
import prepare_result as prepare

SCHEMA_PATH = (
    BASE.parents[1]
    / "apps/api/src/ontofoundry_api/contracts/ontofoundry.proposals.v1.schema.json"
)
SCHEMA = json.loads(SCHEMA_PATH.read_bytes())
CATALOG = json.loads((SKILL / "references/examples/catalog.json").read_bytes())
EXAMPLES = [SKILL / "references/examples" / e["file"] for e in CATALOG["examples"]]


def pinned(example):
    entry = next(e for e in CATALOG["examples"] if e["file"] == example.name)
    ctx = json.loads(
        (BASE / "tests/fixtures" / (entry["context"] or "context.json")).read_bytes()
    )
    if not entry["context"]:
        ctx["draft"] = empty_snapshot(ctx["run"]["workspace_id"])
        ctx["element_hashes"] = {}
        ctx["run"]["source_draft_sha256"] = snapshot_sha256(ctx["draft"])
    return ctx


def server_parse(batch, ctx):
    run = {k: v for k, v in ctx["run"].items() if k != "schema_version"}
    material = (BASE / "tests/fixtures/material.md").read_bytes()
    return parse_result(
        json.dumps(batch).encode(),
        RunContext(**run, draft=ctx["draft"], instance_baseline=ctx["instance_baseline"]),
        lambda mid: (
            (hashlib.sha256(material).hexdigest(), material.decode().splitlines())
            if mid == "11111111-1111-4111-8111-111111111111"
            else None
        ),
    )


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda p: p.stem)
def test_every_example_through_cli_and_final_graph(example, tmp_path):
    ctx = pinned(example)
    batch = prepare.assemble(ctx, [json.loads(example.read_bytes())])
    context = tmp_path / "context.json"
    context.write_text(json.dumps(ctx))
    result = tmp_path / "result.json"
    result.write_text(json.dumps(batch))
    completed = subprocess.run(
        [
            sys.executable,
            str(SKILL / "scripts/check_result.py"),
            "--schema",
            str(SCHEMA_PATH),
            "--context",
            str(context),
            str(result),
        ],
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout.decode()
    assert server_parse(batch, ctx)


def test_examples_cover_targets_and_operations():
    items = [item for p in EXAMPLES for item in json.loads(p.read_bytes())]
    assert {i["target_kind"] for i in items} == set(checker.TARGET_KINDS)
    assert {i["operation"] for i in items} == {"create", "update", "delete"}


def test_examples_show_chinese_names():
    # The agent copies examples, so every named element demonstrates display_name.
    named = {"object_type", "property", "link_type", "rule", "metric", "dataset"}
    missing = [
        (p.name, item["after"]["name"])
        for p in EXAMPLES
        for item in json.loads(p.read_bytes())
        if item["target_kind"] in named and item["operation"] != "delete"
        and not item["after"].get("display_name")
    ]
    assert missing == []


@pytest.mark.parametrize(
    "mutation", ["cross_dataset", "manual_evidence", "bad_quote", "bad_lines"]
)
def test_final_graph_and_evidence_still_reject(mutation):
    path = (
        SKILL
        / "references/examples"
        / ("metrics.json" if mutation == "cross_dataset" else "facts.json")
    )
    ctx = pinned(path)
    batch = prepare.assemble(ctx, [json.loads(path.read_bytes())])
    if mutation == "cross_dataset":
        batch["items"].append(
            {
                "operation": "create",
                "target_kind": "dataset",
                "client_ref": "other",
                "before": None,
                "after": {"name": "yunfan_refunds", "display_name": "云帆退款", "table_name": "demo_other"},
            }
        )
        component = batch["items"][2]["after"]
        component["dataset_id"] = {"client_ref": "other"}
        component["measure"]["dataset_id"] = {"client_ref": "other"}
    else:
        evidence = batch["items"][3]["after"]["evidence"][0]
        if mutation == "manual_evidence":
            batch["items"][3]["after"]["evidence"] = [
                {
                    "id": "77777777-7777-4777-8777-777777777777",
                    "kind": "manual",
                    "created_by": "fictional-member",
                    "created_at": "2026-10-20T00:00:00Z",
                    "note": "伪造人工证据",
                }
            ]
        elif mutation == "bad_quote":
            evidence["quote"] = "不存在的原文"
        else:
            evidence["locator"]["line_end"] = 50
    if mutation == "cross_dataset":
        assert any(i.status == "unacceptable" for i in server_parse(batch, ctx).items)
    else:
        with pytest.raises(ProposalContractError):
            server_parse(batch, ctx)


def test_discriminator_error_is_short_and_report_is_complete(tmp_path, capsys):
    ctx = pinned(SKILL / "references/examples/metrics.json")
    items = json.loads((SKILL / "references/examples/metrics.json").read_bytes())
    items[1]["after"]["aggregation"] = "total"
    batch = prepare.assemble(ctx, [items])
    batch["items"] *= 40
    result = tmp_path / "result.json"
    result.write_text(json.dumps(batch))
    assert checker.validate_file(result, SCHEMA_PATH) == 1
    output = capsys.readouterr().out
    assert len(output.encode()) <= 4096
    assert "SCHEMA_ENUM" in output and "show_example.py --part 04" in output
    report = json.loads(Path(str(result) + ".errors.json").read_bytes())
    assert report["total"] >= 40 and len(report["errors"]) == report["total"]
    assert report["schema_details"]
    result.write_text("{")
    assert checker.validate_file(result, SCHEMA_PATH) == 1
    assert len(capsys.readouterr().out.encode()) <= 4096


def test_automatic_local_budget_and_atomic_publish(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    ctx = pinned(SKILL / "references/examples/facts.json")
    ctx["execution"] = {"repair_used": 0, "budget_file": "output/budget.json"}
    context = tmp_path / "context.json"
    context.write_text(json.dumps(ctx))
    batch = prepare.assemble(
        ctx, [json.loads((SKILL / "references/examples/facts.json").read_bytes())]
    )
    result = tmp_path / "candidate.json"
    final = tmp_path / "final.json"
    for used in range(4):
        batch["items"][0]["after"]["description"] = str(used)
        result.write_text(json.dumps(batch))
        assert checker.validate_file(
            result, SCHEMA_PATH, context, publish=final
        ) == int(used > 2)
        ledger = json.loads((tmp_path / "output/budget.json").read_bytes())
        assert ledger["used"] == used
        if used <= 2:
            assert final.read_bytes() == result.read_bytes()
        else:
            assert final.read_bytes() != result.read_bytes()
    assert not list(tmp_path.glob("**/.pending-*"))
    assert "REPAIR_BUDGET_EXHAUSTED" in capsys.readouterr().out


def test_prepare_does_not_replace_final_on_bad_fragment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    final = tmp_path / "final.json"
    final.write_text("previous")
    fragment = tmp_path / "items.json"
    fragment.write_text('[{"operation":"update"}]')
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare_result.py",
            "--schema",
            str(SCHEMA_PATH),
            "--context",
            str(BASE / "tests/fixtures/context.json"),
            "--output",
            str(final),
            str(fragment),
        ],
    )
    assert prepare.main() == 1
    assert final.read_text() == "previous"
    with pytest.raises(ValueError):
        prepare.workspace_path(tmp_path.parent / "outside.json")


def test_local_source_scope_and_reference_literals():
    path = SKILL / "references/examples/mapping.json"
    ctx = pinned(path)
    batch = prepare.assemble(ctx, [json.loads(path.read_bytes())])
    other = deepcopy(batch["items"][-1])
    other["client_ref"] = "second_mapping"
    batch["items"].append(other)
    assert not checker.check_result(batch, SCHEMA, ctx)  # same local main is legal
    other["after"]["fields"]["loan_no"]["source_id"] = "aux"
    errors = checker.check_result(batch, SCHEMA, ctx)
    assert any("source_id" in e and "LOCAL_SOURCE_UNKNOWN" in e for e in errors)


def test_budget_targets_and_historical_conservation():
    report = budget.byte_report()
    assert report["first_read_pass"] and report["work_pack_pass"]
    assert report["selected_examples_pass"] and report["skill_and_reference_pass"]
    assert report["all_limits_pass"], report["limits"]
    assert all(route["pass"] for route in report["routes"].values())
    for task, expected in budget.EXPECTED.items():
        rows = json.loads((BASE / f"tests/fixtures/usage-{task}.json").read_bytes())
        report = budget.summarize(task, rows)
        assert report["conserved"] and report["runtime_turns"] == expected[3]
        assert sum(c["I"] for c in report["categories"].values()) == report["I"]
        if task.startswith("task_dd4f"):
            assert report["cache_fallback_candidates"] == [14, 22, 29, 34, 38, 40, 42]
            assert report["usage_turns"] == 43


def test_copy_backslash_and_missing_trace(tmp_path):
    path = tmp_path / "trace.tsv"
    raw = json.dumps({"usage": {"input_tokens": 1}, "ignored": "one\\two"}).replace(
        "\\", "\\\\"
    )
    path.write_text("1\t1\tusage.updated\t" + raw + "\n")
    assert budget.trace_rows(path)[0]["U"] == 1
    assert budget.summarize("unknown", budget.trace_rows(path))["categories"][
        "无法分类"
    ]


def test_read_input_boundaries_and_original_lines(tmp_path):
    path = tmp_path / "material.md"
    path.write_text("首行\n原证据\n末行\n")
    command = [sys.executable, str(SKILL / "scripts/read_input.py"), str(path)]
    completed = subprocess.run(
        [*command, "--start", "2", "--end", "2"], capture_output=True, check=False
    )
    result = json.loads(completed.stdout)
    assert result["original_range"] == [2, 2] and result["unread_ranges"] == [
        [1, 1],
        [3, 3],
    ]
    path.write_text("大" * 10000)
    completed = subprocess.run(command, capture_output=True, check=False)
    assert completed.returncode == 1 and len(completed.stdout) < 8192


def test_skill_reference_paths_exist():
    import re

    for document in (SKILL / "references").glob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
            if "://" not in target:
                assert (document.parent / target.split("#")[0]).exists(), (
                    document,
                    target,
                )


def test_invalid_ledger_is_not_reset(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    context = pinned(SKILL / "references/examples/facts.json")
    context["execution"] = {"repair_used": 0, "budget_file": "budget.json"}
    (tmp_path / "context.json").write_text(json.dumps(context))
    (tmp_path / "budget.json").write_text("{}")
    result = prepare.assemble(
        context, [json.loads((SKILL / "references/examples/facts.json").read_bytes())]
    )
    (tmp_path / "result.json").write_text(json.dumps(result))
    assert checker.validate_file("result.json", SCHEMA_PATH, "context.json") == 1
    assert (tmp_path / "budget.json").read_text() == "{}"
    assert "INPUT_KEYERROR" in capsys.readouterr().out


def test_catalog_discovers_all_examples_and_core_topics():
    directory = SKILL / "references/examples"
    actual = {str(p.relative_to(directory)) for p in directory.rglob("*.json")}
    registered = (
        [e["file"] for e in CATALOG["examples"]]
        + CATALOG["protocols"]
        + ["catalog.json"]
    )
    assert len(registered) == len(set(registered))
    assert actual == set(registered)
    assert not (directory / "negative").exists()
    for topic in [
        "facts",
        "inheritance",
        "identifiers",
        "mapping",
        "metrics",
        "rules",
        "operations",
        "reuse-fact",
    ]:
        assert any(topic in entry["topics"] for entry in CATALOG["examples"])


@pytest.mark.parametrize("kind", sorted(checker.TARGET_KINDS))
@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_lookup_output_is_bounded_and_passes_both_validators(kind, operation):
    command = [
        sys.executable,
        str(SKILL / "scripts/show_example.py"),
        kind,
        "--with-deps",
        "--operation",
        operation,
    ]
    completed = subprocess.run(command, capture_output=True, check=False)
    assert completed.returncode == 0, completed.stdout.decode()
    assert len(completed.stdout) <= 8192
    items = json.loads(completed.stdout)
    assert any(i["target_kind"] == kind and i["operation"] == operation for i in items)
    path = SKILL / "references/examples" / CATALOG["lookup"][kind][operation]
    ctx = pinned(path)
    batch = prepare.assemble(ctx, [items])
    assert not checker.check_result(batch, SCHEMA, ctx)
    assert server_parse(batch, ctx)


def test_unknown_lookup_lists_choices():
    completed = subprocess.run(
        [sys.executable, str(SKILL / "scripts/show_example.py"), "unknown"],
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1 and len(completed.stdout) <= 8192
    assert all(k in completed.stdout.decode() for k in checker.TARGET_KINDS)


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_field",
        "missing",
        "wrong_type",
        "placeholder",
        "branch",
        "source",
        "reference",
        "token",
        "before",
        "hash",
        "duplicate",
    ],
)
def test_errors_have_location_expectation_actual_and_executable_lookup(mutation):
    import shlex

    name = "mapping" if mutation == "source" else "facts"
    if mutation in {"before", "hash", "duplicate"}:
        name = "operations"
    path = SKILL / f"references/examples/{name}.json"
    ctx = pinned(path)
    batch = prepare.assemble(ctx, [json.loads(path.read_bytes())])
    assert not checker.check_result(batch, SCHEMA, ctx)
    assert server_parse(batch, ctx)
    item = batch["items"][0]
    if mutation == "unknown_field":
        item["after"]["technical_name"] = "forbidden"
    elif mutation == "missing":
        del item["after"]["name"]
    elif mutation == "wrong_type":
        item["after"]["name"] = 5
    elif mutation == "placeholder":
        batch["items"][2]["after"]["verbalizes"] = ["{source}至{other}"]
    elif mutation == "branch":
        metric_path = SKILL / "references/examples/metrics.json"
        ctx = pinned(metric_path)
        batch = prepare.assemble(ctx, [json.loads(metric_path.read_bytes())])
        batch["items"][3]["after"]["time_field"] = {
            "dataset_id": {"client_ref": "daily"},
            "column": "sales",
        }
    elif mutation == "source":
        batch["items"][-1]["after"]["fields"]["loan_no"]["source_id"] = "aux"
    elif mutation == "reference":
        item["after"]["extends"] = {"client_ref": "absent"}
    elif mutation == "token":
        batch["run_token"] = "stale"
    elif mutation == "before":
        item["before"]["description"] = "stale"
    elif mutation == "hash":
        item["expected_target_hash"] = "0" * 64
    else:
        batch["items"].append(deepcopy(item))
    errors = checker.check_result(batch, SCHEMA, ctx)
    assert errors
    for error in errors:
        assert re.match(r"错误 \[[A-Z_]+\]：/", error)
        assert "期望" in error and "实际" in error and "下一步：" in error
        step = error.split("下一步：", 1)[1]
        if "show_example.py" not in step:
            continue
        # Writing errors point at an example; the printed command runs as is.
        command = shlex.split(step.split("：", 1)[1])
        assert command[0] == "$DATAAGENT_PYTHON_BIN" and Path(command[1]).is_file()
        completed = subprocess.run(
            [sys.executable, *command[1:]], capture_output=True, check=False
        )
        assert completed.returncode == 0 and len(completed.stdout) <= 8192
    if mutation == "source":
        parsed = server_parse(batch, ctx)
        assert parsed.items[-1].status == "unacceptable"
        assert parsed.items[-1].status_reason
    else:
        with pytest.raises(ProposalContractError) as caught:
            server_parse(batch, ctx)
        assert "期望" in str(caught.value) and "实际" in str(caught.value)
        assert "show_example.py" in str(caught.value) and "/" in str(caught.value)


def test_prepare_reports_exact_fragment_location_and_preserves_output(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    context = pinned(SKILL / "references/examples/operations.json")
    item = json.loads((SKILL / "references/examples/operations.json").read_bytes())[0]
    item["before"]["description"] = "错误旧值"
    with pytest.raises(prepare.PrepareInputError) as caught:
        prepare.assemble(context, [[item]])
    message = str(caught.value)
    assert "/items/0/before" in message and "期望" in message and "实际" in message
    # A stale before is fixed by reading the pinned value, not by an example.
    assert "show_element.py --work-pack" in message and "33333333-3333-4333-8333-333333333333" in message
    item["target_id"] = "absent"
    with pytest.raises(prepare.PrepareInputError, match="/items/0/target_id"):
        prepare.assemble(context, [[item]])
    (tmp_path / "items.json").write_text(json.dumps([item]))
    (tmp_path / "final.json").write_text("previous")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "prepare_result.py",
            "--context",
            str(BASE / "tests/fixtures/context.json"),
            "--schema",
            str(SCHEMA_PATH),
            "--output",
            "final.json",
            "items.json",
        ],
    )
    assert prepare.main() == 1
    assert (tmp_path / "final.json").read_text() == "previous"
    assert len(capsys.readouterr().out.encode()) <= 4096
    assert json.loads((tmp_path / "final.json.errors.json").read_bytes())["total"] == 1


def test_manual_evidence_preservation_and_meaningful_calculation_examples():
    path = SKILL / "references/examples/reuse-fact.json"
    ctx = pinned(path)
    batch = prepare.assemble(ctx, [json.loads(path.read_bytes())])
    assert server_parse(batch, ctx)
    batch["items"][0]["after"]["evidence"] = []
    with pytest.raises(ProposalContractError) as caught:
        server_parse(batch, ctx)
    assert caught.value.code == "MANUAL_EVIDENCE_FORBIDDEN"
    example = json.loads(
        (SKILL / "references/examples/expression-binding.json").read_bytes()
    )
    assert (
        example[-1]["after"]["fields"]["line_amount"]["expression"]
        == "main.copy_count * main.deposit_each"
    )
    assert 2 * 30 == 60
    joins = json.loads((SKILL / "references/examples/link-joins.json").read_bytes())
    link = next(i for i in joins if i["client_ref"] == "reports")
    assert link["after"]["data_join"]["source_property_ids"] == [
        {"client_ref": "manager_no"}
    ]


def test_method_section_ranges_and_budgeted_decision_reads():
    import re

    for path in (BASE / "skills").glob("*/references/extract-*.md"):
        lines = path.read_text().splitlines()
        for heading, start, end in re.findall(r"([^：；]+) (\d+)–(\d+)行", lines[2]):
            start, end = int(start), int(end)
            assert lines[start - 1] == "## " + heading
            assert 0 < start <= end <= len(lines)
            assert not any(line.startswith("## ") for line in lines[start:end])


@pytest.mark.parametrize(
    "kind,variant,filename",
    [
        ("metric", "ratio", "metrics.json"),
        ("metric", "expression", "metrics.json"),
        ("mapping", "expression", "expression-binding.json"),
        ("mapping", "shared_parent", "inheritance.json"),
        ("link_type", "direct", "link-joins.json"),
        ("link_type", "mapping_table", "link-joins.json"),
        ("rule", "derivation", "derivation.json"),
    ],
)
def test_branch_lookup_output_is_a_positive_example(kind, variant, filename):
    command = [
        sys.executable,
        str(SKILL / "scripts/show_example.py"),
        kind,
        "--with-deps",
        "--variant",
        variant,
    ]
    completed = subprocess.run(command, capture_output=True, check=False)
    assert completed.returncode == 0 and len(completed.stdout) <= 8192
    ctx = pinned(SKILL / "references/examples" / filename)
    batch = prepare.assemble(ctx, [json.loads(completed.stdout)])
    assert not checker.check_result(batch, SCHEMA, ctx)
    assert server_parse(batch, ctx)
