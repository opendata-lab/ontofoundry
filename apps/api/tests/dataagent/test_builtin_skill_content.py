from __future__ import annotations

from pathlib import Path

from conftest import PACKAGE_ROOT, REPO_ROOT, REPO_DATAAGENT_DIR  # noqa: E402


SKILLS_ROOT = REPO_DATAAGENT_DIR / ".claude" / "skills"
SYSTEM_PROMPT = PACKAGE_ROOT / "prompts" / "data_agent_system_prompt.md"


def test_md2ossie_is_the_only_bundled_skill():
    bundled = sorted(path.name for path in SKILLS_ROOT.iterdir() if path.is_dir())
    assert bundled == ["md2ossie"]


def test_md2ossie_contains_offline_schema_and_validator():
    root = SKILLS_ROOT / "md2ossie"
    assert (root / "SKILL.md").is_file()
    assert (root / "scripts" / "validate_ossie.py").is_file()
    assert (root / "assets" / "vendor" / "apache-ossie" / "README.md").is_file()


def test_global_prompt_is_platform_neutral_and_workspace_bounded():
    prompt = SYSTEM_PROMPT.read_text(encoding="utf-8")
    for token in ("OntoFoundry", "运行边界", "工作区", "output/", "不伪造工具结果"):
        assert token in prompt
    for token in ("portal MCP", "DATAAGENT_PLATFORM_SKILL_ROOT", "run_sql.py"):
        assert token not in prompt
