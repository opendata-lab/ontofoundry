"""Persist and reuse stepwise artifacts without invoking external services."""

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from run_helpers import RUN_TOKEN, reconcile, row
from test_materials import upload as upload_material
from test_modeling import ROOT, create_session
from test_t3_proposal_results import proposals_run, result

from ontofoundry_api.api import agent_conversation
from ontofoundry_api.db_models import ModelingSessionRecord
from ontofoundry_api.domain.snapshot import empty_snapshot
from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError
from ontofoundry_api.services.modeling_input import scenario_facts

EXAMPLES = (
    Path(__file__).resolve().parents[3]
    / "integrations/dataagent/shared/references/examples/protocol"
)
PRIOR = {
    "plan_md": "场景：全量\n虚构订单与会员",
    "entities": {"items": [{"name": "fictional_order", "display_name": "虚构订单"}]},
}


def set_row(client, session_id, **values):
    with client.app.state.session_factory() as db:
        record = db.get(ModelingSessionRecord, session_id)
        for key, value in values.items():
            setattr(record, key, value)
        db.commit()


def downloads(monkeypatch, files):
    paths = []

    async def download(self, topic_id, path):
        assert topic_id == "topic-1"
        paths.append(path)
        value = files.get(path, DataAgentError("missing", status_code=404))
        if isinstance(value, BaseException):
            raise value
        return (
            value
            if isinstance(value, bytes)
            else json.dumps(value, ensure_ascii=False).encode()
        ), "application/json"

    monkeypatch.setattr(DataAgentClient, "download", download)
    return paths


@pytest.mark.parametrize("protocol", ["needs-input-entities", "needs-input-issues"])
def test_awaiting_reply_saves_confirmed_plan_and_new_protocol(
    client, monkeypatch, protocol
):
    session, manifest = proposals_run(client)
    marker = json.loads((EXAMPLES / f"{protocol}.json").read_bytes())
    marker["run_token"] = RUN_TOKEN
    plan = deepcopy(PRIOR)
    if protocol.endswith("issues"):
        plan.pop("entities")
        plan["issues"] = json.loads((EXAMPLES / "issues.json").read_bytes())
    files = {
        f"output/ontofoundry-needs-input-{RUN_TOKEN}.json": marker,
        "modeling/plan.md": plan["plan_md"].encode(),
    }
    files.update(
        {f"modeling/{key}.json": value for key, value in plan.items() if key != "plan_md"}
    )
    paths = downloads(monkeypatch, files)
    assert reconcile(client, session["id"]) == "awaiting_reply"
    current = row(client, session["id"])
    assert current.run_manifest_json == {**manifest, "prior_plan": plan}
    assert current.task_status == "finished"
    assert paths[-3:] == [
        "modeling/plan.md",
        "modeling/entities.json",
        "modeling/issues.json",
    ]
    assert reconcile(client, session["id"]) == "awaiting_reply"
    assert len(paths) == 5


def test_plan_download_503_does_not_prevent_awaiting_reply(client, monkeypatch):
    session, manifest = proposals_run(client)
    files = {
        f"output/ontofoundry-needs-input-{RUN_TOKEN}.json": {
            "run_token": RUN_TOKEN,
            "questions": ["请确认虚构实体"],
        }
    }
    files.update(
        {
            f"modeling/{name}": DataAgentError("unavailable", status_code=503)
            for name in ("plan.md", "entities.json", "issues.json")
        }
    )
    downloads(monkeypatch, files)
    assert reconcile(client, session["id"]) == "awaiting_reply"
    assert row(client, session["id"]).run_manifest_json == manifest
    assert "prior_plan" not in row(client, session["id"]).run_manifest_json


@pytest.fixture
def fake_agent(client, monkeypatch):
    uploads, prompts = {}, []

    class FakeAgent:
        async def create_topic(self, *_):
            return {"topic_id": "topic-1"}

        async def upload(self, topic_id, name, content, media_type):
            assert topic_id == "topic-1"
            path = "inputs/" + name
            uploads[path] = content
            return {"rel_path": path}

        async def deliver(self, **kwargs):
            prompts.append(kwargs["content"])
            return {"task_id": f"fictional-task-{len(prompts)}", "task_status": "running"}

    monkeypatch.setattr(agent_conversation, "_client", lambda *_: FakeAgent())
    monkeypatch.setattr(agent_conversation, "_require_configured", lambda *_: None)
    client.app.state.settings.modeling_result_contract = "proposals"
    return uploads, prompts


