"""External plugin manifests, skill layout, secret references and offline shipping."""

import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "plugins/ontofoundry"
NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def test_plugin_manifests_parse_and_names_match_sources():
    manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
    marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    assert NAME.fullmatch(manifest["name"])
    assert NAME.fullmatch(marketplace["name"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
    assert manifest["name"] == PLUGIN.name
    for item in marketplace["plugins"]:
        assert NAME.fullmatch(item["name"])
        source = ROOT / item["source"]
        assert source.resolve().is_relative_to(ROOT)
        shipped = json.loads((source / ".claude-plugin/plugin.json").read_text())
        assert item["name"] == shipped["name"] == source.name
    assert any(item["name"] == manifest["name"] for item in marketplace["plugins"])


def test_mcp_configuration_has_only_secret_references():
    raw = (PLUGIN / ".mcp.json").read_text()
    config = json.loads(raw)
    manifest = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
    assert "ofpat." not in raw and "ofrun." not in raw
    for server in config["mcpServers"].values():
        authorization = server["headers"]["Authorization"]
        assert re.fullmatch(r"Bearer \$\{(?:user_config\.[a-z_]+|[A-Z_]+)\}", authorization)
        assert server["type"] == "http"
        for reference in re.findall(r"\$\{user_config\.([a-z_]+)\}", authorization):
            assert manifest["userConfig"][reference]["sensitive"] is True


def frontmatter(path):
    text = path.read_text()
    assert text.startswith("---\n")
    _, header, body = text.split("---", 2)
    fields = {}
    for match in re.finditer(r"(?m)^([a-z_]+):\s*([^\n]*)(?:\n((?:[ \t]+[^\n]*\n?)*))?", header):
        key, value, continuation = match.groups()
        if value in {"|", ">", "|-", ">-"}:
            value = " ".join((continuation or "").split())
        fields[key] = value.strip().strip('"\'')
    assert body.strip()
    return fields


def test_skills_are_one_directory_level_and_frontmatter_is_portable():
    skills = PLUGIN / "skills"
    files = list(skills.rglob("SKILL.md"))
    assert files
    assert all(len(path.relative_to(skills).parts) == 2 for path in files)
    for directory in skills.iterdir():
        assert directory.is_dir() and (directory / "SKILL.md").is_file()
    for path in files:
        fields = frontmatter(path)
        assert fields.keys() == {"name", "description"}
        assert fields["name"] == path.parent.name and NAME.fullmatch(fields["name"])
        assert 0 < len(fields["description"]) <= 1024


def test_offline_package_includes_plugin_and_marketplace(tmp_path):
    docker = tmp_path / "fiction-docker"
    docker.write_text('''#!/usr/bin/env python3
import sys
from pathlib import Path
if "-o" in sys.argv:
    Path(sys.argv[sys.argv.index("-o") + 1]).write_bytes(b"fictional offline image")
''')
    docker.chmod(0o755)
    output = tmp_path / "offline"
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/create-offline-package.sh"), str(output)],
        env={**os.environ, "DOCKER": str(docker)}, capture_output=True, text=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    for path in (PLUGIN / ".claude-plugin/plugin.json", PLUGIN / ".mcp.json", PLUGIN / "skills/ontology-grounding/SKILL.md", ROOT / ".claude-plugin/marketplace.json"):
        assert (output / path.relative_to(ROOT)).read_bytes() == path.read_bytes()
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    for relative in ("plugins/ontofoundry/.claude-plugin/plugin.json", "plugins/ontofoundry/.mcp.json", "plugins/ontofoundry/skills/ontology-grounding/SKILL.md", ".claude-plugin/marketplace.json"):
        assert "test -f " + relative in ci
