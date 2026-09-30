"""T8: new runs default to proposals; the switch is observable."""

from test_modeling import ROOT, create_session
from test_t4_proposal_decisions import chain, decide, seed_batch

from ontofoundry_api.config import Settings
from ontofoundry_api.db_models import ModelingSessionRecord


def test_new_runs_ask_for_proposals_by_default():
    Settings.model_config["env_file"] = None
    assert Settings().modeling_result_contract == "proposals"


def test_metrics_report_legacy_runs_batches_staleness_and_decisions(client):
    session = create_session(client)
    po, prop, _link = seed_batch(client, session, chain(session))["items"]
    assert decide(client, session, [(po["id"], "reject")]).status_code == 200
    legacy = create_session(client)
    with client.app.state.session_factory() as db:
        db.get(ModelingSessionRecord, legacy["id"]).task_status = "running"
        db.commit()

    metrics = client.get(ROOT + "/proposal-metrics").json()

    assert metrics["legacy_active_runs"] == 1
    assert metrics["batches"] == {"total": 1, "available": 1}
    assert metrics["batch_failure_rate"] == 0.0
    assert metrics["items"]["rejected"] == 1
    assert metrics["items"]["conflict"] == 2  # dependents of the rejected root
    assert metrics["stale_rate"] == 1.0
    assert metrics["decisions"]["reject"] == 1


def test_a_proposals_run_refuses_an_old_full_snapshot_result(client, monkeypatch):
    import json
    from pathlib import Path

    from run_helpers import install_download, reconcile, row
    from test_t3_proposal_results import proposals_run

    from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError

    session, _manifest = proposals_run(client)
    legacy = json.loads((Path(__file__).parent / "fixtures" / "ontofoundry_result_v1.json").read_text("utf-8"))
    install_download(monkeypatch, [legacy])

    async def refuse(self, **_):
        raise DataAgentError("unavailable")

    monkeypatch.setattr(DataAgentClient, "deliver", refuse)

    assert reconcile(client, session["id"]) == "failed_permanent"
    assert row(client, session["id"]).draft_json == session["draft"]
    batch = client.get(ROOT + f"/sessions/{session['id']}/proposal-batches").json()["items"][0]
    assert batch["status"] == "failed"
    assert batch["error"]["code"] == "RESULT_SCHEMA_INVALID"
