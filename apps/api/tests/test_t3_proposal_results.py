"""T3: a proposals-contract run stores a batch and never touches the draft."""

from __future__ import annotations

import json
from copy import deepcopy
from urllib.parse import urlsplit

import pytest
from run_helpers import RUN_TOKEN, TASK_ID, install_download, reconcile, row
from sqlalchemy import select, update
from test_modeling import ROOT, create_session, save

from ontofoundry_api.contracts.proposals import SCHEMA_VERSION
from ontofoundry_api.db_models import (
    ModelingSessionRecord,
    ProposalBatchRecord,
    ProposalItemDependencyRecord,
    ProposalItemRecord,
)
from ontofoundry_api.domain.canonical import element_sha256, snapshot_sha256
from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError
from ontofoundry_api.services.proposals import dependency_map, effective_statuses


def proposals_run(client) -> tuple[dict, dict]:
    """A session whose finished run was pinned to its current draft."""
    session = create_session(client)
    draft = session["draft"]
    manifest = {
        "run_token": RUN_TOKEN,
        "workspace_id": session["workspace_id"],
        "session_id": session["id"],
        "base_version_id": session["base_version_id"],
        "base_version_sha256": session["base_version_sha256"],
        "source_session_revision": session["revision"] + 1,
        "source_draft_sha256": snapshot_sha256(draft),
        "materials": [],
        "producer": {"agent_id": "agent", "skill": "ontofoundry-modeling", "mode": "model"},
        "result_contract": "proposals",
        "pinned_draft": draft,
        "input_files": {"schema": "inputs/schema.json", "materials": []},
    }
    with client.app.state.session_factory() as db:
        db.execute(
            update(ModelingSessionRecord)
            .where(ModelingSessionRecord.id == session["id"])
            .values(
                task_status="finished",
                dataagent_topic_id="topic-1",
                dataagent_task_id=TASK_ID,
                dataagent_task_mode="model",
                dataagent_run_token=RUN_TOKEN,
                result_state="",
                revision=session["revision"] + 1,
                run_manifest_json=manifest,
            )
        )
        db.commit()
    session["revision"] += 1
    return session, manifest


def result(manifest: dict, items: list[dict]) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        **{
            key: manifest[key]
            for key in (
                "run_token",
                "workspace_id",
                "session_id",
                "base_version_id",
                "base_version_sha256",
                "source_session_revision",
                "source_draft_sha256",
            )
        },
        "items": items,
    }


def some_items(draft: dict) -> list[dict]:
    target = draft["object_types"][0]
    return [
        {
            "client_ref": "po",
            "operation": "create",
            "target_kind": "object_type",
            "target_id": None,
            "expected_target_hash": None,
            "before": None,
            "after": {"display_name": "采购订单", "name": "purchase_order"},
        },
        {
            "client_ref": "po-no",
            "operation": "create",
            "target_kind": "property",
            "target_id": None,
            "expected_target_hash": None,
            "before": None,
            "after": {
                "owner_type_id": {"client_ref": "po"},
                "value_kind": "string",
                "display_name": "订单号",
                "name": "order_no",
            },
        },
        {
            "operation": "update",
            "target_kind": "object_type",
            "target_id": target["id"],
            "expected_target_hash": element_sha256(target, collection="object_types"),
            "before": target,
            "after": {
                **{k: v for k, v in target.items() if k != "id"},
                "description": "提案修改",
            },
        },
    ]


def stored(client, session_id):
    with client.app.state.session_factory() as db:
        batches = db.scalars(
            select(ProposalBatchRecord).where(ProposalBatchRecord.session_id == session_id)
        ).all()
        items = db.scalars(
            select(ProposalItemRecord)
            .where(ProposalItemRecord.session_id == session_id)
            .order_by(ProposalItemRecord.ordinal)
        ).all()
        deps = db.scalars(
            select(ProposalItemDependencyRecord).where(
                ProposalItemDependencyRecord.session_id == session_id
            )
        ).all()
        for value in [*batches, *items, *deps]:
            db.expunge(value)
    return batches, items, deps


