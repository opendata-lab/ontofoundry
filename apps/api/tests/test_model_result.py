from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, update
from sqlalchemy.sql.dml import Update

from ontofoundry_api.db_models import ModelingSessionRecord, WorkspaceRecord, utc_now
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.services.dataagent import (
    DataAgentClient,
    DataAgentError,
    build_turn_prompt,
)
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID, build_demo_draft
from ontofoundry_api.services.model_result import reconcile_run

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"
RESULT_PATH = Path(__file__).parent / "fixtures" / "ontofoundry_result_v1.json"
RUN_TOKEN = "0123456789abcdef0123456789abcdef"
TASK_ID = "task-model-1"
def _payload() -> dict:
    return json.loads(RESULT_PATH.read_text(encoding="utf-8"))


def _empty_draft() -> dict:
    return OntologyDraft(workspace_id=DEMO_WORKSPACE_ID).model_dump(mode="json")


def _create_model_session(client, **values) -> dict:
    response = client.post(ROOT + "/sessions", json={"title": "T5 result"})
    assert response.status_code == 201, response.text
    session = response.json()
    defaults = {
        "draft_json": _empty_draft(),
        "candidates_json": [],
        "task_status": "finished",
        "task_detail": "DataAgent 处理完成",
        "dataagent_topic_id": "topic-1",
        "dataagent_task_id": TASK_ID,
        "dataagent_task_mode": "model",
        "dataagent_run_token": RUN_TOKEN,
        "result_state": "",
        "result_warnings": [],
    }
    defaults.update(values)
    with client.app.state.session_factory() as db:
        db.execute(
            update(ModelingSessionRecord)
            .where(ModelingSessionRecord.id == session["id"])
            .values(**defaults)
        )
        db.commit()
    return session


def _row(client, session_id: str) -> ModelingSessionRecord:
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session_id)
        assert item is not None
        db.expunge(item)
        return item


def _install_download(monkeypatch, values) -> list[str]:
    queue = list(values)
    paths: list[str] = []

    async def download(self, topic_id: str, rel_path: str):
        assert topic_id == "topic-1"
        paths.append(rel_path)
        value = queue.pop(0)
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, bytes):
            return value, "application/json"
        return json.dumps(value, ensure_ascii=False).encode(), "application/json"

    monkeypatch.setattr(DataAgentClient, "download", download)
    return paths


def _reconcile(client, session_id: str, task_id: str = TASK_ID) -> str:
    return asyncio.run(
        reconcile_run(client.app, str(DEMO_WORKSPACE_ID), session_id, task_id)
    )


def test_valid_result_replaces_draft_and_clears_candidates(client, monkeypatch):
    old_draft = build_demo_draft().model_dump(mode="json")
    session = _create_model_session(
        client,
        draft_json=old_draft,
        candidates_json=[{"id": "old", "status": "pending"}],
    )
    before = _row(client, session["id"])
    with client.app.state.session_factory() as db:
        current_version_id = db.get(
            WorkspaceRecord, str(DEMO_WORKSPACE_ID)
        ).current_version_id
    _install_download(monkeypatch, [_payload()])

    assert _reconcile(client, session["id"]) == "done"

    after = _row(client, session["id"])
    assert after.draft_json != before.draft_json
    assert after.revision == before.revision + 1
    assert after.result_state == "done"
    assert after.task_status == "finished"
    assert after.candidates_json == []
    assert len(after.draft_json["object_types"]) == 2
    assert len(after.draft_json["link_types"]) == 1
    assert len(after.draft_json["mappings"]) == 1
    assert "supplier" not in {
        item["technical_name"] for item in after.draft_json["object_types"]
    }
    with client.app.state.session_factory() as db:
        assert (
            db.get(WorkspaceRecord, str(DEMO_WORKSPACE_ID)).current_version_id
            == current_version_id
        )
    assert "预览差异后发布新版本" in after.task_detail


def test_chat_completion_never_downloads_or_changes_draft_and_candidates(
    client, monkeypatch
):
    old = [{"id": "old", "status": "pending"}]
    session = _create_model_session(
        client, dataagent_task_mode="chat", candidates_json=old
    )

    async def forbidden(*args, **kwargs):
        raise AssertionError("chat must not download a modeling result")

    monkeypatch.setattr(DataAgentClient, "download", forbidden)
    before = _row(client, session["id"])
    assert _reconcile(client, session["id"]) == ""
    after = _row(client, session["id"])
    assert after.draft_json == before.draft_json
    assert after.candidates_json == old
    assert after.revision == before.revision


