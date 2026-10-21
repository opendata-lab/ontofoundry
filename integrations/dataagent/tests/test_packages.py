"""Standalone distribution and generated-contract compatibility, without services."""

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from zipfile import ZipFile

import pytest
from jsonschema import Draft202012Validator, FormatChecker

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from build_packages import SKILLS, build
from generate_output_schemas import INSTANCE_SOURCE, SOURCE, TARGETS, generate
from test_workflow import SCHEMA, pinned


@pytest.fixture(scope="module")
def packages(tmp_path_factory):
    destination = tmp_path_factory.mktemp("distribution")
    build(destination)
    return destination


def run(script, cwd, *args):
    # No repository PYTHONPATH: all script imports and templates must be in-package.
    env = {**os.environ, "PYTHONPATH": "", "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run([sys.executable, str(script), *map(str, args)], cwd=cwd, env=env, capture_output=True)
    assert result.returncode == 0, (result.stdout.decode(), result.stderr.decode())
    return result.stdout


@pytest.mark.parametrize("name", SKILLS)
def test_each_archive_runs_in_isolation(name, packages, tmp_path):
    with ZipFile(packages / f"{name}.zip") as archive:
        assert all(path.startswith(name + "/") for path in archive.namelist())
        assert not any("/tests/" in path or "offline_budget.py" in path or "__pycache__" in path for path in archive.namelist())
        archive.extractall(tmp_path)
    skill = tmp_path / name
    assert not skill.is_symlink()
    for file in (BASE / "shared").rglob("*"):
        if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
            assert (skill / file.relative_to(BASE / "shared")).read_bytes() == file.read_bytes()
    # All installed documentation links must resolve inside the installed package.
    for document in [skill / "SKILL.md", *(skill / "references").rglob("*.md")]:
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text()):
            if "://" not in target:
                path = (document.parent / target.split("#")[0]).resolve()
                assert path.is_relative_to(skill) and path.exists(), (document, target)
    scripts = skill / "scripts"
    parts = tmp_path / "parts"
    parts.mkdir()
    for part in ("01", "02", "03", "04", "05"):
        output = run(scripts / "show_example.py", tmp_path, "--part", part)
        assert len(output) <= 8192 and isinstance(json.loads(output), list)
        (parts / f"{part}.json").write_bytes(output)
    # A real complete fixture, not --help or empty fragments; the platform schema
    # is supplied as run input and never fetched from the repository by the CLI.
    context = pinned(BASE / "shared/references/examples/create-object_type.json")
    (tmp_path / "context.json").write_text(json.dumps(context))
    (tmp_path / "schema.json").write_text(json.dumps(SCHEMA))
    run(scripts / "init_workflow.py", tmp_path, "--work-pack", _pack(tmp_path))
    run(scripts / "read_input.py", tmp_path, "context.json", "--start", "1", "--end", "1")
    run(scripts / "check_part.py", tmp_path, "--context", "context.json", "--schema", "schema.json", *sorted(parts.glob("*.json")))
    run(scripts / "prepare_result.py", tmp_path, "--context", "context.json", "--schema", "schema.json", "--output", "result.json", "parts")
    batch = json.loads((tmp_path / "result.json").read_bytes())
    assert len(batch["items"]) > 10
    assert batch["workspace_id"] == context["run"]["workspace_id"]
    run(scripts / "check_result.py", tmp_path, "--context", "context.json", "--schema", "schema.json", "result.json")

    # Exercise baseline reads and mixed instance/definition edits in every ZIP.
    context = pinned(BASE / "shared/references/examples/instance-baseline.json")
    (tmp_path / "context.json").write_text(json.dumps(context))
    output = run(scripts / "show_example.py", tmp_path, "material_object", "--operation", "update", "--with-deps")
    assert json.loads(output)[0]["target_kind"] == "material_object"
    entries = context["instance_baseline"]["items"]
    selected = json.loads(run(scripts / "show_element.py", tmp_path, "--work-pack", "work-pack.json", *[f'{e["target_kind"]}:{e["target_id"]}' for e in entries]))
    assert [e["hash"] for e in selected["elements"]] == [e["hash"] for e in entries]
    edits = json.loads((skill / "references/examples/instance-baseline.json").read_bytes())
    # Omitted guards must also be filled by the isolated script.
    for item in edits:
        item.pop("before", None)
        item.pop("expected_target_hash", None)
    (tmp_path / "edits.json").write_text(json.dumps(edits))
    run(scripts / "check_part.py", tmp_path, "--work-pack", "work-pack.json", "edits.json")
    run(scripts / "prepare_result.py", tmp_path, "--context", "context.json", "--schema", "schema.json", "--output", "mixed.json", "edits.json")
    run(scripts / "check_result.py", tmp_path, "--context", "context.json", "--schema", "schema.json", "mixed.json")
    mixed = json.loads((tmp_path / "mixed.json").read_bytes())
    assert {i["target_kind"] for i in mixed["items"]} == {"property", "material_object", "material_link"}
    for item in mixed["items"]:
        if item["target_kind"] in {"material_object", "material_link"}:
            entry = next(e for e in entries if e["target_id"] == item["target_id"])
            assert item["before"] == entry["element"]
            assert item["expected_target_hash"] == entry["hash"]


