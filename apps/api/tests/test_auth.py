import threading
import time
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from ontofoundry_api.api.auth import NONCE_COOKIE, build_state, parse_state, safe_return_to
from ontofoundry_api.config import Settings
from ontofoundry_api.db_models import UserRecord, WorkspaceMemberRecord
from ontofoundry_api.main import create_app
from ontofoundry_api.services.workspaces import create_workspace, upsert_oauth_user


@pytest.fixture
def login_client(tmp_path):
    config = tmp_path / "auth.py"
    config.write_text('''
ADMIN_USERS = ["admin"]
LOCAL_USERS = [
    {"username": "admin", "password": "admin123"},
    {"username": "星港用户", "password": "星港密码"},
]
OAUTH_PROVIDERS = [{
    "name": "internal",
    "remote_app": {
        "client_id": "example-client",
        "client_secret": "example-secret",
        "authorize_url": "https://sso.example.com/oauth/authorize?audience=example",
        "access_token_url": "https://sso.example.com/oauth/token",
        "api_base_url": "https://sso.example.com/oauth/",
        "redirect_uri": "http://testserver/api/v1/auth/callback/internal",
        "client_kwargs": {"scope": "openid profile email"},
    },
}]
def oauth_user_info(provider, token_response, oauth_remotes):
    response = oauth_remotes[provider].get("userinfo")
    response.raise_for_status()
    return response.json()["data"]
OAUTH_USER_INFO = oauth_user_info
''')
    settings = Settings(
        environment="test", auth_mode="login", auth_config=config,
        database_url=f"sqlite+pysqlite:///{tmp_path / 'login.db'}",
        data_dir=tmp_path / "files", auto_create_schema=True, seed_demo=False,
        session_secret="test-login-secret-with-more-than-32-chars",
    )
    with TestClient(create_app(settings)) as client:
        yield client


@pytest.fixture
def oauth_http(monkeypatch):
    network = {
        "token": {"access_token": "secret-access-token", "refresh_token": "secret-refresh-token", "extra": {"id": 7}},
        "profile": {"code": 0, "data": {"sub": "user-7", "display_name": "星港用户", "email": "user@example.com", "role": "admin"}},
        "token_status": 200, "requests": [], "threads": [],
    }

    def handler(request):
        network["requests"].append(request)
        network["threads"].append(threading.get_ident())
        if request.url.path == "/oauth/token":
            return httpx.Response(network["token_status"], json=network["token"])
        assert str(request.url) == "https://sso.example.com/oauth/userinfo"
        return httpx.Response(200, json=network["profile"])

    transport = httpx.MockTransport(handler)
    real_async_client, real_client = httpx.AsyncClient, httpx.Client
    monkeypatch.setattr("ontofoundry_api.services.auth.httpx.AsyncClient", lambda **kwargs: real_async_client(transport=transport, **kwargs))
    monkeypatch.setattr("ontofoundry_api.services.auth.httpx.Client", lambda **kwargs: real_client(transport=transport, **kwargs))
    return network


def start_oauth(client, return_to="/workspaces/example"):
    response = client.get("/api/v1/auth/login/internal", params={"return_to": return_to}, follow_redirects=False)
    assert response.status_code == 302
    return parse_qs(urlparse(response.headers["location"]).query)["state"][0]


def complete_oauth(client, state):
    return client.get("/api/v1/auth/callback/internal", params={"code": "example-code", "state": state}, follow_redirects=False)


def test_oauth_state_round_trip_and_nonce_binding():
    state = build_state(nonce="nonce-a", return_to="/workspaces/1", secret="secret")
    payload = parse_state(state=state, nonce="nonce-a", secret="secret")
    assert payload["return_to"] == "/workspaces/1"


def test_oauth_state_rejects_wrong_nonce():
    state = build_state(nonce="nonce-a", return_to="/", secret="secret")
    with pytest.raises(HTTPException, match="OAuth nonce"):
        parse_state(state=state, nonce="nonce-b", secret="secret")


def test_oauth_state_rejects_signature_and_expiry(monkeypatch):
    state = build_state(nonce="nonce-a", return_to="/", secret="secret")
    with pytest.raises(HTTPException, match="OAuth state"):
        parse_state(state=state, nonce="nonce-a", secret="wrong-secret")
    now = time.time()
    monkeypatch.setattr("ontofoundry_api.api.auth.time.time", lambda: now + 601)
    with pytest.raises(HTTPException, match="已过期"):
        parse_state(state=state, nonce="nonce-a", secret="secret")