def test_result_is_stored_as_a_batch_and_the_draft_is_untouched(client, monkeypatch):
    session, manifest = proposals_run(client)
    before = row(client, session["id"])
    install_download(monkeypatch, [result(manifest, some_items(session["draft"]))])

    assert reconcile(client, session["id"]) == "done"

    after = row(client, session["id"])
    assert after.draft_json == before.draft_json
    assert after.revision == before.revision
    assert after.task_status == "finished" and "3 条提案" in after.task_detail
    batches, items, deps = stored(client, session["id"])
    assert [b.status for b in batches] == ["available"]
    assert [i.operation for i in items] == ["create", "create", "update"]
    assert {i.status for i in items} == {"pending"}
    assert [(d.item_id, d.depends_on_item_id) for d in deps] == [(items[1].id, items[0].id)]


def test_consuming_the_same_result_twice_changes_nothing(client, monkeypatch):
    session, manifest = proposals_run(client)
    payload = result(manifest, some_items(session["draft"]))
    install_download(monkeypatch, [payload, payload])
    assert reconcile(client, session["id"]) == "done"
    assert reconcile(client, session["id"]) == "done"
    batches, items, _ = stored(client, session["id"])
    assert len(batches) == 1 and len(items) == 3


def test_edits_during_the_run_only_make_affected_items_stale(client, monkeypatch):
    session, manifest = proposals_run(client)
    edited = deepcopy(session["draft"])
    edited["object_types"][0]["description"] = "运行期间的人工修改"
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session["id"])
        item.draft_json = edited
        item.revision += 1
        db.commit()
    install_download(monkeypatch, [result(manifest, some_items(session["draft"]))])

    assert reconcile(client, session["id"]) == "done"

    _, items, _ = stored(client, session["id"])
    with client.app.state.session_factory() as db:
        deps = dependency_map(
            db, [items[0].batch_id], session["workspace_id"], session["id"]
        )
    statuses = effective_statuses(items, deps, edited)
    assert statuses[items[2].id][0] == "stale"  # the edited target
    assert statuses[items[0].id][0] == statuses[items[1].id][0] == "pending"
    # Editing the target back makes the item pending again: nothing was written.
    assert effective_statuses(items, deps, session["draft"])[items[2].id][0] == "pending"


def test_a_new_batch_supersedes_older_pending_items_on_the_same_target(client, monkeypatch):
    session, manifest = proposals_run(client)
    install_download(monkeypatch, [result(manifest, some_items(session["draft"]))])
    assert reconcile(client, session["id"]) == "done"

    second = {**manifest, "run_token": "f" * 32}
    with client.app.state.session_factory() as db:
        db.execute(
            update(ModelingSessionRecord)
            .where(ModelingSessionRecord.id == session["id"])
            .values(
                dataagent_task_id="task-2",
                dataagent_run_token="f" * 32,
                result_state="",
                run_manifest_json=second,
            )
        )
        db.commit()
    install_download(monkeypatch, [result(second, some_items(session["draft"])[2:])])
    assert reconcile(client, session["id"], "task-2") == "done"

    _, items, _ = stored(client, session["id"])
    by_batch = {}
    for item in items:
        by_batch.setdefault(item.batch_id, []).append(item)
    old, new = sorted(by_batch.values(), key=len, reverse=True)
    assert [i.status for i in old] == ["pending", "pending", "superseded"]
    assert [i.status for i in new] == ["pending"]


def test_a_rejected_result_is_handed_back_for_repair(client, monkeypatch):
    async def upload(self, topic_id, name, data, media_type):
        return {"rel_path": "inputs/" + name}

    monkeypatch.setattr(DataAgentClient, "upload", upload)

    session, manifest = proposals_run(client)
    bad = result(manifest, some_items(session["draft"]))
    bad["items"][2]["expected_target_hash"] = "0" * 64
    install_download(monkeypatch, [bad])
    sent: list[str] = []

    async def deliver(self, **kwargs):
        sent.append(kwargs["content"])
        return {"task_id": "task-repair"}

    monkeypatch.setattr(DataAgentClient, "deliver", deliver)

    assert reconcile(client, session["id"]) == ""
    after = row(client, session["id"])
    assert after.dataagent_task_id == "task-repair"
    assert after.run_manifest_json["run_token"] == after.dataagent_run_token != RUN_TOKEN
    assert "TARGET_HASH_MISMATCH" in sent[0]
    assert (
        after.dataagent_run_token in sent[0]
    )  # The new dynamic entry points carry the token.
    assert stored(client, session["id"])[0] == []


