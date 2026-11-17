"""The fixed kit and its variants pass the platform's submission checks; scripts stay bounded."""

import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

import offline_budget as budget
import platform_check
import prepare_result as prepare
import pytest
from ontofoundry_api.contracts.proposal_diagnostics import diagnostic
from runpaths import TARGET_KINDS

BASE = Path(__file__).resolve().parents[1]
SKILL = BASE / "shared"
KIT = SKILL / "references/extract-kit"
MATERIAL = (KIT / "material.md").read_bytes()
SHOW = [sys.executable, str(SKILL / "scripts/show_example.py")]


def show(*args):
    return subprocess.run([*SHOW, *args], capture_output=True, check=False)


def kit_material(_material_id):
    return hashlib.sha256(MATERIAL).hexdigest(), MATERIAL.decode().splitlines()


def kit_batch():
    return {"items": [i for n in ("01", "02", "03", "04", "05") for i in json.loads((KIT / f"{n}.json").read_bytes())]}


def test_the_kit_passes_the_platform_with_its_real_material():
    assert platform_check.errors(kit_batch(), platform_check.empty_pinned(), kit_material) == []


def test_the_kit_shows_every_kind_operation_and_chinese_names():
    items = kit_batch()["items"] + [i for n in ("update", "edit") for i in json.loads((KIT / f"{n}.json").read_bytes())]
    assert {i["target_kind"] for i in items} >= set(TARGET_KINDS) - {"material_link"} | {"material_link"}
    assert {i["operation"] for i in items} == {"create", "update", "delete"}
    named = {"object_type", "property", "link_type", "rule", "metric", "dataset"}
    assert [i["client_ref"] for i in items if i["target_kind"] in named and i["operation"] == "create"
            and not i["after"].get("display_name")] == []


@pytest.mark.parametrize("name", sorted(json.loads((KIT / "variants.json").read_bytes())))
def test_every_variant_is_bounded_and_passes_the_platform(name):
    completed = show("--variant", name)
    assert completed.returncode == 0 and len(completed.stdout) <= 8192, completed.stdout.decode()
    pinned = (json.loads((BASE / "tests/fixtures/reuse-fact-context.json").read_bytes())
              if name == "reuse-fact" else platform_check.empty_pinned())
    assert platform_check.errors({"items": json.loads(completed.stdout)}, pinned) == []


@pytest.mark.parametrize("mutation", ["manual_evidence", "bad_quote", "bad_lines", "cross_dataset_ratio"])
def test_the_platform_still_rejects_broken_kit_content(mutation):
    batch = kit_batch()
    fact = next(i for i in batch["items"] if i["target_kind"] == "material_object")
    if mutation == "manual_evidence":
        fact["after"]["evidence"] = [{"id": "77777777-7777-4777-8777-777777777777", "kind": "manual",
                                      "created_by": "fictional-member", "created_at": "2026-10-20T00:00:00Z", "note": "伪造"}]
    elif mutation == "bad_quote":
        fact["after"]["evidence"][0]["quote"] = "不存在的原文"
    elif mutation == "bad_lines":
        fact["after"]["evidence"][0]["locator"]["line_end"] = 50
    else:
        # 平均押金 = 押金 / 赔偿（另一数据集）: ratio components must share a dataset.
        ratio = next(i for i in batch["items"] if i["client_ref"] == "mean_deposit")
        ratio["after"]["denominator_id"] = {"client_ref": "charge"}
    assert platform_check.errors(batch, platform_check.empty_pinned(), kit_material)


def test_lookup_by_kind_names_the_kit_part():
    completed = show("metric", "material_link")
    out = completed.stdout.decode()
    assert completed.returncode == 1 and "--part 04" in out and "--part 05" in out
    assert "未知类型" in show("unknown").stdout.decode()
    listed = show("--variant", "nope").stdout.decode()
    assert all(name in listed for name in json.loads((KIT / "variants.json").read_bytes()))


