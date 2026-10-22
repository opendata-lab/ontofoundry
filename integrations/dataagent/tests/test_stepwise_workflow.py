from pathlib import Path
BASE = Path(__file__).resolve().parents[1]

"""Stepwise workspace, fragment and protocol contracts, entirely offline."""

import importlib
import json
import subprocess
import sys
from copy import deepcopy

import pytest
from test_workflow import CATALOG, SCHEMA, SCHEMA_PATH, SKILL, checker, pinned, prepare
from test_workflow import budget as offline_budget

# test_workflow adds the standalone scripts directory to the import path.
check_part = importlib.import_module("check_part")
init_workflow = importlib.import_module("init_workflow")


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False))
    return path


def invoke(monkeypatch, module, *args):
    monkeypatch.setattr(sys, "argv", [module.__name__ + ".py", *map(str, args)])
    return module.main()


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
                "new_table_keys": ["t2"],
            }
        },
    )
    assert invoke(monkeypatch, init_workflow, "--work-pack", pack) == 0
    root = tmp_path / "modeling"
    assert all((root / folder).is_dir() for folder in ("parts", "checks"))
    template = (root / "plan.md").read_text()
    assert all(
        text in template
        for text in (str(pack), "本体为空：是", "fictional-material", "t2", "⑥输出")
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


@pytest.mark.parametrize("existing", [False, True])
def test_init_restores_prior_plan_without_overwriting(tmp_path, monkeypatch, existing):
    monkeypatch.chdir(tmp_path)
    pack = write_json(tmp_path / "pack.json", {})
    prior = {
        "plan_md": "场景：全量\n已确认范围",
        "entities": {"items": [{"name": "fictional_order"}]},
        "issues": {"items": []},
    }
    bundle = write_json(tmp_path / "prior.json", prior)
    root = tmp_path / "modeling"
    root.mkdir()
    if existing:
        for name in ("plan.md", "entities.json", "issues.json", "notes.md"):
            (root / name).write_text("已有文件")
    assert (
        invoke(monkeypatch, init_workflow, "--work-pack", pack, "--prior-plan", bundle)
        == 0
    )
    if existing:
        assert all(
            (root / name).read_text() == "已有文件"
            for name in ("plan.md", "entities.json", "issues.json", "notes.md")
        )
    else:
        assert (root / "plan.md").read_text() == prior["plan_md"]
        for name in ("entities", "issues"):
            assert json.loads((root / f"{name}.json").read_bytes()) == prior[name]
        assert (root / "notes.md").is_file()


def mapping_example():
    path = SKILL / "references/examples/create-mapping.json"
    return pinned(path), json.loads(path.read_bytes())


def test_check_part_cross_fragment_references_are_pending_and_reports_use_requested_dir(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    ctx, items = mapping_example()
    fragment = write_json(tmp_path / "03-mapping.json", [items[-1]])
    context = write_json(tmp_path / "context.json", ctx)
    reports = tmp_path / "custom-reports"
    assert (
        invoke(
            monkeypatch,
            check_part,
            "--context",
            context,
            "--schema",
            SCHEMA_PATH,
            "--reports",
            reports,
            fragment,
        )
        == 0
    )
    report = json.loads((reports / "03-mapping.json").read_bytes())
    assert report["errors"] == []
    assert report["pending_refs"] == ["loans", "loans_ds"]
    assert not (tmp_path / "modeling/checks").exists()
    assert not list(tmp_path.rglob("*budget*"))


def test_check_part_accepts_numbers_and_reads_paths_from_the_work_pack(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    ctx, items = mapping_example()
    (tmp_path / "modeling/parts").mkdir(parents=True)
    write_json(tmp_path / "modeling/parts/03-datasets.json", [items[-1]])
    context = write_json(tmp_path / "context.json", ctx)
    pack = write_json(tmp_path / "pack.json", {"context_file": str(context), "schema_file": str(SCHEMA_PATH)})
    assert invoke(monkeypatch, check_part, "--work-pack", pack, "03") == 0
    assert "modeling/parts/03-datasets.json：通过" in capsys.readouterr().out
    assert invoke(monkeypatch, check_part, "--work-pack", pack, "03-datasets") == 0
    assert invoke(monkeypatch, check_part, "--work-pack", pack, "04") == 1
    assert "现有：03-datasets.json" in capsys.readouterr().out
    assert invoke(monkeypatch, check_part, "03") == 2


@pytest.mark.parametrize("mutation", ["duplicate", "shape"])
def test_check_part_rejects_duplicate_refs_and_invalid_shape(
    tmp_path, monkeypatch, mutation
):
    monkeypatch.chdir(tmp_path)
    ctx, items = mapping_example()
    fragment = [items[0], deepcopy(items[0])] if mutation == "duplicate" else [items[0]]
    if mutation == "shape":
        fragment[0]["after"]["name"] = 42
    path = write_json(tmp_path / "part.json", fragment)
    context = write_json(tmp_path / "context.json", ctx)
    assert (
        invoke(
            monkeypatch, check_part, "--context", context, "--schema", SCHEMA_PATH, path
        )
        == 1
    )
    report = json.loads((tmp_path / "modeling/checks/part.json").read_bytes())
    assert report["errors"]
    field = "client_ref" if mutation == "duplicate" else "name"
    assert any(field in e for e in report["errors"])


def test_check_part_missing_display_name_is_a_hint():
    ctx, items = mapping_example()
    item = items[0]
    del item["after"]["display_name"]
    report = check_part.check_fragment([item], ctx, SCHEMA)
    assert not report["errors"]
    assert "/items/0/after/display_name：建议填写中文名称" in report["hints"]


@pytest.mark.parametrize("title", ["absent", None, {"client_ref": "branch_name"}])
def test_check_part_optional_title_hint_does_not_fail_or_infer_names(
    tmp_path, monkeypatch, capsys, title
):
    monkeypatch.chdir(tmp_path)
    ctx = pinned(SKILL / "references/examples/create-object_type.json")
    items = [
        {"operation": "create", "target_kind": "object_type", "client_ref": "branch",
         "after": {"name": "branch", "display_name": "分馆"}},
        {"operation": "create", "target_kind": "property", "client_ref": "branch_name",
         "after": {"name": "branch_name", "display_name": "分馆名称",
                   "owner_type_id": {"client_ref": "branch"}, "value_kind": "string"}},
    ]
    if title != "absent":
        items[0]["after"]["title_property_id"] = title
    original = deepcopy(items)
    fragment = write_json(tmp_path / "01-types.json", items)
    context = write_json(tmp_path / "context.json", ctx)
    assert invoke(monkeypatch, check_part, "--context", context, "--schema", SCHEMA_PATH, fragment) == 0
    report = json.loads((tmp_path / "modeling/checks/01-types.json").read_bytes())
    output = capsys.readouterr().out
    assert report["errors"] == report["pending_refs"] == []
    if isinstance(title, dict):
        assert report["hints"] == []
        assert "未设标题属性" not in output
    else:
        hint = "分馆（branch）未设标题属性（可不设）：若材料给出名称属性请设置，否则按标识显示，按名称解析会找不到；无需仅为此提示修正。"
        assert report["hints"] == [hint]
        assert hint in output
    assert items == original
    assert not list(tmp_path.rglob("*budget*"))


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_check_part_title_hint_ignores_existing_entities(operation):
    ctx = json.loads((BASE / "tests/fixtures/context.json").read_bytes())
    entity = ctx["draft"]["object_types"][0]
    item = {"operation": operation, "target_kind": "object_type", "target_id": entity["id"]}
    if operation == "update":
        item["after"] = {"name": entity["name"], "display_name": "分馆"}
    report = check_part.check_fragment([item], ctx, SCHEMA)
    assert report["errors"] == []
    assert report["hints"] == []


def test_check_part_rejects_dangling_reference_inside_mapping():
    ctx, items = mapping_example()
    items[-1]["after"]["fields"]["loan_no"]["source_id"] = "missing_local_source"
    # A mapping's sources are local, so another fragment cannot supply this ID.
    assert any(
        "LOCAL_SOURCE_UNKNOWN" in e
        for e in checker.check_result(prepare.assemble(ctx, [items]), SCHEMA, ctx)
    )
    report = check_part.check_fragment(items, ctx, SCHEMA)
    assert report["errors"], report


def test_prepare_directory_is_sorted_and_equivalent_to_explicit_files(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    ctx, items = mapping_example()
    context = write_json(tmp_path / "context.json", ctx)
    parts = tmp_path / "parts"
    parts.mkdir()
    for name, chunk in (
        ("03-mappings.json", items[-1:]),
        ("01-types.json", items[:4]),
        ("02-datasets.json", items[4:5]),
    ):
        write_json(parts / name, chunk)
    (parts / "ignore.txt").write_text("ignored")
    (parts / "nested").mkdir()
    write_json(parts / "nested/not-a-part.json", [])
    files = sorted(parts.glob("*.json"))
    assert prepare.fragment_files([parts]) == files
    for output, inputs in (("directory.json", [parts]), ("explicit.json", files)):
        assert (
            invoke(
                monkeypatch,
                prepare,
                "--context",
                context,
                "--schema",
                SCHEMA_PATH,
                "--output",
                output,
                *inputs,
            )
            == 0
        )
    assert (tmp_path / "directory.json").read_bytes() == (
        tmp_path / "explicit.json"
    ).read_bytes()
    assert json.loads((tmp_path / "directory.json").read_bytes())["items"] == items


def test_prepare_empty_directory_fails_and_preserves_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    parts = tmp_path / "parts"
    parts.mkdir()
    (parts / "ignored.md").write_text("not a fragment")
    with pytest.raises(ValueError, match="没有 JSON 片段"):
        prepare.fragment_files([parts])
    final = tmp_path / "final.json"
    final.write_text("previous")
    assert (
        invoke(
            monkeypatch,
            prepare,
            "--context",
            BASE / "tests/fixtures/context.json",
            "--schema",
            SCHEMA_PATH,
            "--output",
            final,
            parts,
        )
        == 1
    )
    assert final.read_text() == "previous"
    assert json.loads((tmp_path / "final.json.errors.json").read_bytes())["total"] == 1


def lookup(*args):
    return subprocess.run(
        [sys.executable, str(SKILL / "scripts/show_example.py"), *args],
        capture_output=True,
        check=False,
    )


def test_show_example_multiple_kinds_omit_dependencies_but_keep_owned_rules():
    completed = lookup("property", "mapping", "value_type", "property")
    assert completed.returncode == 0, completed.stdout.decode()
    assert len(completed.stdout) <= 8192
    output = json.loads(completed.stdout)
    assert list(output) == ["property", "mapping", "value_type"]
    for kind in ("property", "mapping"):
        assert output[kind]["items"]
        assert all(item["target_kind"] == kind for item in output[kind]["items"])
        assert output[kind]["依赖已省略"]
    value_items = output["value_type"]["items"]
    assert {item["target_kind"] for item in value_items} == {"value_type", "rule"}
    assert all(
        i["after"]["owner_kind"] == "value_type"
        for i in value_items
        if i["target_kind"] == "rule"
    )


def test_show_example_with_deps_rejects_multiple_kinds():
    completed = lookup("property", "mapping", "--with-deps")
    assert completed.returncode == 1
    assert "一次只查一个类型" in completed.stdout.decode()


def test_new_protocol_examples_are_registered():
    names = {"needs-input-entities", "needs-input-issues", "entities", "issues"}
    assert {f"protocol/{name}.json" for name in names} <= set(CATALOG["protocols"])
    assert CATALOG["future_topics"] == {}
    for name in names:
        value = json.loads(
            (SKILL / f"references/examples/protocol/{name}.json").read_bytes()
        )
        if name.startswith("needs-input"):
            assert value["run_token"] == "example"
            assert isinstance(value["questions"], list) and value["questions"]
            assert all(isinstance(q, str) and q.strip() for q in value["questions"])
        else:
            assert isinstance(value["items"], list) and value["items"]


def test_stepwise_routes_and_updated_limits_pass():
    report = offline_budget.byte_report()
    assert report["all_limits_pass"]
    for name in ("技能入口", "entity-extraction入口", "semantic-grounding入口"):
        assert report["limits"][name]["limit"] == 1100
    assert report["limits"]["系统正文"]["limit"] == 450
    combined = report["routes"]["定义与实例组合"]
    assert combined["limit"] == 36000 and combined["pass"]
    assert {"技能入口", "实例技能入口", "抽取步骤", "实例步骤", "收尾步骤", "工作包", "带原行号材料", "前轮计划", "实例方法", "实例正例"} <= combined["components"].keys()
    assert combined["bytes"] == sum(c["bytes"] for c in combined["components"].values())
    for name, limit in (("第一步（计划）", 15500), ("第二步（抽取）", 36000)):
        route = report["routes"][name]
        assert route["limit"] == limit and route["bytes"] <= limit and route["pass"]
    for name, limit in (("技能入口", 1100), ("计划步骤", 1500), ("优化步骤", 900), ("共同必读", 9600)):
        assert report["limits"][name]["limit"] == limit
        assert report["limits"][name]["pass"]
    route = report["routes"]["第二步（抽取）"]
    components = route["components"]
    assert {"工作包", "带原行号材料", "前轮计划", "表结构", "原则", "技能入口"} <= components.keys()
    assert {f"写法包/{name}" for name in ("guide.md", "values.json", "01.json", "02.json", "03.json", "04.json", "05.json")} <= components.keys()
    assert route["bytes"] == sum(c["bytes"] for c in components.values())
    assert route["estimated_rounds"]["normal"] == [9, 11]
    assert route["estimated_rounds"]["two_repairs"] == [13, 15]
