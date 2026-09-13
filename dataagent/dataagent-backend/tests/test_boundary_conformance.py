import json
import sys
from pathlib import Path

from core.boundary_policy import build_boundary_policy


def test_serialized_pi_policy_matches_schema_and_roots(tmp_path: Path):
    workspace = tmp_path / "workspace"
    skill = tmp_path / "skill"
    scratch = tmp_path / "scratch"
    policy = build_boundary_policy(
        workspace,
        {"enabled_roots": {"modeling": str(skill)}},
        [str(scratch)],
        {"DATAAGENT_PYTHON_BIN": sys.executable},
    )
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "contracts"
        / "boundary"
        / "v1"
        / "boundary-policy.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert set(policy) == set(schema["required"])
    assert policy["profile"] == "pi_agent_core"
    assert policy["allowed_roots"] == [
        str(workspace.resolve()),
        str(skill.resolve()),
        str(scratch.resolve()),
    ]
    assert policy["allowed_executables"] == [str(Path(sys.executable).resolve())]
    assert policy["tool_result_root"] is None
    assert policy["readonly_commands"] == []
