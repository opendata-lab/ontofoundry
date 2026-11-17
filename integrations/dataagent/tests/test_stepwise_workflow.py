"""Stepwise workspace, fragment and protocol contracts, entirely offline."""

import importlib
import json
import subprocess
import sys
from pathlib import Path

import offline_budget
import pytest

BASE = Path(__file__).resolve().parents[1]
SKILL = BASE / "shared"
KIT = SKILL / "references/extract-kit"

init_workflow = importlib.import_module("init_workflow")
prepare = prepare_result = importlib.import_module("prepare_result")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False))
    return path


def invoke(monkeypatch, module, *args):
    if module.__name__ == "prepare_result":
        monkeypatch.setattr(module, "platform_submit", lambda *_: True)
    monkeypatch.setattr(sys, "argv", [module.__name__ + ".py", *map(str, args)])
    return module.main()


def lookup(*args):
    return subprocess.run([sys.executable, str(SKILL / "scripts/show_example.py"), *args], capture_output=True, check=False)


def test_init_template_is_idempotent_and_preserves_all_existing_files(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    pack = write_json(
        tmp_path / "pack.json",
        {
            "scenario_facts": {
                "draft_empty": True,
                "new_material_ids": ["fictional-material"],
                "new_table_count": 1,
            }
        },
    )
    assert invoke(monkeypatch, init_workflow, "--work-pack", pack) == 0
    root = tmp_path / "modeling"
    assert all((root / folder).is_dir() for folder in ("parts", "checks"))
    template = (root / "plan.md").read_text()
    assert all(
        text in template
        for text in (str(pack), "本体为空：是", "fictional-material", "新增关联表：1 张", "⑥输出")
    )
    for name in (
        "plan.md",
        "notes.md",
        "entities.json",
        "issues.json",
        "parts/01-types.json",
        "checks/01-types.json",
    ):
        (root / name).write_text("保留原内容：" + name)
    before = {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    }
    assert invoke(monkeypatch, init_workflow, "--work-pack", pack) == 0
    assert {
        p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()
    } == before


def test_init_has_no_prior_plan_to_restore(tmp_path, monkeypatch):
    # The plan is approved inside the run; nothing carries over between runs.
    monkeypatch.chdir(tmp_path)
    pack = write_json(tmp_path / "pack.json", {})
    with pytest.raises(SystemExit):
        invoke(monkeypatch, init_workflow, "--work-pack", pack, "--prior-plan", "plan.json")


def test_prepare_directory_is_sorted_and_equivalent_to_explicit_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(prepare, "plan_not_approved", lambda: None)
    items = [i for n in ("01", "02", "03") for i in json.loads((KIT / f"{n}.json").read_bytes())]
    parts = tmp_path / "parts"
    parts.mkdir()
    for name, chunk in (("03-mappings.json", items[-3:]), ("01-types.json", items[:-6]), ("02-links.json", items[-6:-3])):
        write_json(parts / name, chunk)
    (parts / "ignore.txt").write_text("ignored")
    (parts / "nested").mkdir()
    write_json(parts / "nested/not-a-part.json", [])
    files = sorted(parts.glob("*.json"))
    assert prepare.fragment_files([parts]) == files
    for output, inputs in (("directory.json", [parts]), ("explicit.json", files)):
        pack = write_json(tmp_path / f"{output}.pack", {"result_file": output})
        assert invoke(monkeypatch, prepare, "--work-pack", pack, *inputs) == 0
    assert (tmp_path / "directory.json").read_bytes() == (tmp_path / "explicit.json").read_bytes()
    merged = json.loads((tmp_path / "directory.json").read_bytes())["items"]
    assert [i["client_ref"] for i in merged] == [i["client_ref"] for i in items[:-6] + items[-6:-3] + items[-3:]]


def test_prepare_empty_directory_fails_and_preserves_output(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(prepare, "plan_not_approved", lambda: None)
    parts = tmp_path / "parts"
    parts.mkdir()
    (parts / "ignored.md").write_text("not a fragment")
    with pytest.raises(ValueError, match="没有 JSON 片段"):
        prepare.fragment_files([parts])
    final = tmp_path / "final.json"
    final.write_text("previous")
    pack = write_json(tmp_path / "pack.json", {"result_file": "final.json"})
    assert invoke(monkeypatch, prepare, "--work-pack", pack, parts) == 1
    assert "NO_FRAGMENTS" in capsys.readouterr().out
    assert final.read_text() == "previous"


def test_protocol_formats_are_present():
    for name in ("entities", "issues"):
        value = json.loads((SKILL / f"references/examples/protocol/{name}.json").read_bytes())
        assert isinstance(value["items"], list) and value["items"]


def test_stepwise_routes_and_updated_limits_pass():
    report = offline_budget.byte_report()
    assert report["all_limits_pass"]
    for name in ("技能入口", "entity-extraction入口", "semantic-grounding入口"):
        assert report["limits"][name]["limit"] == 1100
    assert report["limits"]["系统正文"]["limit"] == 450
    combined = report["routes"]["定义与实例组合"]
    assert combined["limit"] == 36000 and combined["pass"]
    assert {"技能入口", "实例技能入口", "抽取步骤", "实例步骤", "收尾步骤", "工作包", "带原行号材料", "已批准计划", "实例方法"} <= combined["components"].keys()
    assert combined["bytes"] == sum(c["bytes"] for c in combined["components"].values())
    for name, limit in (("第一步（计划）", 15500), ("第二步（抽取）", 36000)):
        route = report["routes"][name]
        assert route["limit"] == limit and route["bytes"] <= limit and route["pass"]
    for name, limit in (("技能入口", 1100), ("计划步骤", 1500), ("优化步骤", 900), ("共同必读", 9600)):
        assert report["limits"][name]["limit"] == limit
        assert report["limits"][name]["pass"]
    route = report["routes"]["第二步（抽取）"]
    components = route["components"]
    assert {"工作包", "带原行号材料", "已批准计划", "表结构", "原则", "技能入口"} <= components.keys()
    assert {f"写法包/{name}" for name in ("guide.md", "values.json", "01.json", "02.json", "03.json", "04.json", "05.json")} <= components.keys()
    assert route["bytes"] == sum(c["bytes"] for c in components.values())
    assert route["estimated_rounds"]["normal"] == [9, 11]
    assert route["estimated_rounds"]["two_repairs"] == [13, 15]


def test_prepare_waits_for_an_approved_plan(tmp_path, monkeypatch, capsys):
    # Bash stays open for research in plan mode, so merging and submitting
    # hold until DataAgent reports the plan approved.
    monkeypatch.chdir(tmp_path)
    pack = write_json(tmp_path / "pack.json", {})
    monkeypatch.setenv("DATAAGENT_PLAN_STATE", "pending")
    assert invoke(monkeypatch, prepare, "--work-pack", pack, "01") != 0
    out = capsys.readouterr().out
    assert "错误 [PLAN_NOT_APPROVED]" in out and "ExitPlanMode" in out
    assert not (tmp_path / "modeling").exists()

    monkeypatch.setenv("DATAAGENT_PLAN_STATE", "approved")
    invoke(monkeypatch, prepare, "--work-pack", pack, "01")
    assert "PLAN_NOT_APPROVED" not in capsys.readouterr().out


def test_part_lookup_accepts_hand_written_fragment_names():
    for part in ("01b", "02b", "03b"):
        result = lookup("--part", part)
        assert result.returncode == 0
        assert result.stdout == lookup("--part", part[:2]).stdout
