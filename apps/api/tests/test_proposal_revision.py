"""Reviewers can revise a pending create or update proposal before deciding it."""

from test_modeling import ROOT, create_session
from test_t4_proposal_decisions import chain, current, decide, seed_batch, update


def revise(client, session, item, fields, revision=None):
    return client.patch(
        ROOT + f"/sessions/{session['id']}/proposals/{item['id']}/after",
        json={
            "fields": fields,
            "expected_session_revision": session["revision"] if revision is None else revision,
        },
    )


def test_revised_content_is_what_gets_accepted(client):
    session = create_session(client)
    target = session["draft"]["object_types"][0]
    (item,) = seed_batch(client, session, [update("object_type", target, description="提案描述")])["items"]
    # Two saves of different fields in a row: the second keeps the first.
    response = revise(client, session, item, {"display_name": "审阅后名称"})
    assert response.status_code == 200, response.text
    session = current(client, session)
    response = revise(client, session, item, {"description": "审阅后描述"})
    assert response.status_code == 200, response.text
    session = current(client, session)
    detail = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{item['batch_id']}").json()
    revised = detail["items"][0]
    assert revised["after"]["display_name"] == "审阅后名称"
    assert {c["path"] for c in revised["field_changes"]} >= {"display_name", "description"}

    accepted = decide(client, session, [(item["id"], "accept")])
    assert accepted.status_code == 200, accepted.text
    obj = accepted.json()["session"]["draft"]["object_types"][0]
    assert (obj["display_name"], obj["description"]) == ("审阅后名称", "审阅后描述")


def test_identity_and_evidence_stay_with_the_proposal(client):
    session = create_session(client)
    items = seed_batch(client, session, chain(session))["items"]
    po = items[0]
    locked = revise(client, session, po, {"id": "00000000-0000-4000-8000-000000000000", "evidence": []})
    assert locked.status_code == 422 and locked.json()["error"]["code"] == "FIELD_NOT_EDITABLE"
    assert revise(client, session, po, {"display_name": "采购单"}).status_code == 200
    session = current(client, session)
    detail = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{po['batch_id']}").json()
    revised = next(i for i in detail["items"] if i["id"] == po["id"])
    assert revised["after"]["id"] == po["after"]["id"]
    assert revised["after"].get("evidence", []) == po["after"].get("evidence", [])
    # Dependents still point at the unchanged identity and can be accepted together.
    result = decide(client, session, [(i["id"], "accept") for i in items])
    assert result.status_code == 200, result.text


def test_invalid_content_stale_revision_and_decided_items_are_refused(client):
    session = create_session(client)
    target = session["draft"]["object_types"][0]
    (item,) = seed_batch(client, session, [update("object_type", target, description="提案描述")])["items"]

    invalid = revise(client, session, item, {"name": ""})
    assert invalid.status_code == 422 and invalid.json()["error"]["code"] == "VALIDATION_FAILED"

    stale = revise(client, session, item, {"description": "过期修改"}, revision=session["revision"] - 1)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "SESSION_REVISION_CHANGED"

    assert decide(client, session, [(item["id"], "reject")]).status_code == 200
    session = current(client, session)
    decided = revise(client, session, item, {"description": "已决定后修改"})
    assert decided.status_code == 409 and decided.json()["error"]["code"] == "PROPOSAL_NOT_DECIDABLE"
