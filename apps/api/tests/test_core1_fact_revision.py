"""Explicit duplicate fact revision appends real evidence and rewrites pending endpoints."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from core1_fixtures import example_draft_json
from test_modeling import ROOT, create_session, save
from test_t4_proposal_decisions import create, decide, seed_batch

from ontofoundry_api.api.proposals import FactProposalRevision
from ontofoundry_api.domain.canonical import element_sha256
from ontofoundry_api.domain.evidence import EvidenceError
from ontofoundry_api.services.errors import ServiceError


@pytest.mark.parametrize(
    "invalid",
    ["missing-material", "wrong-hash", "outside-lines", "wrong-quote", "duplicate"],
)
def test_revision_converts_evidence_errors_without_database_or_mutation(
    monkeypatch, invalid
):
    from ontofoundry_api.services import fact_revision

    draft = example_draft_json("07-instances-and-evidence")
    for elements in draft.values():
        if isinstance(elements, list):
            for element in elements:
                if "evidence" in element:
                    element["evidence"] = []
    actor = SimpleNamespace(id=str(uuid4()))
    target = draft["material_objects"][0]
    target["evidence"] = [
        {
            "id": str(uuid4()),
            "kind": "manual",
            "note": "已核对虚构客户记录",
            "created_by": actor.id,
            "created_at": "2026-10-18T00:00:00Z",
        }
    ]
    other = draft["material_objects"][1]
    other["evidence"] = [{**deepcopy(target["evidence"][0]), "id": str(uuid4())}]
    material_id = str(uuid4())
    evidence = {
        "id": str(uuid4()),
        "kind": "material",
        "material_id": material_id,
        "material_sha256": "a" * 64,
        # Persisted proposal evidence includes defaults emitted by the request model.
        "locator": {"heading": None, "line_start": 1, "line_end": 1},
        "quote": "星港商店",
    }
    proposal_after = {**deepcopy(target), "id": str(uuid4()), "evidence": [evidence]}
    session_id, proposal_id = str(uuid4()), str(uuid4())
    session = SimpleNamespace(revision=3, draft_json=draft)
    item = SimpleNamespace(
        id=proposal_id,
        workspace_id=draft["workspace_id"],
        session_id=session_id,
        batch_id=str(uuid4()),
        target_kind="material_object",
        operation="create",
        target_id=proposal_after["id"],
        after_json=proposal_after,
        status="pending",
    )

    class MemoryRecords:
        def scalar(self, statement):
            return session

        def get(self, model, identity):
            assert identity == proposal_id
            return item

        def commit(self):
            pytest.fail("Invalid evidence must not commit a revision")

    monkeypatch.setattr(fact_revision, "batch_items", lambda *args: [item])
    monkeypatch.setattr(fact_revision, "dependency_map", lambda *args: {item.id: []})
    monkeypatch.setattr(
        fact_revision,
        "material_lookup",
        lambda *args: (
            lambda identity: ("a" * 64, ["星港商店"]) if identity == material_id else None
        ),
    )

    def unexpected_store(*args, **kwargs):
        pytest.fail("Invalid evidence must fail before storing any revision batch")

    monkeypatch.setattr(fact_revision, "store_batch", unexpected_store)
    extra = deepcopy(evidence)
    extra["id"] = str(uuid4())
    if invalid == "missing-material":
        extra["material_id"] = str(uuid4())
    elif invalid == "wrong-hash":
        extra["material_sha256"] = "b" * 64
    elif invalid == "outside-lines":
        extra["locator"]["line_end"] = 2
    elif invalid == "wrong-quote":
        extra["quote"] = "不存在的虚构引文"
    else:
        # Same-element duplicates fail request validation; a cross-element UUID
        # reaches reconciliation while preserving all target and proposal evidence.
        extra = deepcopy(other["evidence"][0])
    after = {
        **deepcopy(target),
        "evidence": [*deepcopy(target["evidence"]), evidence, extra],
    }
    body = FactProposalRevision.model_validate(
        {
            "expected_session_revision": 3,
            "target_id": target["id"],
            "expected_target_hash": element_sha256(target, collection="material_objects"),
            "after": after,
        }
    )
    previous_draft, previous_item = deepcopy(draft), deepcopy(vars(item))
    with pytest.raises(ServiceError) as error:
        fact_revision.revise_fact(
            MemoryRecords(),
            draft["workspace_id"],
            session_id,
            proposal_id,
            body,
            actor,
            None,
        )
    assert error.value.status_code == 422
    assert error.value.code == (
        "EVIDENCE_ID_DUPLICATE" if invalid == "duplicate" else "EVIDENCE_INVALID"
    )
    assert isinstance(error.value.__cause__, EvidenceError)
    assert error.value.code == error.value.__cause__.code
    assert error.value.message == str(error.value.__cause__)
    if invalid == "duplicate":
        assert error.value.message == "证据 UUID 不能转移到其他元素"
    else:
        where = f"material_objects[{target['id']}].evidence[2]"
        assert (
            error.value.message
            == {
                "missing-material": f"{where}：材料 {extra['material_id']} 不属于当前空间",
                "wrong-hash": f"{where}：材料哈希缺失或与已保存的材料不一致",
                "outside-lines": f"{where}：证据行号超出材料范围",
                "wrong-quote": f"{where}：引用原文与材料第 1–1 行不符",
            }[invalid]
        )
    assert draft == previous_draft
    assert session.draft_json == previous_draft
    assert vars(item) == previous_item
    assert session.revision == 3


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
        if relation["name"] == "buyer"
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
    batch_url = ROOT + f"/sessions/{session['id']}/proposal-batches"
    before_batches = client.get(batch_url).json()
    before_session = client.get(ROOT + f"/sessions/{session['id']}").json()
    missing = {**deepcopy(evidence), "id": str(uuid4()), "material_id": str(uuid4())}
    invalid = client.post(
        url, json={**body, "after": {**after, "evidence": [evidence, missing]}}
    )
    assert invalid.status_code == 422, invalid.text
    assert invalid.json()["error"]["code"] == "EVIDENCE_INVALID"
    assert "不属于当前空间" in invalid.json()["error"]["message"]
    assert client.get(batch_url).json() == before_batches
    assert client.get(batch_url + f"/{batch['id']}").json() == batch
    assert client.get(ROOT + f"/sessions/{session['id']}").json() == before_session
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