def send(client, session_id, mode="model"):
    response = client.post(
        ROOT + f"/sessions/{session_id}/agent-conversation/messages",
        json={"content": "确认虚构订单范围", "metadata": {"mode": mode}},
    )
    assert response.status_code == 202, response.text
    return row(client, session_id).run_manifest_json


def work_pack(uploads, manifest):
    return json.loads(uploads[manifest["input_files"]["work_pack"]])


def test_next_run_uploads_prior_bundle_and_third_run_drops_it(
    client, monkeypatch, fake_agent
):
    session, _ = proposals_run(client)
    downloads(
        monkeypatch,
        {
            f"output/ontofoundry-needs-input-{RUN_TOKEN}.json": {
                "run_token": RUN_TOKEN,
                "questions": ["请确认范围"],
            },
            "modeling/plan.md": PRIOR["plan_md"].encode(),
            "modeling/entities.json": PRIOR["entities"],
        },
    )
    assert reconcile(client, session["id"]) == "awaiting_reply"
    uploads, prompts = fake_agent
    manifest = send(client, session["id"])
    pack = work_pack(uploads, manifest)
    prior_path = f"inputs/ontofoundry-prior-plan-{manifest['run_token']}.json"
    assert pack["prior_plan_file"] == prior_path
    assert json.loads(uploads[prior_path]) == PRIOR
    assert pack["workflow_dir"] == "modeling/"
    assert "prior_plan" not in manifest
    assert "工作流：modeling/" in prompts[-1]
    assert prompts[-1].endswith("确认虚构订单范围")
    set_row(client, session["id"], task_status="finished", result_state="done")
    manifest = send(client, session["id"])
    assert "prior_plan_file" not in work_pack(uploads, manifest)
    assert "prior_plan" not in manifest
    assert len([p for p in uploads if "ontofoundry-prior-plan-" in p]) == 1


@pytest.mark.parametrize("state", ["done", "failed_permanent", ""])
def test_model_only_uses_plan_after_awaiting_reply(client, fake_agent, state):
    session, manifest = proposals_run(client)
    set_row(
        client,
        session["id"],
        run_manifest_json={**manifest, "prior_plan": PRIOR},
        result_state=state,
    )
    uploads, _ = fake_agent
    current = send(client, session["id"])
    assert "prior_plan_file" not in work_pack(uploads, current)
    assert not any("ontofoundry-prior-plan-" in p for p in uploads)


def test_chat_does_not_upload_or_reference_confirmed_plan(client, fake_agent):
    session, manifest = proposals_run(client)
    set_row(
        client,
        session["id"],
        result_state="awaiting_reply",
        run_manifest_json={**manifest, "prior_plan": PRIOR},
        mode="chat",
    )
    uploads, prompts = fake_agent
    current = send(client, session["id"], "chat")
    assert "prior_plan" not in current and "input_files" not in current
    assert not any("prior-plan" in p or "work-pack" in p for p in uploads)
    assert "工作流：modeling/" not in prompts[-1]