def test_run_token_path_isolation_does_not_consume_previous_round_file(
    client, monkeypatch
):
    session = _create_model_session(client, dataagent_run_token="new-token")
    paths = _install_download(
        monkeypatch,
        [DataAgentError("missing", status_code=404)],
    )
    before = _row(client, session["id"])

    assert _reconcile(client, session["id"]) == "failed_permanent"
    after = _row(client, session["id"])
    assert paths == ["output/ontofoundry-result-new-token.json"]
    assert after.draft_json == before.draft_json
    assert after.candidates_json == before.candidates_json
    assert "new-token" in after.task_detail


def test_file_run_token_mismatch_is_permanent_and_preserves_model(
    client, monkeypatch
):
    session = _create_model_session(client)
    payload = _payload()
    payload["run_token"] = "previous-round"
    _install_download(monkeypatch, [payload])
    before = _row(client, session["id"])

    assert _reconcile(client, session["id"]) == "failed_permanent"
    after = _row(client, session["id"])
    assert "run_token" in after.task_detail
    assert after.draft_json == before.draft_json
    assert after.candidates_json == before.candidates_json


def test_same_task_is_idempotent(client, monkeypatch):
    session = _create_model_session(client)
    paths = _install_download(monkeypatch, [_payload()])
    assert _reconcile(client, session["id"]) == "done"
    first = _row(client, session["id"])
    assert _reconcile(client, session["id"]) == "done"
    second = _row(client, session["id"])
    assert second.candidates_json == first.candidates_json
    assert second.revision == first.revision
    assert len(paths) == 1


def test_download_timeout_is_retriable_then_next_reconcile_succeeds(
    client, monkeypatch
):
    session = _create_model_session(client)
    paths = _install_download(
        monkeypatch,
        [DataAgentError("timeout", status_code=503), _payload()],
    )
    before = _row(client, session["id"])

    assert _reconcile(client, session["id"]) == "failed_retriable"
    failed = _row(client, session["id"])
    assert failed.draft_json == before.draft_json
    assert failed.candidates_json == before.candidates_json
    assert failed.revision == before.revision

    assert _reconcile(client, session["id"]) == "done"
    recovered = _row(client, session["id"])
    assert recovered.result_state == "done"
    assert recovered.candidates_json == []
    assert len(recovered.draft_json["object_types"]) == 2
    assert len(paths) == 2


@pytest.mark.parametrize(
    ("download_value", "detail"),
    [
        (DataAgentError("not found", status_code=404), "没有产出"),
        (b"not-json", "JSON"),
        ({**_payload(), "schema_version": "wrong"}, "schema_version"),
        (
            {
                **_payload(),
                "ontology": {"version": "wrong", "name": "bad", "ontology": []},
            },
            "Ossie",
        ),
        (
            {
                **_payload(),
                "ontology": {
                    "version": "0.2.0.dev0",
                    "name": "values_only",
                    "ontology": [
                        {"concept": "code", "type": "ValueType", "extends": ["String"]}
                    ],
                },
            },
            "无法导入",
        ),
    ],
)
def test_permanent_failures_are_specific_and_never_mutate_model(
    client, monkeypatch, download_value, detail
):
    session = _create_model_session(
        client, candidates_json=[{"id": "keep", "status": "pending"}]
    )
    before = _row(client, session["id"])
    _install_download(monkeypatch, [download_value])

    assert _reconcile(client, session["id"]) == "failed_permanent"
    after = _row(client, session["id"])
    assert after.task_status == "failed"
    assert detail in after.task_detail
    assert after.draft_json == before.draft_json
    assert after.candidates_json == before.candidates_json
    assert after.revision == before.revision


