"""T4: proposal listing, decisions and the acceptance transaction."""

from __future__ import annotations

import json
from copy import deepcopy
from uuid import uuid4

from dataset_binding import bind_datasets
from sqlalchemy import select
from test_modeling import ROOT, create_session, save
from test_t1_proposal_contract import items_only

from ontofoundry_api.contracts.proposals import RunContext, parse_result
from ontofoundry_api.db_models import (
    ModelingSessionRecord,
    OntologyElementIdentityRecord,
    ProposalItemRecord,
)
from ontofoundry_api.domain.canonical import element_sha256, snapshot_sha256
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.proposals import store_batch


def seed_batch(
    client, session: dict, items: list[dict], run_token: str | None = None
) -> dict:
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
    from ontofoundry_api.services.instance_store import baseline
    with client.app.state.session_factory() as db:
        instances = baseline(db, session["workspace_id"], session["id"])
    context = RunContext(**{k: manifest[k] for k in list(manifest)[:7]}, draft=draft, instance_baseline=instances)
    result = {"items": items_only(items)}
    with client.app.state.session_factory() as db:
        parsed = parse_result(
            json.dumps(result).encode(),
            context,
            material_lookup(db, client.app.state.settings, session["workspace_id"]),
        )
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
    return client.get(
        ROOT + f"/sessions/{session['id']}/proposal-batches/{parsed.id}"
    ).json()


def create(ref, kind, after):
    after = dict(after)
    if kind == "property":
        after.setdefault("value_kind", "string")
    if kind == "link_type":
        after.setdefault("multiplicity", "many_to_one")
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
        "expected_target_hash": element_sha256(
            element, collection=kind + "s" if kind != "property" else "properties"
        ),
        "before": element,
        "after": {**{k: v for k, v in element.items() if k != "id"}, **changes},
    }


