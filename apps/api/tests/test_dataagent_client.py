import json
from functools import partial

import httpx
import pytest

from ontofoundry_api.config import Settings
from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError


def _client(monkeypatch, handler, *, access_key: str = "secret") -> DataAgentClient:
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", partial(real_async_client, transport=transport))
    return DataAgentClient(
        "https://dataagent.example/",
        prefix="/custom/runtime/",
        website_id="website-1",
        access_key=access_key,
        session_ref="ontofoundry:workspace-1:session-1",
    )


def _assert_auth_headers(request: httpx.Request, *, access_key: bool = True) -> None:
    assert request.headers["X-ODW-Client"] == "widget"
    assert request.headers["X-ODW-Website-Id"] == "website-1"
    assert request.headers["X-ODW-User-Id"] == "ontofoundry:workspace-1:session-1"
    if access_key:
        assert request.headers["X-ODW-Access-Key"] == "secret"
    else:
        assert "X-ODW-Access-Key" not in request.headers


def test_dataagent_settings_defaults():
    settings = Settings(environment="test")

    assert settings.dataagent_api_prefix == "/api/v1/nl2sql"
    assert settings.dataagent_website_id == "ontofoundry"
    assert settings.dataagent_access_key == ""


@pytest.mark.asyncio
async def test_runtime_paths_and_auth_headers(monkeypatch):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        _assert_auth_headers(request)
        if request.url.path.endswith("/sdk-events/stream"):
            return httpx.Response(200, content=b'data: {"seq_id": 1}\n\n')
        return httpx.Response(200, json={"ok": True})

    client = _client(monkeypatch, handler)

    await client.create_topic("Topic", "agent-1")
    await client.delete_topic("topic-1")
    await client.upload("topic-1", "notes.md", b"hello", "text/markdown")
    await client.deliver(
        topic_id="topic-1",
        content="hello",
        agent_id="agent-1",
        execution_mode="auto",
    )
    await client.task("task-1")
    await client.task_message("task-1")
    await client.cancel("task-1")
    await client.permission_decision("task-1", "permission-1", {"decision": "allow"})
    await client.question_answer("task-1", "question-1", {"answers": [{"value": "yes"}]})
    chunks = [chunk async for chunk in client.stream("task-1", after_id=4)]

    assert chunks == [b'data: {"seq_id": 1}\n\n']
    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/custom/runtime/topics"),
        ("DELETE", "/custom/runtime/topics/topic-1"),
        ("POST", "/custom/runtime/topics/topic-1/files"),
        ("POST", "/custom/runtime/tasks/deliver-message"),
        ("GET", "/custom/runtime/tasks/task-1"),
        ("GET", "/custom/runtime/tasks/task-1/message"),
        ("POST", "/custom/runtime/tasks/task-1/cancel"),
        ("POST", "/custom/runtime/tasks/task-1/permission-decision"),
        ("POST", "/custom/runtime/tasks/task-1/question-answer"),
        ("GET", "/custom/runtime/tasks/task-1/sdk-events/stream"),
    ]
    assert dict(requests[-1].url.params) == {"after_id": "4"}
    assert requests[-1].headers["Accept"] == "text/event-stream"
    assert json.loads(requests[-3].read()) == {
        "request_id": "permission-1",
        "decision": "allow",
    }
    assert json.loads(requests[-2].read()) == {
        "request_id": "question-1",
        "answers": [{"value": "yes"}],
    }


@pytest.mark.asyncio
async def test_access_key_header_is_omitted_when_empty(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        _assert_auth_headers(request, access_key=False)
        return httpx.Response(200, json={"topic_id": "topic-1"})

    client = _client(monkeypatch, handler, access_key="")

    await client.create_topic("Topic", "agent-1")


@pytest.mark.asyncio
async def test_messages_fetches_all_three_pages_in_seq_id_order(monkeypatch):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        page = int(request.url.params["page"])
        start = (page - 1) * 500 + 1
        count = 500 if page < 3 else 1
        return httpx.Response(
            200,
            json={
                "topic_id": "topic-1",
                "page": page,
                "page_size": 500,
                "order": "asc",
                "total": 1001,
                "items": [
                    {"message_id": f"message-{seq_id}", "seq_id": seq_id}
                    for seq_id in range(start, start + count)
                ],
            },
        )

    client = _client(monkeypatch, handler)

    messages = await client.messages("topic-1")

    assert len(messages) == 1001
    assert [message["seq_id"] for message in messages] == list(range(1, 1002))
    assert [request.url.path for request in requests] == [
        "/custom/runtime/topics/topic-1/messages",
        "/custom/runtime/topics/topic-1/messages",
        "/custom/runtime/topics/topic-1/messages",
    ]
    assert [dict(request.url.params) for request in requests] == [
        {"page": "1", "page_size": "500", "order": "asc"},
        {"page": "2", "page_size": "500", "order": "asc"},
        {"page": "3", "page_size": "500", "order": "asc"},
    ]


@pytest.mark.asyncio
async def test_download_returns_bytes_and_content_type(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/custom/runtime/topics/topic-1/files/output/result.json"
        _assert_auth_headers(request)
        return httpx.Response(
            200,
            content=b'{"ok": true}',
            headers={"Content-Type": "application/json"},
        )

    client = _client(monkeypatch, handler)

    assert await client.download("topic-1", "output/result.json") == (
        b'{"ok": true}',
        "application/json",
    )


@pytest.mark.asyncio
async def test_agent_profile_uses_public_router_not_runtime_prefix(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/dataagent/agents/agent-1"
        _assert_auth_headers(request)
        return httpx.Response(200, json={"agent_id": "agent-1"})

    client = _client(monkeypatch, handler)

    assert await client.agent_profile("agent-1") == {"agent_id": "agent-1"}


@pytest.mark.asyncio
async def test_agent_profile_404_has_actionable_hint(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "agent not found"})

    client = _client(monkeypatch, handler)

    with pytest.raises(DataAgentError) as caught:
        await client.agent_profile("missing-agent")

    assert caught.value.status_code == 404
    assert "missing-agent" in caught.value.hint
    assert "可见性" in caught.value.hint
