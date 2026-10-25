"""Conversation-only modeling inputs remain citable across runs."""

import hashlib
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from test_modeling import ROOT, create_session
from test_stepwise_modeling import fake_agent, set_row, work_pack

from ontofoundry_api.api import agent_conversation
from ontofoundry_api.db_models import MaterialChunkRecord, MaterialRecord, ModelingSessionRecord
from ontofoundry_api.domain.evidence import check_material_evidence
from ontofoundry_api.services import request_material
from ontofoundry_api.services.dataagent import DataAgentError
from ontofoundry_api.services.materials_lookup import material_lookup
from ontofoundry_api.services.material_source import material_source_path

REQUEST = "  # 云杉维修站\r\n工单 WX-101 已由小岚接单，预计明日完工。\r\n"


def send(client, session_id, content=REQUEST, mode="model"):
    return client.post(
        ROOT + f"/sessions/{session_id}/agent-conversation/messages",
        json={"content": content, "metadata": {"mode": mode}},
    )


def test_request_is_original_markdown_in_work_pack_and_valid_evidence(client, monkeypatch, fake_agent):
    monkeypatch.setattr(request_material, "utc_now", lambda: datetime(2026, 10, 25, 8, 46, tzinfo=UTC))
    session = create_session(client)
    response = send(client, session["id"])
    assert response.status_code == 202, response.text
    uploads, _ = fake_agent
    sha = hashlib.sha256(REQUEST.encode()).hexdigest()
    with client.app.state.session_factory() as db:
        current = db.get(ModelingSessionRecord, session["id"])
        material = db.scalar(select(MaterialRecord).where(MaterialRecord.sha256 == sha))
        assert current.material_ids == [material.id]
        assert material.origin == "conversation_request"
        assert material.name == "建模需求-2026-10-25-1646.md"
        assert material.byte_size == len(REQUEST.encode())
        chunks = db.scalars(select(MaterialChunkRecord).where(MaterialChunkRecord.material_id == material.id)).all()
        assert "".join(c.text for c in chunks) == REQUEST
        path = material_source_path(db, client.app.state.settings, material)
        assert path.read_bytes() == REQUEST.encode()
        entry, = work_pack(uploads, current.run_manifest_json)["materials"]
        assert entry["id"] == material.id and entry["sha256"] == sha
        assert entry["lines"] == 2 and entry["original_range"] == [1, 2]
        assert uploads[entry["path"]] == REQUEST.encode()
        assert current.run_manifest_json["input_files"]["materials"] == [entry]
        check_material_evidence({
            "material_id": material.id, "material_sha256": sha,
            "locator": {"line_start": 2, "line_end": 2},
            "quote": "工单 WX-101 已由小岚接单",
        }, material_lookup(db, client.app.state.settings, material.workspace_id), "文档实例")
        path.unlink()
        assert material_source_path(db, client.app.state.settings, material).read_bytes() == REQUEST.encode()
    overview = client.get(ROOT + "/materials/overview").json()["items"]
    assert any(m["id"] == entry["id"] and m["origin"] == "conversation_request" for m in overview)


@pytest.mark.parametrize(("content", "mode", "saved"), [
    ("需" * 19, "model", False), ("需" * 20, "model", True),
    ("  " + "需" * 19 + "\n", "model", False),
    (" " * 21, "model", False), ("确认", "model", False),
    ("重试", "model", False), (REQUEST, "chat", False),
])
def test_eligibility(client, fake_agent, content, mode, saved):
    session = create_session(client)
    assert send(client, session["id"], content, mode).status_code == 202
    with client.app.state.session_factory() as db:
        current = db.get(ModelingSessionRecord, session["id"])
        assert len(current.material_ids) == int(saved)
        assert len(list(db.scalars(select(MaterialRecord)))) == int(saved)


def test_repeated_request_confirmation_and_cross_session_reuse(client, fake_agent):
    first = create_session(client)
    assert send(client, first["id"]).status_code == 202
    for content in (REQUEST, "确认", "重试"):
        set_row(client, first["id"], task_status="finished", result_state="awaiting_reply")
        assert send(client, first["id"], content).status_code == 202
    second = create_session(client)
    assert send(client, second["id"]).status_code == 202
    uploads, _ = fake_agent
    with client.app.state.session_factory() as db:
        materials = list(db.scalars(select(MaterialRecord)))
        assert len(materials) == 1
        for session in (first, second):
            current = db.get(ModelingSessionRecord, session["id"])
            assert current.material_ids == [materials[0].id]
            assert work_pack(uploads, current.run_manifest_json)["materials"][0]["id"] == materials[0].id


def test_existing_upload_keeps_its_origin(client, fake_agent):
    response = client.post(ROOT + "/materials", params={"name": "原有需求.md"}, content=REQUEST.encode())
    assert response.status_code == 201, response.text
    material = response.json()
    session = create_session(client)
    assert send(client, session["id"]).status_code == 202
    with client.app.state.session_factory() as db:
        current = db.get(ModelingSessionRecord, session["id"])
        assert current.material_ids == [material["id"]]
        record = db.get(MaterialRecord, material["id"])
        assert record.origin == "upload" and record.name == "原有需求.md"


def test_busy_run_rolls_back_new_request_and_session_selection(client, fake_agent):
    session = create_session(client)
    set_row(client, session["id"], task_status="running")
    assert send(client, session["id"]).status_code == 409
    with client.app.state.session_factory() as db:
        assert db.get(ModelingSessionRecord, session["id"]).material_ids == []
        assert db.scalar(select(MaterialRecord)) is None


def test_upload_failure_keeps_request_for_short_retry(client, monkeypatch, fake_agent):
    session = create_session(client)
    set_row(client, session["id"], dataagent_topic_id="topic-1")
    original_client = agent_conversation._client

    async def fail_upload(*args):
        raise DataAgentError("虚构远端暂不可用", status_code=503)

    monkeypatch.setattr(agent_conversation, "_client", lambda *_: SimpleNamespace(upload=fail_upload))
    assert send(client, session["id"]).status_code == 503
    with client.app.state.session_factory() as db:
        current = db.get(ModelingSessionRecord, session["id"])
        material_id, = current.material_ids
        assert current.task_status == "failed"
    monkeypatch.setattr(agent_conversation, "_client", original_client)
    assert send(client, session["id"], "重试").status_code == 202
    uploads, _ = fake_agent
    with client.app.state.session_factory() as db:
        current = db.get(ModelingSessionRecord, session["id"])
        assert current.material_ids == [material_id]
        assert work_pack(uploads, current.run_manifest_json)["materials"][0]["id"] == material_id
