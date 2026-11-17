"""AI-08: a run may start with pending proposals; its result absorbs them into one pending batch."""

from run_helpers import RUN_TOKEN, TASK_ID
from sqlalchemy import select, update
from test_modeling import ROOT, create_session
from test_t1_proposal_contract import items_only
from test_t4_proposal_decisions import chain, create, decide, seed_batch

from ontofoundry_api.db_models import ModelingSessionRecord, ProposalItemRecord
from ontofoundry_api.domain.canonical import snapshot_sha256
from ontofoundry_api.services.proposals import proposal_context, run_review_context
from ontofoundry_api.services.run_credentials import RunGrant, issue


def run_on_top_of_pending(client, session):
    """A running run pinned the way the platform now pins it: pending proposals applied."""
    with client.app.state.session_factory() as db:
        record = db.get(ModelingSessionRecord, session["id"])
        review = run_review_context(db, record)
        candidate = review.pop("candidate_draft")
        manifest = {
            "run_token": RUN_TOKEN, "workspace_id": session["workspace_id"], "session_id": session["id"],
            "base_version_id": session["base_version_id"], "base_version_sha256": session["base_version_sha256"],
            "source_session_revision": session["revision"] + 1, "source_draft_sha256": snapshot_sha256(session["draft"]),
            "materials": [], "producer": {"agent_id": "agent", "skill": "ontofoundry-modeling", "mode": "model"},
            "result_contract": "proposals", "pinned_draft": candidate, **review,
        }
        db.execute(update(ModelingSessionRecord).where(ModelingSessionRecord.id == session["id"]).values(
            task_status="running", dataagent_topic_id="topic-1", dataagent_task_id=TASK_ID,
            dataagent_task_mode="model", dataagent_run_token=RUN_TOKEN, result_state="",
            revision=session["revision"] + 1, run_manifest_json=manifest,
        ))
        credential = issue(client.app.state.settings.session_secret, RunGrant(
            session["workspace_id"], session["id"], RUN_TOKEN, session["base_version_id"], record.created_by))
        db.commit()
    url = f"/api/v1/workspaces/{session['workspace_id']}/sessions/{session['id']}/proposals"
    return manifest, candidate, url, {"Authorization": "Bearer " + credential}


def items_of(client, session_id):
    with client.app.state.session_factory() as db:
        rows = db.scalars(select(ProposalItemRecord).where(ProposalItemRecord.session_id == session_id)).all()
        return [(r.id, r.batch_id, r.status, r.operation, r.target_id, r.after_json) for r in rows]


def test_a_run_sees_pending_proposals_in_its_draft_and_context(client):
    session = create_session(client)
    pending = seed_batch(client, session, chain(session)[:1])
    manifest, candidate, _, _ = run_on_top_of_pending(client, session)
    target = pending["items"][0]["target_id"]
    assert any(o["id"] == target for o in candidate["object_types"])
    context = proposal_context(manifest, candidate)
    assert [p["target_id"] for p in context["pending_proposals"]] == [target]
    assert "unpublished_changes" in context


def test_submission_revises_pending_items_and_carries_the_rest(client):
    session = create_session(client)
    pending = seed_batch(client, session, chain(session)[:2])  # object po, property on it
    po, prop = pending["items"]
    _, candidate, url, headers = run_on_top_of_pending(client, session)
    pending_object = next(o for o in candidate["object_types"] if o["id"] == po["target_id"])
    revised = {
        "operation": "update", "target_kind": "object_type", "target_id": po["target_id"],
        "after": {**{k: v for k, v in pending_object.items() if k != "id"}, "description": "智能体修订"},
    }
    added = create("extra", "object_type", {"display_name": "补充对象", "name": "extra_object"})
    response = client.post(url, json={"items": items_only([revised, added])}, headers=headers)
    assert response.status_code == 200 and response.json()["passed"], response.text
    new_batch = response.json()["batch_id"]

    rows = {(r[1], r[4]): r for r in items_of(client, session["id"])}
    old = [r for r in rows.values() if r[1] == pending["id"]]
    assert {r[2] for r in old} == {"superseded"}
    new = [r for r in rows.values() if r[1] == new_batch]
    by_target = {r[4]: r for r in new}
    # The pending create, revised by the agent, is still a create of the same element.
    assert by_target[po["target_id"]][3] == "create"
    assert by_target[po["target_id"]][5]["description"] == "智能体修订"
    # The untouched pending property is carried over; the new object is added.
    assert by_target[prop["target_id"]][2] == "pending"
    assert len(new) == 3 and all(r[2] == "pending" for r in new)

    events = client.get(ROOT + f"/sessions/{session['id']}/change-events", params={"target_id": po["target_id"]}).json()["items"]
    assert any(e["subject"] == "proposal" and e["action"] == "revised" and e["actor_kind"] == "agent" for e in events)


def test_withdrawing_a_pending_create_drops_it(client):
    session = create_session(client)
    pending = seed_batch(client, session, chain(session)[:1])
    po = pending["items"][0]
    _, _, url, headers = run_on_top_of_pending(client, session)
    withdrawn = {"operation": "delete", "target_kind": "object_type", "target_id": po["target_id"]}
    added = create("extra", "object_type", {"display_name": "补充对象", "name": "extra_object"})
    response = client.post(url, json={"items": items_only([withdrawn, added])}, headers=headers)
    assert response.status_code == 200 and response.json()["passed"], response.text
    new = [r for r in items_of(client, session["id"]) if r[1] == response.json()["batch_id"]]
    assert [r[4] for r in new if r[4] == po["target_id"]] == []
    assert len(new) == 1


def test_only_the_merged_batch_is_pending_and_it_can_be_accepted(client):
    session = create_session(client)
    pending = seed_batch(client, session, chain(session)[:2])
    _, _, url, headers = run_on_top_of_pending(client, session)
    added = create("extra", "object_type", {"display_name": "补充对象", "name": "extra_object"})
    response = client.post(url, json={"items": items_only([added])}, headers=headers)
    assert response.status_code == 200 and response.json()["passed"], response.text
    batch = response.json()["batch_id"]
    pending_rows = [r for r in items_of(client, session["id"]) if r[2] == "pending"]
    assert {r[1] for r in pending_rows} == {batch}
    with client.app.state.session_factory() as db:
        db.execute(update(ModelingSessionRecord).where(ModelingSessionRecord.id == session["id"]).values(task_status="finished", result_state="done"))
        db.commit()
    current = client.get(ROOT + f"/sessions/{session['id']}").json()
    accepted = decide(client, current, [(r[0], "accept") for r in pending_rows])
    assert accepted.status_code == 200, accepted.text
    detail = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches/{pending['id']}").json()
    assert detail["counts"] == {"pending": 0, "accepted": 0, "rejected": 0}
