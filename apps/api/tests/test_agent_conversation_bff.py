from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from functools import partial
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, update

from ontofoundry_api.db_models import (
    MaterialRecord,
    ModelingSessionRecord,
    WorkspaceMemberRecord,
    utc_now,
)
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.run_status import to_run_status

ROOT = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}"
OTHER_WORKSPACE_ID = "00000000-0000-0000-0000-000000000099"


def _create_session(client, title: str = "Agent Conversation 契约") -> dict:
    response = client.post(ROOT + "/sessions", json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


def _endpoint(session_id: str) -> str:
    return ROOT + f"/sessions/{session_id}/agent-conversation"


def _install_transport(monkeypatch, handler) -> None:
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        partial(real_async_client, transport=transport),
    )


def _configure(client) -> None:
    settings = client.app.state.settings
    settings.dataagent_base_url = "https://dataagent.example"
    settings.dataagent_access_key = "server-secret"


def _json_request(request: httpx.Request) -> dict:
    return json.loads(request.read())


def _messages_response(items: list[dict], *, page: int = 1, total: int | None = None):
    return httpx.Response(
        200,
        json={
            "topic_id": "topic-1",
            "page": page,
            "page_size": 500,
            "order": "asc",
            "total": len(items) if total is None else total,
            "items": items,
        },
    )


def _set_session(client, session_id: str, **values) -> None:
    with client.app.state.session_factory() as db:
        db.execute(
            update(ModelingSessionRecord)
            .where(ModelingSessionRecord.id == session_id)
            .values(**values)
        )
        db.commit()


def _session_row(client, session_id: str) -> ModelingSessionRecord:
    with client.app.state.session_factory() as db:
        item = db.get(ModelingSessionRecord, session_id)
        assert item is not None
        db.expunge(item)
        return item


def test_all_six_endpoints_require_membership_and_reject_cross_workspace_session(client):
    session = _create_session(client)
    base = _endpoint(session["id"])
    calls = [
        ("GET", base, None),
        ("POST", base + "/messages", {"content": "hello", "metadata": {}}),
        ("GET", base + "/events", None),
        ("POST", base + "/cancel", {"task_id": "task-1"}),
        (
            "POST",
            base + "/interactions",
            {
                "task_id": "task-1",
                "kind": "question",
                "request_id": "q-1",
                "payload": {"answers": []},
            },
        ),
        ("GET", base + "/files/output/result.json", None),
    ]

    with client.app.state.session_factory() as db:
        db.execute(
            delete(WorkspaceMemberRecord).where(
                WorkspaceMemberRecord.workspace_id == str(DEMO_WORKSPACE_ID)
            )
        )
        db.commit()

    for method, path, payload in calls:
        response = client.request(method, path, json=payload)
        assert response.status_code == 403, (method, path, response.text)

    # Membership is checked before the workspace/session ownership lookup.
    for method, path, payload in calls:
        other_path = path.replace(str(DEMO_WORKSPACE_ID), OTHER_WORKSPACE_ID)
        response = client.request(method, other_path, json=payload)
        assert response.status_code == 403, (method, other_path, response.text)


