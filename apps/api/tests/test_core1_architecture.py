"""Core runtime stays format independent; import services own adapter access."""

import ast
from pathlib import Path

import pytest

from ontofoundry_api.domain.snapshot import read_snapshot

ROOT = Path(__file__).parents[1] / "src/ontofoundry_api"


def test_no_runtime_adapter_dependency():
    allowed = {"import_materials.py", "imports.py", "import_completion.py", "exports.py"}
    for directory in ("domain", "services", "api", "contracts"):
        for path in (ROOT / directory).glob("*.py"):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    assert not (node.module or "").startswith("ontofoundry_api.ossie"), path
                    if path.name not in allowed:
                        assert not (node.module or "").startswith(
                            "ontofoundry_api.adapters"
                        ), path
    for name in [
        "models_v3",
        "legacy_v1",
        "runtime_views",
        "semantic_views",
        "semantic_authoring",
        "semantic_edit",
        "semantic_fields",
        "role_join",
        "fact_views",
    ]:
        assert not (ROOT / "domain" / (name + ".py")).exists()


@pytest.mark.parametrize("version", [None, "1", "2", "3", "unknown"])
def test_snapshot_rejects_missing_and_obsolete_versions(version):
    data = {"workspace_id": "00000000-0000-4000-8000-000000000001"}
    if version is not None:
        data["schema_version"] = version
    with pytest.raises(ValueError):
        read_snapshot(data)
