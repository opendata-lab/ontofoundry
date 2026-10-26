"""Snapshot the actual modeling, repair and independent chat templates offline."""

import json
from pathlib import Path

import pytest
from run_helpers import RUN_TOKEN, install_download, reconcile, row
from test_t3_proposal_results import proposals_run, result, stored

from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.services.dataagent import (
    DataAgentClient,
    DataAgentError,
    build_turn_prompt,
    proposal_instructions,
)
from ontofoundry_api.services.model_review import build_proposal_repair_request
from ontofoundry_api.services.modeling_input import build_work_pack, execution_input

FIXTURES = (
    Path(__file__).resolve().parents[3]
    / "integrations/dataagent/tests/fixtures"
)


def render(case):
    token = "new-run" if case == "repair" else "example"
    if case == "repair":
        return build_proposal_repair_request(
            ["TARGET_HASH_MISMATCH：目标哈希不一致"],
            run_token=token,
            work_pack_file="inputs/work-pack-new-run.json",
            repair_used=2,
        )
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


@pytest.mark.parametrize("case", ["first", "repair", "no_material", "mcp", "chat"])
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


def test_repair_rebuilds_pack_with_preserved_inputs_and_actual_error(client, monkeypatch):
    from copy import deepcopy

    from test_t3_proposal_results import some_items

    session, manifest = proposals_run(client)
    material_index = {
        "id": "fictional-material",
        "sha256": "a" * 64,
        "path": "inputs/original.md",
        "bytes": 10,
        "lines": 1,
        "original_range": [1, 1],
    }
    user_id = row(client, session["id"]).created_by
    manifest["input_files"].update(
        mcp_access={
            "url": f"http://fictional.local/api/v1/ontology/workspaces/{session['workspace_id']}/mcp",
            "user_id": user_id,
        },
        materials=[material_index],
        mcp="inputs/pinned-mcp.json",
        work_pack="inputs/old-pack.json",
        tables=[{"table": "retail.orders", "connection": "虚构零售库", "kind": "table", "comment": "虚构订单", "column_count": 2}],
        tables_file="inputs/tables.json",
        scenario_facts={"draft_empty": False, "new_material_ids": ["fictional-material"], "new_table_keys": ["t1"]},
    )
    manifest["repair_used"] = 1
    before = deepcopy(manifest)
    with client.app.state.session_factory() as db:
        db.get(ModelingSessionRecord, session["id"]).run_manifest_json = manifest
        db.commit()
    batch = result(manifest, some_items(session["draft"]))
    batch["items"][2]["expected_target_hash"] = "0" * 64
    install_download(monkeypatch, [batch])
    uploads, sent = {}, []

    async def upload(self, topic_id, name, content, media_type):
        uploads["inputs/" + name] = json.loads(content)
        return {"rel_path": "inputs/" + name}

    async def deliver(self, **kwargs):
        sent.append(kwargs["content"])
        return {"task_id": "repaired-task"}

    monkeypatch.setattr(DataAgentClient, "upload", upload)
    monkeypatch.setattr(DataAgentClient, "deliver", deliver)
    assert reconcile(client, session["id"]) == ""
    latest = row(client, session["id"]).run_manifest_json
    pack = uploads[latest["input_files"]["work_pack"]]
    context = uploads[pack["context_file"]]
    assert context["draft"] == before["pinned_draft"]
    assert pack["run"]["run_token"] == latest["run_token"] != RUN_TOKEN
    assert (
        pack["execution"] == context["execution"] == execution_input(latest["run_token"], 2)
    )
    assert (
        pack["materials"] == [material_index]
        and pack["schema_file"] == before["input_files"]["schema"]
    )
    assert pack["mcp_config_file"] != before["input_files"]["mcp"]
    # Repair keeps the linked-table catalog and its column file.
    assert pack["tables"] == before["input_files"]["tables"]
    assert pack["tables_file"] == before["input_files"]["tables_file"]
    assert pack["workflow_dir"] == "modeling/"
    assert pack["scenario_facts"] == before["input_files"]["scenario_facts"]
    assert "prior_plan_file" not in pack
    assert "在 modeling/parts/ 已有片段上修改" in sent[0]
    from urllib.parse import urlsplit

    from ontofoundry_api.services.run_credentials import RunGrant, issue, verify

    mcp = uploads[pack["mcp_config_file"]]
    grant = verify(
        client.app.state.settings.session_secret,
        mcp["headers"]["Authorization"].removeprefix("Bearer "),
    )
    assert (
        grant.run_token == latest["run_token"]
        and grant.version_id == before["base_version_id"]
    )
    assert grant.user_id == user_id
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "get_ontology", "arguments": {}},
    }
    response = client.post(urlsplit(mcp["url"]).path, headers=mcp["headers"], json=body)
    assert response.status_code == 200
    assert (
        response.json()["result"]["structuredContent"]["version_id"]
        == before["base_version_id"]
    )
    old = issue(
        client.app.state.settings.session_secret,
        RunGrant(
            session["workspace_id"],
            session["id"],
            RUN_TOKEN,
            before["base_version_id"],
            user_id,
        ),
    )
    assert (
        client.post(
            urlsplit(mcp["url"]).path,
            headers={**mcp["headers"], "Authorization": "Bearer " + old},
            json=body,
        ).status_code
        == 401
    )
    assert "ofrun." not in sent[0]
    assert pack["result_file"] in sent[0] and "待确认" not in sent[0]
    assert "TARGET_HASH_MISMATCH" in sent[0] and "/items/2/expected_target_hash" in sent[0]
    assert "期望" in sent[0] and "实际" in sent[0] and "show_example.py" in sent[0]
    assert "old-pack" not in sent[0] and before["source_draft_sha256"] not in sent[0]
    assert "累计修正：2/2" in sent[0]


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