def test_topic_is_lazy_created_then_reused_across_refresh_and_second_send(
    client, monkeypatch
):
    _configure(client)
    session = _create_session(client)
    base = _endpoint(session["id"])
    created = 0
    delivered = 0
    messages = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal created, delivered
        path = request.url.path
        if request.method == "POST" and path.endswith("/topics"):
            created += 1
            return httpx.Response(200, json={"topic_id": "topic-1"})
        if request.method == "POST" and path.endswith("/files"):
            return httpx.Response(200, json={"rel_path": "uploads/context.json"})
        if path.endswith("/tasks/deliver-message"):
            delivered += 1
            payload = _json_request(request)
            task_id = f"task-{delivered}"
            messages.append(
                {
                    "message_id": f"message-{delivered}",
                    "topic_id": "topic-1",
                    "task_id": task_id,
                    "sender_type": "user",
                    "type": "text",
                    "content": payload["content"],
                    "seq_id": delivered,
                }
            )
            return httpx.Response(
                200,
                json={"task_id": task_id, "task_status": "waiting"},
            )
        if path.endswith("/topics/topic-1/messages"):
            return _messages_response(messages)
        if path.endswith("/tasks/task-1"):
            return httpx.Response(
                200, json={"task_id": "task-1", "task_status": "finished"}
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    _install_transport(monkeypatch, handler)

    empty = client.get(base)
    assert empty.status_code == 200
    assert empty.json() == {"messages": [], "run": None}
    assert created == 0

    first = client.post(base + "/messages", json={"content": "第一轮", "metadata": {}})
    assert first.status_code == 202, first.text
    assert first.json()["task_id"] == "task-1"
    assert created == 1

    refreshed = client.get(base)
    assert refreshed.status_code == 200, refreshed.text
    assert len(refreshed.json()["messages"]) == 1
    assert _session_row(client, session["id"]).dataagent_topic_id == "topic-1"

    second = client.post(
        base + "/messages",
        json={"content": "第二轮", "metadata": {"mode": "chat"}},
    )
    assert second.status_code == 202, second.text
    assert second.json()["task_id"] == "task-2"
    assert created == 1
    assert delivered == 2


def test_dataagent_identity_headers_are_complete(client, monkeypatch):
    _configure(client)
    session = _create_session(client)
    seen: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers)
        if request.url.path.endswith("/topics"):
            return httpx.Response(200, json={"topic_id": "topic-1"})
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json={"rel_path": "uploads/context.json"})
        return httpx.Response(200, json={"task_id": "task-1", "task_status": "waiting"})

    _install_transport(monkeypatch, handler)
    response = client.post(
        _endpoint(session["id"]) + "/messages",
        json={"content": "hello", "metadata": {}},
    )
    assert response.status_code == 202, response.text
    assert seen
    for headers in seen:
        assert headers["X-ODW-Client"] == "widget"
        assert headers["X-ODW-Website-Id"] == "ontofoundry"
        assert headers["X-ODW-User-Id"] == (
            f"ontofoundry:{DEMO_WORKSPACE_ID}:{session['id']}"
        )
        assert headers["X-ODW-Access-Key"] == "server-secret"


def test_get_fetches_all_history_pages(client, monkeypatch):
    _configure(client)
    session = _create_session(client)
    _set_session(client, session["id"], dataagent_topic_id="topic-1")
    pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        pages.append(page)
        start = (page - 1) * 500
        size = 500 if page < 3 else 1
        items = [
            {
                "message_id": f"message-{index}",
                "topic_id": "topic-1",
                "sender_type": "user",
                "type": "text",
                "content": str(index),
                "seq_id": index,
            }
            for index in range(start, start + size)
        ]
        return _messages_response(items, page=page, total=1001)

    _install_transport(monkeypatch, handler)
    response = client.get(_endpoint(session["id"]))
    assert response.status_code == 200, response.text
    assert len(response.json()["messages"]) == 1001
    assert pages == [1, 2, 3]


def test_material_upload_is_idempotent(client, monkeypatch, tmp_path):
    _configure(client)
    session = _create_session(client)
    material_id = str(uuid4())
    material_content = b"material"
    material_sha = "a" * 64
    material_path = client.app.state.settings.data_dir / str(DEMO_WORKSPACE_ID) / (
        material_sha + ".md"
    )
    material_path.parent.mkdir(parents=True, exist_ok=True)
    material_path.write_bytes(material_content)
    with client.app.state.session_factory() as db:
        db.add(
            MaterialRecord(
                id=material_id,
                workspace_id=str(DEMO_WORKSPACE_ID),
                name="source.md",
                sha256=material_sha,
                byte_size=len(material_content),
            )
        )
        db.execute(
            update(ModelingSessionRecord)
            .where(ModelingSessionRecord.id == session["id"])
            .values(material_ids=[material_id])
        )
        db.commit()

    uploaded_names: list[str] = []
    task_number = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal task_number
        path = request.url.path
        if path.endswith("/topics"):
            return httpx.Response(200, json={"topic_id": "topic-1"})
        if path.endswith("/files"):
            disposition = request.read().decode("utf-8", errors="ignore")
            uploaded_names.append(disposition)
            return httpx.Response(200, json={"rel_path": "uploads/file"})
        if path.endswith("/deliver-message"):
            task_number += 1
            return httpx.Response(
                200,
                json={"task_id": f"task-{task_number}", "task_status": "waiting"},
            )
        if path.endswith("/tasks/task-1"):
            return httpx.Response(
                200, json={"task_id": "task-1", "task_status": "finished"}
            )
        if path.endswith("/messages"):
            return _messages_response([])
        raise AssertionError(path)

    _install_transport(monkeypatch, handler)
    base = _endpoint(session["id"])
    assert client.post(base + "/messages", json={"content": "one", "metadata": {}}).status_code == 202
    assert client.get(base).status_code == 200
    assert client.post(base + "/messages", json={"content": "two", "metadata": {}}).status_code == 202

    material_uploads = [body for body in uploaded_names if "source.md" in body]
    context_uploads = [body for body in uploaded_names if "ontofoundry-context" in body]
    assert len(material_uploads) == 1
    assert len(context_uploads) == 2
    assert _session_row(client, session["id"]).uploaded_material_ids == [material_id]