def test_expired_processing_lease_can_be_reclaimed_after_process_crash(
    client, monkeypatch
):
    class SimulatedProcessDeath(BaseException):
        pass

    session = _create_model_session(client)
    _install_download(monkeypatch, [SimulatedProcessDeath(), _payload()])
    with pytest.raises(SimulatedProcessDeath):
        _reconcile(client, session["id"])
    claimed = _row(client, session["id"])
    assert claimed.result_state == "processing"
    assert claimed.result_claimed_at is not None

    with client.app.state.session_factory() as db:
        db.execute(
            update(ModelingSessionRecord)
            .where(ModelingSessionRecord.id == session["id"])
            .values(result_claimed_at=utc_now() - timedelta(minutes=6))
        )
        db.commit()
    assert _reconcile(client, session["id"]) == "done"
    assert _row(client, session["id"]).result_state == "done"


def test_worker_that_lost_its_claim_cannot_write_version_draft(client, monkeypatch):
    session = _create_model_session(client)

    async def stolen_claim(self, topic_id: str, rel_path: str):
        with client.app.state.session_factory() as db:
            db.execute(
                update(ModelingSessionRecord)
                .where(ModelingSessionRecord.id == session["id"])
                .values(result_claimed_at=utc_now() + timedelta(seconds=1))
            )
            db.commit()
        return json.dumps(_payload()).encode(), "application/json"

    monkeypatch.setattr(DataAgentClient, "download", stolen_claim)
    assert _reconcile(client, session["id"]) == "processing"
    row = _row(client, session["id"])
    assert row.result_state == "processing"
    assert row.candidates_json == []
    assert row.draft_json == _empty_draft()


def test_manual_revision_change_during_run_is_never_overwritten(client, monkeypatch):
    session = _create_model_session(client)
    manual_draft = _empty_draft()
    manual_draft["requires"] = ["manual change"]

    async def edit_before_download_returns(self, topic_id: str, rel_path: str):
        with client.app.state.session_factory() as db:
            db.execute(
                update(ModelingSessionRecord)
                .where(ModelingSessionRecord.id == session["id"])
                .values(
                    draft_json=manual_draft,
                    revision=ModelingSessionRecord.revision + 1,
                )
            )
            db.commit()
        return json.dumps(_payload()).encode(), "application/json"

    monkeypatch.setattr(DataAgentClient, "download", edit_before_download_returns)
    assert _reconcile(client, session["id"]) == "failed_permanent"
    row = _row(client, session["id"])
    assert row.draft_json == manual_draft
    assert row.task_status == "failed"
    assert "会话已更新" in row.task_detail


def test_result_claim_cannot_attach_task_a_lease_after_task_b_starts(
    client, monkeypatch
):
    session = _create_model_session(client)
    engine = client.app.state.session_factory.kw["bind"]
    switched = False

    def switch_task_before_claim(
        conn, clauseelement, multiparams, params, execution_options
    ):
        nonlocal switched
        if (
            switched
            or not isinstance(clauseelement, Update)
            or clauseelement.table.name != ModelingSessionRecord.__tablename__
        ):
            return
        switched = True
        with client.app.state.session_factory() as db:
            db.execute(
                update(ModelingSessionRecord)
                .where(ModelingSessionRecord.id == session["id"])
                .values(
                    dataagent_task_id="task-model-2",
                    dataagent_run_token="run-token-2",
                    task_status="running",
                )
            )
            db.commit()

    async def forbidden_download(*args, **kwargs):
        raise AssertionError("task A must lose the claim before downloading")

    event.listen(engine, "before_execute", switch_task_before_claim)
    monkeypatch.setattr(DataAgentClient, "download", forbidden_download)
    try:
        assert _reconcile(client, session["id"]) == ""
    finally:
        event.remove(engine, "before_execute", switch_task_before_claim)

    row = _row(client, session["id"])
    assert row.dataagent_task_id == "task-model-2"
    assert row.task_status == "running"
    assert row.last_result_task_id is None
    assert row.result_state == ""


def test_task_a_download_404_cannot_mark_task_b_failed(client, monkeypatch):
    session = _create_model_session(client)

    async def task_b_starts_then_a_is_missing(self, topic_id: str, rel_path: str):
        with client.app.state.session_factory() as db:
            db.execute(
                update(ModelingSessionRecord)
                .where(ModelingSessionRecord.id == session["id"])
                .values(
                    dataagent_task_id="task-model-2",
                    dataagent_run_token="run-token-2",
                    task_status="running",
                    revision=ModelingSessionRecord.revision + 1,
                )
            )
            db.commit()
        raise DataAgentError("missing", status_code=404)

    monkeypatch.setattr(DataAgentClient, "download", task_b_starts_then_a_is_missing)
    assert _reconcile(client, session["id"]) == "processing"
    row = _row(client, session["id"])
    assert row.dataagent_task_id == "task-model-2"
    assert row.dataagent_run_token == "run-token-2"
    assert row.task_status == "running"
    assert row.result_state == "processing"


