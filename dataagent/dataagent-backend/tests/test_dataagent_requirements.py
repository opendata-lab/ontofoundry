from __future__ import annotations

from pathlib import Path


REQUIREMENTS = Path(__file__).resolve().parents[1] / "requirements.txt"


def test_dataagent_runtime_preinstalls_pytest_for_skill_validation():
    requirements = REQUIREMENTS.read_text(encoding="utf-8").splitlines()

    assert any(line.strip().startswith("pytest") for line in requirements)


def test_dataagent_runtime_does_not_install_claude_agent_sdk():
    requirements = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    assert not any(line.strip().startswith("claude-agent-sdk") for line in requirements)