def test_concurrent_posts_cas_before_remote_and_deliver_only_once(client, monkeypatch):
    _configure(client)
    session = _create_session(client)
    deliver_count = 0
    lock = threading.Lock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal deliver_count
        if request.url.path.endswith("/topics"):
            return httpx.Response(200, json={"topic_id": "topic-1"})
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json={"rel_path": "uploads/context.json"})
        if request.url.path.endswith("/deliver-message"):
            with lock:
                deliver_count += 1
            time.sleep(0.15)
            return httpx.Response(200, json={"task_id": "task-1", "task_status": "waiting"})
        raise AssertionError(request.url.path)

    _install_transport(monkeypatch, handler)
    url = _endpoint(session["id"]) + "/messages"

    def send():
        return client.post(url, json={"content": "race", "metadata": {}})

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _: send(), range(2)))

    assert sorted(response.status_code for response in responses) == [202, 409]
    assert deliver_count == 1


def test_remote_failure_releases_claim_and_deletes_new_topic(client, monkeypatch):
    _configure(client)
    session = _create_session(client)
    deleted: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/topics"):
            return httpx.Response(200, json={"topic_id": "topic-new"})
        if request.method == "DELETE":
            deleted.append(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(503, json={"detail": "unavailable"})

    _install_transport(monkeypatch, handler)
    response = client.post(
        _endpoint(session["id"]) + "/messages",
        json={"content": "hello", "metadata": {}},
    )
    assert response.status_code == 503
    row = _session_row(client, session["id"])
    assert row.task_status == "failed"
    assert row.dataagent_task_id is None
    assert deleted == ["topic-new"]


@pytest.mark.parametrize("failure_kind", ["timeout", "disconnect", "server-5xx"])
def test_unknown_deliver_outcome_stays_submitting_then_reconciles_without_redelivery(
    client, monkeypatch, failure_kind
):
    """A task created before a broken response must block a duplicate submit."""
    _configure(client)
    session = _create_session(client)
    _set_session(
        client,
        session["id"],
        task_status="finished",
        dataagent_topic_id="topic-1",
        dataagent_task_id="task-previous",
    )
    delivered_content = ""
    deliver_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal deliver_count, delivered_content
        path = request.url.path
        if path.endswith("/files"):
            return httpx.Response(200, json={"rel_path": "uploads/context.json"})
        if path.endswith("/deliver-message"):
            deliver_count += 1
            delivered_content = _json_request(request)["content"]
            if failure_kind == "timeout":
                raise httpx.ReadTimeout("response timed out", request=request)
            if failure_kind == "server-5xx":
                return httpx.Response(503, json={"detail": "unavailable"})
            raise httpx.ReadError("response disconnected", request=request)
        if path.endswith("/messages"):
            return _messages_response(
                [
                    {
                        "message_id": "message-lost-response",
                        "topic_id": "topic-1",
                        "task_id": "task-lost-response",
                        "sender_type": "user",
                        "type": "text",
                        "content": delivered_content,
                        "seq_id": 1,
                    }
                ]
            )
        if path.endswith("/tasks/task-lost-response"):
            return httpx.Response(
                200,
                json={
                    "task_id": "task-lost-response",
                    "task_status": "waiting",
                },
            )
        raise AssertionError(path)

    _install_transport(monkeypatch, handler)
    base = _endpoint(session["id"])
    lost = client.post(base + "/messages", json={"content": "one", "metadata": {}})
    assert lost.status_code == 503
    claimed = _session_row(client, session["id"])
    assert claimed.task_status == "submitting"
    assert claimed.dataagent_task_id is None

    duplicate = client.post(
        base + "/messages", json={"content": "duplicate", "metadata": {}}
    )
    assert duplicate.status_code == 409
    assert deliver_count == 1

    _set_session(
        client,
        session["id"],
        updated_at=utc_now() - timedelta(seconds=121),
    )
    reconciled = client.get(base)
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["run"]["task_id"] == "task-lost-response"
    row = _session_row(client, session["id"])
    assert row.dataagent_task_id == "task-lost-response"
    assert row.task_status == "queued"
    assert deliver_count == 1


def test_new_topic_is_persisted_before_unknown_deliver_and_can_be_reconciled(
    client, monkeypatch
):
    """The first turn can reconcile a lost deliver response via its saved topic."""
    _configure(client)
    session = _create_session(client)
    delivered_content = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal delivered_content
        path = request.url.path
        if path.endswith("/topics"):
            return httpx.Response(200, json={"topic_id": "topic-new"})
        if path.endswith("/files"):
            return httpx.Response(200, json={"rel_path": "uploads/context.json"})
        if path.endswith("/deliver-message"):
            delivered_content = _json_request(request)["content"]
            raise httpx.ReadTimeout("response timed out", request=request)
        if path.endswith("/messages"):
            return _messages_response(
                [
                    {
                        "message_id": "message-first-turn",
                        "topic_id": "topic-new",
                        "task_id": "task-first-turn",
                        "sender_type": "user",
                        "type": "text",
                        "content": delivered_content,
                        "seq_id": 1,
                    }
                ]
            )
        if path.endswith("/tasks/task-first-turn"):
            return httpx.Response(
                200,
                json={"task_id": "task-first-turn", "task_status": "waiting"},
            )
        raise AssertionError(path)

    _install_transport(monkeypatch, handler)
    base = _endpoint(session["id"])
    lost = client.post(base + "/messages", json={"content": "one", "metadata": {}})
    assert lost.status_code == 503
    claimed = _session_row(client, session["id"])
    assert claimed.task_status == "submitting"
    assert claimed.dataagent_topic_id == "topic-new"

    _set_session(
        client,
        session["id"],
        updated_at=utc_now() - timedelta(seconds=121),
    )
    reconciled = client.get(base)
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["run"]["task_id"] == "task-first-turn"
    row = _session_row(client, session["id"])
    assert row.dataagent_topic_id == "topic-new"
    assert row.dataagent_task_id == "task-first-turn"


@pytest.mark.parametrize("failure_kind", ["connection-refused", "bad-request"])
def test_definite_deliver_failure_releases_claim(client, monkeypatch, failure_kind):
    _configure(client)
    session = _create_session(client)
    _set_session(client, session["id"], dataagent_topic_id="topic-1")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json={"rel_path": "uploads/context.json"})
        if request.url.path.endswith("/deliver-message"):
            if failure_kind == "bad-request":
                return httpx.Response(422, json={"detail": "invalid prompt"})
            raise httpx.ConnectError("connection refused", request=request)
        raise AssertionError(request.url.path)

    _install_transport(monkeypatch, handler)
    response = client.post(
        _endpoint(session["id"]) + "/messages",
        json={"content": "hello", "metadata": {}},
    )
    assert response.status_code == (422 if failure_kind == "bad-request" else 503)
    row = _session_row(client, session["id"])
    assert row.task_status == "failed"
    assert row.dataagent_task_id is None


