"""Accepted proposals stay visible and can undo unchanged draft elements."""

from copy import deepcopy

import pytest
from sqlalchemy import select
from test_modeling import ROOT, create_session, save
from test_t4_proposal_decisions import chain, create, current, decide, seed_batch, update

from ontofoundry_api.db_models import (
    ProposalDecisionItemRecord,
    ProposalDecisionRequestRecord,
    ProposalItemRecord,
)
from ontofoundry_api.domain.canonical import snapshot_sha256


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
    proposal = create(
        "undo", "object_type", {"display_name": "可撤销实体", "name": "undo_type"}
    )
    if operation != "create":
        session, first = accepted(client, session, [proposal])
        element = next(
            e
            for e in session["draft"]["object_types"]
            if e["id"] == first["items"][0]["target_id"]
        )
        proposal = (
            update("object_type", element, description="接受的新描述")
            if operation == "update"
            else delete("object_type", element)
        )
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
    assert body["results"] == [
        {"proposal_id": item["id"], "status": "rejected", "reason": ""}
    ]
    assert (
        decide(client, session, [(item["id"], "reject")], key="undo-replay-key").json()
        == body
    )
    assert current(client, session)["revision"] == body["session"]["revision"]
    assert client.get(detail_url).json()["counts"]["rejected"] == 1
    with client.app.state.session_factory() as db:
        stored = db.get(ProposalItemRecord, item["id"])
        assert stored.status == "rejected" and stored.accepted_revision is None
        assert stored.decided_by and stored.decided_at
        record = db.scalar(
            select(ProposalDecisionRequestRecord).where(
                ProposalDecisionRequestRecord.session_id == session["id"],
                ProposalDecisionRequestRecord.idempotency_key == "undo-replay-key",
            )
        )
        assert record.result_session_revision == body["session"]["revision"]
        assert (
            db.get(ProposalDecisionItemRecord, (record.id, item["id"])).decision == "reject"
        )
    restored = decide(client, body["session"], [(item["id"], "restore")])
    assert restored.status_code == 200, restored.text
    assert restored.json()["results"][0]["status"] == "pending"
    assert restored.json()["session"]["pending_proposal_count"] == 1


@pytest.mark.parametrize("later_change", ["manual", "proposal"])
def test_undo_refuses_later_edits_without_changing_draft_or_decision(client, later_change):
    session = create_session(client)
    target = session["draft"]["object_types"][0]
    session, batch = accepted(
        client, session, [update("object_type", target, description="第一次接受")]
    )
    target = session["draft"]["object_types"][0]
    if later_change == "manual":
        draft = deepcopy(session["draft"])
        draft["object_types"][0]["description"] = "后续人工修改"
        response = save(client, session, draft)
        assert response.status_code == 200, response.text
        session = response.json()
    else:
        session, _ = accepted(
            client, session, [update("object_type", target, description="后续提案修改")]
        )
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
    target = next(
        e
        for e in session["draft"]["object_types"]
        if e["id"] == batch["items"][0]["target_id"]
    )
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
        assert all(
            db.get(ProposalItemRecord, i["id"]).status == "accepted" for i in batch["items"]
        )


def test_undo_validates_the_whole_draft_before_writing(client):
    session = create_session(client)
    session, root_batch = accepted(client, session, chain(session)[:1])
    root = root_batch["items"][0]
    # A later proposal refers to the root without a recorded item dependency.
    session, _ = accepted(
        client,
        session,
        [
            create(
                "later",
                "property",
                {
                    "display_name": "后续属性",
                    "name": "later_property",
                    "owner_type_id": root["target_id"],
                },
            )
        ],
    )
    refused = decide(client, session, [(root["id"], "reject")])
    assert refused.status_code == 422, refused.text
    assert refused.json()["error"]["code"] == "VALIDATION_FAILED"
    assert "撤销后草稿校验未通过" in refused.json()["error"]["message"]
    assert current(client, session)["draft"] == session["draft"]
    assert current(client, session)["revision"] == session["revision"]


def test_undo_preserves_unrelated_manual_edits(client):
    session = create_session(client)
    target = session["draft"]["object_types"][0]
    session, batch = accepted(
        client, session, [update("object_type", target, description="提案描述")]
    )
    draft = deepcopy(session["draft"])
    draft["object_types"][1]["description"] = "另一个元素的修改"
    edited = save(client, session, draft)
    assert edited.status_code == 200, edited.text
    response = decide(client, edited.json(), [(batch["items"][0]["id"], "reject")])
    assert response.status_code == 200, response.text
    result = response.json()["session"]["draft"]
    assert result["object_types"][0] == target
    assert result["object_types"][1] == draft["object_types"][1]


def test_rule_undo_preserves_stable_id_without_legacy_owner_history(client):
    session = create_session(client)
    owner_id = session["draft"]["object_types"][0]["id"]
    session, batch = accepted(
        client,
        session,
        [
            create(
                "rule",
                "rule",
                {
                    "display_name": "规则",
                    "name": "rule",
                    "expression": "true",
                    "owner_kind": "object_type",
                    "owner_id": owner_id,
                    "rule_kind": "constraint",
                },
            )
        ],
    )
    response = decide(client, session, [(batch["items"][0]["id"], "reject")])
    assert response.status_code == 200, response.text
    assert response.json()["session"]["draft"]["rules"] == []
