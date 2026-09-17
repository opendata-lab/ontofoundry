"""Engine-neutral preparation shared by DataAgent and its Pi Cell."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from dataagent_backend.config import (
    get_settings,
    resolve_sql_read_timeout_seconds,
    resolve_workspace_scratch_dirs,
)

from dataagent_backend.core.data_scope import normalize_data_scope
from dataagent_backend.core.mcp_admin_service import resolve_runtime_mcp_servers
from dataagent_backend.core.skill_discovery import (
    resolve_builtin_skill_root_dir,
    resolve_skill_discovery_root_dir,
)

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "data_agent_system_prompt.md"
FILE_BOUNDARY_PATH_KEYS = {
    "Read": ("file_path", "path"),
    "LS": ("path",),
    "Glob": ("path", "pattern"),
    "Grep": ("path", "glob"),
    "Write": ("file_path",),
    "Edit": ("file_path",),
    "MultiEdit": ("file_path",),
    "NotebookEdit": ("notebook_path",),
}
DISCARD_SINK_PATHS: frozenset[Path] = frozenset({Path("/dev/null")})
BASH_OPERATOR_CHARS = frozenset("();<>|&")


def _dedupe_strings(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip()
        if item and item not in seen:
            result.append(item)
            seen.add(item)
    return result


def build_workspace_allowed_roots(
    workspace: str | Path,
    skill_runtime: dict[str, Any] | None,
    scratch_dirs: list[str] | tuple[str, ...] | None = None,
) -> list[Path]:
    roots = [Path(workspace).expanduser().resolve(strict=False)]
    for root in dict((skill_runtime or {}).get("enabled_roots") or {}).values():
        text = str(root or "").strip()
        if text:
            roots.append(Path(text).expanduser().resolve(strict=False))
    for root in scratch_dirs or []:
        text = str(root or "").strip()
        if text:
            roots.append(Path(text).expanduser().resolve(strict=False))
    result: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            result.append(root)
            seen.add(key)
    return result


def build_system_prompt(
    database_hint: str | None,
    skill_runtime: dict[str, Any] | None = None,
    agent_snapshot: dict[str, Any] | None = None,
) -> str:
    enabled_skills = list((skill_runtime or {}).get("enabled_folders") or [])
    enabled_text = "、".join(enabled_skills) if enabled_skills else "未配置"
    lines = [
        SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip(),
        "",
        "# 运行时上下文",
        f"- 已启用 Skills：{enabled_text}。",
    ]
    scratch_dirs = resolve_workspace_scratch_dirs(get_settings())
    if scratch_dirs:
        lines.append(
            f"- 可写临时目录：{'、'.join(scratch_dirs)}。仅用于中间文件；最终交付必须写入工作区 `output/`。"
        )
    else:
        lines.append("- 可写临时目录：无。所有文件读写都必须在当前会话工作区内完成。")
    custom_prompt = str((agent_snapshot or {}).get("system_prompt") or "").strip()
    if custom_prompt:
        lines.extend(["", "# 智能体系统提示词", custom_prompt])
    scopes = normalize_data_scope((agent_snapshot or {}).get("data_scope") or {}).get("allowed_scopes", [])
    lines.extend(["", "# 已授权数据范围"])
    if scopes:
        for item in scopes:
            cluster = "null" if item.get("cluster_id") is None else str(item.get("cluster_id"))
            lines.append(
                f"- cluster_id={cluster}, source_type={item.get('source_type') or ''}, database={item.get('database') or ''}"
            )
    else:
        lines.append("- 无。未配置数据范围时禁止访问任何元数据或查询任何数据。")
    if database_hint:
        lines.append(f"- 用户显式提供的 database hint: {database_hint}")
    return "\n".join(lines)


def resolve_agent_skill_runtime(
    agent_snapshot: dict[str, Any] | None,
    fallback_runtime: dict[str, Any],
) -> dict[str, Any]:
    selected = _dedupe_strings((agent_snapshot or {}).get("skill_folders"))
    if not selected:
        if agent_snapshot:
            return {
                "primary_folder": "",
                "primary_root": "",
                "enabled_folders": [],
                "enabled_roots": {},
            }
        return fallback_runtime
    discovery_root = resolve_skill_discovery_root_dir()
    roots = {folder: str((discovery_root / folder).resolve()) for folder in selected}
    return {
        "primary_folder": selected[0],
        "primary_root": roots[selected[0]],
        "enabled_folders": selected,
        "enabled_roots": roots,
    }


def build_runtime_env(
    cfg: Any,
    provider_env: dict[str, str],
    params: Any | None = None,
    skill_runtime: dict[str, Any] | None = None,
) -> dict[str, str]:
    python_bin = Path(sys.executable).absolute()
    skills_root = Path(
        str((skill_runtime or {}).get("primary_root") or resolve_builtin_skill_root_dir())
    ).resolve()
    enabled_folders = [str(item) for item in ((skill_runtime or {}).get("enabled_folders") or [])]
    enabled_roots = dict((skill_runtime or {}).get("enabled_roots") or {})
    runtime_env = dict(os.environ)
    runtime_env.update(provider_env)
    sql_timeout = int(getattr(params, "sql_read_timeout_seconds", 0) or 0)
    if sql_timeout <= 0:
        sql_timeout = resolve_sql_read_timeout_seconds(cfg, getattr(params, "execution_mode", None))
    runtime_env.update(
        {
            "DATAAGENT_QUERY_LIMIT": str(int(cfg.query_result_limit or 1000)),
            "DATAAGENT_RESULT_PREVIEW_ROWS": str(min(20, int(cfg.query_result_limit or 1000))),
            "DATAAGENT_SQL_READ_TIMEOUT_SECONDS": str(sql_timeout),
            "DATAAGENT_ORIGINAL_QUESTION": str(getattr(params, "question", "") or "").strip(),
            "DATAAGENT_PYTHON_BIN": str(python_bin),
            "DATAAGENT_SKILL_ROOT": str(skills_root),
            "DATAAGENT_ENABLED_SKILLS": ",".join(enabled_folders),
            "DATAAGENT_ENABLED_SKILL_ROOTS": json.dumps(enabled_roots, ensure_ascii=False),
            "DATAAGENT_DATA_SCOPE_JSON": json.dumps(
                normalize_data_scope((getattr(params, "agent_snapshot", None) or {}).get("data_scope") or {}),
                ensure_ascii=False,
                sort_keys=True,
            ),
            "VIRTUAL_ENV": str(python_bin.parent.parent),
            "PATH": f"{python_bin.parent}:{os.getenv('PATH', '')}",
            "TZ": str(os.getenv("TZ") or "Asia/Shanghai"),
            "MCP_TOOL_TIMEOUT": str(
                max(1, int(getattr(cfg, "dataagent_mcp_tool_timeout_seconds", 0) or 180)) * 1000
            ),
        }
    )
    agent_env = (getattr(params, "agent_snapshot", None) or {}).get("env_vars") or {}
    if isinstance(agent_env, dict):
        runtime_env.update({str(key): str(value) for key, value in agent_env.items()})
    return runtime_env


def build_mcp_servers(
    mcp_server_ids: list[str] | tuple[str, ...] | None = None,
) -> dict[str, dict[str, Any]]:
    return resolve_runtime_mcp_servers(mcp_server_ids)


def default_model_for_provider(provider_id: str) -> str:
    if provider_id == "openrouter":
        return "anthropic/claude-sonnet-4.5"
    if provider_id == "anyrouter":
        return "claude-opus-4-6"
    return "claude-sonnet-4-20250514"


def resolve_max_turns(cfg: Any, execution_mode: str | None, agent_max_turns: int | None = None) -> int:
    if int(agent_max_turns or 0) > 0:
        return max(1, int(agent_max_turns or 0))
    mode = str(execution_mode or "").strip().lower()
    if mode in {"background", "auto"}:
        return max(
            1,
            int(getattr(cfg, "agent_background_max_turns", 0) or getattr(cfg, "agent_max_turns", 0) or 40),
        )
    return max(
        1,
        int(getattr(cfg, "agent_interactive_max_turns", 0) or getattr(cfg, "agent_max_turns", 0) or 24),
    )
