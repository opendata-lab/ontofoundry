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
