from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import update

from ontofoundry_api.db_models import ModelingSessionRecord, utc_now
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.ossie.importer import import_ossie
from ontofoundry_api.services.dataagent import (
    DataAgentClient,
    DataAgentError,
    build_turn_prompt,
)
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.model_result import build_candidates, reconcile_run

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"
RESULT_PATH = Path(__file__).parent / "fixtures" / "ontofoundry_result_v1.json"
RUN_TOKEN = "0123456789abcdef0123456789abcdef"
TASK_ID = "task-model-1"
TOP_LEVEL_WARNING = (
    "本轮结果包含顶层本体约束变更，v1 不生成候选，"
    "如需应用请手工编辑或导入 Ossie 文件"
)


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


def test_build_candidates_has_deterministic_ids_before_and_annotations():
    before = _empty_draft()
    imported, _ = import_ossie(
        _payload()["ontology"],
        workspace_id=str(DEMO_WORKSPACE_ID),
        base=before,
        mode="merge",
    )
    first = build_candidates(before, imported, _payload()["annotations"], TASK_ID)
    second = build_candidates(before, imported, _payload()["annotations"], TASK_ID)

    assert first == second
    assert {candidate["kind"] for candidate in first} == {
        "object_type",
        "link_type",
        "mapping",
    }
    assert all(
        candidate["id"]
        == f"{TASK_ID}:{candidate['kind']}:{candidate['value']['id']}"
        for candidate in first
    )
    assert all("before" in candidate for candidate in first)
    assert all(candidate["before"] is None for candidate in first)
    customer = next(
        candidate
        for candidate in first
        if candidate["kind"] == "object_type"
        and candidate["value"]["technical_name"] == "customer"
    )
    assert customer["reason"] == "Customer is the central sales entity"
    assert customer["evidence"][0]["material_id"] == "material-1"


def test_unmatched_annotation_is_ignored():
    payload = _payload()
    payload["annotations"].append(
        {
            "target": {"kind": "object_type", "key": "not_present"},
            "reason": "must not leak",
            "evidence": [{"material_id": "x", "line_start": 1, "line_end": 1}],
        }
    )
    imported, _ = import_ossie(
        payload["ontology"], workspace_id=str(DEMO_WORKSPACE_ID), base=_empty_draft()
    )
    candidates = build_candidates(
        _empty_draft(), imported, payload["annotations"], TASK_ID
    )
    assert "must not leak" not in {candidate["reason"] for candidate in candidates}


def test_valid_result_writes_candidates_only_and_warns_for_top_level_change(
    client, monkeypatch
):
    session = _create_model_session(client)
    before = _row(client, session["id"])
    _install_download(monkeypatch, [_payload()])

    assert _reconcile(client, session["id"]) == "done"

    after = _row(client, session["id"])
    assert after.draft_json == before.draft_json
    assert after.revision == before.revision + 1
    assert after.result_state == "done"
    assert after.task_status == "finished"
    assert [item["kind"] for item in after.candidates_json].count("object_type") == 2
    assert [item["kind"] for item in after.candidates_json].count("link_type") == 1
    assert [item["kind"] for item in after.candidates_json].count("mapping") == 1
    assert TOP_LEVEL_WARNING in after.result_warnings
    assert not {"object", "link", "constraint"} & {
        item["kind"] for item in after.candidates_json
    }


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


def test_merge_never_proposes_deleting_existing_types():
    before, _ = import_ossie(
        _payload()["ontology"],
        workspace_id=str(DEMO_WORKSPACE_ID),
        base=_empty_draft(),
        mode="merge",
    )
    partial = deepcopy(_payload()["ontology"])
    partial["ontology"] = [
        item for item in partial["ontology"] if item["concept"] == "customer"
    ]
    partial.pop("ontology_mappings")
    partial["requires"] = []
    imported, _ = import_ossie(
        partial, workspace_id=str(DEMO_WORKSPACE_ID), base=before, mode="merge"
    )
    candidates = build_candidates(before, imported, [], TASK_ID)
    assert candidates == []
    assert len(imported["object_types"]) == 2


def test_existing_mapping_never_becomes_an_update_candidate():
    before, _ = import_ossie(
        _payload()["ontology"],
        workspace_id=str(DEMO_WORKSPACE_ID),
        base=_empty_draft(),
        mode="merge",
    )
    changed = deepcopy(_payload()["ontology"])
    changed["ontology_mappings"][0]["semantic_model"]["datasets"][0][
        "source"
    ] = "other.customers"
    imported, _ = import_ossie(
        changed, workspace_id=str(DEMO_WORKSPACE_ID), base=before, mode="merge"
    )
    assert not [
        item
        for item in build_candidates(before, imported, [], TASK_ID)
        if item["kind"] == "mapping"
    ]


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
    assert recovered.candidates_json
    assert len(paths) == 2


def test_success_supersedes_only_old_pending_candidates(client, monkeypatch):
    old = [
        {"id": "pending", "status": "pending"},
        {"id": "accepted", "status": "accepted"},
        {"id": "ignored", "status": "ignored"},
    ]
    session = _create_model_session(client, candidates_json=old)
    _install_download(monkeypatch, [_payload()])
    assert _reconcile(client, session["id"]) == "done"
    by_id = {item["id"]: item for item in _row(client, session["id"]).candidates_json}
    assert by_id["pending"]["status"] == "superseded"
    assert by_id["accepted"]["status"] == "accepted"
    assert by_id["ignored"]["status"] == "ignored"


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


def test_accepted_candidates_update_draft_and_manual_edit_conflicts(
    client, monkeypatch
):
    session = _create_model_session(client)
    _install_download(monkeypatch, [_payload()])
    assert _reconcile(client, session["id"]) == "done"
    row = _row(client, session["id"])
    ids = [item["id"] for item in row.candidates_json]

    accepted = client.post(
        ROOT + f"/sessions/{session['id']}/candidates",
        json={"revision": row.revision, "ids": ids, "action": "accept"},
    )
    assert accepted.status_code == 200, accepted.text
    assert len(accepted.json()["draft"]["object_types"]) == 2
    assert len(accepted.json()["draft"]["link_types"]) == 1
    assert len(accepted.json()["draft"]["mappings"]) == 1

    conflict_session = _create_model_session(client)
    _install_download(monkeypatch, [_payload()])
    assert _reconcile(client, conflict_session["id"]) == "done"
    row = _row(client, conflict_session["id"])
    target = next(item for item in row.candidates_json if item["kind"] == "object_type")
    manually_changed = deepcopy(row.draft_json)
    manual = deepcopy(target["value"])
    manual["description"] = "manual edit wins"
    manually_changed["object_types"].append(manual)
    with client.app.state.session_factory() as db:
        db.execute(
            update(ModelingSessionRecord)
            .where(ModelingSessionRecord.id == conflict_session["id"])
            .values(draft_json=manually_changed)
        )
        db.commit()
    response = client.post(
        ROOT + f"/sessions/{conflict_session['id']}/candidates",
        json={"revision": row.revision, "ids": [target["id"]], "action": "accept"},
    )
    assert response.status_code == 200, response.text
    candidate = next(
        item for item in response.json()["candidates"] if item["id"] == target["id"]
    )
    assert "手工修改" in candidate["conflict"]
    current = next(
        item
        for item in response.json()["draft"]["object_types"]
        if item["id"] == target["value"]["id"]
    )
    assert current["description"] == "manual edit wins"


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


def test_worker_that_lost_its_claim_cannot_write_candidates(client, monkeypatch):
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
    assert _row(client, session["id"]).candidates_json


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