@pytest.mark.parametrize("value", ["//malicious.example/path", "https://malicious.example", "/\\malicious.example", "/\nmalicious"])
def test_return_path_cannot_escape_the_site(value):
    assert safe_return_to(value) == "/"
    assert safe_return_to("/workspaces/1") == "/workspaces/1"


def test_options_are_public_and_hide_secrets(login_client):
    response = login_client.get("/api/v1/auth/options")
    assert response.status_code == 200
    assert response.json() == {"local_login": True, "oauth": {"name": "internal"}}
    assert "admin123" not in response.text
    assert "example-secret" not in response.text
    assert login_client.get("/api/v1/auth/me").status_code == 401


def test_each_login_option_can_be_disabled(login_client):
    original = login_client.app.state.auth_config
    login_client.app.state.auth_config = replace(original, oauth=None, oauth_user_info=None)
    assert login_client.get("/api/v1/auth/options").json() == {"local_login": True, "oauth": None}
    login_client.app.state.auth_config = replace(original, local_users={})
    assert login_client.get("/api/v1/auth/options").json() == {"local_login": False, "oauth": {"name": "internal"}}
    assert login_client.post("/api/v1/auth/login/local", json={"username": "admin", "password": "admin123"}).status_code == 401


@pytest.mark.parametrize("username, password", [("admin", "admin123"), ("星港用户", "星港密码")])
def test_local_login_session_username_and_logout(login_client, username, password):
    response = login_client.post("/api/v1/auth/login/local", json={"username": username, "password": password})
    assert response.status_code == 204
    assert response.content == b""
    cookie = response.headers["set-cookie"]
    assert "httponly" in cookie.lower() and "samesite=lax" in cookie.lower()
    principal = login_client.get("/api/v1/auth/me").json()
    assert principal["username"] == username
    assert principal["display_name"] == username
    assert principal["email"] is None
    with login_client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(WorkspaceMemberRecord)) == 0
    assert login_client.post("/api/v1/auth/logout").status_code == 204
    assert login_client.get("/api/v1/auth/me").status_code == 401
    login_client.post("/api/v1/auth/login/local", json={"username": username, "password": password})
    assert login_client.get("/api/v1/auth/me").json()["id"] == principal["id"]


@pytest.mark.parametrize("username, password", [("admin", "wrong-password"), ("unknown", "admin123"), ("unknown", ""), ("admin", "")])
def test_local_login_failure_is_generic_and_logged(login_client, username, password, caplog):
    response = login_client.post("/api/v1/auth/login/local", json={"username": username, "password": password})
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "用户名或密码错误"
    assert username in caplog.text
    if password:
        assert password not in caplog.text
    assert login_client.get("/api/v1/auth/me").status_code == 401


def test_local_password_comparison_uses_constant_time(login_client, monkeypatch):
    import hmac

    calls = []
    original = hmac.compare_digest

    def compare(left, right):
        calls.append((left, right))
        return original(left, right)

    monkeypatch.setattr("ontofoundry_api.services.auth.hmac.compare_digest", compare)
    login_client.post("/api/v1/auth/login/local", json={"username": "星港用户", "password": "星港密码"})
    assert ("星港密码".encode(), "星港密码".encode()) in calls


def test_provider_redirect_and_cookie_binding(login_client):
    state = start_oauth(login_client, "//malicious.example")
    payload = parse_state(
        state=state, nonce=login_client.cookies.get(NONCE_COOKIE),
        secret=login_client.app.state.settings.session_secret,
    )
    assert payload["provider"] == "internal" and payload["return_to"] == "/"
    response = login_client.get("/api/v1/auth/login/internal", follow_redirects=False)
    params = parse_qs(urlparse(response.headers["location"]).query)
    assert params["audience"] == ["example"]
    assert params["client_id"] == ["example-client"]
    assert params["redirect_uri"] == ["http://testserver/api/v1/auth/callback/internal"]
    assert params["scope"] == ["openid profile email"]
    assert params["response_type"] == ["code"]
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age=600" in cookie