def test_a_rejected_result_without_repair_is_kept_as_a_failed_batch(client, monkeypatch):
    async def upload(self, topic_id, name, content, media_type):
        return {"rel_path": "inputs/" + name}

    monkeypatch.setattr(DataAgentClient, "upload", upload)

    session, manifest = proposals_run(client)
    bad = result(manifest, some_items(session["draft"]))
    bad["run_token"] = "wrong"
    install_download(monkeypatch, [bad])

    async def refuse(self, **_kwargs):
        raise DataAgentError("unavailable")

    monkeypatch.setattr(DataAgentClient, "deliver", refuse)

    assert reconcile(client, session["id"]) == "failed_permanent"
    (batch,), items, _ = stored(client, session["id"])
    assert batch.status == "failed" and items == []
    assert batch.error_json["code"] == "RESULT_CONTEXT_MISMATCH"
    assert row(client, session["id"]).draft_json == session["draft"]


def test_proposals_prompt_carries_header_hashes_and_pinned_mcp(client, monkeypatch):
    from ontofoundry_api.api import agent_conversation

    uploads: dict[str, bytes] = {}
    prompts: list[str] = []

    class FakeAgent:
        async def create_topic(self, *_):
            return {"topic_id": "topic-1"}

        async def upload(self, topic_id, name, data, content_type):
            uploads[name] = data
            return {"rel_path": "inputs/" + name}

        async def deliver(self, **kwargs):
            prompts.append(kwargs["content"])
            return {"task_id": "task-1", "task_status": "running"}

    monkeypatch.setattr(agent_conversation, "_client", lambda *_: FakeAgent())
    monkeypatch.setattr(agent_conversation, "_require_configured", lambda _r: None)
    client.app.state.settings.modeling_result_contract = "proposals"
    session = create_session(client)
    session["draft"]["object_types"][0]["description"] = "固定前的修改"
    session = save(client, session, session["draft"]).json()

    response = client.post(
        ROOT + f"/sessions/{session['id']}/agent-conversation/messages",
        json={"content": "建模", "metadata": {"mode": "model"}},
    )
    assert response.status_code == 202, response.text
    manifest = row(client, session["id"]).run_manifest_json
    assert manifest["result_contract"] == "proposals"
    assert manifest["pinned_draft"] == session["draft"]

    context = json.loads(
        next(v for k, v in uploads.items() if k.startswith("ontofoundry-context-"))
    )
    assert context["run"] == {k: v for k, v in result(manifest, []).items() if k != "items"}
    first = session["draft"]["object_types"][0]
    assert context["element_hashes"][first["id"]] == element_sha256(
        first, collection="object_types"
    )
    pack = json.loads(
        next(v for k, v in uploads.items() if k.startswith("ontofoundry-work-pack-"))
    )
    assert pack["context_file"].startswith("inputs/ontofoundry-context-")
    assert pack["run"] == context["run"]
    assert pack["execution"]["repair_used"] == 0
    assert pack["elements"] and len(json.dumps(pack, ensure_ascii=False).encode()) < 8192
    assert manifest["repair_budget_required"] is True
    assert "ontofoundry.proposals.v1.schema.json" in uploads
    (prompt,) = prompts
    assert manifest["run_token"] in prompt and manifest["source_draft_sha256"] not in prompt
    token = manifest["run_token"]
    assert pack["result_file"] == f"output/ontofoundry-result-{token}.json"
    assert pack["needs_input_file"] == f"output/ontofoundry-needs-input-{token}.json"
    assert pack["needs_input_file"] in prompt and pack["result_file"] in prompt
    assert "questions" not in prompt and "结果头" not in prompt
    assert session["base_version_id"] == pack["run"]["base_version_id"]
    assert "ofrun." not in prompt
    access_name = f"ontofoundry-mcp-{manifest['run_token']}.json"
    assert pack["mcp_config_file"] == "inputs/" + access_name
    assert "inputs/" + access_name not in prompt
    access = json.loads(uploads[access_name])
    assert access["headers"]["Authorization"].startswith("Bearer ofrun.")
    path = urlsplit(access["url"]).path
    called = client.post(
        path,
        headers=access["headers"],
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "get_ontology", "arguments": {}},
        },
    ).json()
    assert called["result"]["structuredContent"]["version_id"] == session["base_version_id"]