def test_task_a_success_cannot_write_version_draft_after_task_b_starts(
    client, monkeypatch
):
    session = _create_model_session(client)

    async def task_b_starts_before_a_download_returns(
        self, topic_id: str, rel_path: str
    ):
        with client.app.state.session_factory() as db:
            db.execute(
                update(ModelingSessionRecord)
                .where(ModelingSessionRecord.id == session["id"])
                .values(
                    dataagent_task_id="task-model-2",
                    dataagent_run_token="run-token-2",
                    task_status="running",
                )
            )
            db.commit()
        return json.dumps(_payload()).encode(), "application/json"

    monkeypatch.setattr(
        DataAgentClient, "download", task_b_starts_before_a_download_returns
    )
    assert _reconcile(client, session["id"]) == "processing"
    row = _row(client, session["id"])
    assert row.dataagent_task_id == "task-model-2"
    assert row.dataagent_run_token == "run-token-2"
    assert row.task_status == "running"
    assert row.result_state == "processing"
    assert row.candidates_json == []


def test_events_retry_retriable_result_before_done_and_return_model_metadata(
    client, monkeypatch
):
    client.app.state.settings.dataagent_base_url = "https://dataagent.example"
    client.app.state.settings.dataagent_access_key = "server-secret"
    session = _create_model_session(client, task_status="running")
    calls: list[object] = []

    async def stream(self, task_id: str, after_id: int = 0):
        if False:  # pragma: no cover - makes this an empty async iterator
            yield b""

    async def task(self, task_id: str):
        return {"task_id": task_id, "task_status": "finished"}

    async def download(self, topic_id: str, rel_path: str):
        calls.append("download")
        if calls.count("download") == 1:
            raise DataAgentError("timeout", status_code=503)
        return json.dumps(_payload()).encode(), "application/json"

    async def no_wait(delay: int):
        calls.append(delay)

    monkeypatch.setattr(DataAgentClient, "stream", stream)
    monkeypatch.setattr(DataAgentClient, "task", task)
    monkeypatch.setattr(DataAgentClient, "download", download)
    monkeypatch.setattr("ontofoundry_api.api.agent_conversation.asyncio.sleep", no_wait)

    response = client.get(
        ROOT + f"/sessions/{session['id']}/agent-conversation/events"
    )
    assert response.status_code == 200, response.text
    assert calls == ["download", 2, "download"]
    assert response.text.count("event: done") == 1
    assert '"status":"finished"' in response.text
    assert '"metadata":{"mode":"model"}' in response.text
    row = _row(client, session["id"])
    assert row.candidates_json == []
    assert len(row.draft_json["object_types"]) == 2


def test_events_exhaust_three_retries_before_permanent_done(client, monkeypatch):
    client.app.state.settings.dataagent_base_url = "https://dataagent.example"
    client.app.state.settings.dataagent_access_key = "server-secret"
    session = _create_model_session(client, task_status="running")
    calls: list[object] = []

    async def stream(self, task_id: str, after_id: int = 0):
        if False:  # pragma: no cover - makes this an empty async iterator
            yield b""

    async def task(self, task_id: str):
        return {"task_id": task_id, "task_status": "finished"}

    async def timeout(self, topic_id: str, rel_path: str):
        calls.append("download")
        raise DataAgentError("timeout", status_code=503)

    async def no_wait(delay: int):
        calls.append(delay)

    monkeypatch.setattr(DataAgentClient, "stream", stream)
    monkeypatch.setattr(DataAgentClient, "task", task)
    monkeypatch.setattr(DataAgentClient, "download", timeout)
    monkeypatch.setattr("ontofoundry_api.api.agent_conversation.asyncio.sleep", no_wait)

    response = client.get(
        ROOT + f"/sessions/{session['id']}/agent-conversation/events"
    )
    assert response.status_code == 200, response.text
    assert calls == ["download", 2, "download", 4, "download", 8, "download"]
    assert response.text.count("event: done") == 1
    assert '"status":"failed"' in response.text
    assert "重试三次后仍失败" in response.text
    row = _row(client, session["id"])
    assert row.result_state == "failed_permanent"
    assert row.draft_json == _empty_draft()
    assert row.candidates_json == []


