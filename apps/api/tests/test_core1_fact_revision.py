"""Explicit duplicate fact revision appends real evidence and rewrites pending endpoints."""

from copy import deepcopy
from uuid import uuid4

from test_modeling import ROOT, create_session, save
from test_t4_proposal_decisions import create, decide, seed_batch

from ontofoundry_api.domain.canonical import element_sha256


def test_revision_uses_current_target_hash_and_preserves_pending_adjacency(client):
    session = create_session(client)
    draft = session["draft"]
    prop = next(p for p in draft["properties"] if p["technical_name"] == "label")
    prop.update(identifier=True, unique=True)
    customer = next(
        o for o in draft["material_objects"] if o["type_id"] == prop["owner_type_id"]
    )
    order_type = next(o for o in draft["object_types"] if o["technical_name"] == "order")
    order_fact = {
        "id": str(uuid4()),
        "type_id": order_type["id"],
        "values": {"order_no": "O1"},
        "evidence": [],
    }
    draft["material_objects"].append(order_fact)
    session = save(client, session, draft).json()
    uploaded = client.post(
        ROOT + "/materials",
        params={"name": "虚构客户.md"},
        content="星港商店完成订单。".encode(),
    )
    assert uploaded.status_code == 201, uploaded.text
    material = uploaded.json()
    assert material["id"] in {
        m["id"] for m in client.get(ROOT + "/materials").json()["items"]
    }
    evidence = {
        "kind": "material",
        "id": str(uuid4()),
        "material_id": material["id"],
        "material_sha256": material["sha256"],
        "locator": {"line_start": 1, "line_end": 1},
        "quote": "星港商店",
    }
    link = next(
        relation
        for relation in draft["link_types"]
        if relation["technical_name"] == "buyer"
    )
    batch = seed_batch(
        client,
        session,
        [
            create(
                "customer_fact",
                "material_object",
                {
                    "type_id": customer["type_id"],
                    "values": customer["values"],
                    "evidence": [evidence],
                },
            ),
            create(
                "buyer_fact",
                "material_link",
                {
                    "type_id": link["id"],
                    "source_id": order_fact["id"],
                    "target_id": {"client_ref": "customer_fact"},
                },
            ),
        ],
    )
    item = batch["items"][0]
    assert [c["id"] for c in item["duplicate_candidates"]] == [customer["id"]]
    after = {**deepcopy(customer), "evidence": [evidence]}
    url = ROOT + f"/sessions/{session['id']}/proposal-items/{item['id']}/revision"
    body = {
        "expected_session_revision": session["revision"],
        "target_id": customer["id"],
        "expected_target_hash": element_sha256(customer, collection="material_objects"),
        "after": after,
    }
    stale = client.post(url, json={**body, "expected_target_hash": "0" * 64})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "PROPOSAL_STALE"
    revised = client.post(url, json=body)
    assert revised.status_code == 200, revised.text
    revision = revised.json()
    assert (
        client.get(ROOT + f"/sessions/{session['id']}").json()["revision"]
        == session["revision"]
    )
    assert revision["items"][0]["operation"] == "update"
    assert revision["items"][1]["after"]["target_id"] == customer["id"]
    response = decide(client, session, [(i["id"], "accept") for i in revision["items"]])
    assert response.status_code == 200, response.text
    accepted = response.json()["session"]["draft"]
    assert len(accepted["material_objects"]) == 2
    updated = next(o for o in accepted["material_objects"] if o["id"] == customer["id"])
    assert updated["evidence"][0]["id"] == evidence["id"]


def test_fact_revision_migrates_pending_upstream_and_preserves_both_endpoints(client):
    from pr23_fixtures import example_session

    session = example_session(client, "07-instances-and-evidence")
    customer = next(
        o for o in session["draft"]["material_objects"] if "customer_no" in o["values"]
    )
    returns = next(
        o
        for o in session["draft"]["object_types"]
        if o["technical_name"] == "return_request"
    )
    link = session["draft"]["link_types"][0]
    batch = seed_batch(
        client,
        session,
        [
            create(
                "duplicate_customer",
                "material_object",
                {
                    "type_id": customer["type_id"],
                    "values": customer["values"],
                    "evidence": [],
                },
            ),
            create(
                "new_return",
                "material_object",
                {
                    "type_id": returns["id"],
                    "values": {"return_no": "RT-0201", "refund": 200},
                    "evidence": [],
                },
            ),
            create(
                "return_customer",
                "material_link",
                {
                    "type_id": link["id"],
                    "source_id": {"client_ref": "new_return"},
                    "target_id": {"client_ref": "duplicate_customer"},
                    "evidence": [],
                },
            ),
        ],
    )
    customer_item = batch["items"][0]
    response = client.post(
        ROOT + f"/sessions/{session['id']}/proposal-items/{customer_item['id']}/revision",
        json={
            "expected_session_revision": session["revision"],
            "target_id": customer["id"],
            "expected_target_hash": element_sha256(customer, collection="material_objects"),
            "after": customer,
        },
    )
    assert response.status_code == 200, response.text
    revision = response.json()
    assert len(revision["items"]) == 3
    revised_customer, new_return, adjacency = revision["items"]
    assert (
        revised_customer["operation"] == "update"
        and revised_customer["target_id"] == customer["id"]
    )
    assert set(adjacency["depends_on"]) == {revised_customer["id"], new_return["id"]}
    assert adjacency["after"]["source_id"] == new_return["target_id"]
    assert adjacency["after"]["target_id"] == customer["id"]
    old = client.get(
        ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}"
    ).json()
    assert {i["stored_status"] for i in old["items"]} == {"superseded"}
    accepted = decide(client, session, [(i["id"], "accept") for i in revision["items"]])
    assert accepted.status_code == 200, accepted.text
    graph = accepted.json()["session"]["draft"]
    assert len(graph["material_objects"]) == len(session["draft"]["material_objects"]) + 1
    assert len(graph["material_links"]) == len(session["draft"]["material_links"]) + 1
    assert (
        next(
            relation
            for relation in graph["material_links"]
            if relation["source_id"] == new_return["target_id"]
        )["target_id"]
        == customer["id"]
    )