def test_material_paths_carry_over_to_later_runs(client, monkeypatch):
    from ontofoundry_api.api import agent_conversation

    uploads: list[str] = []
    prompts: list[str] = []
    packs = []

    class FakeAgent:
        async def create_topic(self, *_):
            return {"topic_id": "topic-1"}

        async def upload(self, topic_id, name, data, content_type):
            uploads.append(name)
            if name.startswith("ontofoundry-work-pack-"):
                packs.append(json.loads(data))
            return {"rel_path": "inputs/" + name}

        async def deliver(self, **kwargs):
            prompts.append(kwargs["content"])
            return {"task_id": f"task-{len(prompts)}", "task_status": "running"}

    monkeypatch.setattr(agent_conversation, "_client", lambda *_: FakeAgent())
    monkeypatch.setattr(agent_conversation, "_require_configured", lambda _r: None)
    material = client.post(
        ROOT + "/materials?name=a.md", content="# a\n内容\n".encode()
    ).json()
    session = create_session(client)
    session = client.put(
        ROOT + f"/sessions/{session['id']}",
        json={
            "revision": session["revision"],
            "draft": session["draft"],
            "material_ids": [material["id"]],
        },
    ).json()

    def turn():
        response = client.post(
            ROOT + f"/sessions/{session['id']}/agent-conversation/messages",
            json={"content": "建模", "metadata": {"mode": "model"}},
        )
        assert response.status_code == 202, response.text
        with client.app.state.session_factory() as db:
            item = db.get(ModelingSessionRecord, session["id"])
            item.task_status = "finished"
            db.commit()

    turn()
    turn()
    assert (
        sum(1 for name in uploads if name.startswith(material["id"])) == 1
    )  # uploaded once
    assert f"inputs/{material['id']}-a.md" not in prompts[1]
    assert packs[-1]["materials"][0]["path"] == f"inputs/{material['id']}-a.md"
    assert packs[-1]["materials"][0]["original_range"] == [1, 2]
    manifest = row(client, session["id"]).run_manifest_json
    assert manifest["materials"][0]["path"] == f"inputs/{material['id']}-a.md"


def test_proposals_run_with_needs_input_marker_asks_for_a_reply(client, monkeypatch):
    session, _ = proposals_run(client)
    paths = install_download(
        monkeypatch,
        [
            DataAgentError("missing", status_code=404),
            {"run_token": RUN_TOKEN, "questions": ["需要包含哪些业务对象？"]},
        ],
    )

    assert reconcile(client, session["id"]) == "awaiting_reply"
    current = row(client, session["id"])
    assert current.task_status == "finished"
    assert current.task_detail == "智能体需要你确认后才能生成提案，请在对话中回复"
    assert stored(client, session["id"])[0] == []
    detail = client.get(ROOT + "/sessions/" + session["id"]).json()
    assert detail["result_state"] == "awaiting_reply"
    assert detail["task_detail"] == current.task_detail

    assert reconcile(client, session["id"]) == "awaiting_reply"
    assert paths == [
        f"output/ontofoundry-result-{RUN_TOKEN}.json",
        f"output/ontofoundry-needs-input-{RUN_TOKEN}.json",
        "modeling/plan.md",
        "modeling/entities.json",
        "modeling/issues.json",
    ]


@pytest.mark.parametrize(
    "marker",
    [
        pytest.param(DataAgentError("missing marker", status_code=404), id="missing"),
        pytest.param(b"not json", id="invalid-json"),
        pytest.param(
            {"run_token": "previous-round", "questions": ["是否继续？"]},
            id="wrong-token",
        ),
        pytest.param({"run_token": RUN_TOKEN, "questions": []}, id="empty-questions"),
        pytest.param({"run_token": RUN_TOKEN, "questions": ["   "]}, id="blank-question"),
        pytest.param({"run_token": RUN_TOKEN, "questions": [1]}, id="non-string-question"),
    ],
)
def test_proposals_run_without_valid_marker_fails_permanently(client, monkeypatch, marker):
    session, _ = proposals_run(client)
    before = row(client, session["id"])
    paths = install_download(
        monkeypatch, [DataAgentError("missing", status_code=404), marker]
    )

    assert reconcile(client, session["id"]) == "failed_permanent"
    current = row(client, session["id"])
    assert current.result_state == "failed_permanent"
    assert current.task_status == "failed"
    assert (
        current.task_detail
        == "建模没有产出提案：智能体结束时没有写入结果文件，请重试或换个说法描述需求"
    )
    assert current.draft_json == before.draft_json
    assert current.candidates_json == before.candidates_json
    assert current.revision == before.revision
    assert stored(client, session["id"])[0] == []
    detail = client.get(ROOT + "/sessions/" + session["id"]).json()
    assert detail["result_state"] == "failed_permanent"
    assert detail["task_detail"] == current.task_detail

    assert reconcile(client, session["id"]) == "failed_permanent"
    assert paths[2:] == [
        "modeling/plan.md",
        "modeling/notes.md",
        "modeling/parts/01-types.json",
        "modeling/parts/02-links.json",
        "modeling/parts/03-datasets.json",
        "modeling/parts/04-metrics-rules.json",
        "modeling/parts/05-facts.json",
    ]