def test_provider_callback_uses_hook_bound_client_and_full_token(login_client, oauth_http):
    original = login_client.app.state.auth_config
    seen = {}

    def hook(provider, token, remotes):
        seen.update(provider=provider, token=token, remotes=set(remotes), thread=threading.get_ident())
        return original.oauth_user_info(provider, token, remotes)

    login_client.app.state.auth_config = replace(original, oauth_user_info=hook)
    response = complete_oauth(login_client, start_oauth(login_client))
    assert response.status_code == 302 and response.headers["location"] == "/workspaces/example"
    assert login_client.cookies.get(NONCE_COOKIE) is None
    assert seen["token"] == oauth_http["token"]
    assert seen["provider"] == "internal" and seen["remotes"] == {"internal"}
    assert seen["thread"] != oauth_http["threads"][0]
    assert oauth_http["threads"][1] == seen["thread"]
    token_request, user_request = oauth_http["requests"]
    assert parse_qs(token_request.content.decode()) == {
        "grant_type": ["authorization_code"], "code": ["example-code"],
        "client_id": ["example-client"], "client_secret": ["example-secret"],
        "redirect_uri": ["http://testserver/api/v1/auth/callback/internal"],
    }
    assert user_request.headers["authorization"] == "Bearer secret-access-token"
    assert all(value == 15 for value in user_request.extensions["timeout"].values())
    principal = login_client.get("/api/v1/auth/me").json()
    assert principal["username"] == "user-7"
    assert principal["display_name"] == "星港用户"
    assert principal["email"] == "user@example.com"
    with login_client.app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(WorkspaceMemberRecord)) == 0


@pytest.mark.parametrize("profile, expected_name", [
    ({"sub": "user-7", "display_name": "显示名", "preferred_username": "alias"}, "显示名"),
    ({"sub": "user-7", "preferred_username": "alias", "name": "姓名"}, "alias"),
    ({"sub": "user-7", "name": "姓名", "email": "user@example.com"}, "姓名"),
    ({"sub": "user-7", "email": "user@example.com"}, "user@example.com"),
    ({"sub": "user-7", "role": {"arbitrary": "ignored"}}, "user-7"),
])
def test_provider_display_name_fallback_and_role_ignored(login_client, oauth_http, profile, expected_name):
    oauth_http["profile"]["data"] = profile
    assert complete_oauth(login_client, start_oauth(login_client)).status_code == 302
    assert login_client.get("/api/v1/auth/me").json()["display_name"] == expected_name


def test_existing_username_preserves_user_and_membership(login_client, oauth_http):
    from ontofoundry_api.domain.models import WorkspaceCreate

    with login_client.app.state.session_factory() as session:
        existing = upsert_oauth_user(session, username="user-7", display_name="旧名称", email=None)
        existing_id = existing.id
        workspace_id = create_workspace(
            session, payload=WorkspaceCreate(name="星港空间", slug="starlane"), user_id=existing_id,
        ).id
    assert complete_oauth(login_client, start_oauth(login_client)).status_code == 302
    assert login_client.get("/api/v1/auth/me").json()["id"] == existing_id
    with login_client.app.state.session_factory() as session:
        assert session.scalar(select(WorkspaceMemberRecord.role).where(
            WorkspaceMemberRecord.workspace_id == workspace_id,
            WorkspaceMemberRecord.user_id == existing_id,
        )) == "admin"
        assert session.scalar(select(func.count()).select_from(UserRecord)) == 1


@pytest.mark.parametrize("failure", ["exception", "timeout", "list", "missing_sub", "empty_sub", "numeric_sub", "long_sub", "bad_name", "long_name", "bad_email"])
def test_hook_failure_does_not_break_later_logins(login_client, oauth_http, caplog, failure):
    original = login_client.app.state.auth_config

    def bad_hook(provider, token, remotes):
        if failure == "exception":
            raise RuntimeError("secret-access-token secret-refresh-token")
        if failure == "timeout":
            raise httpx.ReadTimeout("secret-access-token")
        return {
            "list": [], "missing_sub": {}, "empty_sub": {"sub": " "},
            "numeric_sub": {"sub": 7}, "long_sub": {"sub": "a" * 255},
            "bad_name": {"sub": "user-7", "display_name": []},
            "long_name": {"sub": "user-7", "display_name": "a" * 121},
            "bad_email": {"sub": "user-7", "email": ["email"]},
        }[failure]

    login_client.app.state.auth_config = replace(original, oauth_user_info=bad_hook)
    failed = complete_oauth(login_client, start_oauth(login_client))
    assert failed.status_code == 302
    assert failed.headers["location"] == "/login?error=oauth_user_info_failed"
    assert login_client.cookies.get(NONCE_COOKIE) is None
    assert login_client.get("/api/v1/auth/me").status_code == 401
    for secret in ("secret-access-token", "secret-refresh-token", "example-secret"):
        assert secret not in caplog.text + failed.text + failed.headers["location"]
    assert login_client.post("/api/v1/auth/login/local", json={"username": "admin", "password": "admin123"}).status_code == 204
    login_client.post("/api/v1/auth/logout")
    login_client.app.state.auth_config = original
    assert complete_oauth(login_client, start_oauth(login_client)).headers["location"] == "/workspaces/example"
    assert login_client.get("/api/v1/auth/me").json()["username"] == "user-7"


