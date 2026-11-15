"""A run keeps the previous run's work only while it can still be valid (design 2026-11-13 modeling resume)."""

from test_request_material import create_session, send
from test_stepwise_modeling import fake_agent, set_row, work_pack  # noqa: F401

from ontofoundry_api.api import agent_conversation
from ontofoundry_api.db_models import ModelingSessionRecord

LONG_FOLLOW_UP = "不要生成指标，只保留对象、关系和数据集，其余照上一轮的成果继续提交。"


def current(client, session_id):
    with client.app.state.session_factory() as db:
        return db.get(ModelingSessionRecord, session_id)


def fail_run(client, session_id, status="finished"):
    set_row(client, session_id, task_status=status, result_state="failed_permanent")


def test_failed_run_on_the_same_baseline_is_continued(client, fake_agent):  # noqa: F811 (pytest fixture)
    session = create_session(client)
    assert send(client, session["id"]).status_code == 202
    first = current(client, session["id"]).run_manifest_json
    assert first["baseline"] and "resume" not in first
    fail_run(client, session["id"])
    assert send(client, session["id"], "继续").status_code == 202
    second = current(client, session["id"]).run_manifest_json
    assert second["baseline"] == first["baseline"]
    assert second["resume"] == {"previous_run_token": first["run_token"], "previous_run_tokens": [first["run_token"]]}
    uploads, _ = fake_agent
    assert work_pack(uploads, second)["run"]["resume"] == second["resume"]


def test_a_long_new_instruction_still_keeps_the_work_for_the_agent_to_decide(client, fake_agent):  # noqa: F811 (pytest fixture)
    # Request texts become materials but are not part of the baseline.
    session = create_session(client)
    assert send(client, session["id"]).status_code == 202
    first = current(client, session["id"]).run_manifest_json
    fail_run(client, session["id"], status="cancelled")
    assert send(client, session["id"], LONG_FOLLOW_UP).status_code == 202
    assert current(client, session["id"]).run_manifest_json["resume"]["previous_run_token"] == first["run_token"]


def test_a_changed_baseline_starts_fresh(client, fake_agent):  # noqa: F811 (pytest fixture)
    session = create_session(client)
    assert send(client, session["id"]).status_code == 202
    fail_run(client, session["id"])
    set_row(client, session["id"], base_version_sha256="0" * 64)
    assert send(client, session["id"], "继续").status_code == 202
    assert "resume" not in current(client, session["id"]).run_manifest_json


def test_a_stored_batch_is_never_continued(client, fake_agent, monkeypatch):  # noqa: F811 (pytest fixture)
    session = create_session(client)
    assert send(client, session["id"]).status_code == 202
    fail_run(client, session["id"])
    monkeypatch.setattr(agent_conversation, "submitted_batch", lambda *args: object())
    assert send(client, session["id"], "继续").status_code == 202
    manifest = current(client, session["id"]).run_manifest_json
    assert "resume" not in manifest
    uploads, _ = fake_agent
    assert "resume" not in work_pack(uploads, manifest)["run"]


def test_budget_exhausted_message_no_longer_suggests_dropping_groups():
    from pathlib import Path

    from ontofoundry_api.services import proposal_submit

    source = Path(proposal_submit.__file__).read_text(encoding="utf-8")
    assert "删去仍不通过的提案组后提交" not in source
    assert "可在本轮成果上继续" in source


def test_continuations_carry_the_whole_unsubmitted_chain(client, fake_agent):  # noqa: F811 (pytest fixture)
    session = create_session(client)
    tokens = []
    for content in (None, "继续", "再试一次"):
        assert (send(client, session["id"]) if content is None else send(client, session["id"], content)).status_code == 202
        tokens.append(current(client, session["id"]).run_manifest_json["run_token"])
        fail_run(client, session["id"])
    assert current(client, session["id"]).run_manifest_json["resume"]["previous_run_tokens"] == tokens[:2]


def test_request_texts_are_not_reported_as_new_material(client, fake_agent):  # noqa: F811 (pytest fixture)
    session = create_session(client)
    assert send(client, session["id"]).status_code == 202
    fail_run(client, session["id"])
    assert send(client, session["id"], LONG_FOLLOW_UP).status_code == 202
    manifest = current(client, session["id"]).run_manifest_json
    pack = work_pack(fake_agent[0], manifest)
    assert pack["scenario_facts"]["new_material_ids"] == []
    assert len(manifest["request_material_ids"]) == 2
    assert all(m.get("from_request") for m in pack["materials"])
