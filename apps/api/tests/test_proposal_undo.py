"""Accepted proposals stay visible and can undo unchanged draft elements."""

from copy import deepcopy

import pytest
from sqlalchemy import select
from test_instance_queries import mapped_session
from test_modeling import ROOT, create_session, save
from test_t4_proposal_decisions import chain, create, current, decide, seed_batch, update

from ontofoundry_api.db_models import (
    ProposalDecisionItemRecord,
    ProposalDecisionRequestRecord,
    ProposalItemRecord,
)
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.domain.runtime_views import (
    apply_legacy_mappings,
    apply_mapping_form,
    legacy_mapping_form,
)


def accepted(client, session, proposals):
    batch = seed_batch(client, session, proposals)
    response = decide(client, session, [(i["id"], "accept") for i in batch["items"]])
    assert response.status_code == 200, response.text
    return response.json()["session"], batch


def delete(kind, element):
    proposal = update(kind, element)
    return {**proposal, "operation": "delete", "after": None}


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_undo_restores_element_and_records_a_replayable_decision(client, operation):
    session = create_session(client)
    proposal = create("undo", "object_type", {"name": "可撤销实体", "technical_name": "undo_type"})
    if operation != "create":
        session, first = accepted(client, session, [proposal])
        element = next(e for e in session["draft"]["object_types"] if e["id"] == first["items"][0]["target_id"])
        proposal = update("object_type", element, description="接受的新描述") if operation == "update" else delete("object_type", element)
    before = deepcopy(session["draft"])
    session, batch = accepted(client, session, [proposal])
    (item,) = batch["items"]
    detail_url = ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}"
    detail = client.get(detail_url).json()
    assert detail["items"][0]["status"] == "accepted"
    assert detail["counts"]["accepted"] == 1

    response = decide(client, session, [(item["id"], "reject")], key="undo-replay-key")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"session", "results", "validation"}
    assert body["session"]["draft"] == before
    assert body["session"]["draft_sha256"] == snapshot_sha256(before)
    assert body["session"]["revision"] == session["revision"] + 1
    assert body["results"] == [{"proposal_id": item["id"], "status": "rejected", "reason": ""}]
    assert decide(client, session, [(item["id"], "reject")], key="undo-replay-key").json() == body
    assert current(client, session)["revision"] == body["session"]["revision"]
    assert client.get(detail_url).json()["counts"]["rejected"] == 1
    with client.app.state.session_factory() as db:
        stored = db.get(ProposalItemRecord, item["id"])
        assert stored.status == "rejected" and stored.accepted_revision is None
        assert stored.decided_by and stored.decided_at
        record = db.scalar(select(ProposalDecisionRequestRecord).where(
            ProposalDecisionRequestRecord.session_id == session["id"],
            ProposalDecisionRequestRecord.idempotency_key == "undo-replay-key",
        ))
        assert record.result_session_revision == body["session"]["revision"]
        assert db.get(ProposalDecisionItemRecord, (record.id, item["id"])).decision == "reject"
    restored = decide(client, body["session"], [(item["id"], "restore")])
    assert restored.status_code == 200, restored.text
    assert restored.json()["results"][0]["status"] == "pending"
    assert restored.json()["session"]["pending_proposal_count"] == 1


@pytest.mark.parametrize("later_change", ["manual", "proposal"])
def test_undo_refuses_later_edits_without_changing_draft_or_decision(client, later_change):
    session = create_session(client)
    target = session["draft"]["object_types"][0]
    session, batch = accepted(client, session, [update("object_type", target, description="第一次接受")])
    target = session["draft"]["object_types"][0]
    if later_change == "manual":
        draft = deepcopy(session["draft"])
        draft["object_types"][0]["description"] = "后续人工修改"
        response = save(client, session, draft)
        assert response.status_code == 200, response.text
        session = response.json()
    else:
        session, _ = accepted(client, session, [update("object_type", target, description="后续提案修改")])
    (item,) = batch["items"]
    refused = decide(client, session, [(item["id"], "reject")])
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "PROPOSAL_UNDO_CONFLICT"
    assert refused.json()["error"]["message"] == "该元素在接受后又被修改，不能直接撤销"
    assert current(client, session)["draft"] == session["draft"]
    assert current(client, session)["revision"] == session["revision"]
    with client.app.state.session_factory() as db:
        assert db.get(ProposalItemRecord, item["id"]).status == "accepted"


