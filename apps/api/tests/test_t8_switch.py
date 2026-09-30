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
