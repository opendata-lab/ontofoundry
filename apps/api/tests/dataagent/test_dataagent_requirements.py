from __future__ import annotations

from pathlib import Path

from conftest import PACKAGE_ROOT, REPO_ROOT, REPO_DATAAGENT_DIR  # noqa: E402


# 合并之后依赖只有一个声明处：两个包共用的发行清单。
PYPROJECT = REPO_ROOT / "apps" / "api" / "pyproject.toml"


def _declared_dependencies() -> list[str]:
    import tomllib

    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    project = data.get("project", {})
    groups = data.get("dependency-groups", {})
    return [
        str(item)
        for item in list(project.get("dependencies", []))
        + [d for group in groups.values() for d in group]
    ]


def test_dataagent_runtime_preinstalls_pytest_for_skill_validation():
    """Skill 自带 pytest 套件，运行时镜像里必须有 pytest 才能验证它们。"""
    assert any(dep.strip().startswith("pytest") for dep in _declared_dependencies())


def test_dataagent_runtime_does_not_install_claude_agent_sdk():
    """执行引擎是 Pi，不是 Claude Agent SDK；装上它只会掩盖引擎选错。"""
    assert not any(
        dep.strip().startswith("claude-agent-sdk") for dep in _declared_dependencies()
    )