def _pack(tmp_path):
    path = tmp_path / "work-pack.json"
    path.write_text(json.dumps({"context_file": "context.json", "schema_file": "schema.json"}))
    return path


def test_extraction_schemas_are_generated_and_preserve_platform_contract(tmp_path):
    generate(SOURCE, tmp_path)
    source = json.loads(SOURCE.read_bytes())
    for name, targets in TARGETS.items():
        generated = tmp_path / name / "output-schema.json"
        assert generated.read_bytes() == (BASE / "skills" / name / "output-schema.json").read_bytes()
        schema = json.loads(generated.read_bytes())
        Draft202012Validator.check_schema(schema)
        assert {k: v for k, v in schema.items() if k != "$defs"} == {k: v for k, v in source.items() if k != "$defs"}
        item = schema["$defs"]["item"]
        assert set(item["properties"]["target_kind"]["enum"]) == targets
        assert {b["properties"]["target_kind"]["const"] for b in item["oneOf"]} == targets
        for definition, value in schema["$defs"].items():
            if definition != "item":
                assert value == source["$defs"][definition]
        # Every platform-valid example remains valid exactly for its target subset.
        for example in (BASE / "shared/references/examples").glob("*.json"):
            items = json.loads(example.read_bytes())
            if not isinstance(items, list):
                continue
            for raw in items:
                raw = {"before": None, **raw}
                if not Draft202012Validator({"$ref": "#/$defs/item", "$defs": source["$defs"]}).is_valid(raw):
                    continue
                validator = Draft202012Validator({"$ref": "#/$defs/item", "$defs": schema["$defs"]})
                assert validator.is_valid(raw) == (raw["target_kind"] in targets), (name, example, raw)
    # A changed contract must flow through the generator rather than a copied fixture.
    source["properties"]["run_token"]["maxLength"] = 97
    modified = tmp_path / "modified.json"
    modified.write_text(json.dumps(source))
    generate(modified, tmp_path / "changed")
    for name in TARGETS:
        schema = json.loads((tmp_path / "changed" / name / "output-schema.json").read_bytes())
        assert schema["properties"]["run_token"]["maxLength"] == 97


def test_schema_generation_rejects_instance_contract_drift(tmp_path):
    instances = json.loads(INSTANCE_SOURCE.read_bytes())
    instances["$defs"]["MaterialObject"]["properties"]["values"]["maxProperties"] = 17
    path = tmp_path / "instances.json"
    path.write_text(json.dumps(instances))
    with pytest.raises(ValueError, match="Instance/proposal contracts differ: MaterialObject"):
        generate(SOURCE, tmp_path / "output", instance_source=path)
    assert not (tmp_path / "output").exists()


def grounding():
    uid = "22222222-2222-4222-8222-222222222222"
    return {
        "workspace_id": uid, "version_id": uid, "question": "星河电子近三个月的采购金额",
        "metrics": [{"id": uid, "display_name": "采购金额"}],
        "object_types": [{"id": uid, "display_name": "供应商"}],
        "entities": [{"mention": "星河电子", "object_type_id": uid, "status": "MATCHED", "entity_ref": uid, "display": "星河电子有限公司", "match": "name_contains"}],
        "filters": [{"property_id": uid, "operator": "eq", "value_from": "entities[0]"}],
        "time_range": {"text": "近三个月", "field": {"dataset_id": uid, "column": "order_date"}},
        "unresolved": [], "clarification": None,
    }


