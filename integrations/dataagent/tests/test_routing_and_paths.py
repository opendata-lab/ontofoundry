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
    assert "不写提案" in discovery and "不写提案" in plan
    # Named things are instances shown as examples, never their own types or confirmations.
    assert "具名的具体事物" in plan and "examples" in plan and "不逐个请用户确认" in plan
    assert "不定标识、对应表、关系、属性" in plan and "第 3 轮前写完" in plan
    assert "确认前不写定义或实例提案" in extraction
    assert "确认范围" in agent


def test_protocol_templates_show_concepts_with_examples():
    entities = json.loads((SKILL / "references/examples/protocol/entities.json").read_bytes())
    assert any(item.get("examples") for item in entities["items"])
    question = json.loads((SKILL / "references/examples/protocol/needs-input-entities.json").read_bytes())["questions"][0]
    assert "不需逐个确认" in question


def test_init_prints_this_runs_paths_and_commands(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads/fictional.md").write_text("澄页图书馆\n")
    pack = write_json(tmp_path / "uploads/pack.json", {
        "result_file": "output/result.json", "needs_input_file": "output/needs.json",
        "context_file": "uploads/context.json", "schema_file": "uploads/schema.json",
        "tables_file": "uploads/tables.json", "materials": [{"id": "m", "path": "uploads/fictional.md", "lines": 1}],
    })
    assert invoke(monkeypatch, init_workflow, "--work-pack", "uploads/pack.json") == 0
    out = capsys.readouterr().out
    for text in ("uploads/fictional.md", "output/result.json", "output/needs.json", "uploads/tables.json",
                 "check_part.py --work-pack uploads/pack.json 01",
                 "prepare_result.py --work-pack uploads/pack.json modeling/parts/", "modeling/tmp/", "/tmp",
                 "references/examples/protocol/entities.json", "references/examples/protocol/needs-input-entities.json",
                 "references/examples/protocol/issues.json"):
        assert text in out, text
    assert (tmp_path / "modeling/tmp").is_dir() and (tmp_path / "output").is_dir()
    assert pack.is_file()


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


def test_init_prints_table_reads_that_each_fit_one_read(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "uploads").mkdir()
    tables = write_json(tmp_path / "uploads/tables.json", fictional_tables(9))
    write_json(tmp_path / "uploads/pack.json", {"tables_file": "uploads/tables.json", "result_file": "output/r.json"})
    assert invoke(monkeypatch, init_workflow, "--work-pack", "uploads/pack.json") == 0
    commands = [line.split("--tables ")[1] for line in capsys.readouterr().out.splitlines() if "--tables " in line]
    assert len(commands) > 1
    assert [k for c in commands for k in c.split(",")] == [f"t{n}" for n in range(1, 10)]
    for keys in commands:
        assert len(read_input.render_tables(tables.read_text(), [keys]).encode()) <= read_input.LIMIT


def test_table_keys_accept_commas_or_spaces(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path / "tables.json", fictional_tables(3, columns=2))
    assert invoke(monkeypatch, read_input, "tables.json", "--tables", "t1", "t2,t3") == 0
    out = capsys.readouterr().out
    assert all(f"## t{n} " in out for n in (1, 2, 3))


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


def test_a_table_too_wide_for_one_read_is_split_by_column_ranges(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    tables = write_json(tmp_path / "tables.json", fictional_tables(1, columns=200))
    text = tables.read_text()
    specs = [spec for batch in read_input.table_batches(text) for spec in batch]
    assert len(specs) > 1 and all(spec.startswith("t1:") for spec in specs)
    covered = [n for spec in specs for n in range(int(spec[3:].split("-")[0]), int(spec.split("-")[1]) + 1)]
    assert covered == list(range(1, 201))
    for spec in specs:
        assert invoke(monkeypatch, read_input, "tables.json", "--tables", spec) == 0
        assert len(capsys.readouterr().out.encode()) <= read_input.LIMIT + 1


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


def test_errors_say_why_what_happened_and_what_to_run(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    material = tmp_path / "notes.md"
    material.write_text("\n".join("澄页图书馆的借阅规则说明" * 30 for _ in range(40)))
    # Too large: actual size, limit, nothing changed, and the exact range that fits.
    assert invoke(monkeypatch, read_input, "notes.md") == 1
    out = capsys.readouterr().out
    assert out.startswith("错误 [OUTPUT_TOO_LARGE]：输出 ") and "超过单次 8000 字节上限" in out and "notes.md 未改动" in out
    step = out.split("下一步：", 1)[1].split("，", 1)[0]
    args = shlex.split(step)[2:]
    assert invoke(monkeypatch, read_input, *args) == 0
    capsys.readouterr()
    # Bad range: the file's real length and a corrected command.
    assert invoke(monkeypatch, read_input, "notes.md", "--start", "50", "--end", "60") == 1
    out = capsys.readouterr().out
    assert "错误 [INVALID_ARGUMENT]：行范围 50–60 无效，notes.md 共 40 行" in out and "--end 40" in out
    # Broken JSON: line and column.
    (tmp_path / "bad.json").write_text('{"a": 1,\n "b": }')
    assert invoke(monkeypatch, read_input, "bad.json", "--pointer", "/a") == 1
    assert "错误 [JSON_INVALID]：bad.json 第 2 行" in capsys.readouterr().out
    # Missing pointer: what does exist there.
    (tmp_path / "ok.json").write_text('{"items": [1, 2, 3]}')
    assert invoke(monkeypatch, read_input, "ok.json", "--pointer", "/items/7") == 1
    assert "3 项的数组，有效下标 0–2" in capsys.readouterr().out


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


def test_reads_that_cannot_shrink_by_lines_or_ranges_still_get_a_way_out(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    write_json(tmp_path / "tables.json", fictional_tables(1, columns=400))
    # An explicit range that is still too wide is split further, never repeated.
    assert invoke(monkeypatch, read_input, "tables.json", "--tables", "t1:1-300") == 1
    out = capsys.readouterr().out
    specs = [c.split("--tables ")[1].split("；")[0].split("，")[0].strip() for c in out.split("下一步：", 1)[1].split("；") if "--tables" in c]
    assert len(specs) > 1 and "t1:1-300" not in specs
    assert specs[0].startswith("t1:1-") and specs[-1].endswith("-300")
    for spec in specs:
        assert invoke(monkeypatch, read_input, "tables.json", "--tables", spec) == 0
        capsys.readouterr()
    # One line longer than a read: cut by characters, not the same line again.
    (tmp_path / "one.md").write_text("澄页" * 4000)
    assert invoke(monkeypatch, read_input, "one.md") == 1
    out = capsys.readouterr().out
    assert "单行就有" in out and "cut -c 1-2500" in out
    # A broken JSON's suggested lines stay inside the file.
    (tmp_path / "bad.json").write_text('{"a":\n}')
    assert invoke(monkeypatch, read_input, "bad.json", "--pointer", "/a") == 1
    assert "--end 2" in capsys.readouterr().out


def test_facts_method_belongs_to_entity_extraction_on_both_routes():
    discovery = (SKILLS / "ontology-discovery/references/steps/extract.md").read_text()
    facts = (SKILLS / "entity-extraction/references/steps/facts.md").read_text()
    assert "entity-extraction/references/extract-facts.md" in discovery
    assert "实例抽取技能 entity-extraction" in facts
    assert "不在 ontology-discovery" in discovery and "不在 ontology-discovery" in facts