def test_model_prompt_contains_complete_versioned_result_contract():
    prompt = build_turn_prompt(
        "build it",
        mode="model",
        workspace_id="workspace-1",
        session_id="session-1",
        context_file="uploads/context.json",
        material_files=["uploads/material.md"],
        run_token=RUN_TOKEN,
    )
    assert "ontofoundry.model-result/v1" in prompt
    assert '"run_token"' in prompt
    assert RUN_TOKEN in prompt
    assert f"output/ontofoundry-result-{RUN_TOKEN}.json" in prompt
    assert "Apache Ossie 0.2.0.dev0" in prompt
    assert "完整" in prompt
    assert "替换当前草稿的完整快照" in prompt
    assert "原样复用其 technical_name" in prompt
    assert "snake_case" in prompt
    assert "ai_context.ontofoundry.display_names" in prompt
    assert '"customer":"客户"' in prompt
    assert "预览差异后发布" in prompt


@pytest.mark.parametrize("status_code", [408, 425, 429, 500, 502, 503])
def test_transient_download_failures_stay_retriable(status_code):
    """A rate-limited or timed-out fetch must not discard a produced model.

    429 is the case that matters: the result file exists and is correct, and
    the only thing wrong is that we asked too fast. Marking that permanent
    throws away work the agent already did, with no path back to it.
    """
    from ontofoundry_api.services.model_result import _is_retriable_download

    assert _is_retriable_download(status_code) is True


@pytest.mark.parametrize("status_code", [400, 403, 404, 422])
def test_definitive_download_failures_are_permanent(status_code):
    """These describe the result, not the request, and will not change on retry."""
    from ontofoundry_api.services.model_result import _is_retriable_download

    assert _is_retriable_download(status_code) is False


def test_a_model_that_breaks_a_draft_invariant_fails_instead_of_crashing(
    client, monkeypatch
):
    """The backstop for anything `import_ossie` cannot turn into a valid draft.

    Only OssieImportError was caught, so a pydantic ValidationError escaped out
    of whichever request happened to be reconciling — the conversation endpoint
    answered 500 and the lease stayed held with result_state parked on
    "processing", leaving the run unresolvable and the conversation unreadable.
    """
    old_draft = build_demo_draft().model_dump(mode="json")
    session = _create_model_session(
        client,
        draft_json=old_draft,
        candidates_json=[{"id": "old", "status": "pending"}],
    )
    before = _row(client, session["id"])
    _install_download(monkeypatch, [_payload()])

    def _reject(*args, **kwargs):
        OntologyDraft.model_validate(
            {"workspace_id": str(DEMO_WORKSPACE_ID), "mappings": [{"bad": True}]}
        )

    monkeypatch.setattr(
        "ontofoundry_api.services.model_result.import_ossie", _reject
    )

    assert _reconcile(client, session["id"]) == "failed_permanent"

    after = _row(client, session["id"])
    assert after.task_status == "failed"
    assert "不满足草稿约束" in after.task_detail
    # The rejected model never touches what the user already has.
    assert after.draft_json == before.draft_json
    assert after.candidates_json == before.candidates_json
    assert after.revision == before.revision


def test_result_warnings_say_what_the_import_could_not_carry_over(client, monkeypatch):
    """`skipped` is the actionable half and used to be dropped.

    Keeping only `notes` meant a draft could come back smaller than the answer
    described — a relation quietly missing its data join — with nothing on screen
    explaining which concept was missing a mapping.
    """
    session = _create_model_session(client)
    payload = _payload()
    _install_download(monkeypatch, [payload])

    def _import(*args, **kwargs):
        return (
            OntologyDraft(workspace_id=DEMO_WORKSPACE_ID).model_dump(mode="json"),
            {
                "notes": ["文件带有 OntoFoundry 扩展信息"],
                "skipped": [
                    {
                        "path": "semantic_model.relationships[belongs_to_order]",
                        "reason": "order_item 没有数据映射，该关系的数据连接未设置",
                    }
                ],
            },
        )

    monkeypatch.setattr(
        "ontofoundry_api.services.model_result.import_ossie", _import
    )

    assert _reconcile(client, session["id"]) == "done"

    warnings = _row(client, session["id"]).result_warnings
    assert "文件带有 OntoFoundry 扩展信息" in warnings
    assert any("order_item 没有数据映射" in item for item in warnings)


