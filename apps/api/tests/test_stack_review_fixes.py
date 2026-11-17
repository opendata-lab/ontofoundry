"""Regression tests for the Codex review of the write-pipeline stack (2026-11-17)."""

import uuid
from uuid import uuid4

from sqlalchemy import update
from test_instance_store import (
    accept_all,
    baseline,
    create_instance,
    instance_update,
    staged_batch,
)
from test_modeling import ROOT, create_session, publish
from test_rule_acceptance import with_rules
from test_t4_proposal_decisions import create, decide, seed_batch

from ontofoundry_api.db_models import ProposalItemRecord


def entry_for(client, session, target_id):
    return next(i for i in baseline(client, session)["items"] if i["target_id"] == target_id)


def test_a_published_instance_can_be_changed_twice_before_publishing(client):
    """1: the second change is checked against this session's draft revision."""
    session = create_session(client)
    entry = baseline(client, session)["items"][0]
    session, _ = accept_all(client, session, [instance_update(entry, values={"label": "第一次"})])
    session, _ = accept_all(client, session, [instance_update(entry_for(client, session, entry["target_id"]), values={"label": "第二次"})])
    assert entry_for(client, session, entry["target_id"])["element"]["values"]["label"] == "第二次"
    deletion = {**instance_update(entry_for(client, session, entry["target_id"])), "operation": "delete", "after": None}
    session, _ = accept_all(client, session, [deletion])
    assert all(i["target_id"] != entry["target_id"] for i in baseline(client, session)["items"])


def test_new_evidence_on_a_published_instance_survives_publish(client):
    """2: publishing a draft does not re-check its evidence without a material lookup."""
    session = create_session(client)
    material = client.post(ROOT + "/materials", params={"name": "月湾客户补充.md"}, content="月湾客户已登记".encode()).json()
    entry = baseline(client, session)["items"][0]
    change = instance_update(entry, evidence=[{
        "id": str(uuid4()), "kind": "material", "material_id": material["id"], "material_sha256": material["sha256"],
        "locator": {"line_start": 1, "line_end": 1}, "quote": "月湾客户"}])
    session, _ = accept_all(client, session, [change])
    published = publish(client, session)
    assert published.status_code == 200, published.text
    public = next(i for i in client.get(ROOT + "/instances").json()["items"] if i["target_id"] == entry["target_id"])
    assert [e["material_id"] for e in public["element"]["evidence"] if e["kind"] == "material"][-1] == material["id"]


def test_deleting_a_published_instance_keeps_other_sessions_pending_relations(client):
    """3: publishing a delete refuses rather than deleting another session's relation."""
    first, second = create_session(client), create_session(client)
    customer = entry_for(client, first, baseline(client, first)["items"][0]["target_id"])
    order = next(t for t in second["draft"]["object_types"] if t["name"] == "order")
    link_type = second["draft"]["link_types"][0]
    second, links = accept_all(client, second, [
        create("order-x", "material_object", {"type_id": order["id"], "values": {"order_no": "O-X"}}),
        create("buyer-x", "material_link", {"type_id": link_type["id"], "source_id": {"client_ref": "order-x"},
                                            "target_id": customer["target_id"]}),
    ])
    deletion = {**instance_update(customer), "operation": "delete", "after": None}
    first, _ = accept_all(client, first, [deletion])
    refused = publish(client, first)
    assert refused.status_code == 409, refused.text
    assert refused.json()["error"]["code"] == "INSTANCE_REFERENCED_ELSEWHERE"
    link_id = links["items"][1]["target_id"]
    assert any(i["target_id"] == link_id for i in baseline(client, second)["items"])


def test_undoing_a_type_undoes_both_changes_to_its_instance(client):
    """4: a cascade over a create and a later update of the same instance."""
    session, batch = staged_batch(client, create_session(client))
    instance_id = batch["items"][-1]["target_id"]
    session, _ = accept_all(client, session, [instance_update(entry_for(client, session, instance_id), values={"code": "WH-B"})])
    type_item = next(i for i in batch["items"] if i["target_kind"] == "object_type")
    response = decide(client, session, [(type_item["id"], "reject")])
    assert response.status_code == 200, response.text
    assert all(i["target_id"] != instance_id for i in baseline(client, response.json()["session"])["items"])


def partial_accept(client, session, ids):
    current = client.get(ROOT + f"/sessions/{session['id']}").json()
    return client.post(ROOT + f"/sessions/{session['id']}/proposal-decisions", json={
        "idempotency_key": str(uuid.uuid4()), "expected_session_revision": current["revision"],
        "decisions": [{"proposal_id": i, "decision": "accept"} for i in ids], "partial": True})


def test_accept_all_sets_aside_the_whole_atomic_group_and_records_nothing_for_it(client):
    """5 and 6: the refused item's group waits with it; no accepted row is logged for either."""
    session = with_rules(client, create_session(client),
                         ("no_test_customer", "不收测试客户", "object_type", "customer", "customer.label <> '测试客户'"))
    bad, peer, other = create_instance(session, "测试客户"), create_instance(session, "同组客户"), create_instance(session, "独立客户")
    batch = seed_batch(client, session, [bad, peer, other])
    ids = {i["client_ref"]: i["id"] for i in batch["items"]}
    group = str(uuid4())
    with client.app.state.session_factory() as db:
        db.execute(update(ProposalItemRecord).where(ProposalItemRecord.id.in_([ids[bad["client_ref"]], ids[peer["client_ref"]]]))
                   .values(atomic_group_id=group))
        db.commit()
    response = partial_accept(client, session, list(ids.values()))
    assert response.status_code == 200, response.text
    results = {r["proposal_id"]: r for r in response.json()["results"]}
    assert results[ids[other["client_ref"]]]["status"] == "accepted"
    assert results[ids[peer["client_ref"]]]["status"] == "pending" and "同组" in results[ids[peer["client_ref"]]]["reason"]
    for ref in (bad["client_ref"], peer["client_ref"]):
        item = next(i for i in batch["items"] if i["client_ref"] == ref)
        events = client.get(ROOT + f"/sessions/{session['id']}/change-events", params={"target_id": item["target_id"]}).json()["items"]
        assert not any(e["subject"] == "proposal" and e["action"] == "accepted" for e in events)


def test_a_pending_delete_is_not_in_the_public_history(client):
    """7: others see an instance's history only as published."""
    session = create_session(client)
    entry = baseline(client, session)["items"][0]
    deletion = {**instance_update(entry), "operation": "delete", "after": None}
    session, _ = accept_all(client, session, [deletion])
    url = ROOT + f"/instances/material_object/{entry['target_id']}/history"
    assert [h["operation"] for h in client.get(url).json()["items"]] == ["create"]
    assert client.get(url, params={"session_id": session["id"]}).json()["items"][-1]["operation"] == "delete"