@pytest.mark.parametrize(
    "status",
    ["submitting", "queued", "running", "waiting_input", "waiting_permission"],
)
def test_post_rejects_every_active_status_without_remote_side_effect(
    client, monkeypatch, status
):
    _configure(client)
    session = _create_session(client)
    _set_session(client, session["id"], task_status=status)
    remote_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal remote_calls
        remote_calls += 1
        return httpx.Response(500)

    _install_transport(monkeypatch, handler)
    response = client.post(
        _endpoint(session["id"]) + "/messages",
        json={"content": "hello", "metadata": {}},
    )
    assert response.status_code == 409
    assert remote_calls == 0


def test_events_transform_frames_ping_resubscribe_and_done_after_reconcile(
    client, monkeypatch
):
    _configure(client)
    session = _create_session(client)
    _set_session(
        client,
        session["id"],
        task_status="running",
        dataagent_topic_id="topic-1",
        dataagent_task_id="task-1",
        dataagent_task_mode="chat",
    )
    stream_count = 0
    task_count = 0
    order: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal stream_count, task_count
        if request.url.path.endswith("/sdk-events/stream"):
            stream_count += 1
            if stream_count == 1:
                return httpx.Response(200, content=b'data: {"seq_id":1,"type":"delta"}\n\n')
            return httpx.Response(200, content=b"")
        if request.url.path.endswith("/tasks/task-1"):
            task_count += 1
            status = "running" if task_count == 1 else "finished"
            return httpx.Response(200, json={"task_id": "task-1", "task_status": status})
        raise AssertionError(request.url.path)

    async def reconcile(*args):
        order.append("reconcile")

    async def no_sleep(_delay):
        return None

    _install_transport(monkeypatch, handler)
    monkeypatch.setattr(
        "ontofoundry_api.api.agent_conversation.reconcile_run", reconcile
    )
    monkeypatch.setattr("ontofoundry_api.api.agent_conversation.asyncio.sleep", no_sleep)
    response = client.get(_endpoint(session["id"]) + "/events")
    assert response.status_code == 200, response.text
    body = response.text
    assert 'event: agent-event\ndata: {"seq_id":1,"type":"delta"}\n\n' in body
    assert ": ping\n\n" in body
    assert "event: done\n" in body
    assert '"status":"finished"' in body
    assert body.index("event: agent-event") < body.index("event: done")
    assert order == ["reconcile"]
    assert stream_count == 2


