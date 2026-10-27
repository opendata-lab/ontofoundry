import json
from copy import deepcopy
from uuid import uuid4

import pytest
from dataset_binding import bind_datasets
from run_helpers import TASK_ID, install_download, reconcile, row
from sqlalchemy import select
from test_instance_store import create_instance
from test_modeling import ROOT, create_session, save
from test_proposal_checks import running_check
from test_t3_proposal_results import proposals_run, result, some_items, stored
from test_t4_proposal_decisions import chain, current, decide, seed_batch

from ontofoundry_api.db_models import (
    ModelingSessionRecord,
    ProposalBatchRecord,
    ProposalItemRecord,
)
from ontofoundry_api.services.dataagent import DataAgentClient
from ontofoundry_api.services.modeling_runs import _persist_task_projection


def test_revising_a_proposal_to_an_existing_name_is_atomic(client):
    session = create_session(client)
    batch = seed_batch(client, session, chain(session)[:1])
    item = batch["items"][0]
    response = client.patch(ROOT + f"/sessions/{session['id']}/proposals/{item['id']}/after", json={
        "expected_session_revision": session["revision"],
        "fields": {"name": session["draft"]["object_types"][0]["name"]},
    })
    assert response.status_code == 422, response.text
    assert current(client, session)["revision"] == session["revision"]
    with client.app.state.session_factory() as db:
        assert db.get(ProposalItemRecord, item["id"]).after_json == item["after"]


