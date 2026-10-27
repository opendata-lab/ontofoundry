"""Revising a pending instance proposal never writes the instance itself."""

from copy import deepcopy
from uuid import uuid4

import pytest
from test_instance_store import accept_all, baseline, create_instance
from test_modeling import ROOT, create_session
from test_t4_proposal_decisions import decide, seed_batch


def test_fact_revision_only_revises_pending_proposal(client):
    session = create_session(client)
    target = baseline(client, session)["items"][0]
    proposal = create_instance(session, target["element"]["values"]["label"])
    batch = seed_batch(client, session, [proposal])
    item = batch["items"][0]
    endpoint = ROOT + f"/sessions/{session['id']}/proposal-items/{item['id']}/revision"
    body = {
        "expected_session_revision": session["revision"],
        "target_id": target["target_id"],
        "expected_target_hash": target["hash"],
        "after": target["element"],
    }
    assert (
        client.post(endpoint, json={**body, "expected_target_hash": "0" * 64}).status_code
        == 409
    )
    revised = client.post(endpoint, json=body)
    assert revised.status_code == 200, revised.text
    new_item = revised.json()["items"][0]
    assert (
        new_item["operation"] == "update"
        and new_item["expected_instance_revision"] == target["revision"]
    )
    assert baseline(client, session)["items"][0] == target
    old = client.get(
        ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}"
    ).json()
    assert revised.json()["id"] == batch["id"]
    assert new_item["id"] == item["id"]
    assert old["items"][0]["stored_status"] == "pending"
    session["revision"] += 1
    accepted = decide(client, session, [(new_item["id"], "accept")])
    assert accepted.status_code == 200, accepted.text
    assert (
        baseline(client, accepted.json()["session"])["items"][0]["revision"]
        == target["revision"] + 1
    )


@pytest.mark.parametrize(
    "invalid", ["missing-material", "wrong-hash", "outside-lines", "wrong-quote"]
)
def test_revision_rejects_invalid_evidence_before_any_change(client, invalid):
    session = create_session(client)
    material = client.post(
        ROOT + "/materials", params={"name": "虚构客户出处.md"}, content="月湾客户".encode()
    ).json()
    evidence = {
        "id": str(uuid4()),
        "kind": "material",
        "material_id": material["id"],
        "material_sha256": material["sha256"],
        "locator": {"line_start": 1, "line_end": 1},
        "quote": "月湾客户",
    }
    proposal = create_instance(session)
    proposal["after"]["evidence"] = [evidence]
    session, accepted = accept_all(client, session, [proposal])
    target = next(
        i
        for i in baseline(client, session)["items"]
        if i["target_id"] == accepted["items"][0]["target_id"]
    )
    batch = seed_batch(client, session, [create_instance(session)])
    after = deepcopy(target["element"])
    extra = {**deepcopy(evidence), "id": str(uuid4())}
    if invalid == "missing-material":
        extra["material_id"] = str(uuid4())
    elif invalid == "wrong-hash":
        extra["material_sha256"] = "0" * 64
    elif invalid == "outside-lines":
        extra["locator"]["line_end"] = 2
    else:
        extra["quote"] = "材料中没有的引文"
    after["evidence"].append(extra)
    response = client.post(
        ROOT
        + f"/sessions/{session['id']}/proposal-items/{batch['items'][0]['id']}/revision",
        json={
            "expected_session_revision": session["revision"],
            "target_id": target["target_id"],
            "expected_target_hash": target["hash"],
            "after": after,
        },
    )
    assert (
        response.status_code == 422
        and response.json()["error"]["code"] == "EVIDENCE_INVALID"
    )
    assert (
        next(
            i
            for i in baseline(client, session)["items"]
            if i["target_id"] == target["target_id"]
        )
        == target
    )
    old = client.get(
        ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}"
    ).json()
    assert old == batch


def test_fact_revision_preserves_upstream_dependencies_and_rewrites_endpoints(client):
    from pr23_fixtures import example_session
    from test_t4_proposal_decisions import create

    session = example_session(client, "07-instances-and-evidence", with_instances=True)
    entries = baseline(client, session)["items"]
    target = next(
        i
        for i in entries
        if i["target_kind"] == "material_object" and "customer_no" in i["element"]["values"]
    )
    returns = next(
        o for o in session["draft"]["object_types"] if o["name"] == "return_request"
    )
    batch = seed_batch(
        client,
        session,
        [
            create(
                "duplicate",
                "material_object",
                {
                    "type_id": target["element"]["type_id"],
                    "values": target["element"]["values"],
                },
            ),
            create(
                "return",
                "material_object",
                {"type_id": returns["id"], "values": {"return_no": "RT-0201"}},
            ),
            create(
                "return-link",
                "material_link",
                {
                    "type_id": session["draft"]["link_types"][0]["id"],
                    "source_id": {"client_ref": "return"},
                    "target_id": {"client_ref": "duplicate"},
                },
            ),
        ],
    )
    response = client.post(
        ROOT
        + f"/sessions/{session['id']}/proposal-items/{batch['items'][0]['id']}/revision",
        json={
            "expected_session_revision": session["revision"],
            "target_id": target["target_id"],
            "expected_target_hash": target["hash"],
            "after": target["element"],
        },
    )
    assert response.status_code == 200, response.text
    revised = response.json()["items"]
    assert len(revised) == 3
    assert revised[0]["operation"] == "update"
    assert revised[2]["after"]["target_id"] == target["target_id"]
    assert revised[2]["after"]["source_id"] == revised[1]["target_id"]
    assert set(revised[2]["depends_on"]) == {revised[0]["id"], revised[1]["id"]}
    before = baseline(client, session)
    assert (
        next(i for i in before["items"] if i["target_id"] == target["target_id"]) == target
    )
    # Revising a pending fact moves the session revision, like other revisions.
    session = client.get(ROOT + f"/sessions/{session['id']}").json()
    accepted = decide(client, session, [(i["id"], "accept") for i in revised])
    assert accepted.status_code == 200, accepted.text
    assert (
        len(baseline(client, accepted.json()["session"])["items"])
        == len(before["items"]) + 2
    )