def test_undo_of_a_delete_refuses_a_recreated_target(client):
    session = create_session(client)
    session, batch = accepted(client, session, chain(session)[:1])
    target = next(e for e in session["draft"]["object_types"] if e["id"] == batch["items"][0]["target_id"])
    session, batch = accepted(client, session, [delete("object_type", target)])
    draft = deepcopy(session["draft"])
    draft["object_types"].append({**target, "description": "人工重新创建"})
    edited = save(client, session, draft)
    assert edited.status_code == 200, edited.text
    refused = decide(client, edited.json(), [(batch["items"][0]["id"], "reject")])
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "PROPOSAL_UNDO_CONFLICT"
    assert current(client, session)["draft"] == draft


def test_undo_requires_accepted_dependents_and_reverts_them_first(client):
    original = create_session(client)
    proposals = chain(original)
    proposals[2]["depends_on"] = ["po-no"]
    session, batch = accepted(client, original, proposals)
    root, prop, link = batch["items"]
    refused = decide(client, session, [(root["id"], "reject")])
    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "DEPENDENCY_INCOMPLETE"
    assert current(client, session)["draft"] == session["draft"]
    # Request ordering must not determine the draft application ordering.
    response = decide(client, session, [(i["id"], "reject") for i in (root, prop, link)])
    assert response.status_code == 200, response.text
    assert response.json()["session"]["draft"] == original["draft"]
    assert response.json()["session"]["revision"] == session["revision"] + 1


def test_a_changed_dependent_makes_group_undo_atomic(client):
    session = create_session(client)
    session, batch = accepted(client, session, chain(session))
    draft = deepcopy(session["draft"])
    draft["properties"][-1]["description"] = "人工保留"
    response = save(client, session, draft)
    assert response.status_code == 200, response.text
    session = response.json()
    refused = decide(client, session, [(i["id"], "reject") for i in batch["items"]])
    assert refused.status_code == 409
    assert current(client, session)["draft"] == draft
    with client.app.state.session_factory() as db:
        assert all(db.get(ProposalItemRecord, i["id"]).status == "accepted" for i in batch["items"])


def test_undo_validates_the_whole_draft_before_writing(client):
    session = create_session(client)
    session, root_batch = accepted(client, session, chain(session)[:1])
    root = root_batch["items"][0]
    # A later proposal refers to the root without a recorded item dependency.
    session, _ = accepted(client, session, [create("later", "property", {
        "name": "后续属性", "technical_name": "later_property", "owner_type_id": root["target_id"],
    })])
    refused = decide(client, session, [(root["id"], "reject")])
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "VALIDATION_FAILED"
    assert "撤销后草稿校验未通过" in refused.json()["error"]["message"]
    assert current(client, session)["draft"] == session["draft"]
    assert current(client, session)["revision"] == session["revision"]


def test_undo_preserves_unrelated_manual_edits(client):
    session = create_session(client)
    target = session["draft"]["object_types"][0]
    session, batch = accepted(client, session, [update("object_type", target, description="提案描述")])
    draft = deepcopy(session["draft"])
    draft["object_types"][1]["description"] = "另一个元素的修改"
    edited = save(client, session, draft)
    assert edited.status_code == 200, edited.text
    response = decide(client, edited.json(), [(batch["items"][0]["id"], "reject")])
    assert response.status_code == 200, response.text
    result = response.json()["session"]["draft"]
    assert result["object_types"][0] == target
    assert result["object_types"][1] == draft["object_types"][1]


@pytest.mark.parametrize("operation", ["create", "delete"])
def test_undo_restores_created_or_deleted_concept_context(client, operation):
    session = create_session(client)
    proposal = create("context", "object_type", {
        "name": "上下文实体", "technical_name": "context_undo",
        "concept_context": {"synonyms": ["别名"], "instructions": "上下文"},
    })
    if operation == "delete":
        session, batch = accepted(client, session, [proposal])
        target = next(e for e in session["draft"]["object_types"] if e["id"] == batch["items"][0]["target_id"])
        proposal = delete("object_type", target)
    before = deepcopy(session["draft"])
    session, batch = accepted(client, session, [proposal])
    response = decide(client, session, [(batch["items"][0]["id"], "reject")])
    assert response.status_code == 200, response.text
    assert response.json()["session"]["draft"] == before


