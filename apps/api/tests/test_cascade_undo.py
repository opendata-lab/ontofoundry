"""Step 2c-1: undo and 退回待审 across unpublished batches, and the publish boundary."""

from copy import deepcopy
from uuid import uuid4

import pytest
from core1_fixtures import example_draft_json
from test_modeling import ROOT, create_session, publish
from test_proposal_undo import accepted
from test_t4_proposal_decisions import chain, create, current, decide, seed_batch, update

from ontofoundry_api.db_models import ModelingSessionRecord, ProposalItemRecord
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.services.errors import ServiceError


def property_on(root, name):
    return create(name, "property", {"display_name": name, "name": name, "owner_type_id": root["target_id"]})


def test_back_to_pending_takes_what_was_built_on_it_out_of_the_draft(client):
    session = create_session(client)
    session, root_batch = accepted(client, session, chain(session)[:1])
    root = root_batch["items"][0]
    session, later_batch = accepted(client, session, [property_on(root, "later_property")])
    later = later_batch["items"][0]

    response = decide(client, session, [(root["id"], "back_to_pending")])
    assert response.status_code == 200, response.text
    assert {r["proposal_id"]: (r["status"], r["triggered_by"]) for r in response.json()["results"]} == {
        root["id"]: ("pending", None),
        later["id"]: ("pending", root["id"]),
    }
    draft = current(client, session)["draft"]
    assert all(o["id"] != root["target_id"] for o in draft["object_types"])
    assert all(p["id"] != later["target_id"] for p in draft["properties"])
    with client.app.state.session_factory() as db:
        assert db.get(ProposalItemRecord, root["id"]).accepted_revision is None


def test_back_to_pending_only_applies_to_accepted_proposals(client):
    session = create_session(client)
    batch = seed_batch(client, session, chain(session)[:1])
    response = decide(client, session, [(batch["items"][0]["id"], "back_to_pending")])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROPOSAL_NOT_DECIDABLE"


def test_back_to_pending_refuses_instances(client):
    session = create_session(client)
    customer = next(o for o in session["draft"]["object_types"] if o["name"] == "customer")
    session, batch = accepted(client, session, [
        create("c", "material_object", {"type_id": customer["id"], "values": {"label": "月湾客户"}, "evidence": []}),
    ])
    response = decide(client, session, [(batch["items"][0]["id"], "back_to_pending")])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROPOSAL_NOT_RETURNABLE"


def test_back_to_pending_refuses_to_strand_items_in_a_read_only_agent_batch(client):
    session = create_session(client)
    session, root_batch = accepted(client, session, chain(session)[:1])
    root = root_batch["items"][0]
    session, later_batch = accepted(client, session, [property_on(root, "later_property")])
    with client.app.state.session_factory() as db:  # a newer run started after the later batch
        record = db.get(ModelingSessionRecord, session["id"])
        record.run_manifest_json = {"source_session_revision": session["revision"] + 1}
        record.human_batch_id = root_batch["id"]  # the root's own batch stays decidable
        db.commit()
    response = decide(client, session, [(root["id"], "back_to_pending")])
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "PROPOSAL_NOT_RETURNABLE"
    assert "请改用撤销" in response.json()["error"]["message"]


def test_undo_may_reach_a_read_only_agent_batch(client):
    session = create_session(client)
    session, root_batch = accepted(client, session, chain(session)[:1])
    root = root_batch["items"][0]
    session, later_batch = accepted(client, session, [property_on(root, "later_property")])
    with client.app.state.session_factory() as db:
        record = db.get(ModelingSessionRecord, session["id"])
        record.run_manifest_json = {"source_session_revision": session["revision"] + 1}
        db.commit()
    # Keep only the root's batch decidable (as a human batch is): the explicit item must
    # be decidable, the item the cascade reaches need not be.
    with client.app.state.session_factory() as db:
        record = db.get(ModelingSessionRecord, session["id"])
        record.human_batch_id = root_batch["id"]
        db.commit()
    response = decide(client, session, [(root["id"], "reject")])
    assert response.status_code == 200, response.text
    assert {r["proposal_id"]: r["status"] for r in response.json()["results"]} == {
        root["id"]: "rejected", later_batch["items"][0]["id"]: "rejected",
    }