def test_pending_proposals_block_new_runs(client):
    session = create_session(client)
    seed_batch(client, session, chain(session))
    response = client.post(ROOT + f"/sessions/{session['id']}/agent-conversation/messages", json={"content": "继续补充虚构订单"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PENDING_PROPOSALS"
    assert row(client, session["id"]).revision == session["revision"]


@pytest.mark.parametrize("state,claimed", [(None, False), ("processing", True), ("failed_retriable", True)])
def test_result_processing_blocks_new_runs(client, state, claimed):
    session, _ = proposals_run(client)
    with client.app.state.session_factory() as db:
        record = db.get(ModelingSessionRecord, session["id"])
        record.result_state = state or ""
        record.last_result_task_id = TASK_ID if claimed else None
        db.commit()
    response = client.post(ROOT + f"/sessions/{session['id']}/agent-conversation/messages", json={"content": "继续建模"})
    assert response.status_code == 409
    assert response.json()["error"] == {"code": "RESULT_PROCESSING", "message": "上一轮结果还在处理，请稍候"}
    assert row(client, session["id"]).dataagent_task_id == TASK_ID


@pytest.mark.parametrize("status", ["submitting", "queued", "running", "waiting_input", "waiting_permission", "finished"])
def test_occupied_session_blocks_draft_and_decisions(client, status):
    session = create_session(client)
    batch = seed_batch(client, session, chain(session))
    with client.app.state.session_factory() as db:
        record = db.get(ModelingSessionRecord, session["id"])
        record.task_status = status
        record.dataagent_task_mode = "model"
        record.dataagent_task_id = TASK_ID
        record.result_state = "processing" if status == "finished" else ""
        db.commit()
    edited = deepcopy(session["draft"])
    edited["object_types"][0]["description"] = "运行中编辑"
    assert save(client, session, edited).status_code == 409
    for decision in ("accept", "reject", "restore"):
        response = decide(client, session, [(batch["items"][0]["id"], decision)])
        assert response.status_code == 409
        assert response.json()["error"]["code"] in {"SESSION_RUNNING", "RESULT_PROCESSING"}
    response = client.patch(ROOT + f"/sessions/{session['id']}/proposals/{batch['items'][0]['id']}/after", json={
        "expected_session_revision": session["revision"], "fields": {"description": "修订"},
    })
    assert response.status_code == 409


@pytest.mark.parametrize("decision", ["accept", "reject", "restore"])
def test_old_batch_is_read_only_after_a_new_run_starts(client, decision):
    session = create_session(client)
    batch = seed_batch(client, session, chain(session)[:1])
    with client.app.state.session_factory() as db:
        record = db.get(ModelingSessionRecord, session["id"])
        record.run_manifest_json = {"source_session_revision": session["revision"] + 1}
        db.commit()
    response = decide(client, session, [(batch["items"][0]["id"], decision)])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROPOSAL_BATCH_READ_ONLY"
    detail = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}").json()
    assert detail["read_only"]


def test_reused_evidence_id_is_rejected_during_check(client):
    session, manifest, url, headers = running_check(client)
    material = client.post(ROOT + "/materials?name=虚构实例证据.md", content="星湾客户与月港客户".encode()).json()
    evidence = {"id": str(uuid4()), "kind": "material", "material_id": material["id"],
        "material_sha256": material["sha256"], "locator": {"line_start": 1, "line_end": 1}, "quote": "星湾客户"}
    one = create_instance(session, "星湾客户")
    two = create_instance(session, "月港客户")
    two["client_ref"] = "second-fictional-customer"
    for item in (one, two):
        item["after"]["evidence"] = [deepcopy(evidence)]
    response = client.post(url, json=result(manifest, [one, two]), headers=headers)
    assert response.status_code == 200, response.text
    assert not response.json()["passed"]
    assert response.json()["contract_errors"][0]["code"] == "EVIDENCE_ID_DUPLICATE"
    with client.app.state.session_factory() as db:
        assert db.scalar(select(ProposalBatchRecord.id)) is None


def test_checked_query_dataset_and_instances_are_accepted_without_live_probe(client, monkeypatch):
    session, manifest, url, headers = running_check(client)
    source = bind_datasets(client, {"datasets": [{"name": "fictional_orders", "table_name": "fictional_orders",
        "schema_name": "public", "dialect": "postgres", "columns": [{"name": "code", "physical_type": "text"}]}]})["datasets"][0]
    query = {**source, "source_kind": "query", "table_name": None, "schema_name": None,
        "query_sql": "SELECT code FROM public.fictional_orders"}
    payload = result(manifest, [*some_items(session["draft"]), create_instance(session), {
        "operation": "create", "target_kind": "dataset", "client_ref": "fictional-query", "before": None, "after": query}])

    def forbidden(*args, **kwargs):
        pytest.fail("提案检查和接受不能探测业务库")

    monkeypatch.setattr("ontofoundry_api.services.dataset_validation.connect_readonly", forbidden)
    checked = client.post(url, json=payload, headers=headers)
    assert checked.status_code == 200 and checked.json()["passed"], checked.text
    with client.app.state.session_factory() as db:
        db.get(ModelingSessionRecord, session["id"]).task_status = "finished"
        db.commit()
    install_download(monkeypatch, [payload])
    assert reconcile(client, session["id"]) == "done"
    batches, items, _ = stored(client, session["id"])
    assert len(batches) == 1
    response = decide(client, session, [(item.id, "accept") for item in items])
    assert response.status_code == 200, response.text
    assert len(response.json()["results"]) == len(items)
    assert {item["status"] for item in response.json()["results"]} == {"accepted"}


def test_cancelled_run_never_stores_a_late_result(client, monkeypatch):
    session, manifest = proposals_run(client)

    async def download(self, topic_id, path):
        _persist_task_projection(client.app.state.session_factory, session["id"], task_id=TASK_ID,
            upstream_status="suspended", detail="已取消")
        return json.dumps(result(manifest, some_items(session["draft"]))).encode(), "application/json"

    monkeypatch.setattr(DataAgentClient, "download", download)
    assert reconcile(client, session["id"]) == "failed_permanent"
    assert stored(client, session["id"])[0:2] == ([], [])
    assert row(client, session["id"]).run_manifest_json["invalidated"]


def test_batch_storage_and_result_completion_roll_back_together(client, monkeypatch):
    from ontofoundry_api.services import model_result

    session, manifest = proposals_run(client)
    install_download(monkeypatch, [result(manifest, some_items(session["draft"]))])
    original = model_result.store_batch

    def fail_after_insert(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("fictional transaction failure")

    monkeypatch.setattr(model_result, "store_batch", fail_after_insert)
    assert reconcile(client, session["id"]) == "failed_permanent"
    assert stored(client, session["id"])[0:2] == ([], [])
    assert row(client, session["id"]).draft_json == session["draft"]


def test_snapshot_never_settles_or_rewrites_the_run(client, monkeypatch):
    import httpx
    from test_agent_conversation_bff import (
        _configure,
        _endpoint,
        _install_transport,
        _messages_response,
    )

    _configure(client)
    session, _ = proposals_run(client)

    async def forbidden(*args, **kwargs):
        pytest.fail("对话快照不能处理建模结果")

    def handler(request):
        if request.url.path.endswith("/messages"):
            return _messages_response([])
        return httpx.Response(200, json={"task_status": "finished", "task_id": TASK_ID})

    monkeypatch.setattr(DataAgentClient, "download", forbidden)
    _install_transport(monkeypatch, handler)
    response = client.get(_endpoint(session["id"]))
    assert response.status_code == 200, response.text
    assert response.json()["run"]["status"] == "finished"
    assert row(client, session["id"]).result_state != "done"


def test_events_decode_chinese_across_network_chunks(client, monkeypatch):
    from test_agent_conversation_bff import _configure, _endpoint

    _configure(client)
    session, _ = proposals_run(client)
    frame = ('data: ' + json.dumps({"seq_id": 1, "event_type": "content.delta", "data": {"text": "虚构客户"}}, ensure_ascii=False) + '\n\n').encode()

    async def stream(self, task_id, cursor):
        for byte in frame:
            yield bytes([byte])

    async def task(self, task_id):
        return {"task_id": task_id, "task_status": "finished"}

    monkeypatch.setattr(DataAgentClient, "stream", stream)
    monkeypatch.setattr(DataAgentClient, "task", task)
    response = client.get(_endpoint(session["id"]) + "/events")
    assert response.status_code == 200
    assert "虚构客户" in response.text and "\ufffd" not in response.text
    assert stored(client, session["id"])[0] == []


def test_state_cleanup_migration_removes_references_and_decision_cache(client):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    from ontofoundry_api.db_models import (
        ProposalDecisionItemRecord,
        ProposalDecisionRequestRecord,
    )

    session = create_session(client)
    batch = seed_batch(client, session, chain(session))
    path = Path(__file__).resolve().parents[1] / "src/ontofoundry_api/alembic/versions/20261026_000001_serial_atomic_modeling.py"
    spec = importlib.util.spec_from_file_location("serial_atomic", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with client.app.state.session_factory() as db:
        original = db.get(ProposalBatchRecord, batch["id"])
        values = {column.name: getattr(original, column.name) for column in ProposalBatchRecord.__table__.columns}
        failed_id, request_id = str(uuid4()), str(uuid4())
        db.add(ProposalBatchRecord(**{**values, "id": failed_id, "run_token": "fictional-failed", "status": "failed",
            "result_sha256": "f" * 64}))
        for item, status in zip(batch["items"], ["unacceptable", "unacceptable", "superseded"], strict=True):
            db.get(ProposalItemRecord, item["id"]).status = status
        db.add(ProposalDecisionRequestRecord(id=request_id, workspace_id=session["workspace_id"], session_id=session["id"],
            idempotency_key="fictional-old-decision", request_sha256="a" * 64,
            expected_session_revision=session["revision"], result_session_revision=session["revision"],
            response_json={"fictional": "cached old response"}, actor_id=row(client, session["id"]).created_by))
        db.flush()
        db.add(ProposalDecisionItemRecord(workspace_id=session["workspace_id"], session_id=session["id"],
            request_id=request_id, batch_id=batch["id"], item_id=batch["items"][0]["id"], decision="reject"))
        db.flush()
        with Operations.context(MigrationContext.configure(db.connection())):
            migration.upgrade()
        db.commit()
        db.expire_all()
        assert db.get(ProposalBatchRecord, failed_id) is None
        assert db.get(ProposalDecisionRequestRecord, request_id) is None
        remaining = list(db.scalars(select(ProposalItemRecord).where(ProposalItemRecord.batch_id == batch["id"])))
        assert len(remaining) == 1 and remaining[0].status == "rejected"


def test_unbound_dataset_is_proposed_but_not_accepted_until_bound(client):
    from test_t1_proposal_contract import create

    session = create_session(client)
    dataset = create("fictional-unbound", "dataset", {
        "name": "fictional_returns", "display_name": "虚构退货", "source_kind": "table",
        "schema_name": "public", "table_name": "fictional_returns", "columns": [],
    })
    batch = seed_batch(client, session, [dataset])
    response = decide(client, session, [(batch["items"][0]["id"], "accept")])
    assert response.status_code == 422, response.text
    assert response.json()["error"]["code"] == "DATASET_SOURCE_INVALID"
    assert current(client, session)["revision"] == session["revision"]