@pytest.mark.parametrize("kind", ["object_type", "value_type"])
def test_undo_restores_concept_context_and_protects_later_context_edits(client, kind):
    session = create_session(client)
    if kind == "value_type":
        session, batch = accepted(client, session, [create("value", kind, {"name": "金额概念", "technical_name": "undo_value", "concept": "UndoValue"})])
        target_id = batch["items"][0]["target_id"]
        target = next(e for e in session["draft"]["value_types"] if e["id"] == target_id)
    else:
        target = session["draft"]["object_types"][0]
    before = deepcopy(session["draft"])
    session, batch = accepted(client, session, [update(kind, target, concept_context={"synonyms": ["别名"], "instructions": "提案上下文"})])
    item = batch["items"][0]
    changed = deepcopy(session["draft"])
    changed["extension_v4"]["concept_context"][target["id"]]["instructions"] = "后续修改"
    edited = save(client, session, changed)
    assert edited.status_code == 200, edited.text
    assert decide(client, edited.json(), [(item["id"], "reject")]).status_code == 409
    restored = save(client, edited.json(), session["draft"])
    assert restored.status_code == 200, restored.text
    undone = decide(client, restored.json(), [(item["id"], "reject")])
    assert undone.status_code == 200, undone.text
    assert undone.json()["session"]["draft"] == before


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_rule_undo_restores_owner_refs_and_native_presence(client, operation):
    session = create_session(client)
    session, batch = accepted(client, session, chain(session)[:1])
    owner_id = batch["items"][0]["target_id"]
    proposal = create("rule", "rule", {
        "name": "可撤销规则", "technical_name": "undo_rule", "expression": "true",
        "owner_kind": "object_type", "owner_id": owner_id, "rule_kind": "constraint",
    })
    if operation != "create":
        session, batch = accepted(client, session, [proposal])
        rule = next(e for e in session["draft"]["rules"] if e["id"] == batch["items"][0]["target_id"])
        proposal = update("rule", rule, rule_kind="derivation") if operation == "update" else delete("rule", rule)
    before = deepcopy(session["draft"])
    session, batch = accepted(client, session, [proposal])
    response = decide(client, session, [(batch["items"][0]["id"], "reject")])
    assert response.status_code == 200, response.text
    assert response.json()["session"]["draft"] == before


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_mapping_undo_uses_the_compatibility_form(client, mapped_session, operation):
    session, _, _ = mapped_session
    form = legacy_mapping_form(session["draft"])
    draft = apply_mapping_form(session["draft"], joins={key: None for key in form["joins"]})
    response = save(client, session, draft)
    assert response.status_code == 200, response.text
    session = response.json()
    mapping = legacy_mapping_form(session["draft"])["mappings"][0]
    if operation == "create":
        removed = legacy_mapping_form(session["draft"])
        draft = apply_legacy_mappings(session["draft"], removed["mappings"][1:], {key: None for key in removed["joins"]})
        response = save(client, session, draft)
        assert response.status_code == 200, response.text
        session = response.json()
        proposal = create("mapping", "mapping", {key: value for key, value in mapping.items() if key != "id"})
    else:
        proposal = update("mapping", mapping, fields={}) if operation == "update" else delete("mapping", mapping)
    before = legacy_mapping_form(session["draft"])["mappings"]
    session, batch = accepted(client, session, [proposal])
    response = decide(client, session, [(batch["items"][0]["id"], "reject")])
    assert response.status_code == 200, response.text
    assert legacy_mapping_form(response.json()["session"]["draft"])["mappings"] == before