def test_publishing_closes_the_proposals_decided_before_it(client):
    session = create_session(client)
    session, batch = accepted(client, session, chain(session)[:1])
    published = publish(client, session)
    assert published.status_code == 200, published.text
    session = published.json()["session"]
    for decision in ("reject", "back_to_pending"):
        response = decide(client, session, [(batch["items"][0]["id"], decision)])
        assert response.status_code == 409, response.text
        assert response.json()["error"]["code"] == "PROPOSAL_BATCH_PUBLISHED"
    detail = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}").json()
    assert detail["read_only"]
    # Work after the publish stays decidable.
    item = batch["items"][0]
    root = {"target_id": item["target_id"]}
    session, later_batch = accepted(client, session, [property_on(root, "after_publish")])
    undone = decide(client, session, [(later_batch["items"][0]["id"], "reject")])
    assert undone.status_code == 200, undone.text


def test_back_to_pending_and_cascades_are_in_the_change_log(client):
    session = create_session(client)
    session, root_batch = accepted(client, session, chain(session)[:1])
    root = root_batch["items"][0]
    session, later_batch = accepted(client, session, [property_on(root, "later_property")])
    later = later_batch["items"][0]
    assert decide(client, session, [(root["id"], "back_to_pending")]).status_code == 200
    events = client.get(ROOT + f"/sessions/{session['id']}/change-events", params={"target_id": later["target_id"]}).json()["items"]
    proposal_row = next(e for e in events if e["subject"] == "proposal" and e["action"] == "back_to_pending")
    draft_row = next(e for e in events if e["subject"] == "draft" and e["action"] == "removed")
    assert draft_row["cause_id"] == proposal_row["id"]
    root_events = client.get(ROOT + f"/sessions/{session['id']}/change-events", params={"target_id": root["target_id"]}).json()["items"]
    root_row = next(e for e in root_events if e["subject"] == "proposal" and e["action"] == "back_to_pending")
    assert proposal_row["cause_id"] == root_row["id"]


def test_publish_rechecks_the_merged_result(monkeypatch):
    """Another session bound a table; this one added a property: the merge is incomplete."""
    from ontofoundry_api.services import sessions

    latest = example_draft_json("01-basic-sales")
    merged = deepcopy(latest)
    customer = next(o for o in merged["object_types"] if o["name"] == "customer")
    merged["properties"].append({"id": str(uuid4()), "owner_type_id": customer["id"], "name": "vip_level", "value_kind": "string"})
    monkeypatch.setattr(sessions, "version_snapshot", lambda db, workspace_id, version_id: latest)
    with pytest.raises(ServiceError) as error:
        sessions._check_merged_definitions(None, "w", "v", OntologyDraft.model_validate(merged))
    assert error.value.code == "ACCEPT_CHECK_FAILED"
    assert any(issue.endswith("属性 vip_level（vip_level）未绑定") for issue in error.value.details["issues"])
    # Nothing changed: nothing to re-check.
    sessions._check_merged_definitions(None, "w", "v", OntologyDraft.model_validate(latest))


def test_undo_order_is_newest_first_across_three_changes(client):
    session = create_session(client)
    target = session["draft"]["object_types"][0]
    original = target.get("description", "")
    session, first = accepted(client, session, [update("object_type", target, description="一")])
    for text in ("二", "三"):
        target = session["draft"]["object_types"][0]
        session, _ = accepted(client, session, [update("object_type", target, description=text)])
    response = decide(client, session, [(first["items"][0]["id"], "reject")])
    assert response.status_code == 200, response.text
    assert len(response.json()["results"]) == 3
    assert current(client, session)["draft"]["object_types"][0].get("description", "") == original


def test_items_sent_back_to_pending_can_be_accepted_again_together(client):
    session = create_session(client)
    session, root_batch = accepted(client, session, chain(session)[:1])
    root = root_batch["items"][0]
    session, later_batch = accepted(client, session, [property_on(root, "later_property")])
    later = later_batch["items"][0]
    returned = decide(client, session, [(root["id"], "back_to_pending")])
    assert returned.status_code == 200, returned.text
    session = returned.json()["session"]
    # Accepting the property alone takes the object it needs, from the other batch.
    again = decide(client, session, [(later["id"], "accept")])
    assert again.status_code == 200, again.text
    assert {r["proposal_id"]: r["status"] for r in again.json()["results"]} == {
        later["id"]: "accepted", root["id"]: "accepted",
    }
    draft = current(client, session)["draft"]
    assert any(p["id"] == later["target_id"] for p in draft["properties"])