@pytest.mark.parametrize("item", [
    {"operation": "create", "target_kind": "metric", "after": {"kind": "ratio"}},
    {"operation": "create", "target_kind": "material_link", "after": {}},
    {"operation": "update", "target_kind": "property", "after": {}},
    {"operation": "delete", "target_kind": "rule"},
])
def test_platform_errors_point_at_a_kit_entry_that_runs(item):
    message = diagnostic("/items/0", "示例错误", "期望形状", "实际值", item)
    entry = shlex.split(message.split("scripts/show_example.py", 1)[1])
    completed = show(*entry)
    assert completed.returncode == 0 and len(completed.stdout) <= 8192, (entry, completed.stdout.decode())


def test_examples_never_show_material_hashes():
    for args in (["--part", "01"], ["--part", "05"], ["--variant", "reuse-fact"]):
        completed = show(*args)
        assert b"material_sha256" not in completed.stdout and b'"material_id"' in completed.stdout


def test_only_the_protocol_formats_remain_under_examples():
    directory = SKILL / "references/examples"
    assert {p.relative_to(directory).as_posix() for p in directory.rglob("*.json")} == {
        "protocol/entities.json", "protocol/issues.json"}


def test_prepare_reports_the_fragment_and_preserves_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "plan.md").write_text("")
    item = {"target_kind": "object_type", "after": {"name": "x"}}
    with pytest.raises(prepare.PrepareInputError) as caught:
        prepare.assemble([[item]])
    assert "/items/0/operation" in str(caught.value) and "期望" in str(caught.value)
    parts = tmp_path / "modeling/parts"
    parts.mkdir(parents=True)
    (parts / "01-types.json").write_text(json.dumps([item]))
    (tmp_path / "final.json").write_text("previous")
    (tmp_path / "pack.json").write_text(json.dumps({"result_file": "final.json"}))
    monkeypatch.setattr(prepare, "plan_not_approved", lambda: None)
    monkeypatch.setattr(sys, "argv", ["prepare_result.py", "--work-pack", "pack.json"])
    assert prepare.main() == 1
    out = capsys.readouterr().out
    assert "modeling/parts/01-types.json#/0" in out and len(out.encode()) <= 4096
    assert (tmp_path / "final.json").read_text() == "previous"
    with pytest.raises(ValueError):
        prepare.workspace_path(tmp_path.parent / "outside.json")


def test_calculation_variants_say_what_they_compute():
    found = json.loads((KIT / "variants.json").read_bytes())
    binding = found["expression-binding"][-1]["after"]["fields"]["line_amount"]["expression"]
    assert binding == "main.copy_count * main.deposit_each"
    link = next(i for i in found["link-joins"] if i["client_ref"] == "reports")
    assert link["after"]["data_join"]["source_property_ids"] == [{"client_ref": "manager_no"}]


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
    result = completed.stdout.decode()
    assert "2→原证据" in result and "未读范围：1–1、3–3" in result
    assert "--start 3" in result
    path.write_text("大" * 10000)
    completed = subprocess.run(command, capture_output=True, check=False)
    assert completed.returncode == 0 and len(completed.stdout) < 8192
    assert "超长内容已截断" in completed.stdout.decode()


def test_skill_reference_paths_exist():
    import re

    for document in (SKILL / "references").glob("*.md"):
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
            if "://" not in target:
                assert (document.parent / target.split("#")[0]).exists(), (
                    document,
                    target,
                )


def test_method_section_ranges_and_budgeted_decision_reads():
    import re

    for path in (BASE / "skills").glob("*/references/extract-*.md"):
        lines = path.read_text().splitlines()
        for heading, start, end in re.findall(r"([^：；]+) (\d+)–(\d+)行", lines[2]):
            start, end = int(start), int(end)
            assert lines[start - 1] == "## " + heading
            assert 0 < start <= end <= len(lines)
            assert not any(line.startswith("## ") for line in lines[start:end])
