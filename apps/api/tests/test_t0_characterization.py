"""T0: lock the current modeling/publish behavior before the Proposal-first rework.

Each test pins what the code does today. Tests marked "KNOWN GAP" describe
behavior the proposal-first design (docs/design/2026-09-26-...) deliberately
changes; the phase that changes it must update that test on purpose, never
silently. Everything else must keep passing through T1–T8.
"""

from copy import deepcopy
from uuid import uuid4

import pytest
from test_modeling import ONTOLOGY, ROOT, create_session, publish, save

from ontofoundry_api.db_models import ModelingSessionRecord, OntologyVersionRecord


def version_count(client):
    with client.app.state.session_factory() as db:
        return db.query(OntologyVersionRecord).count()


def set_candidates(client, session_id, candidates):
    with client.app.state.session_factory() as db:
        db.get(ModelingSessionRecord, session_id).candidates_json = candidates
        db.commit()


def preview(client, session):
    return client.post(
        ROOT + "/sessions/" + session["id"] + "/preview",
        json={"revision": session["revision"], "message": ""},
    )


# --- candidates -----------------------------------------------------------


def test_accepting_a_candidate_writes_the_draft_and_bumps_revision(client):
    s = create_session(client)
    before = deepcopy(s["draft"]["object_types"][0])
    cid = str(uuid4())
    set_candidates(
        client,
        s["id"],
        [
            {
                "id": cid,
                "kind": "object_type",
                "value": {**before, "description": "Agent 的建议"},
                "before": before,
                "status": "pending",
            }
        ],
    )

    result = client.post(
        ROOT + "/sessions/" + s["id"] + "/candidates",
        json={"revision": s["revision"], "ids": [cid], "action": "accept"},
    )

    assert result.status_code == 200, result.text
    body = result.json()
    assert body["revision"] == s["revision"] + 1
    accepted = next(t for t in body["draft"]["object_types"] if t["id"] == before["id"])
    assert accepted["description"] == "Agent 的建议"
    assert body["candidates"][0]["status"] == "accepted"


def test_accept_that_would_break_the_draft_changes_nothing(client):
    s = create_session(client)
    first, second = s["draft"]["object_types"][:2]
    cid = str(uuid4())
    # Renaming one type to another's technical name violates draft uniqueness.
    set_candidates(
        client,
        s["id"],
        [
            {
                "id": cid,
                "kind": "object_type",
                "value": {**second, "technical_name": first["technical_name"]},
                "before": second,
                "status": "pending",
            }
        ],
    )

    result = client.post(
        ROOT + "/sessions/" + s["id"] + "/candidates",
        json={"revision": s["revision"], "ids": [cid], "action": "accept"},
    )

    assert result.status_code == 422
    after = client.get(ROOT + "/sessions/" + s["id"]).json()
    assert after["revision"] == s["revision"]
    assert after["draft"] == s["draft"]


def test_candidate_decision_with_stale_revision_is_rejected(client):
    s = create_session(client)
    saved = save(client, s, s["draft"]).json()
    result = client.post(
        ROOT + "/sessions/" + s["id"] + "/candidates",
        json={"revision": s["revision"], "ids": [], "action": "accept"},
    )
    assert result.status_code == 409
    assert client.get(ROOT + "/sessions/" + s["id"]).json()["revision"] == saved["revision"]


# --- session revision and active runs -------------------------------------


@pytest.mark.parametrize(
    "status", ["submitting", "queued", "running", "waiting_input", "waiting_permission"]
)
def test_active_run_blocks_draft_saves_and_publish(client, status):
    # KNOWN GAP (T3/T4): proposal-first allows edits during a run under CAS only.
    s = create_session(client)
    with client.app.state.session_factory() as db:
        db.get(ModelingSessionRecord, s["id"]).task_status = status
        db.commit()

    assert save(client, s, s["draft"]).status_code == 409
    assert publish(client, s).status_code == 409
    assert version_count(client) == 1


# --- preview --------------------------------------------------------------