@pytest.mark.parametrize("status_code", [408, 425, 429, 500, 502, 503])
def test_proposals_marker_download_error_is_retriable(client, monkeypatch, status_code):
    session, _ = proposals_run(client)
    before = row(client, session["id"])
    paths = install_download(
        monkeypatch,
        [
            DataAgentError("missing", status_code=404),
            DataAgentError("marker unavailable", status_code=status_code),
            result(before.run_manifest_json, []),
        ],
    )

    assert reconcile(client, session["id"]) == "failed_retriable"
    current = row(client, session["id"])
    assert current.result_state == "failed_retriable"
    assert current.task_status == "finished"
    assert current.task_detail == "建模结果下载暂时失败，等待重试：marker unavailable"
    assert current.draft_json == before.draft_json
    assert current.candidates_json == before.candidates_json
    assert current.revision == before.revision
    assert stored(client, session["id"])[0] == []

    assert reconcile(client, session["id"]) == "done"
    assert reconcile(client, session["id"]) == "done"
    assert paths == [
        f"output/ontofoundry-result-{RUN_TOKEN}.json",
        f"output/ontofoundry-needs-input-{RUN_TOKEN}.json",
        f"output/ontofoundry-result-{RUN_TOKEN}.json",
    ]


@pytest.mark.parametrize("repair", [True, False])
def test_unexpected_parse_failure_uses_standard_rejection(client, monkeypatch, repair):
    async def upload(self, topic_id, name, data, media_type):
        return {"rel_path": "inputs/" + name}

    monkeypatch.setattr(DataAgentClient, "upload", upload)

    from ontofoundry_api.services import model_result

    session, manifest = proposals_run(client)
    install_download(monkeypatch, [result(manifest, [])])

    def broken(*args, **kwargs):
        raise KeyError("client_ref")

    sent = []

    async def deliver(self, **kwargs):
        sent.append(kwargs["content"])
        if not repair:
            raise DataAgentError("unavailable")
        return {"task_id": "task-repair"}

    monkeypatch.setattr(model_result, "parse_result", broken)
    monkeypatch.setattr(DataAgentClient, "deliver", deliver)
    assert reconcile(client, session["id"]) == ("" if repair else "failed_permanent")
    assert "RESULT_VALIDATION_FAILED" in sent[0]
    assert row(client, session["id"]).draft_json == session["draft"]
    batches, items, _ = stored(client, session["id"])
    assert items == []
    if repair:
        assert batches == []
        assert row(client, session["id"]).dataagent_task_id == "task-repair"
    else:
        assert batches[0].error_json["code"] == "RESULT_VALIDATION_FAILED"


