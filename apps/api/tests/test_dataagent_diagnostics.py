from functools import partial

import httpx
import pytest
from fastapi.testclient import TestClient

from ontofoundry_api.config import Settings
from ontofoundry_api.main import create_app
from ontofoundry_api.services.dataagent import DataAgentClient, DataAgentError
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID

HEALTH_PATH = "/api/v1/system/dataagent-health"


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
        username="dev",
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
                "该站点开启了服务端接入校验：把 access-key 接口生成的密钥"
                "填入 ONTOFOUNDRY_DATAAGENT_ACCESS_KEY"
            ),
        ),
        (
            "agent_missing",
            502,
            "DataAgent 上找不到该 Agent",
            (
                "创建 agent_id=agent-missing、安装 ontology-discovery 与 entity-extraction Skill，"
                "并确认其可见性允许 Widget 访问"
            ),
        ),
    ],
)
async def test_five_failures_have_stable_http_status_message_and_hint(
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
    seen_users: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        seen_users.append(request.headers["X-DataAgent-User-Id"])
        return httpx.Response(200, json={"agent_id": settings.dataagent_agent_id})

    _dataagent_client(monkeypatch, handler)
    response = client.get(HEALTH_PATH)

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert [check["name"] for check in response.json()["checks"]] == [
        "配置完整性",
        "连通性",
        "站点放行",
        "Agent 存在性",
    ]
    assert all(check["ok"] for check in response.json()["checks"])
    assert requested_paths == [f"/api/v1/dataagent/agents/{settings.dataagent_agent_id}"]
    # The check runs as the requesting platform admin.
    assert seen_users == ["dev"]


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
    response = client.get(HEALTH_PATH)

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
            "创建 agent_id=missing-agent、安装 ontology-discovery 与 entity-extraction Skill，"
            "并确认其可见性允许 Widget 访问"
        ),
    }
    assert requested_paths == ["/api/v1/dataagent/agents/missing-agent"]
    assert not any("/topics" in path for path in requested_paths)


def test_empty_dataagent_base_url_does_not_block_app_or_ontology(client):
    assert client.app.state.settings.dataagent_base_url == ""

    response = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/version")

    assert response.status_code == 200
    assert response.json()["workspace_id"] == str(DEMO_WORKSPACE_ID)
    assert response.json()["version_id"]


def test_health_reports_skipped_checks_when_base_url_missing(client):
    assert client.app.state.settings.dataagent_base_url == ""

    response = client.get(HEALTH_PATH)

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is False
    assert [check["ok"] for check in payload["checks"]] == [False] * 4
    assert payload["checks"][0]["message"] == "DataAgent 未配置"


def test_workspace_scoped_health_route_is_gone(client):
    response = client.get(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/settings/dataagent-health"
    )

    assert response.status_code == 404


def test_health_requires_a_platform_admin_in_login_mode(tmp_path):
    config = tmp_path / "auth.py"
    config.write_text(
        'ADMIN_USERS = ["fiction-admin"]\n'
        'LOCAL_USERS = [{"username": "fiction-admin", "password": "fiction-pass"},'
        ' {"username": "fiction-viewer", "password": "viewer-pass"}]\n'
    )
    settings = Settings(
        environment="test",
        auth_mode="login",
        auth_config=config,
        database_url=f"sqlite+pysqlite:///{tmp_path / 'login.db'}",
        data_dir=tmp_path / "files",
        auto_create_schema=True,
        seed_demo=False,
        session_secret="test-login-secret-with-more-than-32-chars",
    )
    with TestClient(create_app(settings)) as viewer_client:
        assert viewer_client.get(HEALTH_PATH).status_code == 401
        login = viewer_client.post(
            "/api/v1/auth/login/local",
            json={"username": "fiction-viewer", "password": "viewer-pass"},
        )
        assert login.status_code == 204
        # A signed-in user who is not a platform admin must not see internal
        # addresses or agent ids.
        denied = viewer_client.get(HEALTH_PATH)
        assert denied.status_code == 403
        assert "agent_id" not in denied.text
    with TestClient(create_app(settings)) as login_client:

        login = login_client.post(
            "/api/v1/auth/login/local",
            json={"username": "fiction-admin", "password": "fiction-pass"},
        )
        assert login.status_code == 204
        response = login_client.get(HEALTH_PATH)

    assert response.status_code == 200
    assert response.json()["ok"] is False