def test_grounding_ids_and_ambiguous_clarification():
    schema = json.loads((BASE / "skills/semantic-grounding/output-schema.json").read_bytes())
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    result = grounding()
    assert validator.is_valid(result)
    for path, field in [("metrics", "id"), ("object_types", "id"), ("entities", "object_type_id"), ("filters", "property_id")]:
        invalid = deepcopy(result)
        del invalid[path][0][field]
        assert not validator.is_valid(invalid)
    result["entities"][0].update(status="AMBIGUOUS", entity_ref=None, display=None, match=None)
    for question in (None, ""):
        result["clarification"] = question
        assert not validator.is_valid(result)
    result["clarification"] = "是星河电子有限公司，还是星河电子终端有限公司？"
    assert validator.is_valid(result)
    result["filters"][0]["value"] = "重复条件"
    assert not validator.is_valid(result)


def test_plugin_install_only_copies_skills_and_reports_admin_work(packages, tmp_path):
    with ZipFile(packages / "ontofoundry-dataagent-plugin.zip") as archive:
        archive.extractall(tmp_path)
    root = tmp_path / "ontofoundry-dataagent"
    manifest = json.loads((root / "plugin.json").read_bytes())
    assert [entry["name"] for entry in manifest["skills"]] == list(SKILLS)
    assert manifest["minimum_platform_version"]
    assert manifest["mcp_services"][0]["tools"] == ["search_ontology", "get_ontology", "search_objects", "get_object", "resolve_entity"]
    target = tmp_path / "installed with spaces"
    env = {**os.environ, "SKILLS_ROOT_DIR": str(target)}
    command = ["sh", str(root / "install.sh")]
    installed = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True)
    assert installed.returncode == 0, installed.stderr.decode()
    assert {p.name for p in target.iterdir()} == set(SKILLS)
    assert "管理员后续步骤" in installed.stdout.decode()
    for name in SKILLS:
        assert (target / name / "scripts/check_result.py").is_file()
    # Validate the entire source before copying anything into a fresh destination.
    (root / "skills/entity-extraction/scripts/check_result.py").unlink()
    env["SKILLS_ROOT_DIR"] = str(tmp_path / "invalid-install")
    failed = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True)
    assert failed.returncode != 0 and not Path(env["SKILLS_ROOT_DIR"]).exists()


def test_two_extraction_skills_merge_into_one_result(packages, tmp_path):
    for name in ("ontology-discovery", "entity-extraction"):
        with ZipFile(packages / f"{name}.zip") as archive:
            archive.extractall(tmp_path)
    discovery = tmp_path / "ontology-discovery"
    extraction = tmp_path / "entity-extraction"
    items = json.loads((discovery / "references/examples/facts.json").read_bytes())
    context = pinned(BASE / "shared/references/examples/facts.json")
    (tmp_path / "context.json").write_text(json.dumps(context))
    (tmp_path / "schema.json").write_text(json.dumps(SCHEMA))
    parts = tmp_path / "parts"
    parts.mkdir()
    for name, skill in (("01-definitions", discovery), ("05-facts", extraction)):
        schema = json.loads((skill / "output-schema.json").read_bytes())
        kinds = set(schema["$defs"]["item"]["properties"]["target_kind"]["enum"])
        fragment = [item for item in items if item["target_kind"] in kinds]
        assert fragment
        (parts / f"{name}.json").write_text(json.dumps(fragment))
        run(skill / "scripts/check_part.py", tmp_path, "--schema", skill / "output-schema.json", "--context", "context.json", parts / f"{name}.json")
    run(discovery / "scripts/prepare_result.py", tmp_path, "--schema", "schema.json", "--context", "context.json", "--output", "result.json", "parts")
    result = json.loads((tmp_path / "result.json").read_bytes())
    assert len(result["items"]) == len(items)
    assert {i["target_kind"] for i in result["items"]} == {"object_type", "property", "link_type", "material_object", "material_link"}
