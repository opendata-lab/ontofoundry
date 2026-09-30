"""T3: a proposals-contract run stores a batch and never touches the draft."""

from __future__ import annotations

import json
from copy import deepcopy

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
        "producer": {"agent_id": "agent", "skill": "md2ossie", "mode": "model"},
        "result_contract": "proposals",
        "pinned_draft": draft,
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
            "after": {"name": "采购订单", "technical_name": "purchase_order"},
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
                "name": "订单号",
                "technical_name": "order_no",
            },
        },
        {
            "operation": "update",
            "target_kind": "object_type",
            "target_id": target["id"],
            "expected_target_hash": element_sha256(target),
            "before": target,
            "after": {**{k: v for k, v in target.items() if k != "id"}, "description": "提案修改"},
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
        deps = dependency_map(db, [items[0].batch_id], session["workspace_id"], session["id"])
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
    assert after.dataagent_run_token in sent[0]  # the new header to copy
    assert stored(client, session["id"])[0] == []


def test_a_rejected_result_without_repair_is_kept_as_a_failed_batch(client, monkeypatch):
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

    context = json.loads(next(v for k, v in uploads.items() if k.startswith("ontofoundry-context-")))
    first = session["draft"]["object_types"][0]
    assert context["element_hashes"][first["id"]] == element_sha256(first)
    assert "ontofoundry.proposals.v1.schema.json" in uploads
    (prompt,) = prompts
    assert manifest["run_token"] in prompt and manifest["source_draft_sha256"] in prompt
    assert "Bearer ofrun." in prompt and session["base_version_id"] in prompt


def test_material_paths_carry_over_to_later_runs(client, monkeypatch):
    from ontofoundry_api.api import agent_conversation

    uploads: list[str] = []
    prompts: list[str] = []

    class FakeAgent:
        async def create_topic(self, *_):
            return {"topic_id": "topic-1"}

        async def upload(self, topic_id, name, data, content_type):
            uploads.append(name)
            return {"rel_path": "inputs/" + name}

        async def deliver(self, **kwargs):
            prompts.append(kwargs["content"])
            return {"task_id": f"task-{len(prompts)}", "task_status": "running"}

    monkeypatch.setattr(agent_conversation, "_client", lambda *_: FakeAgent())
    monkeypatch.setattr(agent_conversation, "_require_configured", lambda _r: None)
    material = client.post(ROOT + "/materials?name=a.md", content="# a\n内容\n".encode()).json()
    session = create_session(client)
    session = client.put(
        ROOT + f"/sessions/{session['id']}",
        json={"revision": session["revision"], "draft": session["draft"], "material_ids": [material["id"]]},
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
    assert sum(1 for name in uploads if name.startswith(material["id"])) == 1  # uploaded once
    assert f"inputs/{material['id']}-a.md" in prompts[1]  # still named in the second run
    manifest = row(client, session["id"]).run_manifest_json
    assert manifest["materials"][0]["path"] == f"inputs/{material['id']}-a.md"
