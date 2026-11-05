"""Run settlement: run isolation and leases."""

from datetime import timedelta

import pytest
from run_helpers import TASK_ID, install_download, reconcile
from test_t3_proposal_results import proposals_run, result, some_items

from ontofoundry_api.db_models import ModelingSessionRecord, utc_now
from ontofoundry_api.services.dataagent import build_turn_prompt


def test_expired_processing_lease_recovered(client, monkeypatch):
    s, m = proposals_run(client)
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, s["id"])
        item.result_state = "processing"
        item.last_result_task_id = TASK_ID
        item.result_claimed_at = utc_now() - timedelta(minutes=6)
        db.commit()
    paths = install_download(monkeypatch, [result(m, some_items(s["draft"]))])
    assert reconcile(client, s["id"]) == "done"
    assert reconcile(client, s["id"]) == "done"
    assert paths == []  # the submitted batch settles the run; nothing is downloaded


def test_deleted_session_old_callback_is_noop(client, monkeypatch):
    s, m = proposals_run(client)
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, s["id"])
        db.delete(item)
        db.commit()
    paths = install_download(monkeypatch, [])
    assert reconcile(client, s["id"]) == ""
    assert paths == []


def test_model_prompt_requires_proposal_contract():
    with pytest.raises(ValueError):
        build_turn_prompt(
            "建模",
            mode="model",
            workspace_id="fictional",
            session_id="session",
            context_file="context.json",
            material_files=[],
        )
    prompt = build_turn_prompt(
        "建模",
        mode="model",
        workspace_id="fictional",
        session_id="session",
        context_file="context.json",
        material_files=[{"path": "material.md", "bytes": 100000}],
        proposal_prompt="ontofoundry.proposals/v1",
        run_token="round",
    )
    # Modeling runs read the work pack; the generic size hint is for chat only.
    assert "ontofoundry.proposals/v1" in prompt and "超过" not in prompt
    assert "model-result" not in prompt
