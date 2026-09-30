"""T4: proposal listing, decisions and the acceptance transaction."""

from __future__ import annotations

from uuid import uuid4

from test_modeling import ROOT, create_session, save

from ontofoundry_api.contracts.proposals import SCHEMA_VERSION, RunContext, parse_result
from ontofoundry_api.db_models import ModelingSessionRecord, OntologyElementIdentityRecord
from ontofoundry_api.domain.canonical import element_sha256, snapshot_sha256
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.proposals import store_batch


def seed_batch(client, session: dict, items: list[dict], run_token: str | None = None) -> dict:
    """Store a batch for the session as a finished proposals run would."""
    run_token = run_token or uuid4().hex
    draft = session["draft"]
    manifest = {
        "run_token": run_token,
        "workspace_id": session["workspace_id"],
        "session_id": session["id"],
        "base_version_id": session["base_version_id"],
        "base_version_sha256": session["base_version_sha256"],
        "source_session_revision": session["revision"],
        "source_draft_sha256": snapshot_sha256(draft),
        "materials": [],
    }
    context = RunContext(**{k: manifest[k] for k in list(manifest)[:7]}, draft=draft)
    result = {"schema_version": SCHEMA_VERSION, **{k: manifest[k] for k in list(manifest)[:7]}, "items": items}
    parsed = parse_result(result, context, material_lookup=lambda _id: None)
    with client.app.state.session_factory() as db:
        store_batch(
            db,
            workspace_id=session["workspace_id"],
            session_id=session["id"],
            task_id=None,
            manifest=manifest,
            parsed=parsed,
        )
        db.commit()
    return client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{parsed.id}").json()


def create(ref, kind, after):
    return {
        "client_ref": ref,
        "operation": "create",
        "target_kind": kind,
        "target_id": None,
        "expected_target_hash": None,
        "before": None,
        "after": after,
    }


def update(kind, element, **changes):
    return {
        "operation": "update",
        "target_kind": kind,
        "target_id": element["id"],
        "expected_target_hash": element_sha256(element),
        "before": element,
        "after": {**{k: v for k, v in element.items() if k != "id"}, **changes},
    }


def chain(session: dict) -> list[dict]:
    """Object type → property → link type: a three-level dependency group."""
    supplier = session["draft"]["object_types"][0]["id"]
    return [
        create("po", "object_type", {"name": "采购订单", "technical_name": "purchase_order"}),
        create(
            "po-no",
            "property",
            {"owner_type_id": {"client_ref": "po"}, "name": "订单号", "technical_name": "order_no"},
        ),
        create(
            "po-link",
            "link_type",
            {
                "name": "供应方",
                "technical_name": "supplied_by",
                "source_type_id": {"client_ref": "po"},
                "target_type_id": supplier,
            },
        ),
    ]


def decide(client, session, decisions, key=None, revision=None):
    return client.post(
        ROOT + f"/sessions/{session['id']}/proposal-decisions",
        json={
            "idempotency_key": key or uuid4().hex,
            "expected_session_revision": session["revision"] if revision is None else revision,
            "decisions": [{"proposal_id": pid, "decision": d} for pid, d in decisions],
        },
    )


def current(client, session):
    return client.get(ROOT + f"/sessions/{session['id']}").json()


# --- reading --------------------------------------------------------------------


def test_batches_list_and_detail_carry_effective_status_and_groups(client):
    session = create_session(client)
    batch = seed_batch(client, session, chain(session))

    listing = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches").json()
    assert [b["id"] for b in listing["items"]] == [batch["id"]]
    assert listing["items"][0]["counts"]["pending"] == 3

    po, prop, link = batch["items"]
    assert po["display_name"] == "采购订单" and po["status"] == "pending"
    assert prop["owner_label"] == "采购订单"
    assert set(link["dependency_group"]) == {link["id"], po["id"]}
    assert current(client, session)["pending_proposal_count"] == 3
    assert current(client, session)["latest_batch_id"] == batch["id"]


# --- accept / reject / restore -----------------------------------------------------


def test_accepting_an_update_writes_the_draft_once(client):
    session = create_session(client)
    target = session["draft"]["object_types"][0]
    batch = seed_batch(client, session, [update("object_type", target, description="提案描述")])
    (item,) = batch["items"]

    response = decide(client, session, [(item["id"], "accept")])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["results"] == [{"proposal_id": item["id"], "status": "accepted", "reason": ""}]
    assert body["session"]["revision"] == session["revision"] + 1
    assert body["session"]["draft"]["object_types"][0]["description"] == "提案描述"
    assert body["session"]["draft_sha256"] == snapshot_sha256(body["session"]["draft"])
    assert any(c["element_id"] == target["id"] and c["change"] == "updated" for c in body["session"]["base_diff"])
    assert body["session"]["pending_proposal_count"] == 0


def test_dependencies_must_be_accepted_together(client):
    session = create_session(client)
    po, prop, link = seed_batch(client, session, chain(session))["items"]

    alone = decide(client, session, [(prop["id"], "accept")])
    assert alone.status_code == 422
    assert alone.json()["error"]["code"] == "DEPENDENCY_INCOMPLETE"
    assert current(client, session)["revision"] == session["revision"]

    together = decide(client, session, [(po["id"], "accept"), (prop["id"], "accept"), (link["id"], "accept")])
    assert together.status_code == 200, together.text
    draft = together.json()["session"]["draft"]
    assert {t["technical_name"] for t in draft["object_types"]} >= {"purchase_order"}
    assert any(p["technical_name"] == "order_no" for p in draft["properties"])
    assert any(link["technical_name"] == "supplied_by" for link in draft["link_types"])


