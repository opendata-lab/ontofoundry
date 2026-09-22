from functools import partial

import httpx
import pytest

from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID


def _dataagent_client(
    monkeypatch,
    handler,
    *,
    base_url: str = "https://dataagent.example",
    access_key: str = "server-secret",
) -> DataAgentClient:
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        partial(real_async_client, transport=transport),
    )
    return DataAgentClient(
        base_url,
        prefix="/api/v1/nl2sql",
        website_id="ontofoundry",
        access_key=access_key,
        session_ref="ontofoundry:workspace-1:diagnostics",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "expected_status", "expected_message", "expected_hint"),
    [
        (
            "base_url_missing",
            503,
            "DataAgent 未配置",
            "设置 ONTOFOUNDRY_DATAAGENT_BASE_URL 后重启",
        ),
        (
            "connection_failed",
            503,
            "无法连接 DataAgent",
            "检查地址与网络连通性；当前地址 https://dataagent.example",
        ),
        (
            "site_denied",
            502,
            "DataAgent 拒绝了本站点",
            "在管理端 → Widget 接入设置中放行 website_id=ontofoundry",
        ),
        (
            "access_key_rejected",
            502,
            "DataAgent 拒绝了服务端接入密钥",
            (
                "在管理端重新生成密钥并更新 "
                "ONTOFOUNDRY_DATAAGENT_ACCESS_KEY"
            ),
        ),
        (
            "agent_missing",
            502,
            "DataAgent 上找不到该 Agent",
            (
                "创建 agent_id=agent-missing、安装 md2ossie Skill，"
                "并确认其可见性允许 Widget 访问"
            ),
        ),
        (
            "access_key_missing",
            503,
            "未配置服务端接入密钥",
            "设置 ONTOFOUNDRY_DATAAGENT_ACCESS_KEY",
        ),
    ],
)
async def test_six_failures_have_stable_http_status_message_and_hint(
    monkeypatch,
    case,
    expected_status,
    expected_message,
    expected_hint,
):
    def handler(request: httpx.Request) -> httpx.Response:
        if case == "connection_failed":
            raise httpx.ConnectError("connection refused", request=request)
        if case == "site_denied":
            return httpx.Response(403, json={"detail": "site is not allowed"})
        if case == "access_key_rejected":
            return httpx.Response(403, json={"detail": "invalid access key"})
        if case == "agent_missing":
            return httpx.Response(404, json={"detail": "agent not found"})
        raise AssertionError("local configuration failures must not call DataAgent")

    client = _dataagent_client(
        monkeypatch,
        handler,
        base_url="" if case == "base_url_missing" else "https://dataagent.example",
        access_key="" if case == "access_key_missing" else "server-secret",
    )

    with pytest.raises(DataAgentError) as caught:
        if case == "agent_missing":
            await client.agent_profile("agent-missing")
        else:
            await client.create_topic("diagnostics", "agent-1")

    assert caught.value.status_code == expected_status
    assert str(caught.value) == expected_message
    assert caught.value.hint == expected_hint


def test_bff_returns_message_and_hint_for_dataagent_failure(client, monkeypatch):
    settings = client.app.state.settings
    settings.dataagent_base_url = "https://dataagent.example"
    settings.dataagent_access_key = "server-secret"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"detail": "site is not allowed"})

    _dataagent_client(monkeypatch, handler)
    session = client.post(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/sessions",
        json={"title": "diagnostics"},
    ).json()

    base = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/sessions/{session['id']}"
    response = client.post(
        base + "/agent-conversation/messages",
        json={"content": "hello", "metadata": {}},
    )

    assert response.status_code == 502
    assert response.json() == {
        "message": "DataAgent 拒绝了本站点",
        "hint": "在管理端 → Widget 接入设置中放行 website_id=ontofoundry",
    }


def test_health_checks_agent_profile_public_route_and_reports_all_checks(
    client, monkeypatch
):
    settings = client.app.state.settings
    settings.dataagent_base_url = "https://dataagent.example"
    settings.dataagent_access_key = "server-secret"
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(200, json={"agent_id": settings.dataagent_agent_id})

    _dataagent_client(monkeypatch, handler)
    response = client.get(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/settings/dataagent-health"
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert [check["name"] for check in response.json()["checks"]] == [
        "配置完整性",
        "连通性",
        "站点放行",
        "Agent 存在性",
    ]
    assert all(check["ok"] for check in response.json()["checks"])
    assert requested_paths == [
        f"/api/v1/dataagent/agents/{settings.dataagent_agent_id}"
    ]


def test_health_reports_missing_agent_without_using_topic_filter(client, monkeypatch):
    settings = client.app.state.settings
    settings.dataagent_base_url = "https://dataagent.example"
    settings.dataagent_access_key = "server-secret"
    settings.dataagent_agent_id = "missing-agent"
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        return httpx.Response(404, json={"detail": "agent not found"})

    _dataagent_client(monkeypatch, handler)
    response = client.get(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/settings/dataagent-health"
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    agent_check = next(
        check for check in payload["checks"] if check["name"] == "Agent 存在性"
    )
    assert agent_check == {
        "name": "Agent 存在性",
        "ok": False,
        "message": "DataAgent 上找不到该 Agent",
        "hint": (
            "创建 agent_id=missing-agent、安装 md2ossie Skill，"
            "并确认其可见性允许 Widget 访问"
        ),
    }
    assert requested_paths == ["/api/v1/dataagent/agents/missing-agent"]
    assert not any("/topics" in path for path in requested_paths)


def test_empty_dataagent_base_url_does_not_block_app_or_ontology(client):
    assert client.app.state.settings.dataagent_base_url == ""

    response = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/ontology")

    assert response.status_code == 200
    assert response.json()["workspace_id"] == str(DEMO_WORKSPACE_ID)
    assert response.json()["object_types"]