@pytest.mark.parametrize("token", [[], {}, {"access_token": ""}, {"access_token": 42}, {"access_token": "a\nb"}, {"access_token": "token", "token_type": "MAC"}])
def test_invalid_token_response_is_terminal(login_client, oauth_http, token, caplog):
    oauth_http["token"] = token
    response = complete_oauth(login_client, start_oauth(login_client))
    assert response.headers["location"] == "/login?error=oauth_exchange_failed"
    assert login_client.get("/api/v1/auth/me").status_code == 401
    assert len(oauth_http["requests"]) == 1
    assert "example-secret" not in caplog.text


def test_token_endpoint_failure(login_client, oauth_http):
    oauth_http["token_status"] = 500
    assert complete_oauth(login_client, start_oauth(login_client)).headers["location"] == "/login?error=oauth_exchange_failed"


def test_callback_rejects_missing_wrong_and_replayed_nonce(login_client, oauth_http):
    state = start_oauth(login_client)
    nonce = login_client.cookies.get(NONCE_COOKIE)
    nonce_domain = next(cookie.domain for cookie in login_client.cookies.jar if cookie.name == NONCE_COOKIE)
    login_client.cookies.clear()
    assert complete_oauth(login_client, state).status_code == 400
    login_client.cookies.set(NONCE_COOKIE, "wrong-nonce", domain=nonce_domain, path="/api/v1/auth")
    assert complete_oauth(login_client, state).status_code == 400
    login_client.cookies.clear()
    login_client.cookies.set(NONCE_COOKIE, nonce, domain=nonce_domain, path="/api/v1/auth")
    assert complete_oauth(login_client, state).status_code == 302
    assert complete_oauth(login_client, state).status_code == 400
    assert len(oauth_http["requests"]) == 2


def test_state_provider_binding_and_unknown_provider(login_client, oauth_http):
    start_oauth(login_client)
    state = build_state(
        nonce=login_client.cookies.get(NONCE_COOKIE), return_to="/",
        secret=login_client.app.state.settings.session_secret, provider="Other",
    )
    assert complete_oauth(login_client, state).status_code == 400
    for path in ("login", "callback"):
        assert login_client.get(f"/api/v1/auth/{path}/Other").status_code == 404
    assert oauth_http["requests"] == []


@pytest.mark.parametrize("params, expected", [({"error": "access_denied"}, "oauth_denied"), ({}, "oauth_exchange_failed")])
def test_denial_or_missing_code_clears_nonce(login_client, oauth_http, params, expected):
    params = {**params, "state": start_oauth(login_client)}
    response = login_client.get("/api/v1/auth/callback/internal", params=params, follow_redirects=False)
    assert response.headers["location"] == f"/login?error={expected}"
    assert login_client.cookies.get(NONCE_COOKIE) is None
    assert oauth_http["requests"] == []


def test_removed_routes_are_not_registered(login_client):
    for path in ("/api/v1/auth/login", "/api/v1/auth/callback"):
        assert login_client.get(path).status_code == 404


def test_dev_mode_identity_logout_and_redirect_unchanged(client):
    principal = client.get("/api/v1/auth/me").json()
    assert principal["username"] == "dev" and principal["display_name"] == "admin"
    assert client.get("/api/v1/auth/options").json() == {"local_login": False, "oauth": None}
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").json() == principal
    response = client.get("/api/v1/auth/login/internal", params={"return_to": "/workspaces/example"}, follow_redirects=False)
    assert response.status_code == 302 and response.headers["location"] == "/workspaces/example"
    assert client.post("/api/v1/auth/login/local", json={"username": "admin", "password": "admin123"}).status_code == 404
