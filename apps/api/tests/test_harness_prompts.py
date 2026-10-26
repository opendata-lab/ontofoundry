"""Snapshot the actual modeling and independent chat templates offline."""

import json
from pathlib import Path

import pytest
from run_helpers import install_download, reconcile
from test_t3_proposal_results import proposals_run, result, stored

from ontofoundry_api.services.dataagent import (
    DataAgentClient,
    build_turn_prompt,
    proposal_instructions,
)
from ontofoundry_api.services.modeling_input import build_work_pack, execution_input

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "integrations/dataagent/tests/fixtures"
)


def render(case):
    token = "example"
    modeling = case != "chat"
    entry = (
        proposal_instructions(
            run_token=token,
            work_pack_file=f"inputs/work-pack-{case}.json",
            header={"workspace_id": "fictional", "source_draft_sha256": "absent"},
            materials=[{"id": "history", "sha256": "a" * 64, "path": "inputs/history.md"}],
            schema_file="inputs/schema.json",
            mcp={"file": "inputs/mcp.json"},
        )
        if modeling
        else None
    )
    return build_turn_prompt(
        "按已确认范围建模。" if modeling else "名称和英文标识有什么区别？",
        mode="model" if modeling else "chat",
        workspace_id="fictional",
        session_id="session",
        context_file="inputs/context.json",
        context_bytes=60000,
        material_files=[]
        if case == "no_material"
        else [{"path": "inputs/history.md", "bytes": 100}],
        run_token=token,
        proposal_prompt=entry,
    )


@pytest.mark.parametrize("case", ["first", "no_material", "mcp", "chat"])
def test_prompt_snapshot(case):
    expected = json.loads((FIXTURES / "prompt-snapshots.json").read_bytes())
    assert render(case) == expected[case]


def test_dynamic_paths_have_a_single_authoritative_source():
    context = json.loads((FIXTURES / "budget-context.json").read_bytes())
    context["execution"] = execution_input("example")
    pack, _ = build_work_pack(
        context,
        [],
        context_file="inputs/context.json",
        schema_file="inputs/schema.json",
        mcp_config_file="inputs/mcp.json",
    )
    assert pack["mcp_config_file"] == "inputs/mcp.json"
    assert pack["result_file"] in render("mcp") and "needs_input_file" not in pack
    assert "inputs/mcp.json" not in render("mcp") and "source_draft_sha256" not in render(
        "first"
    )
    assert "ontofoundry-result-" not in render("chat") and "超过 50 KB" in render("chat")


def test_a_result_is_consumed_without_looking_for_questions(client, monkeypatch):
    session, manifest = proposals_run(client)
    paths = install_download(monkeypatch, [result(manifest, [])])

    async def forbidden(self, **kwargs):
        pytest.fail("有结果时不能发起模型修复")

    monkeypatch.setattr(DataAgentClient, "deliver", forbidden)
    assert reconcile(client, session["id"]) == "done"
    # Questions are answered inside the run; no question file is read.
    assert not any("needs-input" in path for path in paths)
    assert len(stored(client, session["id"])[0]) == 1


def test_a_run_before_any_publish_still_gets_its_platform_check_credential():
    # No published version: no MCP config to read, but the merge script's
    # platform check still needs this run's credential.
    context = json.loads((FIXTURES / "budget-context.json").read_bytes())
    context["execution"] = execution_input("example")
    pack, _ = build_work_pack(
        context, [], context_file="inputs/context.json", schema_file="inputs/schema.json",
        platform_check_file="inputs/ontofoundry-mcp-example.json",
    )
    assert pack["platform_check_file"] == "inputs/ontofoundry-mcp-example.json"
    assert "mcp_config_file" not in pack
