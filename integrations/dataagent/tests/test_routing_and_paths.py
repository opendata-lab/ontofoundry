"""Routing entries, mandatory scope confirmation and run-path helpers, offline."""

import importlib
import json
import re
import shlex
import subprocess
import sys

from test_stepwise_workflow import invoke, mapping_example, write_json
from test_workflow import BASE, SCHEMA_PATH, SKILL, prepare

init_workflow = importlib.import_module("init_workflow")
read_input = importlib.import_module("read_input")
SKILLS = BASE / "skills"
LINK = re.compile(r"\]\(([^)]+\.md)\)")


def test_entries_only_route_and_every_linked_step_exists():
    for name in ("ontology-discovery", "entity-extraction", "semantic-grounding"):
        entry = SKILLS / name / "SKILL.md"
        assert len(entry.read_bytes()) <= 1100
        links = LINK.findall(entry.read_text())
        assert links and all(link.startswith("references/steps/") for link in links)
        for link in links:
            # A step lives in the skill or in shared (copied into every package).
            assert (SKILLS / name / link).is_file() or (SKILL / link).is_file(), link


def test_step_files_link_to_files_that_exist_after_packaging():
    for step in [*SKILLS.glob("*/references/steps/*.md"), *SKILL.glob("references/steps/*.md")]:
        skill_dir = step.parents[2] if step.parents[2].parent == SKILLS else None
        for link in LINK.findall(step.read_text()):
            candidates = [(step.parent / link).resolve()]
            # Shared files are merged into each skill's references/ on packaging.
            candidates.append((SKILL / "references/steps" / link).resolve())
            if skill_dir:
                candidates.append((SKILL / "references" / (step.parent / link).resolve().relative_to(skill_dir / "references")).resolve())
            for name in ("ontology-discovery", "entity-extraction"):
                candidates.append((SKILLS / name / "references/steps" / link).resolve())
            assert any(c.is_file() for c in candidates), f"{step.name} → {link}"


def test_scope_is_confirmed_before_any_proposal_on_every_path():
    discovery = (SKILLS / "ontology-discovery/SKILL.md").read_text()
    plan = (SKILLS / "ontology-discovery/references/steps/plan.md").read_text()
    extraction = (SKILLS / "entity-extraction/SKILL.md").read_text()
    agent = (BASE / "agents/agent_ontofoundry.md").read_text().split("系统提示词：", 1)[1]
    # The scope is approved inside the run through the plan card.
    assert "获批准" in discovery and "ExitPlanMode" in plan and "AskUserQuestion" in plan
    # Named things are instances shown as examples, never their own types.
    assert "具名的具体事物" in plan and "例子" in plan
    assert "不定关系、属性" in plan and "第 3 轮前定稿" in plan
    assert "获批准前不写定义或实例" in extraction
    assert "新概念先交计划，批准后写提案" in agent


def test_protocol_templates_show_concepts_with_examples():
    entities = json.loads((SKILL / "references/examples/protocol/entities.json").read_bytes())
    assert any(item.get("examples") for item in entities["items"])


