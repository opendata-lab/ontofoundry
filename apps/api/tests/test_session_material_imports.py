"""Ossie imports through a modeling turn, with a fake DataAgent transport."""

import hashlib
import json

import pytest
from sqlalchemy import select
from test_core1_ossie_import import (
    dataset,
    document,
    entity,
    expression,
    field,
    mapped_concept,
    ontology_map,
    rel,
)
from test_linked_tables import link, register
from test_modeling import ROOT
from test_request_material import create_session, send
from test_stepwise_modeling import fake_agent as fake_agent_fixture
from test_stepwise_modeling import set_row, work_pack
from test_t1_proposal_contract import items_only
from test_t4_proposal_decisions import create, decide, seed_batch

from ontofoundry_api.api import agent_conversation
from ontofoundry_api.db_models import (
    MaterialRecord,
    ModelingSessionRecord,
    ProposalBatchRecord,
    ProposalItemRecord,
    SessionMaterialImportRecord,
)
from ontofoundry_api.services import proposal_submit, session_material_imports
from ontofoundry_api.services.dataagent import DataAgentError
from ontofoundry_api.services.material_store import store_text_material
from ontofoundry_api.services.run_credentials import RunGrant, issue

fake_agent = fake_agent_fixture


def attach(client, data=None):
    raw = json.dumps(
        data if data is not None else document(entity("fiction_parcel")),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    response = client.post(
        ROOT + "/materials", params={"name": "虚构货运.ossie.json"}, content=raw
    )
    assert response.status_code == 201, response.text
    session = create_session(client)
    response = client.patch(
        ROOT + f"/sessions/{session['id']}",
        json={"revision": session["revision"], "material_ids": [response.json()["id"]]},
    )
    assert response.status_code == 200, response.text
    return response.json(), raw


def turn(client, session, uploads, *, content="继续"):
    response = send(client, session["id"], content=content)
    assert response.status_code == 202, response.text
    with client.app.state.session_factory() as db:
        manifest = db.get(ModelingSessionRecord, session["id"]).run_manifest_json
    pack = work_pack(uploads, manifest)
    return manifest, pack, json.loads(uploads[pack["import_report"]["file"]])["materials"]


def read_rows(client, session):
    with client.app.state.session_factory() as db:
        return tuple(
            list(db.scalars(select(model).where(model.session_id == session["id"])))
            for model in (
                SessionMaterialImportRecord,
                ProposalBatchRecord,
                ProposalItemRecord,
            )
        )


def result_auth(client, session, manifest):
    with client.app.state.session_factory() as db:
        actor = db.get(ModelingSessionRecord, session["id"]).created_by
    token = issue(
        client.app.state.settings.session_secret,
        RunGrant(
            session["workspace_id"],
            session["id"],
            manifest["run_token"],
            session["base_version_id"],
            actor,
        ),
    )
    return ROOT + f"/sessions/{session['id']}/proposals", {
        "Authorization": "Bearer " + token
    }


def test_pinned_scope_and_original_single_line_evidence(client, fake_agent):
    receipts = dataset(
        "receipts",
        source="retail.FICTION_RECEIPTS",
        fields=[field("id")],
        primary_key=["id"],
    )
    refunds = dataset(
        "refunds",
        source="retail.fiction_refunds",
        fields=[field("id"), field("amount")],
        primary_key=["id"],
    )
    mapping = ontology_map(
        [receipts, refunds],
        concepts=[
            mapped_concept("fiction_receipt", "receipts.id"),
            mapped_concept("fiction_refund", "refunds.id"),
        ],
        metrics=[
            {
                "name": "fiction_refund_total",
                "datatype": "Decimal",
                "expression": expression("SUM(refunds.amount)"),
            }
        ],
    )
    data = document(
        entity(
            "fiction_receipt",
            identify_by=["id"],
            relationships=[rel("id", "String", source="fiction_receipt")],
        ),
        entity(
            "fiction_refund",
            identify_by=["id"],
            relationships=[rel("id", "String", source="fiction_refund")],
        ),
        ontology_mappings=[mapping],
    )
    session, raw = attach(client, data)
    connection = register(client, ["fiction_receipts", "fiction_refunds"])
    set_row(client, session["id"], linked_tables=[link(connection, "fiction_receipts")])
    uploads, _ = fake_agent
    manifest, pack, [report] = turn(client, session, uploads)
    assert len(uploads[manifest["input_files"]["work_pack"]]) <= 8192
    assert "计划逐项列出快照列" in pack["import_report"]["note"]
    assert pack["import_report"]["missing_table_count"] == 1
    assert {item["target_kind"] for item in report["excluded"]} == {
        "dataset",
        "mapping",
        "metric",
    }
    context = json.loads(uploads[pack["context_file"]])
    [pinned_dataset] = [
        item for item in context["draft"]["datasets"] if item["name"] == "receipts"
    ]
    assert pinned_dataset["connection_id"] == connection
    assert pinned_dataset["table_name"] == "fiction_receipts"
    assert not any(item["name"] == "refunds" for item in context["draft"]["datasets"])
    [record], [batch], items = read_rows(client, session)
    assert batch.producer_json["kind"] == "import"
    assert batch.run_token == "import:" + record.id
    assert batch.source_session_revision == manifest["source_session_revision"]
    assert all(
        item.batch_id == record.batch_id and item.status == "pending" for item in items
    )
    item = next(p for p in items if p.target_id == pinned_dataset["id"])
    (evidence,) = item.evidence_json
    assert (
        evidence["material_sha256"]
        == hashlib.sha256(raw).hexdigest()
        == record.material_sha256
    )
    assert evidence["locator"] == {"line_start": 1, "line_end": 1}
    assert evidence["quote"] in raw.decode() and '"name":"receipts"' in evidence["quote"]


def test_pending_proposal_skips_import_until_review(client, fake_agent):
    session, _ = attach(client)
    pending = seed_batch(
        client, session, [create("dock", "object_type", {"name": "fiction_dock"})]
    )
    set_row(client, session["id"], human_batch_id=pending["id"])
    uploads, _ = fake_agent
    _, pack, [report] = turn(client, session, uploads)
    assert "请先处理待审提案" in pack["import_report"]["note"]
    assert report["status"] == "skipped"
    records, batches, _ = read_rows(client, session)
    assert not records and [b.id for b in batches] == [pending["id"]]
    set_row(client, session["id"], task_status="cancelled")
    current = client.get(ROOT + f"/sessions/{session['id']}").json()
    refused = decide(client, current, [(pending["items"][0]["id"], "reject")])
    assert refused.status_code == 200, refused.text
    _, _, [report] = turn(client, session, uploads)
    assert report["status"] == "imported"


def test_invalid_ossie_continues_the_run_with_the_validation_report(client, fake_agent):
    session, _ = attach(client, {"version": "invalid", "ontology": []})
    manifest, pack, [report] = turn(client, session, fake_agent[0])
    assert report["status"] == "failed"
    assert report["translation"]["issues"][0]["construct"] == "document"
    assert manifest["pending_proposals"] == []
    assert "按普通材料阅读" in pack["import_report"]["note"]
    [record], batches, items = read_rows(client, session)
    assert record.batch_id is None and not batches and not items


def test_import_failure_rolls_back_batch_and_only_its_new_files(
    client, fake_agent, monkeypatch
):
    session, _ = attach(client)
    original = session_material_imports.store_import_batch
    content = "虚构仓库的货运资料和请求原文可以继续用于本轮普通建模。"
    temporary = "虚构回滚收据"

    def fail_after_storing(db, settings, session, *args, **kwargs):
        original(db, settings, session, *args, **kwargs)
        store_text_material(db, settings, session.workspace_id, "虚构收据.md", temporary)
        raise RuntimeError("fixture failure after staging")

    monkeypatch.setattr(session_material_imports, "store_import_batch", fail_after_storing)
    manifest, _, [report] = turn(client, session, fake_agent[0], content=content)
    assert report["status"] == "failed" and not manifest["pending_proposals"]
    [record], batches, items = read_rows(client, session)
    assert record.batch_id is None and not batches and not items
    data_dir = client.app.state.settings.data_dir / session["workspace_id"]
    for text, exists in ((temporary, False), (content, True)):
        sha = hashlib.sha256(text.encode()).hexdigest()
        assert (data_dir / (sha + ".md")).exists() == exists
        with client.app.state.session_factory() as db:
            assert (
                bool(
                    db.scalar(select(MaterialRecord.id).where(MaterialRecord.sha256 == sha))
                )
                == exists
            )


@pytest.mark.parametrize("decision", ["accept", "reject"])
def test_cancel_leaves_import_reviewable(client, fake_agent, monkeypatch, decision):
    session, _ = attach(client)
    original_client = agent_conversation._client

    async def cancel(_task_id):
        return {"task_status": "suspended"}

    def with_cancel(*args):
        agent = original_client(*args)
        agent.cancel = cancel
        return agent

    monkeypatch.setattr(agent_conversation, "_client", with_cancel)
    manifest, _, _ = turn(client, session, fake_agent[0])
    [record], [batch], [proposal] = read_rows(client, session)
    assert batch.source_session_revision == manifest["source_session_revision"]
    base = ROOT + f"/sessions/{session['id']}"
    response = client.post(
        base + "/agent-conversation/cancel", json={"task_id": "fictional-task-1"}
    )
    assert response.status_code == 200 and response.json()["status"] == "cancelled", (
        response.text
    )
    response = decide(client, client.get(base).json(), [(proposal.id, decision)])
    assert response.status_code == 200, response.text
    following, _, _ = turn(client, session, fake_agent[0])
    assert "resume" not in following and following["baseline"] != manifest["baseline"]
    [same_record], [same_batch], _ = read_rows(client, session)
    assert same_record.id == record.id and same_batch.id == batch.id


def test_failed_delivery_reuses_batch_and_report_and_keeps_review_open(
    client, fake_agent, monkeypatch
):
    session, _ = attach(client)
    set_row(client, session["id"], dataagent_topic_id="topic-1")
    original_client = agent_conversation._client

    async def reject_delivery(**_):
        raise DataAgentError("虚构投递失败", status_code=422)

    def failing_client(*args):
        agent = original_client(*args)
        agent.deliver = reject_delivery
        return agent

    with monkeypatch.context() as patch:
        patch.setattr(agent_conversation, "_client", failing_client)
        response = send(client, session["id"], "继续")
    assert response.status_code >= 400, response.text
    [record], [batch], [proposal] = read_rows(client, session)

    def unexpected_retry(*_args, **_kwargs):
        pytest.fail("the committed SHA must not be converted again")

    monkeypatch.setattr(session_material_imports, "_convert", unexpected_retry)
    manifest, _, [report] = turn(client, session, fake_agent[0])
    assert report == record.report_json
    assert manifest["resume"] and manifest["session_material_import_batch_id"] == batch.id
    [same_record], [same_batch], _ = read_rows(client, session)
    assert same_record.id == record.id and same_batch.id == batch.id
    set_row(client, session["id"], task_status="cancelled")
    current = client.get(ROOT + f"/sessions/{session['id']}").json()
    response = decide(client, current, [(proposal.id, "accept")])
    assert response.status_code == 200, response.text


def test_agent_revises_imported_create_and_retains_original_evidence(client, fake_agent):
    session, _ = attach(client)
    manifest, _, _ = turn(client, session, fake_agent[0])
    _, [batch], [proposal] = read_rows(client, session)
    url, headers = result_auth(client, session, manifest)
    revised = {
        "operation": "update",
        "target_kind": "object_type",
        "target_id": proposal.target_id,
        "after": {
            **{k: v for k, v in proposal.after_json.items() if k != "id"},
            "display_name": "虚构包裹",
        },
    }
    result = client.post(url, headers=headers, json={"items": items_only([revised])}).json()
    assert result["passed"], result
    _, _, proposals = read_rows(client, session)
    [merged] = [p for p in proposals if p.status == "pending"]
    assert (merged.batch_id, merged.operation, merged.target_id) == (
        result["batch_id"],
        "create",
        proposal.target_id,
    )
    assert merged.after_json["display_name"] == "虚构包裹"
    assert merged.evidence_json == proposal.evidence_json
    assert next(p for p in proposals if p.batch_id == batch.id).status == "superseded"


def test_merged_limit_rejects_a_batch_without_superseding_the_import(
    client, fake_agent, monkeypatch
):
    session, _ = attach(client)
    manifest, _, _ = turn(client, session, fake_agent[0])
    monkeypatch.setattr(proposal_submit, "MAX_ITEMS", 1)
    url, headers = result_auth(client, session, manifest)
    result = client.post(
        url,
        headers=headers,
        json={
            "items": items_only([create("dock", "object_type", {"name": "fiction_dock"})]),
        },
    ).json()
    assert not result["passed"] and result["errors"][0]["code"] == "RESULT_SCHEMA_INVALID"
    _, [batch], [proposal] = read_rows(client, session)
    assert proposal.batch_id == batch.id and proposal.status == "pending"