def test_preview_requires_current_revision(client):
    s = create_session(client)
    save(client, s, s["draft"])
    assert preview(client, s).status_code == 409


def test_preview_returns_revision_validation_ossie_and_diff(client):
    s = create_session(client)
    s["draft"]["object_types"][0]["description"] = "预览中的修改"
    s = save(client, s, s["draft"]).json()

    body = preview(client, s).json()

    assert body["revision"] == s["revision"]
    assert body["validation"]["publishable"] is True
    assert body["ossie"]["version"]
    assert any(c["path"].endswith(".description") for c in body["changes"])


def test_preview_compares_the_raw_draft_not_the_merged_result(client):
    # KNOWN GAP (T6): preview must show the B/L/D merged snapshot and return
    # current_version_id; today it diffs the raw draft against the latest
    # version, so another session's published change reads as a revert.
    a, b = create_session(client), create_session(client)
    a["draft"]["object_types"][0]["description"] = "A 已发布的修改"
    b["draft"]["object_types"][1]["description"] = "B 的修改"
    a = save(client, a, a["draft"]).json()
    b = save(client, b, b["draft"]).json()
    assert publish(client, a).status_code == 200

    body = preview(client, b).json()

    a_type = a["draft"]["object_types"][0]["id"]
    assert any(a_type in c["path"] and c["path"].endswith(".description") for c in body["changes"])
    assert "current_version_id" not in body
    # ...while publishing merges and keeps A's change.
    published = publish(client, b)
    assert published.status_code == 200
    snapshot = client.get(ROOT + "/published-snapshot").json()
    assert {"A 已发布的修改", "B 的修改"} <= {t["description"] for t in snapshot["object_types"]}


# --- publish and merge ----------------------------------------------------


def test_successful_publish_moves_session_base_and_stores_merged_draft(client):
    a, b = create_session(client), create_session(client)
    a["draft"]["object_types"][0]["description"] = "A"
    b["draft"]["object_types"][1]["description"] = "B"
    a = save(client, a, a["draft"]).json()
    b = save(client, b, b["draft"]).json()
    publish(client, a)

    body = publish(client, b).json()

    session = body["session"]
    assert session["base_version_id"] == body["version"]["version_id"]
    assert session["revision"] == b["revision"] + 1
    assert {"A", "B"} <= {t["description"] for t in session["draft"]["object_types"]}


def test_conflicting_publish_leaves_no_version_and_keeps_the_session(client):
    a, b = create_session(client), create_session(client)
    a["draft"]["object_types"][0]["description"] = "A"
    b["draft"]["object_types"][0]["description"] = "B"
    a = save(client, a, a["draft"]).json()
    b = save(client, b, b["draft"]).json()
    publish(client, a)
    count = version_count(client)

    response = publish(client, b)

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["conflicts"] and detail["current_version_id"]
    assert version_count(client) == count
    after = client.get(ROOT + "/sessions/" + b["id"]).json()
    assert after["revision"] == b["revision"]
    assert after["base_version_id"] == b["base_version_id"]


def test_resolve_merge_rejects_a_stale_current_version(client):
    a, b = create_session(client), create_session(client)
    a["draft"]["object_types"][0]["description"] = "A"
    b["draft"]["object_types"][0]["description"] = "B"
    a = save(client, a, a["draft"]).json()
    b = save(client, b, b["draft"]).json()
    publish(client, a)
    detail = publish(client, b).json()["detail"]

    response = client.post(
        ROOT + "/sessions/" + b["id"] + "/resolve-merge",
        json={
            "revision": b["revision"],
            "current_version_id": str(uuid4()),
            "resolutions": {c["path"]: "draft" for c in detail["conflicts"]},
        },
    )

    assert response.status_code == 409
    assert client.get(ONTOLOGY + "/version").json()["version"] == 2


def test_publish_with_stale_revision_is_rejected(client):
    s = create_session(client)
    save(client, s, s["draft"])
    assert publish(client, s).status_code == 409
    assert version_count(client) == 1