def chain(session: dict) -> list[dict]:
    """Object type → property → link type: a three-level dependency group."""
    supplier = session["draft"]["object_types"][0]["id"]
    return [
        create("po", "object_type", {"display_name": "采购订单", "name": "purchase_order"}),
        create(
            "po-no",
            "property",
            {
                "owner_type_id": {"client_ref": "po"},
                "display_name": "订单号",
                "name": "order_no",
            },
        ),
        create(
            "po-link",
            "link_type",
            {
                "name": "supplied_by",
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
            "expected_session_revision": session["revision"]
            if revision is None
            else revision,
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
    batch = seed_batch(
        client, session, [update("object_type", target, description="提案描述")]
    )
    (item,) = batch["items"]

    response = decide(client, session, [(item["id"], "accept")])

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["results"] == [
        {"proposal_id": item["id"], "status": "accepted", "reason": "", "triggered_by": None}
    ]
    assert body["session"]["revision"] == session["revision"] + 1
    assert body["session"]["draft"]["object_types"][0]["description"] == "提案描述"
    assert body["session"]["draft_sha256"] == snapshot_sha256(body["session"]["draft"])
    assert any(
        c["element_id"] == target["id"] and c["change"] == "updated"
        for c in body["session"]["base_diff"]
    )
    assert body["session"]["pending_proposal_count"] == 0


def test_acceptance_expands_pending_dependencies(client):
    session = create_session(client)
    po, prop, link = seed_batch(client, session, chain(session))["items"]
    response = decide(client, session, [(link["id"], "accept"), (prop["id"], "accept")])
    assert response.status_code == 200, response.text
    assert {r["proposal_id"] for r in response.json()["results"]} == {po["id"], prop["id"], link["id"]}
    assert {r["status"] for r in response.json()["results"]} == {"accepted"}


def test_rejecting_a_root_rejects_dependents_and_restore_expands_dependencies(client):
    session = create_session(client)
    proposal_chain = chain(session)
    proposal_chain[2]["depends_on"] = ["po-no"]
    batch = seed_batch(client, session, proposal_chain)
    root, _, leaf = batch["items"]
    rejected = decide(client, session, [(root["id"], "reject")])
    assert rejected.status_code == 200, rejected.text
    assert {r["status"] for r in rejected.json()["results"]} == {"rejected"}
    assert len(rejected.json()["results"]) == 3
    assert current(client, session)["draft"] == session["draft"]
    restored = decide(client, session, [(leaf["id"], "restore")])
    assert restored.status_code == 200, restored.text
    assert len(restored.json()["results"]) == 3
    assert {r["status"] for r in restored.json()["results"]} == {"pending"}
    refused = decide(client, session, [(leaf["id"], "restore")])
    assert refused.status_code == 409


def test_pending_proposals_block_draft_edits(client):
    session = create_session(client)
    target = session["draft"]["object_types"][0]
    seed_batch(client, session, [update("object_type", target, description="提案")])
    draft = {**session["draft"], "object_types": [{**target, "description": "人工修改"}, *session["draft"]["object_types"][1:]]}
    response = save(client, session, draft)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PENDING_PROPOSALS"
    assert current(client, session)["draft"] == session["draft"]





def test_an_id_registered_as_another_kind_cannot_be_created(client):
    session = create_session(client)
    (item,) = seed_batch(
        client,
        session,
        [create("t", "object_type", {"display_name": "新类型", "name": "fresh"})],
    )["items"]
    with client.app.state.session_factory() as db:
        db.add(
            OntologyElementIdentityRecord(
                workspace_id=str(DEMO_WORKSPACE_ID),
                element_id=item["target_id"],
                kind="rule",
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
    (item,) = seed_batch(
        client, session, [update("object_type", target, description="一次")]
    )["items"]
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
    response = decide(
        client, session, [(item["id"], "accept")], revision=session["revision"] - 1
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SESSION_REVISION_CHANGED"


def test_items_of_another_session_are_refused(client):
    mine, theirs = create_session(client), create_session(client)
    (item,) = seed_batch(client, theirs, chain(theirs)[:1])["items"]
    response = decide(client, mine, [(item["id"], "accept")])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "PROPOSAL_NOT_FOUND"


def test_edits_are_blocked_during_a_modeling_run(client):
    session = create_session(client)
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, session["id"])
        row.task_status = "running"
        db.commit()
    edited = deepcopy(session["draft"])
    edited["object_types"][0]["description"] = "运行中编辑"
    response = save(client, session, edited)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SESSION_RUNNING"


def test_batches_page_by_keyset_cursor(client):
    session = create_session(client)
    ids = []
    for i in range(3):
        ids.append(seed_batch(client, session, chain(session)[:1], run_token=f"run-{i}")["id"])
        # A session reviews one batch before the next run produces another.
        with client.app.state.session_factory() as db:
            for item in db.scalars(select(ProposalItemRecord).where(ProposalItemRecord.batch_id == ids[-1])):
                item.status = "rejected"
            db.commit()
    first = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches?limit=2").json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    rest = client.get(
        ROOT
        + f"/sessions/{session['id']}/proposal-batches?limit=2&cursor={first['next_cursor']}"
    ).json()
    seen = [b["id"] for b in first["items"] + rest["items"]]
    assert sorted(seen) == sorted(ids) and rest["next_cursor"] is None
    bad = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches?cursor=nope")
    assert bad.status_code == 422


def test_mapping_with_reference_named_properties_can_be_accepted(client):
    from test_t1_proposal_contract import mapping_name_collision_items

    session = create_session(client)
    items = mapping_name_collision_items()
    # Accepting a dataset needs a bound, registered source (DS-07).
    bind_datasets(client, {"datasets": [i["after"] for i in items if i["target_kind"] == "dataset"]})
    batch = seed_batch(client, session, items)
    response = decide(client, session, [(item["id"], "accept") for item in batch["items"]])
    assert response.status_code == 200, response.text
    mapping = next(
        m
        for m in response.json()["session"]["draft"]["mappings"]
        if "property_id" in m["fields"]
    )
    assert mapping["fields"] == items[-1]["after"]["fields"]


def test_document_proposal_labels_use_candidate_titles_and_endpoints(client):
    session = create_session(client)
    batch = seed_batch(
        client,
        session,
        [
            create(
                "staff",
                "object_type",
                {
                    "display_name": "星港员工",
                    "name": "starport_staff",
                    "title_property_id": {"client_ref": "title"},
                },
            ),
            create(
                "title",
                "property",
                {
                    "owner_type_id": {"client_ref": "staff"},
                    "display_name": "姓名",
                    "name": "staff_name",
                },
            ),
            create(
                "reports",
                "link_type",
                {
                    "name": "reports_to",
                    "source_type_id": {"client_ref": "staff"},
                    "target_type_id": {"client_ref": "staff"},
                },
            ),
            create(
                "lan",
                "material_object",
                {"type_id": {"client_ref": "staff"}, "values": {"staff_name": "小岚"}},
            ),
            create(
                "zhou",
                "material_object",
                {"type_id": {"client_ref": "staff"}, "values": {"staff_name": "小舟"}},
            ),
            create(
                "fact-link",
                "material_link",
                {
                    "type_id": {"client_ref": "reports"},
                    "source_id": {"client_ref": "lan"},
                    "target_id": {"client_ref": "zhou"},
                },
            ),
        ],
    )
    labels = {item["client_ref"]: item["display_name"] for item in batch["items"]}
    assert labels["lan"] == "小岚" and labels["zhou"] == "小舟"
    assert labels["fact-link"] == "小岚 → 小舟"


def test_batch_read_builds_the_candidate_once_and_keeps_item_diagnostics(client, monkeypatch):
    """A batch read used to rebuild the candidate graph per item (quadratic in batch size)."""
    from ontofoundry_api.db_models import ProposalItemRecord
    from ontofoundry_api.services import dataset_proposals

    session = create_session(client)
    sales = next(d for d in session["draft"]["datasets"] if d["name"] == "sales")

    def metric(ref, name):
        return create(ref, "metric", {
            "name": name, "display_name": name, "kind": "simple", "dataset_id": sales["id"],
            "aggregation": "sum", "measure": {"dataset_id": sales["id"], "column": "amount"},
        })

    batch = seed_batch(client, session, [*chain(session), metric("m1", "total_a"), metric("m2", "total_b")])

    # The source is unavailable, so both metrics carry a real diagnostic.
    builds, checks = [], []
    original = dataset_proposals.candidate_for
    monkeypatch.setattr(dataset_proposals, "candidate_for", lambda db, s: builds.append(1) or original(db, s))
    monkeypatch.setattr(dataset_proposals, "check_dataset", lambda db, ws, dataset: checks.append(str(dataset.id)) or {
        "valid": False, "columns": None, "diagnostics": [{"code": "CONNECTION_UNBOUND", "severity": "error", "path": "/connection_id", "message": "x"}]})
    read = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{batch['id']}").json()
    assert len(builds) == 1 and checks == [sales["id"]]  # one candidate, one check per dataset

    # Same diagnostics as computing each item on its own.
    with client.app.state.session_factory() as db:
        expected = {
            item.id: dataset_proposals.proposal_diagnostics(db, session["workspace_id"], item)
            for item in db.scalars(select(ProposalItemRecord).where(ProposalItemRecord.batch_id == batch["id"]))
        }
    assert {i["id"]: i["source_diagnostics"] for i in read["items"]} == expected
    metrics = [i["source_diagnostics"] for i in read["items"] if i["target_kind"] == "metric"]
    assert [[d["code"] for d in diags] for diags in metrics] == [["DATASET_SOURCE_BLOCKED"]] * 2


def test_accepting_merged_batch_ignores_superseded_dependency_root(client):
    """Dynamic dependency reconstruction across open batches must skip superseded rows."""
    from sqlalchemy import update as sa_update
    from test_pending_merge import run_on_top_of_pending

    from ontofoundry_api.services.proposals import dependency_map

    session = create_session(client)
    old_batch = seed_batch(client, session, chain(session)[:2])
    po_old, prop_old = old_batch["items"]
    assert po_old["ordinal"] == 0 and prop_old["ordinal"] == 1

    # Merge a new run on top of pending proposals: revise the property first (ordinal 0),
    # add a new link referencing the pending object (ordinal 1), and leave the object to be
    # carried after them (ordinal 2 > po_old.ordinal 0), deterministically ordering the
    # superseded create ahead of its live replacement across open batches.
    _, candidate, url, headers = run_on_top_of_pending(client, session)
    pending_prop = next(p for p in candidate["properties"] if p["id"] == prop_old["target_id"])
    supplier_id = session["draft"]["object_types"][0]["id"]
    revised_prop = {
        "operation": "update",
        "target_kind": "property",
        "target_id": prop_old["target_id"],
        "after": {
            **{k: v for k, v in pending_prop.items() if k != "id"},
            "description": "修订后的订单号",
        },
    }
    added_link = create(
        "po-link",
        "link_type",
        {
            "name": "supplied_by",
            "source_type_id": po_old["target_id"],
            "target_type_id": supplier_id,
        },
    )
    submitted = client.post(url, json={"items": items_only([revised_prop, added_link])}, headers=headers)
    assert submitted.status_code == 200 and submitted.json()["passed"], submitted.text
    new_batch_id = submitted.json()["batch_id"]

    with client.app.state.session_factory() as db:
        db.execute(
            sa_update(ModelingSessionRecord)
            .where(ModelingSessionRecord.id == session["id"])
            .values(task_status="finished", result_state="done")
        )
        db.commit()

    new_batch = client.get(
        ROOT + f"/sessions/{session['id']}/proposal-batches/{new_batch_id}"
    ).json()
    by_target = {item["target_id"]: item for item in new_batch["items"]}
    po_new = by_target[po_old["target_id"]]
    prop_new = by_target[prop_old["target_id"]]
    link_new = next(item for item in new_batch["items"] if item["target_kind"] == "link_type")
    assert prop_new["ordinal"] == 0 and link_new["ordinal"] == 1 and po_new["ordinal"] == 2

    with client.app.state.session_factory() as db:
        deps = dependency_map(
            db, [old_batch["id"], new_batch_id], session["workspace_id"], session["id"]
        )

    # Accepting the dependents expands to the live object create rather than failing on the superseded one.
    latest_session = current(client, session)
    accepted = decide(client, latest_session, [(prop_new["id"], "accept"), (link_new["id"], "accept")])
    assert accepted.status_code == 200, accepted.text
    assert po_new["id"] in deps.get(prop_new["id"], [])
    assert po_old["id"] not in deps.get(prop_new["id"], [])
    assert po_new["id"] in deps.get(link_new["id"], [])
    assert po_old["id"] not in deps.get(link_new["id"], [])
    # Historical explicit metadata stays on the superseded batch without stale edges to live items.
    assert deps.get(prop_old["id"], []) == [po_old["id"]]

    results = {r["proposal_id"]: r for r in accepted.json()["results"]}
    assert set(results) == {po_new["id"], prop_new["id"], link_new["id"]}
    assert {r["status"] for r in results.values()} == {"accepted"}
    assert results[po_new["id"]]["triggered_by"] in {prop_new["id"], link_new["id"]}

    draft = accepted.json()["session"]["draft"]
    assert any(o["id"] == po_new["target_id"] for o in draft["object_types"])
    assert any(p["id"] == prop_new["target_id"] for p in draft["properties"])
    assert any(link["id"] == link_new["target_id"] for link in draft["link_types"])

    old_detail = client.get(
        ROOT + f"/sessions/{session['id']}/proposal-batches/{old_batch['id']}"
    ).json()
    assert old_detail["counts"] == {"pending": 0, "accepted": 0, "rejected": 0}
    old_prop_view = next(i for i in old_detail["items"] if i["id"] == prop_old["id"])
    assert old_prop_view["depends_on"] == [po_old["id"]]


def test_superseded_rows_do_not_reconstruct_stale_edges_and_preserve_undo_and_rejected_deps(client):
    """Superseded rows referencing an accepted root get no dynamic edge; live undo and rejected deps still work."""
    from sqlalchemy import update as sa_update
    from test_pending_merge import run_on_top_of_pending

    from ontofoundry_api.services.proposals import dependency_map

    session = create_session(client)
    root_batch = seed_batch(client, session, chain(session)[:1])
    root = root_batch["items"][0]
    accepted_root = decide(client, session, [(root["id"], "accept")])
    assert accepted_root.status_code == 200, accepted_root.text
    session = accepted_root.json()["session"]

    # Seed a pending property referencing the accepted root from a separate batch (no persisted edge to root).
    old_prop_batch = seed_batch(
        client,
        session,
        [
            create(
                "po-no",
                "property",
                {
                    "owner_type_id": root["target_id"],
                    "display_name": "订单号",
                    "name": "order_no",
                },
            )
        ],
    )
    old_prop = old_prop_batch["items"][0]

    # Revise that pending property after an unrelated object so old_prop (ordinal 0)
    # deterministically precedes new_prop (ordinal 1) across open batches.
    _, candidate, url, headers = run_on_top_of_pending(client, session)
    pending_prop = next(p for p in candidate["properties"] if p["id"] == old_prop["target_id"])
    extra_obj = create("extra-obj", "object_type", {"display_name": "补充实体", "name": "extra_obj"})
    revised_prop = {
        "operation": "update",
        "target_kind": "property",
        "target_id": old_prop["target_id"],
        "after": {
            **{k: v for k, v in pending_prop.items() if k != "id"},
            "description": "新版订单号",
        },
    }
    submitted = client.post(url, json={"items": items_only([extra_obj, revised_prop])}, headers=headers)
    assert submitted.status_code == 200 and submitted.json()["passed"], submitted.text
    new_prop_batch_id = submitted.json()["batch_id"]

    with client.app.state.session_factory() as db:
        db.execute(
            sa_update(ModelingSessionRecord)
            .where(ModelingSessionRecord.id == session["id"])
            .values(task_status="finished", result_state="done")
        )
        db.commit()

    new_prop_batch = client.get(
        ROOT + f"/sessions/{session['id']}/proposal-batches/{new_prop_batch_id}"
    ).json()
    new_prop = next(i for i in new_prop_batch["items"] if i["target_id"] == old_prop["target_id"])
    assert old_prop["ordinal"] == 0 and new_prop["ordinal"] == 1

    with client.app.state.session_factory() as db:
        deps = dependency_map(
            db,
            [root_batch["id"], old_prop_batch["id"], new_prop_batch_id],
            session["workspace_id"],
            session["id"],
        )
    # No stale dynamic edge reconstructed from the superseded row to the accepted root.
    assert deps.get(old_prop["id"], []) == []
    assert root["id"] in deps.get(new_prop["id"], [])

    # Accept the live property, then undo the accepted root (via human_batch_id so root stays decidable)
    # and verify cascade undo reaches the live replacement without touching the superseded row.
    latest = current(client, session)
    accepted_prop = decide(client, latest, [(new_prop["id"], "accept")])
    assert accepted_prop.status_code == 200, accepted_prop.text
    latest = accepted_prop.json()["session"]
    with client.app.state.session_factory() as db:
        db.get(ModelingSessionRecord, session["id"]).human_batch_id = root_batch["id"]
        db.commit()
    undone = decide(client, latest, [(root["id"], "reject")])
    assert undone.status_code == 200, undone.text
    assert {r["proposal_id"]: r["status"] for r in undone.json()["results"]} == {
        root["id"]: "rejected",
        new_prop["id"]: "rejected",
    }

    # A rejected dependency still blocks accepting a pending dependent.
    fresh = create_session(client)
    rej_batch = seed_batch(client, fresh, chain(fresh)[:2])
    rej_po, rej_prop = rej_batch["items"]
    with client.app.state.session_factory() as db:
        db.get(ProposalItemRecord, rej_po["id"]).status = "rejected"
        db.commit()
    blocked = decide(client, fresh, [(rej_prop["id"], "accept")])
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "PROPOSAL_NOT_DECIDABLE"
    assert blocked.json()["error"]["message"] == "依赖提案已拒绝，请先恢复"
