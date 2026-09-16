from pathlib import Path
from types import SimpleNamespace

from core.runtime_support import (
    build_runtime_env,
    build_workspace_allowed_roots,
    resolve_agent_skill_runtime,
    resolve_max_turns,
)


def test_workspace_roots_include_workspace_skills_and_scratch(tmp_path: Path):
    workspace = tmp_path / "workspace"
    skill = tmp_path / "skill"
    scratch = tmp_path / "scratch"
    roots = build_workspace_allowed_roots(
        workspace,
        {"enabled_roots": {"modeling": str(skill)}},
        [str(scratch)],
    )
    assert roots == [workspace.resolve(), skill.resolve(), scratch.resolve()]


def test_runtime_env_contains_platform_contract(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("PATH", "/usr/bin")
    cfg = SimpleNamespace(
        query_result_limit=100,
        dataagent_mcp_tool_timeout_seconds=180,
        agent_interactive_sql_read_timeout_seconds=300,
    )
    params = SimpleNamespace(
        question="建立本体",
        sql_read_timeout_seconds=60,
        execution_mode="interactive",
        agent_snapshot={"data_scope": {}, "env_vars": {"SAFE_FLAG": "1"}},
    )
    env = build_runtime_env(
        cfg,
        {"ANTHROPIC_API_KEY": "secret"},
        params,
        {
            "primary_root": str(tmp_path),
            "enabled_folders": ["modeling"],
            "enabled_roots": {"modeling": str(tmp_path)},
        },
    )
    assert env["DATAAGENT_SQL_READ_TIMEOUT_SECONDS"] == "60"
    assert env["DATAAGENT_ENABLED_SKILLS"] == "modeling"
    assert env["SAFE_FLAG"] == "1"


def test_agent_profile_with_no_skills_does_not_enable_global_fallback(tmp_path: Path):
    resolved = resolve_agent_skill_runtime(
        {"skill_folders": []},
        {"enabled_folders": ["global"], "enabled_roots": {"global": str(tmp_path)}},
    )
    assert resolved["enabled_folders"] == []
    assert resolved["enabled_roots"] == {}


def test_max_turns_prefers_agent_then_execution_tier():
    cfg = SimpleNamespace(agent_background_max_turns=40, agent_interactive_max_turns=24)
    assert resolve_max_turns(cfg, "auto", 7) == 7
    assert resolve_max_turns(cfg, "background") == 40
    assert resolve_max_turns(cfg, "interactive") == 24