def test_scenario_facts_first_then_added_material_and_table_are_in_pack(
    client, monkeypatch, fake_agent
):
    from ontofoundry_api.services import dataset_sources

    session = create_session(client)
    set_row(client, session["id"], draft_json=empty_snapshot(session["workspace_id"]))
    uploads, _ = fake_agent
    first = send(client, session["id"])
    assert first["input_files"]["scenario_facts"] == {"draft_empty": True}
    assert work_pack(uploads, first)["scenario_facts"] == {"draft_empty": True}
    material = upload_material(client, "虚构新增范围.md")
    connection = SimpleNamespace(
        id="fictional-connection", name="云帆资料库", kind="postgres"
    )
    monkeypatch.setattr(
        dataset_sources,
        "linked_table_details",
        lambda *_: [
            {
                "connection": connection,
                "schema_name": "fictional",
                "table": {"name": "orders", "columns": [{"name": "id", "type": "text"}]},
            }
        ],
    )
    set_row(
        client,
        session["id"],
        task_status="finished",
        result_state="done",
        material_ids=[material["id"]],
        linked_tables=[
            {
                "connection_id": connection.id,
                "schema_name": "fictional",
                "table_name": "orders",
            }
        ],
    )
    second = send(client, session["id"])
    receipt_ids = [m["id"] for m in second["materials"] if m["id"] != material["id"]]
    assert len(receipt_ids) == 1
    expected = {
        "draft_empty": True,
        "new_material_ids": [material["id"], *receipt_ids],
        "new_table_keys": ["t1"],
    }
    assert second["input_files"]["scenario_facts"] == expected
    assert work_pack(uploads, second)["scenario_facts"] == expected
    set_row(client, session["id"], task_status="finished", result_state="done")
    third = send(client, session["id"])
    assert work_pack(uploads, third)["scenario_facts"] == {
        "draft_empty": True,
        "new_material_ids": [],
        "new_table_keys": [],
    }


def test_scenario_facts_compare_full_table_identity_and_do_not_guess_scenario():
    draft = {"object_types": [{"id": "fictional-object"}]}
    previous = {
        "materials": [{"id": "old"}],
        "input_files": {
            "tables": [{"connection": "云帆资料库", "table": "fictional.orders"}]
        },
    }
    tables = [
        {"key": "t3", "connection": "云帆资料库", "table": "fictional.orders"},
        {"key": "t4", "connection": "雾岭资料库", "table": "fictional.orders"},
    ]
    before = deepcopy((draft, previous, tables))
    assert scenario_facts(
        draft, {"materials": [{"id": "old"}, {"id": "new"}]}, previous, tables
    ) == {"draft_empty": False, "new_material_ids": ["new"], "new_table_keys": ["t4"]}
    assert (draft, previous, tables) == before
    assert scenario_facts(draft, {}, {}, tables) == {"draft_empty": False}


@pytest.mark.parametrize("failure", ["missing_result", "rejected_result"])
def test_permanent_failure_records_only_workflow_excerpts_and_sizes(
    client, monkeypatch, failure
):
    session, manifest = proposals_run(client)
    manifest["repair_used"] = 2
    set_row(client, session["id"], run_manifest_json=manifest)
    plan = ("场景：全量\n" + "虚构范围" * 2000).encode()
    notes = ("虚构证据" * 2000).encode()
    parts = {
        f"modeling/parts/{name}.json": b"large-private-body" * 2000
        for name in ("01-types", "02-links", "03-datasets", "04-metrics-rules", "05-facts")
    }
    files = {"modeling/plan.md": plan, "modeling/notes.md": notes, **parts}
    if failure == "rejected_result":
        bad = result(manifest, [])
        bad["run_token"] = "wrong"
        files[f"output/ontofoundry-result-{RUN_TOKEN}.json"] = bad
    paths = downloads(monkeypatch, files)

    async def forbidden(*args, **kwargs):
        pytest.fail("An exhausted run cannot invoke a repair agent")

    monkeypatch.setattr(DataAgentClient, "deliver", forbidden)
    assert reconcile(client, session["id"]) == "failed_permanent"
    current = row(client, session["id"])
    diagnostics = current.run_manifest_json["workflow_diagnostics"]
    assert [entry["path"] for entry in diagnostics] == list(files)[:7]
    for entry in diagnostics:
        original = files[entry["path"]]
        assert entry["bytes"] == len(original)
        assert entry == (
            {
                "path": entry["path"],
                "bytes": len(original),
                "excerpt": original[:4096].decode("utf-8", "ignore"),
            }
            if entry["path"].endswith(".md")
            else {"path": entry["path"], "bytes": len(original)}
        )
        assert entry["path"] in current.task_detail
    assert "large-private-body" not in json.dumps(current.run_manifest_json)
    assert paths[-7:] == list(files)[:7]
    assert current.task_status == "failed"
    assert (
        "没有产出提案" in current.task_detail
        if failure == "missing_result"
        else "被拒收" in current.task_detail
    )
    assert current.draft_json == session["draft"]
