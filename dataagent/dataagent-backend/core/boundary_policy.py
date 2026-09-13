"""Workspace boundary policy serialization for the Pi data plane.

The boundary inputs live in :mod:`core.runtime_support` and stay the single
source of truth. This module only *serializes* them into a language
neutral spec so a data plane that does not run in this process — currently the
Node Pi Cell — can enforce the same decisions locally instead of round-tripping
every tool call back over stdio.

Nothing here re-states a rule. Every list is exported from the constant or the
pure function that the Python enforcement path already uses, so a change on the
Python side cannot silently leave the serialized spec behind. What keeps the two
*enforcement* implementations aligned is the shared conformance fixture at
``dataagent/contracts/boundary/v1/conformance-cases.json``: both sides run the
same case table, so a divergence fails a test rather than reaching production.

The Pi Cell truncates tool output in process and never offloads it to disk, so
the serialized policy has no external tool-result exception.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.runtime_support import (
    BASH_OPERATOR_CHARS,
    DISCARD_SINK_PATHS,
    FILE_BOUNDARY_PATH_KEYS,
    build_workspace_allowed_roots,
)

POLICY_VERSION = 1


def build_boundary_policy(
    project_cwd: str | Path,
    skill_runtime: dict[str, Any] | None,
    scratch_dirs: list[str] | None,
    runtime_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Serialize the workspace boundary policy for the Pi Cell.

    ``project_cwd``, ``skill_runtime`` and ``scratch_dirs`` are the same inputs
    ``_build_workspace_boundary_hooks`` feeds the Python validation path, so the
    two agree by construction. ``runtime_env`` supplies ``DATAAGENT_PYTHON_BIN``.
    """
    workspace = Path(project_cwd).expanduser().resolve(strict=False)
    allowed_roots = build_workspace_allowed_roots(workspace, skill_runtime, scratch_dirs)

    env = runtime_env or {}
    allowed_executables: list[str] = []
    python_bin = str(env.get("DATAAGENT_PYTHON_BIN") or "").strip()
    if python_bin:
        allowed_executables.append(str(Path(python_bin).expanduser().resolve(strict=False)))

    return {
        "policy_version": POLICY_VERSION,
        "profile": "pi_agent_core",
        "workspace_root": str(workspace),
        "allowed_roots": [str(root) for root in allowed_roots],
        "allowed_executables": allowed_executables,
        "discard_sinks": sorted(str(path) for path in DISCARD_SINK_PATHS),
        "tool_path_keys": {tool: list(keys) for tool, keys in FILE_BOUNDARY_PATH_KEYS.items()},
        "operator_chars": "".join(sorted(BASH_OPERATOR_CHARS)),
        "tool_result_root": None,
        "readonly_commands": [],
    }