def test_events_back_off_when_active_stream_repeatedly_ends_empty(client, monkeypatch):
    _configure(client)
    session = _create_session(client)
    _set_session(
        client,
        session["id"],
        task_status="running",
        dataagent_topic_id="topic-1",
        dataagent_task_id="task-1",
        dataagent_task_mode="chat",
    )
    task_count = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal task_count
        if request.url.path.endswith("/sdk-events/stream"):
            return httpx.Response(200, content=b"")
        if request.url.path.endswith("/tasks/task-1"):
            task_count += 1
            status = "running" if task_count <= 3 else "finished"
            return httpx.Response(
                200, json={"task_id": "task-1", "task_status": status}
            )
        raise AssertionError(request.url.path)

    async def record_sleep(delay):
        delays.append(delay)

    _install_transport(monkeypatch, handler)
    monkeypatch.setattr(
        "ontofoundry_api.api.agent_conversation.asyncio.sleep", record_sleep
    )
    response = client.get(_endpoint(session["id"]) + "/events")
    assert response.status_code == 200, response.text
    assert "event: done" in response.text
    assert delays == [0.25, 0.5, 1.0]


@pytest.mark.parametrize(
    ("upstream", "expected"),
    [
        ("waiting", "queued"),
        ("running", "running"),
        ("waiting_input", "waiting_input"),
        ("waiting_permission", "waiting_permission"),
        ("finished", "finished"),
        ("error", "failed"),
        ("suspended", "cancelled"),
        (None, "failed"),
    ],
)
def test_status_mapping_contract(upstream, expected):
    assert to_run_status(upstream) == expected


