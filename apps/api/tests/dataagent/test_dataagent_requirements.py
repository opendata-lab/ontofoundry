from __future__ import annotations

from pathlib import Path

from conftest import PACKAGE_ROOT, REPO_ROOT, REPO_DATAAGENT_DIR  # noqa: E402


REQUIREMENTS = REPO_DATAAGENT_DIR / "dataagent-backend" / "requirements.txt"


def test_dataagent_runtime_preinstalls_pytest_for_skill_validation():
    requirements = REQUIREMENTS.read_text(encoding="utf-8").splitlines()

    assert any(line.strip().startswith("pytest") for line in requirements)


def test_dataagent_runtime_does_not_install_claude_agent_sdk():
    requirements = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    assert not any(line.strip().startswith("claude-agent-sdk") for line in requirements)