def _install_deliver(monkeypatch, task_id: str = "task-repair-1") -> list[str]:
    """Capture the follow-up turns the platform sends back to the agent."""
    sent: list[str] = []

    async def deliver(self, *, topic_id, content, agent_id, execution_mode):
        assert topic_id == "topic-1"
        sent.append(content)
        return {"task_id": task_id, "task_status": "waiting"}

    monkeypatch.setattr(DataAgentClient, "deliver", deliver)
    return sent


def test_an_unusable_result_is_handed_back_to_the_agent_to_fix(client, monkeypatch):
    """Validate, report the errors, let the author correct them.

    The agent is the only thing that can produce a different model, so failing
    the run outright throws away the work and tells the user nothing they can
    act on. Handing back the specific complaints is what a reviewer would do.
    """
    session = _create_model_session(client)
    before = _row(client, session["id"])
    broken = _payload()
    broken["ontology"]["ontology"] = [{"concept": "customer", "type": "NotAType"}]
    _install_download(monkeypatch, [broken])
    sent = _install_deliver(monkeypatch)

    assert _reconcile(client, session["id"]) == ""

    after = _row(client, session["id"])
    assert after.task_status == "running"
    assert after.dataagent_task_id == "task-repair-1"
    # A new nonce, so the corrected result cannot be confused with this one.
    assert after.dataagent_run_token != before.dataagent_run_token
    assert after.draft_json == before.draft_json

    assert len(sent) == 1
    assert "结果校验未通过" in sent[0]
    assert after.dataagent_run_token in sent[0]


def test_the_repair_request_names_what_to_fix(client, monkeypatch):
    """A usable draft that ignores the naming and display-name instructions.

    Observed for real: an agent returned `Customer`, `Order` and `Product`
    alongside `order_item`, with no Chinese display names at all.
    """
    session = _create_model_session(client)
    payload = _payload()
    payload["ontology"]["ontology"][0]["concept"] = "Customer"
    payload["ontology"]["ai_context"]["ontofoundry"]["display_names"] = {}
    _install_download(monkeypatch, [payload])
    sent = _install_deliver(monkeypatch)

    assert _reconcile(client, session["id"]) == ""

    assert len(sent) == 1
    assert "Customer" in sent[0]
    assert "snake_case" in sent[0]
    assert "display_names" in sent[0]
    assert "完整" in sent[0]


def test_a_convention_complaint_never_costs_a_working_model(client, monkeypatch):
    """If the agent cannot be reached, the usable draft is still written.

    Naming is worth one request for a correction. It is not worth discarding a
    model that imports cleanly.
    """
    session = _create_model_session(client)
    payload = _payload()
    payload["ontology"]["ai_context"]["ontofoundry"]["display_names"] = {}
    _install_download(monkeypatch, [payload])

    async def refuse(self, **kwargs):
        raise DataAgentError("DataAgent 拒绝了本次投递", status_code=503)

    monkeypatch.setattr(DataAgentClient, "deliver", refuse)

    assert _reconcile(client, session["id"]) == "done"

    after = _row(client, session["id"])
    assert len(after.draft_json["object_types"]) == 2
    assert any("display_names" in item for item in after.result_warnings)


def test_an_unusable_result_still_fails_when_the_agent_cannot_be_reached(
    client, monkeypatch
):
    session = _create_model_session(client)
    before = _row(client, session["id"])
    broken = _payload()
    broken["ontology"]["ontology"] = [{"concept": "customer", "type": "NotAType"}]
    _install_download(monkeypatch, [broken])

    async def refuse(self, **kwargs):
        raise DataAgentError("DataAgent 拒绝了本次投递", status_code=503)

    monkeypatch.setattr(DataAgentClient, "deliver", refuse)

    assert _reconcile(client, session["id"]) == "failed_permanent"
    after = _row(client, session["id"])
    assert after.task_status == "failed"
    assert after.draft_json == before.draft_json