def test_init_prints_this_runs_paths_and_commands(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads/fictional.md").write_text("澄页图书馆\n")
    pack = write_json(tmp_path / "uploads/pack.json", {
        "result_file": "output/result.json",
        "context_file": "uploads/context.json", "schema_file": "uploads/schema.json",
        "tables_file": "uploads/tables.json", "materials": [{"id": "m", "path": "uploads/fictional.md", "lines": 1}],
    })
    assert invoke(monkeypatch, init_workflow, "--work-pack", "uploads/pack.json") == 0
    out = capsys.readouterr().out
    for text in ("uploads/fictional.md", "output/result.json", "uploads/tables.json",
                 "check_part.py --work-pack uploads/pack.json 01",
                 "prepare_result.py --work-pack uploads/pack.json modeling/parts/", "modeling/tmp/", "/tmp",
                 "references/examples/protocol/entities.json",
                 "references/examples/protocol/issues.json"):
        assert text in out, text
    assert (tmp_path / "modeling/tmp").is_dir() and (tmp_path / "output").is_dir()
    assert pack.is_file()


def test_init_works_from_another_folder_and_lists_inputs(tmp_path, monkeypatch, capsys):
    workspace, skill = tmp_path / "workspace", tmp_path / "skill"
    (workspace / "uploads").mkdir(parents=True)
    skill.mkdir()
    write_json(workspace / "uploads/pack.json", {
        "result_file": "output/result.json",
        "materials": [{"id": "m-1", "path": "uploads/fictional.md", "lines": 21}],
        "tables": [{"key": "t1", "table": "fictional.orders", "comment": "订单"}],
    })
    monkeypatch.chdir(skill)  # e.g. the read-only skill folder
    assert invoke(monkeypatch, init_workflow, "--work-pack", str(workspace / "uploads/pack.json")) == 0
    out = capsys.readouterr().out
    assert (workspace / "modeling/parts").is_dir() and not (skill / "modeling").exists()
    for text in ("uploads/fictional.md（id m-1，21 行）", "表 t1：fictional.orders 订单"):
        assert text in out, text
    assert "MCP 访问文件只供 prepare_result 使用" in out


def test_prepare_takes_the_work_pack_short_names_and_default_parts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ctx, items = mapping_example()
    write_json(tmp_path / "context.json", ctx)
    pack = write_json(tmp_path / "pack.json", {
        "context_file": "context.json", "schema_file": str(SCHEMA_PATH), "result_file": "output/result.json",
    })
    parts = tmp_path / "modeling/parts"
    parts.mkdir(parents=True)
    write_json(parts / "01-types.json", items[:4])
    write_json(parts / "02-datasets.json", items[4:5])
    write_json(parts / "03-mappings.json", items[5:])
    assert invoke(monkeypatch, prepare, "--work-pack", pack) == 0
    default = (tmp_path / "output/result.json").read_bytes()
    assert invoke(monkeypatch, prepare, "--work-pack", pack, "01", "02", "03-mappings") == 0
    assert (tmp_path / "output/result.json").read_bytes() == default
    assert json.loads(default)["items"] == items


def test_wrong_arguments_and_stdin_print_the_correct_commands(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert invoke(monkeypatch, prepare, "--work-pack", "pack.json", "-") == 2
    assert "先写到 modeling/parts/" in capsys.readouterr().out
    script = SKILL / "scripts/check_part.py"
    result = subprocess.run([sys.executable, script, "--work-pack", "uploads/pack.json", "--bogus", "01"],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 2
    assert "参数错误" in result.stdout and "prepare_result.py --work-pack uploads/pack.json modeling/parts/" in result.stdout


def test_missing_material_lists_what_exists(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads/real.md").write_text("x\n")
    assert invoke(monkeypatch, read_input, "uploads/missing.md") == 1
    out = capsys.readouterr().out
    assert "错误 [FILE_NOT_FOUND]：工作区文件 uploads/missing.md 不存在" in out and "real.md" in out


def fictional_tables(count, columns=40):
    def table(n):
        return {"key": f"t{n}", "table": f"ledger.shelf_{n}", "kind": "table", "connection": "澄页只读库",
                "dialect": "mysql", "comment": "书架", "connection_id": "c1", "schema_name": "ledger",
                "table_name": f"shelf_{n}", "primary_key": ["shelf_no"], "foreign_keys": [],
                "columns": [{"name": f"col_{i}", "type": "varchar(64)", "nullable": True, "comment": "书架说明字段"}
                            for i in range(columns)]}
    return {"tables": [table(n) for n in range(1, count + 1)]}


def test_init_prints_search_instead_of_reading_all_tables(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "uploads").mkdir()
    write_json(tmp_path / "uploads/tables.json", fictional_tables(90))
    write_json(tmp_path / "uploads/pack.json", {"tables_file": "uploads/tables.json", "result_file": "output/r.json"})
    assert invoke(monkeypatch, init_workflow, "--work-pack", "uploads/pack.json") == 0
    out = capsys.readouterr().out
    assert "--search-tables" in out and "--tables " not in out and "--describe-tables" not in out


def test_table_keys_accept_commas_or_spaces(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path / "tables.json", fictional_tables(3, columns=2))
    assert invoke(monkeypatch, read_input, "tables.json", "--tables", "t1", "t2,t3") == 0
    out = capsys.readouterr().out
    assert all(f"[ref: t{n}]" in out for n in (1, 2, 3))


def test_check_part_reports_refs_another_fragment_already_defines(tmp_path, monkeypatch, capsys):
    check_part = importlib.import_module("check_part")
    monkeypatch.chdir(tmp_path)
    ctx, items = mapping_example()
    write_json(tmp_path / "context.json", ctx)
    pack = write_json(tmp_path / "pack.json", {"context_file": "context.json", "schema_file": str(SCHEMA_PATH)})
    parts = tmp_path / "modeling/parts"
    parts.mkdir(parents=True)
    write_json(parts / "01-types.json", items[:4])
    clash = {**items[4], "client_ref": items[0]["client_ref"]}
    write_json(parts / "03-datasets.json", [clash])
    assert invoke(monkeypatch, check_part, "--work-pack", pack, "03") == 1
    assert f"client_ref {items[0]['client_ref']} 与 01-types.json 重复" in capsys.readouterr().out


def test_a_table_too_wide_for_one_read_has_exact_continuation(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path / "tables.json", fictional_tables(1, columns=200))
    args, seen = ["tables.json", "--describe-tables", "t1"], []
    while args:
        assert invoke(monkeypatch, read_input, *args) == 0
        out = capsys.readouterr().out
        assert len(out.encode()) <= read_input.LIMIT
        seen += re.findall(r"\[ref: t1\.(col_\d+)\]", out)
        commands = [line.split("续读：", 1)[1] for line in out.splitlines() if "续读：" in line]
        args = shlex.split(commands[0])[2:] if commands else None
    assert seen == [f"col_{n}" for n in range(200)]


def test_check_part_counts_generated_refs_and_ignores_replacements_elsewhere(tmp_path, monkeypatch, capsys):
    check_part = importlib.import_module("check_part")
    monkeypatch.chdir(tmp_path)
    ctx, items = mapping_example()
    write_json(tmp_path / "context.json", ctx)
    pack = write_json(tmp_path / "pack.json", {"context_file": "context.json", "schema_file": str(SCHEMA_PATH)})
    parts = tmp_path / "modeling/parts"
    parts.mkdir(parents=True)
    first = {k: v for k, v in items[0].items() if k != "client_ref"}
    write_json(parts / "01-types.json", [first])
    write_json(parts / "02-other.json", [{**items[4], "client_ref": f"{first['target_kind']}-1"}])
    assert invoke(monkeypatch, check_part, "--work-pack", pack, "02") == 1
    assert f"client_ref {first['target_kind']}-1 与 01-types.json 重复" in capsys.readouterr().out
    # A corrected copy outside modeling/parts/ is merged by explicit choice, not compared.
    (tmp_path / "modeling/tmp").mkdir()
    write_json(tmp_path / "modeling/tmp/02-fixed.json", [{**items[4], "client_ref": f"{first['target_kind']}-1"}])
    invoke(monkeypatch, check_part, "--work-pack", pack, "modeling/tmp/02-fixed.json")
    assert "重复" not in capsys.readouterr().out


def test_show_example_points_field_names_at_their_kind(capsys, monkeypatch):
    show_example = importlib.import_module("show_example")
    assert invoke(monkeypatch, show_example, "data_join") == 1
    out = capsys.readouterr().out
    assert "属于 link_type" in out and "--variant mapping_table" in out


def test_errors_say_why_and_name_valid_pointer_paths(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "notes.md").write_text("首行\n末行")
    assert invoke(monkeypatch, read_input, "notes.md", "--start", "50") == 1
    assert "共 2 行" in capsys.readouterr().out
    (tmp_path / "bad.json").write_text('{"a": 1,\n "b": }')
    assert invoke(monkeypatch, read_input, "bad.json", "--pointer", "/a") == 1
    assert "错误 [JSON_INVALID]：bad.json 第 2 行" in capsys.readouterr().out
    (tmp_path / "ok.json").write_text('{"items": [1, 2, 3]}')
    assert invoke(monkeypatch, read_input, "ok.json", "--pointer", "/items/7") == 1
    assert "--outline" in capsys.readouterr().out


def test_commands_name_scripts_without_climbing_out_of_the_workspace(tmp_path, monkeypatch):
    runpaths = importlib.import_module("runpaths")
    monkeypatch.chdir(tmp_path)
    # The skill lives outside this workspace: its own path, never "../".
    printed = runpaths.command("check_part.py", "--work-pack", "uploads/pack.json", "01")
    assert ".." not in printed and str(runpaths.SKILL_DIR.resolve()) in printed
    # A placeholder left in is quoted, so Bash never reads it as a redirect.
    assert runpaths.command("read_input.py", "<材料路径>").endswith(" '<材料路径>'")
    monkeypatch.setattr(sys, "argv", ["check_result.py", "--work-pack", "uploads/pack.json"])
    assert runpaths.command("show_element.py", "--work-pack", "<工作包>", "x").endswith(" --work-pack uploads/pack.json x")


def test_long_lines_are_bounded_and_broken_json_suggests_valid_source_range(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "one.md").write_text("澄页" * 4000)
    assert invoke(monkeypatch, read_input, "one.md") == 0
    out = capsys.readouterr().out
    assert "超长内容已截断" in out and len(out.encode()) <= read_input.LIMIT
    (tmp_path / "bad.json").write_text('{"a":\n}')
    assert invoke(monkeypatch, read_input, "bad.json", "--pointer", "/a") == 1
    assert "--end 2" in capsys.readouterr().out


def test_facts_method_belongs_to_entity_extraction_on_both_routes():
    discovery = (SKILLS / "ontology-discovery/references/steps/extract.md").read_text()
    facts = (SKILLS / "entity-extraction/references/steps/facts.md").read_text()
    assert "entity-extraction/references/extract-facts.md" in discovery
    assert "实例抽取技能 entity-extraction" in facts
    assert "不在 ontology-discovery" in discovery and "不在 ontology-discovery" in facts


def test_a_new_run_moves_the_last_runs_fragments_but_the_same_run_keeps_them(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "uploads").mkdir()
    def run(token):
        write_json(tmp_path / "uploads/pack.json", {"run": {"run_token": token}})
        assert invoke(monkeypatch, init_workflow, "--work-pack", "uploads/pack.json") == 0
        return capsys.readouterr().out
    run("first")
    write_json(tmp_path / "modeling/parts/01-types.json", [{"operation": "create"}])
    # The same run again (repairs happen inside the run): fragments stay.
    assert "PREVIOUS_PARTS_MOVED" not in run("first")
    assert (tmp_path / "modeling/parts/01-types.json").exists()
    # A new request: the last run's fragments move out of the way.
    out = run("second")
    assert "PREVIOUS_PARTS_MOVED" in out and "modeling/previous/first" in out
    assert not list((tmp_path / "modeling/parts").glob("*.json"))
    assert (tmp_path / "modeling/previous/first/parts/01-types.json").exists()