def test_get_rebuilds_run_metadata_from_persisted_mode(client, monkeypatch):
    _configure(client)
    session = _create_session(client)
    _set_session(
        client,
        session["id"],
        task_status="running",
        dataagent_topic_id="topic-1",
        dataagent_task_id="task-1",
        dataagent_task_mode="model",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            return _messages_response([])
        return httpx.Response(200, json={"task_id": "task-1", "task_status": "running"})

    _install_transport(monkeypatch, handler)
    response = client.get(_endpoint(session["id"]))
    assert response.status_code == 200, response.text
    assert response.json()["run"]["metadata"] == {"mode": "model"}


def test_slow_old_snapshot_cannot_project_over_a_new_task(client, monkeypatch):
    """Browser A's late task-A response must not replace browser B's task B."""
    _configure(client)
    session = _create_session(client)
    _set_session(
        client,
        session["id"],
        task_status="running",
        dataagent_topic_id="topic-1",
        dataagent_task_id="task-old",
        dataagent_run_token="old-token",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            return _messages_response([])
        if request.url.path.endswith("/tasks/task-old"):
            _set_session(
                client,
                session["id"],
                task_status="running",
                dataagent_task_id="task-new",
                dataagent_run_token="new-token",
            )
            return httpx.Response(
                200, json={"task_id": "task-old", "task_status": "finished"}
            )
        raise AssertionError(request.url.path)

    _install_transport(monkeypatch, handler)
    response = client.get(_endpoint(session["id"]))
    assert response.status_code == 200, response.text
    assert response.json()["run"]["task_id"] == "task-new"
    assert response.json()["run"]["status"] == "running"
    row = _session_row(client, session["id"])
    assert row.dataagent_task_id == "task-new"
    assert row.dataagent_run_token == "new-token"
    assert row.task_status == "running"


def test_snapshot_result_reconcile_returns_the_new_task_owner(client, monkeypatch):
    _configure(client)
    session = _create_session(client)
    _set_session(
        client,
        session["id"],
        task_status="finished",
        dataagent_topic_id="topic-1",
        dataagent_task_id="task-old",
        dataagent_task_mode="model",
        dataagent_run_token="old-token",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/messages"):
            return _messages_response([])
        if request.url.path.endswith("/tasks/task-old"):
            return httpx.Response(
                200, json={"task_id": "task-old", "task_status": "finished"}
            )
        raise AssertionError(request.url.path)

    async def reconcile(*args):
        _set_session(
            client,
            session["id"],
            task_status="running",
            task_detail="new task running",
            dataagent_task_id="task-new",
            dataagent_task_mode="chat",
            dataagent_run_token="new-token",
        )
        return ""

    _install_transport(monkeypatch, handler)
    monkeypatch.setattr(
        "ontofoundry_api.api.agent_conversation.reconcile_run", reconcile
    )
    response = client.get(_endpoint(session["id"]))
    assert response.status_code == 200, response.text
    assert response.json()["run"] == {
        "task_id": "task-new",
        "status": "running",
        "detail": "new task running",
        "metadata": {"mode": "chat"},
    }


def test_request_schema_has_no_revision_and_sanitizes_metadata(client, monkeypatch):
    _configure(client)
    session = _create_session(client)
    delivered: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/topics"):
            return httpx.Response(200, json={"topic_id": "topic-1"})
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json={"rel_path": "uploads/context.json"})
        delivered.append(_json_request(request))
        return httpx.Response(200, json={"task_id": "task-1", "task_status": "waiting"})

    _install_transport(monkeypatch, handler)
    response = client.post(
        _endpoint(session["id"]) + "/messages",
        json={
            "content": "hello",
            "metadata": {"mode": "not-valid", "secret": "discard-me"},
            "revision": 999,
        },
    )
    assert response.status_code == 202, response.text
    assert response.json()["metadata"] == {"mode": "chat"}
    assert "普通对话" in delivered[0]["content"]
    assert "discard-me" not in delivered[0]["content"]

    schema = client.get("/openapi.json").json()
    request_schema = schema["components"]["schemas"]["ConversationMessageRequest"]
    assert set(request_schema["properties"]) == {"content", "metadata"}


def test_files_proxy_bytes_and_content_type(client, monkeypatch):
    _configure(client)
    session = _create_session(client)
    _set_session(client, session["id"], dataagent_topic_id="topic-1")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/topics/topic-1/files/output/result.bin")
        return httpx.Response(
            200,
            content=b"\x00\x01result",
            headers={"Content-Type": "application/x-result"},
        )

    _install_transport(monkeypatch, handler)
    response = client.get(_endpoint(session["id"]) + "/files/output/result.bin")
    assert response.status_code == 200
    assert response.content == b"\x00\x01result"
    assert response.headers["content-type"] == "application/x-result"


def test_stale_submitting_claims_matching_remote_task_without_redelivery(
    client, monkeypatch
):
    _configure(client)
    session = _create_session(client)
    token = "a" * 32
    _set_session(
        client,
        session["id"],
        task_status="submitting",
        dataagent_topic_id="topic-1",
        dataagent_run_token=token,
        dataagent_task_mode="chat",
        updated_at=utc_now() - timedelta(seconds=121),
    )
    delivered = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal delivered
        path = request.url.path
        if path.endswith("/deliver-message"):
            delivered += 1
            raise AssertionError("stale reconciliation must never redeliver")
        if path.endswith("/messages"):
            return _messages_response(
                [
                    {
                        "message_id": "message-1",
                        "topic_id": "topic-1",
                        "task_id": "task-lost-response",
                        "sender_type": "user",
                        "type": "text",
                        "content": f"run_token: {token}",
                        "seq_id": 1,
                    }
                ]
            )
        if path.endswith("/tasks/task-lost-response"):
            return httpx.Response(
                200,
                json={
                    "task_id": "task-lost-response",
                    "task_status": "waiting",
                    "prompt": f"run_token: {token}",
                },
            )
        raise AssertionError(path)

    _install_transport(monkeypatch, handler)
    response = client.get(_endpoint(session["id"]))
    assert response.status_code == 200, response.text
    assert response.json()["run"]["task_id"] == "task-lost-response"
    assert response.json()["run"]["status"] == "queued"
    row = _session_row(client, session["id"])
    assert row.dataagent_task_id == "task-lost-response"
    assert row.task_status == "queued"
    assert delivered == 0


def test_stale_submitting_without_matching_task_becomes_failed(client, monkeypatch):
    _configure(client)
    session = _create_session(client)
    _set_session(
        client,
        session["id"],
        task_status="submitting",
        dataagent_topic_id="topic-1",
        dataagent_run_token="b" * 32,
        dataagent_task_mode="chat",
        updated_at=utc_now() - timedelta(seconds=121),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return _messages_response([])

    _install_transport(monkeypatch, handler)
    response = client.get(_endpoint(session["id"]))
    assert response.status_code == 200, response.text
    assert response.json()["run"]["status"] == "failed"
    row = _session_row(client, session["id"])
    assert row.task_status == "failed"
    assert "重试" in row.task_detail


def test_stale_reconciler_cannot_fail_a_newer_run(client, monkeypatch):
    """A stale browser's empty history cannot release a newer run's claim."""
    _configure(client)
    session = _create_session(client)
    _set_session(
        client,
        session["id"],
        task_status="submitting",
        dataagent_topic_id="topic-1",
        dataagent_run_token="old-token",
        updated_at=utc_now() - timedelta(seconds=121),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/messages")
        _set_session(
            client,
            session["id"],
            task_status="running",
            dataagent_task_id="task-new",
            dataagent_run_token="new-token",
        )
        return _messages_response([])

    _install_transport(monkeypatch, handler)
    response = client.get(_endpoint(session["id"]))
    assert response.status_code == 200, response.text
    assert response.json()["run"]["task_id"] == "task-new"
    assert response.json()["run"]["status"] == "running"
    row = _session_row(client, session["id"])
    assert row.dataagent_task_id == "task-new"
    assert row.dataagent_run_token == "new-token"
    assert row.task_status == "running"


def test_stale_first_submit_without_topic_is_released_and_can_retry(
    client, monkeypatch
):
    _configure(client)
    session = _create_session(client)
    _set_session(
        client,
        session["id"],
        task_status="submitting",
        dataagent_topic_id=None,
        dataagent_task_id=None,
        dataagent_run_token="crashed-first-run",
        updated_at=utc_now() - timedelta(seconds=121),
    )

    stale = client.get(_endpoint(session["id"]))
    assert stale.status_code == 200, stale.text
    assert stale.json()["run"]["status"] == "failed"
    assert _session_row(client, session["id"]).task_status == "failed"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/topics"):
            return httpx.Response(200, json={"topic_id": "topic-retry"})
        if request.url.path.endswith("/files"):
            return httpx.Response(200, json={"rel_path": "uploads/context.json"})
        if request.url.path.endswith("/deliver-message"):
            return httpx.Response(
                200, json={"task_id": "task-retry", "task_status": "waiting"}
            )
        raise AssertionError(request.url.path)

    _install_transport(monkeypatch, handler)
    retried = client.post(
        _endpoint(session["id"]) + "/messages",
        json={"content": "retry", "metadata": {}},
    )
    assert retried.status_code == 202, retried.text
    assert retried.json()["task_id"] == "task-retry"


def test_old_event_stream_closes_without_completing_a_new_task(client, monkeypatch):
    _configure(client)
    session = _create_session(client)
    _set_session(
        client,
        session["id"],
        task_status="running",
        dataagent_topic_id="topic-1",
        dataagent_task_id="task-old",
        dataagent_run_token="old-token",
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sdk-events/stream"):
            return httpx.Response(200, content=b"")
        if request.url.path.endswith("/tasks/task-old"):
            _set_session(
                client,
                session["id"],
                task_status="running",
                dataagent_task_id="task-new",
                dataagent_run_token="new-token",
            )
            return httpx.Response(
                200, json={"task_id": "task-old", "task_status": "finished"}
            )
        raise AssertionError(request.url.path)

    _install_transport(monkeypatch, handler)
    response = client.get(_endpoint(session["id"]) + "/events")
    assert response.status_code == 200, response.text
    assert ": ping\n\n" in response.text
    assert "event: done" not in response.text
    row = _session_row(client, session["id"])
    assert row.dataagent_task_id == "task-new"
    assert row.task_status == "running"


def test_events_waits_when_exhaustion_loses_to_a_new_result_lease(
    client, monkeypatch
):
    _configure(client)
    session = _create_session(client)
    _set_session(
        client,
        session["id"],
        task_status="finished",
        dataagent_topic_id="topic-1",
        dataagent_task_id="task-1",
        dataagent_task_mode="model",
    )
    stream_count = 0
    reconcile_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal stream_count
        if request.url.path.endswith("/sdk-events/stream"):
            stream_count += 1
            return httpx.Response(200, content=b"")
        if request.url.path.endswith("/tasks/task-1"):
            return httpx.Response(
                200, json={"task_id": "task-1", "task_status": "finished"}
            )
        raise AssertionError(request.url.path)

    async def reconcile(*args):
        nonlocal reconcile_count
        reconcile_count += 1
        return "failed_retriable" if reconcile_count <= 4 else "done"

    async def no_sleep(_delay):
        return None

    _install_transport(monkeypatch, handler)
    monkeypatch.setattr(
        "ontofoundry_api.api.agent_conversation.reconcile_run", reconcile
    )
    monkeypatch.setattr(
        "ontofoundry_api.api.agent_conversation.exhaust_retriable_result",
        lambda *args: "processing",
    )
    monkeypatch.setattr("ontofoundry_api.api.agent_conversation.asyncio.sleep", no_sleep)

    response = client.get(_endpoint(session["id"]) + "/events")
    assert response.status_code == 200, response.text
    assert "event: done" in response.text
    assert reconcile_count == 5
    assert stream_count == 2


def test_cancel_and_interactions_dispatch_by_kind(client, monkeypatch):
    _configure(client)
    session = _create_session(client)
    _set_session(
        client,
        session["id"],
        task_status="waiting_permission",
        dataagent_topic_id="topic-1",
        dataagent_task_id="task-1",
        dataagent_task_mode="chat",
    )
    requests: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, _json_request(request)))
        if request.url.path.endswith("/permission-decision"):
            return httpx.Response(200, json={"ok": True})
        if request.url.path.endswith("/question-answer"):
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(
            200, json={"task_id": "task-1", "task_status": "suspended"}
        )

    _install_transport(monkeypatch, handler)
    base = _endpoint(session["id"])
    permission = client.post(
        base + "/interactions",
        json={
            "task_id": "task-1",
            "kind": "permission",
            "request_id": "p-1",
            "payload": {"decision": "allow"},
        },
    )
    question = client.post(
        base + "/interactions",
        json={
            "task_id": "task-1",
            "kind": "question",
            "request_id": "q-1",
            "payload": {"answers": [{"value": "yes"}]},
        },
    )
    cancelled = client.post(base + "/cancel", json={"task_id": "task-1"})

    assert permission.json() == {"ok": True}
    assert question.json() == {"ok": True}
    assert cancelled.json()["status"] == "cancelled"
    assert [path.rsplit("/", 1)[-1] for path, _ in requests] == [
        "permission-decision",
        "question-answer",
        "cancel",
    ]
