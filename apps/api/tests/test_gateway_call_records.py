"""Best-effort queue recording, lifecycle transitions and admin audit contracts."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

import pytest
from gateway_helpers import WID, call, recorded, rpc, token, wait_for
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from test_auth import login_client as login_fixture

from ontofoundry_api.db_models import (
    OntologyGatewayCallRecord,
    PersonalAccessTokenRecord,
    UserRecord,
    utc_now,
)
from ontofoundry_api.services import ontology_gateway
from ontofoundry_api.services.gateway_call_log import GatewayCallRecorder

login_client = login_fixture
AUDIT = "/api/v1/admin/gateway-calls"


def test_success_error_arguments_full_response_and_last_used(client):
    item = token(client)
    first = call(client, item["token"], "get_ontology", {"workspace_id": WID, "limit": 1})
    cursor = first["structuredContent"]["next_cursor"]
    second = call(client, item["token"], "get_ontology", {"workspace_id": WID, "limit": 1, "cursor": cursor})
    failure = call(client, item["token"], "get_ontology", {"workspace_id": WID, "cursor": "invalid"})
    rows = recorded(client, 3, outcomes=["ok", "ok", "error"])
    assert [r.response for r in rows] == [r["structuredContent"] for r in (first, second, failure)]
    assert rows[1].arguments["pagination"] is True
    assert all("cursor" not in row.arguments for row in rows)
    assert cursor not in json.dumps(rows[1].arguments)
    assert rows[-1].error_code == "cursor_invalid" and rows[-1].error_message
    assert all(r.user_id and r.token_id == item["id"] and r.duration_ms >= 0 for r in rows)
    assert item["token"] not in json.dumps([r.arguments for r in rows])
    def used():
        with client.app.state.session_factory() as db:
            return db.get(PersonalAccessTokenRecord, item["id"]).last_used_at
    assert wait_for(used)
    detail = client.get(AUDIT + "/" + rows[0].id).json()
    assert set(detail) == {"id", "created_at", "user", "tool", "request_id", "workspaces", "arguments", "response", "outcome", "error_code", "error_message", "duration_ms"}
    assert detail["response"] == first["structuredContent"]
    assert detail["request_id"] == "7"
    assert detail["workspaces"][0]["version_number"] == 1
    assert detail["workspaces"][0]["version_id"] == first["structuredContent"]["version_id"]


def test_started_then_finished_and_unhandled_failure_stays_started(client, monkeypatch):
    credential = token(client)["token"]
    entered, release = threading.Event(), threading.Event()
    original = ontology_gateway.invoke
    def blocked(*args):
        entered.set()
        assert release.wait(4)
        return original(*args)
    monkeypatch.setattr(ontology_gateway, "invoke", blocked)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(call, client, credential, "get_ontology", {"workspace_id": WID})
        try:
            assert entered.wait(2)
            row = recorded(client, outcomes=["started"])[0]
            assert row.response is None and row.duration_ms is None
            detail = client.get(AUDIT + "/" + row.id).json()
            assert detail["outcome"] == "started" and detail["response"] is None
        finally:
            release.set()
        assert not pending.result(timeout=4)["isError"]
    assert recorded(client, outcomes=["ok"])[0].id == row.id
    def crash(*args):
        raise RuntimeError("fictional tool failure")
    monkeypatch.setattr(ontology_gateway, "invoke", crash)
    with pytest.raises(RuntimeError, match="fictional tool failure"):
        call(client, credential, "get_ontology", {"workspace_id": WID})
    assert recorded(client, 2, outcomes=["ok", "started"])[1].response is None


def test_recording_database_block_never_delays_or_changes_result(client, monkeypatch):
    item = token(client)
    expected = call(client, item["token"], "list_spaces")
    recorded(client, outcomes=["ok"])
    entered, release = threading.Event(), threading.Event()
    recorder = client.app.state.gateway_recorder
    original = recorder._write_batch
    def blocked(events):
        entered.set()
        assert release.wait(5)
        original(events)
    monkeypatch.setattr(recorder, "_write_batch", blocked)
    recorder.touch(item["id"], utc_now())
    assert entered.wait(2)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(call, client, item["token"], "list_spaces").result(timeout=1)
        assert result == expected
    finally:
        release.set()
    recorded(client, 2, outcomes=["ok", "ok"])


def test_full_queue_and_enqueue_failure_leave_result_unchanged(client, monkeypatch, caplog):
    credential = token(client)["token"]
    expected = call(client, credential, "list_spaces")
    original = client.app.state.gateway_recorder
    recorder = GatewayCallRecorder(client.app.state.session_factory, capacity=1)
    recorder.queue.put_nowait({"occupied": True})
    client.app.state.gateway_recorder = recorder
    try:
        assert call(client, credential, "list_spaces") == expected
        assert "queue is full" in caplog.text
        def fail(event):
            raise RuntimeError("fictional enqueue error")
        monkeypatch.setattr(recorder.queue, "put_nowait", fail)
        assert call(client, credential, "list_spaces") == expected
        assert "enqueue failed" in caplog.text
    finally:
        client.app.state.gateway_recorder = original


def test_write_failure_logged_and_later_calls_recorded(client, monkeypatch, caplog):
    credential = token(client)["token"]
    recorder = client.app.state.gateway_recorder
    original = recorder._write_batch
    failed = threading.Event()
    def fail(events):
        failed.set()
        raise RuntimeError("fictional recorder failure")
    monkeypatch.setattr(recorder, "_write_batch", fail)
    result = call(client, credential, "list_spaces")
    assert not result["isError"] and failed.wait(2)
    wait_for(lambda: "batch failed" in caplog.text)
    monkeypatch.setattr(recorder, "_write_batch", original)
    call(client, credential, "list_spaces")
    assert any(r.outcome == "ok" for r in recorded(client))


def test_database_outage_retried_and_end_before_start_does_not_regress(client, monkeypatch):
    credential = token(client)["token"]
    recorder = client.app.state.gateway_recorder
    original = recorder._write_batch
    attempts = []
    def flaky(events):
        attempts.append(1)
        if len(attempts) == 1:
            raise OperationalError("fictional", {}, Exception("unavailable"))
        original(events)
    monkeypatch.setattr(recorder, "_write_batch", flaky)
    result = call(client, credential, "list_spaces")
    row = recorded(client, outcomes=["ok"])[0]
    assert row.response == result["structuredContent"] and len(attempts) >= 2
    values = {key: getattr(row, key) for key in ("id", "created_at", "user_id", "token_id", "request_id", "tool", "arguments")}
    original([{"type": "call", "call": {**values, "outcome": "started"}, "workspaces": []}])
    assert recorded(client, outcomes=["ok"])[0].id == row.id
    identity = str(uuid4())
    original([
        {"type": "call", "call": {**values, "id": identity, "outcome": "ok", "response": {"complete": True}, "duration_ms": 1}, "workspaces": []},
        {"type": "call", "call": {**values, "id": identity, "outcome": "started"}, "workspaces": []},
    ])
    with client.app.state.session_factory() as db:
        assert db.get(OntologyGatewayCallRecord, identity).outcome == "ok"


def test_failed_auth_not_recorded(client):
    assert rpc(client, "ofpat.invalid", "tools/list").status_code == 401
    assert rpc(client, None, "tools/list").status_code == 401
    with client.app.state.session_factory() as db:
        assert db.scalar(select(OntologyGatewayCallRecord)) is None


def test_audit_filters_pagination_unknown_space_and_summaries(client):
    item = token(client)
    known = call(client, item["token"], "get_ontology", {"workspace_id": WID, "ids": [str(uuid4())]})
    call(client, item["token"], "search_ontology", {"query": "订单"})
    missing = str(uuid4())
    call(client, item["token"], "get_ontology", {"workspace_id": missing})
    rows = recorded(client, 3, outcomes=["ok", "ok", "error"])
    page = client.get(AUDIT, params={"limit": 1}).json()
    assert set(page) == {"items", "next_cursor"}
    row = page["items"][0]
    assert set(row) == {"id", "created_at", "user", "tool", "workspaces", "summary", "outcome", "error_code", "duration_ms"}
    assert row["workspaces"] == [{"id": missing, "name": None, "version_number": None}]
    second = client.get(AUDIT, params={"limit": 1, "cursor": page["next_cursor"]}).json()
    assert second["items"][0]["summary"] == "订单"
    items = client.get(AUDIT, params={"workspace_id": WID}).json()["items"]
    assert len(items) == 2 and items[-1]["summary"] == "1 个元素"
    assert client.get(AUDIT, params={"outcome": "error"}).json()["items"][0]["id"] == row["id"]
    assert len(client.get(AUDIT, params={"tool": "get_ontology"}).json()["items"]) == 2
    assert len(client.get(AUDIT, params={"user_id": rows[0].user_id}).json()["items"]) == 3
    assert client.get(AUDIT, params={"user_id": str(uuid4())}).json()["items"] == []
    now = utc_now()
    assert client.get(AUDIT, params={"from": (now + timedelta(days=1)).isoformat()}).json()["items"] == []
    assert client.get(AUDIT, params={"to": (now - timedelta(days=1)).isoformat()}).json()["items"] == []
    assert len(client.get(AUDIT, params={"from": (now - timedelta(days=1)).isoformat(), "to": now.isoformat(), "workspace_id": WID}).json()["items"]) == 2
    assert client.get(AUDIT + "/" + rows[0].id).json()["response"] == known["structuredContent"]
    assert client.get(AUDIT + "/" + str(uuid4())).status_code == 404
    assert client.get(AUDIT, params={"limit": 101}).status_code == 422
    assert client.get(AUDIT, params={"cursor": "invalid"}).status_code == 422
    assert client.get(AUDIT, params={"cursor": page["next_cursor"], "tool": "other"}).status_code == 422


def test_audit_requires_platform_admin_login_even_for_detail(login_client):
    for path in (AUDIT, AUDIT + "/fiction"):
        response = login_client.get(path)
        assert response.status_code == 403 and response.json()["error"]["code"] == "PLATFORM_ADMIN_REQUIRED"
    with login_client.app.state.session_factory() as db:
        db.add(UserRecord(id="fiction-user", username="星港用户", display_name="虚构用户"))
        db.commit()
    assert login_client.post("/api/v1/auth/login/local", json={"username": "星港用户", "password": "星港密码"}).status_code == 204
    credential = token(login_client)["token"]
    for path in (AUDIT, AUDIT + "/fiction"):
        assert login_client.get(path).status_code == 403
        response = login_client.get(path, headers={"Authorization": "Bearer " + credential})
        assert response.status_code == 403 and response.json()["error"]["code"] == "PLATFORM_ADMIN_REQUIRED"


def test_shutdown_drain_is_bounded_and_remaining_events_logged(caplog):
    recorder = GatewayCallRecorder(lambda: None)
    recorder.queue.put_nowait({"fiction": True})
    class StuckWorker:
        def join(self, *, timeout):
            assert timeout == 5
        def is_alive(self):
            return True
    recorder.thread = StuckWorker()
    recorder.stop()
    assert recorder.queue.empty() and "shutdown drain exceeded" in caplog.text
    assert recorder.queue.maxsize == 10_000
    assert recorder.stopping.is_set()
    recorder.touch("fiction", utc_now())
    assert "event dropped" in caplog.text
