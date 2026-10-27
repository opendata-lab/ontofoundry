"""Core publication refuses stale requests and active runs without partial writes."""

import pytest
from test_modeling import ROOT, create_session, publish, save

from ontofoundry_api.db_models import ModelingSessionRecord


@pytest.mark.parametrize(
    "status", ["submitting", "queued", "running", "waiting_input", "waiting_permission"]
)
def test_active_run_blocks_publish_and_draft_edits(client, status):
    s = create_session(client)
    with client.app.state.session_factory() as db:
        row = db.get(ModelingSessionRecord, s["id"])
        row.task_status = status
        row.run_manifest_json = {"result_contract": "proposals"}
        db.commit()
    s["draft"]["object_types"][0]["description"] = "运行中编辑"
    response = save(client, s, s["draft"])
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "SESSION_RUNNING"
    assert publish(client, s).status_code == 409


def test_old_publish_envelope_rejected(client):
    s = create_session(client)
    assert (
        client.post(
            ROOT + f"/sessions/{s['id']}/publish", json={"revision": s["revision"]}
        ).status_code
        == 422
    )
    assert (
        client.post(
            ROOT + f"/sessions/{s['id']}/preview",
            json={"expected_session_revision": s["revision"] - 1},
        ).status_code
        == 409
    )