@pytest.mark.parametrize("local_used", [0, 1, 2])
def test_local_and_platform_repairs_share_two_rounds(client, monkeypatch, local_used):
    import hashlib

    session, manifest = proposals_run(client)
    manifest.update(
        repair_used=0,
        repair_budget_required=True,
        input_files={"schema": "inputs/schema.json", "materials": []},
    )
    with client.app.state.session_factory() as db:
        db.get(ModelingSessionRecord, session["id"]).run_manifest_json = manifest
        db.commit()
    sent, contexts = [], []
    current_used = local_used

    async def download(self, topic_id, rel_path):
        current = row(client, session["id"]).run_manifest_json
        batch = result(current, some_items(session["draft"]))
        batch["items"][2]["expected_target_hash"] = "0" * 64
        content = json.dumps(batch, ensure_ascii=False).encode()
        if "needs-input" in rel_path:
            raise DataAgentError("missing", status_code=404)
        if "budget" in rel_path:
            return json.dumps(
                {
                    "run_token": current["run_token"],
                    "used": current_used,
                    "result_sha256": hashlib.sha256(content).hexdigest(),
                }
            ).encode(), "application/json"
        return content, "application/json"

    async def upload(self, topic_id, name, content, media_type):
        contexts.append(json.loads(content))
        return {"rel_path": "inputs/" + name}

    async def deliver(self, **kwargs):
        sent.append(kwargs["content"])
        return {"task_id": f"repair-{len(sent)}"}

    monkeypatch.setattr(DataAgentClient, "download", download)
    monkeypatch.setattr(DataAgentClient, "upload", upload)
    monkeypatch.setattr(DataAgentClient, "deliver", deliver)
    task_id = TASK_ID
    for used in range(local_used, 3):
        current_used = used
        state = reconcile(client, session["id"], task_id)
        assert state == ("" if used < 2 else "failed_permanent")
        if used < 2:
            after = row(client, session["id"])
            assert after.run_manifest_json["repair_used"] == used + 1
            assert contexts[-1]["execution"]["repair_used"] == used + 1
            assert contexts[-1]["run"]["run_token"] == after.dataagent_run_token
            assert contexts[-2]["draft"] == session["draft"]
            assert contexts[-1]["context_file"].endswith(
                f"{after.dataagent_run_token}.json"
            )
            assert contexts[-1]["schema_file"] == "inputs/schema.json"
            assert contexts[-1]["result_file"].endswith(f"{after.dataagent_run_token}.json")
            assert contexts[-1]["needs_input_file"] in sent[-1]
            assert contexts[-1]["run"]["source_draft_sha256"] not in sent[-1]
            task_id = after.dataagent_task_id
            with client.app.state.session_factory() as db:
                db.get(ModelingSessionRecord, session["id"]).task_status = "finished"
                db.commit()
    assert len(sent) == 2 - local_used
    assert row(client, session["id"]).draft_json == session["draft"]
    assert stored(client, session["id"])[0][-1].status == "failed"


@pytest.mark.parametrize(
    "ledger",
    [
        None,
        {"used": 0, "run_token": "old", "result_sha256": "a" * 64},
        {"used": 3, "run_token": RUN_TOKEN, "result_sha256": "a" * 64},
    ],
)
def test_missing_stale_or_exhausted_budget_cannot_trigger_deliver(
    client, monkeypatch, ledger
):
    session, manifest = proposals_run(client)
    manifest.update(repair_used=0, repair_budget_required=True)
    with client.app.state.session_factory() as db:
        db.get(ModelingSessionRecord, session["id"]).run_manifest_json = manifest
        db.commit()
    install_download(
        monkeypatch,
        [result(manifest, []), DataAgentError("missing", status_code=404), ledger],
    )

    async def forbidden(self, **kwargs):
        pytest.fail("计数失效不得自动调用模型")

    monkeypatch.setattr(DataAgentClient, "deliver", forbidden)
    assert reconcile(client, session["id"]) == "failed_permanent"
    assert (
        stored(client, session["id"])[0][-1].error_json["code"] == "REPAIR_BUDGET_INVALID"
    )


@pytest.mark.parametrize("transient", [False, True])
def test_valid_budget_acceptance_and_transient_ledger_download(
    client, monkeypatch, transient
):
    import hashlib

    session, manifest = proposals_run(client)
    manifest.update(repair_used=0, repair_budget_required=True)
    with client.app.state.session_factory() as db:
        db.get(ModelingSessionRecord, session["id"]).run_manifest_json = manifest
        db.commit()
    content = json.dumps(
        result(manifest, some_items(session["draft"])), ensure_ascii=False
    ).encode()
    ledger = {
        "run_token": RUN_TOKEN,
        "used": 2,
        "result_sha256": hashlib.sha256(content).hexdigest(),
    }
    values = [content, ledger]
    if transient:
        values = [content, DataAgentError("暂态故障", status_code=503), *values]
    paths = install_download(monkeypatch, values)

    async def forbidden(self, **kwargs):
        pytest.fail("有效结果或暂态下载不应请求模型")

    monkeypatch.setattr(DataAgentClient, "deliver", forbidden)
    if transient:
        assert reconcile(client, session["id"]) == "failed_retriable"
    assert reconcile(client, session["id"]) == "done"
    assert len(paths) == (4 if transient else 2)
    assert len(stored(client, session["id"])[1]) == 3