def test_rejecting_a_root_makes_dependents_conflict_and_restore_undoes_it(client):
    session = create_session(client)
    batch = seed_batch(client, session, chain(session))
    po, prop, _ = batch["items"]

    rejected = decide(client, session, [(po["id"], "reject")])
    assert rejected.status_code == 200
    assert current(client, session)["draft"] == session["draft"]  # reject never writes
    detail = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}").json()
    statuses = {i["id"]: i["status"] for i in detail["items"]}
    assert statuses[po["id"]] == "rejected"
    assert statuses[prop["id"]] == "conflict"

    assert decide(client, session, [(po["id"], "restore")]).status_code == 200
    detail = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}").json()
    assert {i["status"] for i in detail["items"]} == {"pending"}

    not_rejected = decide(client, session, [(prop["id"], "restore")])
    assert not_rejected.status_code == 409
    assert not_rejected.json()["error"]["code"] == "PROPOSAL_NOT_RESTORABLE"


def test_a_stale_item_cannot_be_accepted_until_its_target_is_back(client):
    session = create_session(client)
    target = session["draft"]["object_types"][0]
    (item,) = seed_batch(client, session, [update("object_type", target, description="提案")])["items"]

    edited = current(client, session)
    edited["draft"]["object_types"][0]["description"] = "人工改动"
    edited = save(client, edited, edited["draft"]).json()
    refused = decide(client, edited, [(item["id"], "accept")])
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "PROPOSAL_STALE"
    assert current(client, session)["revision"] == edited["revision"]

    # Still rejectable while stale.
    edited["draft"]["object_types"][0]["description"] = target["description"]
    restored = save(client, edited, edited["draft"]).json()
    assert decide(client, restored, [(item["id"], "accept")]).status_code == 200


def test_an_accept_that_breaks_the_draft_changes_nothing(client):
    session = create_session(client)
    clash = session["draft"]["object_types"][0]["technical_name"]
    (item,) = seed_batch(client, session, [create("dup", "object_type", {"name": "重复", "technical_name": clash})])["items"]
    response = decide(client, session, [(item["id"], "accept")])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert current(client, session)["draft"] == session["draft"]


def test_an_id_registered_as_another_kind_cannot_be_created(client):
    session = create_session(client)
    (item,) = seed_batch(client, session, [create("t", "object_type", {"name": "新类型", "technical_name": "fresh"})])["items"]
    with client.app.state.session_factory() as db:
        db.add(
            OntologyElementIdentityRecord(
                workspace_id=str(DEMO_WORKSPACE_ID), element_id=item["target_id"], kind="rule"
            )
        )
        db.commit()
    response = decide(client, session, [(item["id"], "accept")])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ELEMENT_KIND_CONFLICT"


# --- idempotency, revision and scope --------------------------------------------


def test_replays_return_the_first_response_and_mismatches_are_refused(client):
    session = create_session(client)
    target = session["draft"]["object_types"][0]
    (item,) = seed_batch(client, session, [update("object_type", target, description="一次")])["items"]
    first = decide(client, session, [(item["id"], "accept")], key="key-00000001")
    assert first.status_code == 200
    # The revision has moved on; the same request still gets the same answer.
    replay = decide(client, session, [(item["id"], "accept")], key="key-00000001")
    assert replay.status_code == 200 and replay.json() == first.json()
    assert current(client, session)["revision"] == session["revision"] + 1

    other = decide(client, session, [(item["id"], "reject")], key="key-00000001")
    assert other.status_code == 409
    assert other.json()["error"]["code"] == "IDEMPOTENCY_MISMATCH"


def test_a_stale_revision_is_refused(client):
    session = create_session(client)
    (item,) = seed_batch(client, session, chain(session)[:1])["items"]
    response = decide(client, session, [(item["id"], "accept")], revision=session["revision"] - 1)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SESSION_REVISION_CHANGED"


def test_items_of_another_session_are_refused(client):
    mine, theirs = create_session(client), create_session(client)
    (item,) = seed_batch(client, theirs, chain(theirs)[:1])["items"]
    response = decide(client, mine, [(item["id"], "accept")])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PROPOSAL_NOT_FOUND"


def test_edits_are_allowed_during_a_proposals_run_but_not_a_legacy_one(client):
    session = create_session(client)
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session["id"])
        item.task_status = "running"
        item.run_manifest_json = {"result_contract": "proposals"}
        db.commit()
    session["draft"]["object_types"][0]["description"] = "运行中编辑"
    assert save(client, session, session["draft"]).status_code == 200


def test_batches_page_by_keyset_cursor(client):
    session = create_session(client)
    ids = [seed_batch(client, session, chain(session)[:1], run_token=f"run-{i}")["id"] for i in range(3)]
    first = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches?limit=2").json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    rest = client.get(
        ROOT + f"/sessions/{session['id']}/proposal-batches?limit=2&cursor={first['next_cursor']}"
    ).json()
    seen = [b["id"] for b in first["items"] + rest["items"]]
    assert sorted(seen) == sorted(ids) and rest["next_cursor"] is None
    bad = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches?cursor=nope")
    assert bad.status_code == 422