def test_created_mapping_is_removed_before_undoing_its_created_concept(client):
    session = create_session(client)
    original = deepcopy(session["draft"])
    session, batch = accepted(client, session, [
        create("concept", "object_type", {"name": "映射实体", "technical_name": "mapped_undo"}),
        create("mapping", "mapping", {
            "type_id": {"client_ref": "concept"}, "connection_alias": "撤销连接",
            "table_name": "undo_table", "key_column": "id", "fields": {},
        }),
    ])
    response = decide(client, session, [(i["id"], "reject") for i in batch["items"]])
    assert response.status_code == 200, response.text
    draft = response.json()["session"]["draft"]
    assert draft["object_types"] == original["object_types"]
    assert legacy_mapping_form(draft)["mappings"] == legacy_mapping_form(original)["mappings"]


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_join_undo_restores_the_owner_oriented_join_and_refuses_later_edits(client, mapped_session, operation):
    session, supplier, material = mapped_session
    link = next(e for e in session["draft"]["link_types"] if e["owner_ref"]["ref"] == supplier["id"] and e["roles"][0]["concept"]["ref"] == material["id"])
    before = legacy_mapping_form(session["draft"])["joins"]
    proposal = update("link_type", link, data_join=None) if operation == "update" else delete("link_type", link)
    session, batch = accepted(client, session, [proposal])
    response = decide(client, session, [(batch["items"][0]["id"], "reject")])
    assert response.status_code == 200, response.text
    assert legacy_mapping_form(response.json()["session"]["draft"])["joins"] == before
    session = response.json()["session"]
    link = next(e for e in session["draft"]["link_types"] if e["id"] == link["id"])
    session, batch = accepted(client, session, [update("link_type", link, description="只改描述")])
    draft = apply_mapping_form(session["draft"], joins={link["id"]: None})
    edited = save(client, session, draft)
    assert edited.status_code == 200, edited.text
    refused = decide(client, edited.json(), [(batch["items"][0]["id"], "reject")])
    assert refused.status_code == 409
    assert current(client, session)["draft"] == draft


def test_undo_of_a_created_link_removes_its_native_join(client, mapped_session):
    session, supplier, material = mapped_session
    original = deepcopy(session["draft"])
    proposal = create("joined", "link_type", {
        "name": "可撤销映射关系", "technical_name": "undo_joined_link",
        "source_type_id": supplier["id"], "target_type_id": material["id"],
        "data_join": {"owner_columns": ["code"], "role_columns": ["supplier_code"]},
    })
    session, batch = accepted(client, session, [proposal])
    item = batch["items"][0]
    assert legacy_mapping_form(session["draft"])["joins"][item["target_id"]]
    response = decide(client, session, [(item["id"], "reject")])
    assert response.status_code == 200, response.text
    draft = response.json()["session"]["draft"]
    assert draft == original


def test_legacy_join_decisions_without_before_history_are_refused_safely(client, mapped_session):
    session, supplier, material = mapped_session
    link = next(e for e in session["draft"]["link_types"] if e["owner_ref"]["ref"] == supplier["id"] and e["roles"][0]["concept"]["ref"] == material["id"])
    session, batch = accepted(client, session, [update("link_type", link, data_join=None)])
    item = batch["items"][0]
    with client.app.state.session_factory() as db:
        record = db.scalar(select(ProposalDecisionRequestRecord).where(
            ProposalDecisionRequestRecord.session_id == session["id"],
            ProposalDecisionRequestRecord.result_session_revision == session["revision"],
        ))
        record.response_json = {key: value for key, value in record.response_json.items() if key != "_undo"}
        db.commit()
    refused = decide(client, session, [(item["id"], "reject")])
    assert refused.status_code == 409, refused.text
    assert "缺少接受前的关系映射记录" in refused.json()["error"]["message"]
    assert current(client, session)["draft"] == session["draft"]


def test_legacy_rule_decisions_without_owner_history_are_refused_safely(client):
    session = create_session(client)
    owner_id = session["draft"]["object_types"][0]["id"]
    session, batch = accepted(client, session, [create("legacy", "rule", {
        "name": "旧规则", "technical_name": "legacy_undo_rule", "expression": "true",
        "owner_kind": "object_type", "owner_id": owner_id, "rule_kind": "constraint",
    })])
    with client.app.state.session_factory() as db:
        record = db.scalar(select(ProposalDecisionRequestRecord).where(
            ProposalDecisionRequestRecord.session_id == session["id"],
            ProposalDecisionRequestRecord.result_session_revision == session["revision"],
        ))
        record.response_json = {key: value for key, value in record.response_json.items() if key != "_undo"}
        db.commit()
    refused = decide(client, session, [(batch["items"][0]["id"], "reject")])
    assert refused.status_code == 409, refused.text
    assert "缺少接受前的规则引用记录" in refused.json()["error"]["message"]
    assert current(client, session)["draft"] == session["draft"]
