"""Routing entries, mandatory scope confirmation and run-path helpers, offline."""

import importlib
import json
import re
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
    assert "文件不存在：uploads/missing.md" in out and "real.md" in out
