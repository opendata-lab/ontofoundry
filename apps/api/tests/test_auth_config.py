import importlib.util
import json
import os
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from ontofoundry_api.config import Settings
from ontofoundry_api.main import create_app
from ontofoundry_api.services.auth_config import AuthConfigError, load_auth_config

PROVIDER = {
    "name": "SSO",
    "remote_app": {
        "client_id": "example-client",
        "client_secret": "example-secret",
        "authorize_url": "https://sso.example.com/oauth/authorize",
        "access_token_url": "https://sso.example.com/oauth/token",
        "redirect_uri": "https://platform.example.com/api/v1/auth/callback/SSO",
        "api_base_url": "https://sso.example.com/oauth/",
        "client_kwargs": {"scope": "openid profile email"},
    },
}
HOOK = "def hook(provider, token_response, oauth_remotes):\n    return {'sub': 'example-user'}\nOAUTH_USER_INFO = hook\n"
DEFAULT_CONFIG = "LOCAL_USERS = [{'username': 'admin', 'password': 'admin123'}]\n"


def write_config(tmp_path, source):
    path = tmp_path / "auth_config.py"
    path.write_text(source)
    return Settings(auth_mode="login", auth_config=path, _env_file=None)


def provider_source(provider=PROVIDER):
    return f"OAUTH_PROVIDERS = {[provider]!r}\n" + HOOK


def test_default_config_warns_without_logging_password(tmp_path, caplog):
    config = load_auth_config(write_config(tmp_path, DEFAULT_CONFIG))
    assert config.local_users == {"admin": "admin123"}
    assert config.oauth is None
    assert "默认密码" in caplog.text
    assert "admin123" not in caplog.text
    assert "admin123" not in repr(config)


def test_changed_default_password_does_not_warn(tmp_path, caplog):
    load_auth_config(write_config(tmp_path, DEFAULT_CONFIG.replace("admin123", "星港密码")))
    assert "默认密码" not in caplog.text


@pytest.mark.parametrize("raw, message", [
    (None, "LOCAL_USERS 必须"), ({}, "LOCAL_USERS 必须"),
    ((), "LOCAL_USERS 必须"), ([1], "条目必须"),
    ([{"password": "secret"}], "username"),
    ([{"username": "", "password": "secret"}], "username"),
    ([{"username": "  ", "password": "secret"}], "username"),
    ([{"username": 42, "password": "secret"}], "username"),
    ([{"username": "a" * 121, "password": "secret"}], "username"),
    ([{"username": "a\nb", "password": "secret"}], "username"),
    ([{"username": "alice"}], "password"),
    ([{"username": "alice", "password": ""}], "password"),
    ([{"username": "alice", "password": 42}], "password"),
    ([{"username": "alice", "password": "one"}, {"username": "alice", "password": "two"}], "唯一"),
])
def test_invalid_local_users(tmp_path, raw, message):
    with pytest.raises(AuthConfigError, match=message):
        load_auth_config(write_config(tmp_path, f"LOCAL_USERS = {raw!r}\n"))


@pytest.mark.parametrize("raw", [None, {}, (), [PROVIDER, PROVIDER], [42]])
def test_invalid_provider_list(tmp_path, raw):
    with pytest.raises(AuthConfigError, match="OAUTH_PROVIDERS"):
        load_auth_config(write_config(tmp_path, DEFAULT_CONFIG + f"OAUTH_PROVIDERS = {raw!r}\n"))


@pytest.mark.parametrize("name", [None, "", "local", "LOCAL", "a.b", "a/b", "认证", "a" * 65])
def test_invalid_provider_name(tmp_path, name):
    provider = deepcopy(PROVIDER)
    provider["name"] = name
    with pytest.raises(AuthConfigError, match="name"):
        load_auth_config(write_config(tmp_path, provider_source(provider)))


@pytest.mark.parametrize("key", [
    "client_id", "client_secret", "authorize_url", "access_token_url", "redirect_uri", "api_base_url",
])
@pytest.mark.parametrize("value", [None, "", 42])
def test_missing_or_invalid_required_remote_fields(tmp_path, key, value):
    provider = deepcopy(PROVIDER)
    provider["remote_app"][key] = value
    with pytest.raises(AuthConfigError, match=key):
        load_auth_config(write_config(tmp_path, provider_source(provider)))


@pytest.mark.parametrize("key, value, message", [
    ("authorize_url", "/authorize", "authorize_url"),
    ("access_token_url", "ftp://sso.example.com/token", "access_token_url"),
    ("api_base_url", "https://sso.example.com/oauth", "api_base_url"),
    ("api_base_url", "https://sso.example.com/?key=x", "api_base_url"),
    ("redirect_uri", "https://platform.example.com/api/v1/auth/callback/Other", "redirect_uri"),
    ("redirect_uri", "https://platform.example.com/api/v1/auth/callback/SSO?x=1", "redirect_uri"),
    ("response_type", "token", "授权码"),
    ("grant_type", "password", "授权码"),
    ("client_kwargs", None, "client_kwargs"),
    ("client_kwargs", {"scope": []}, "scope"),
    ("client_kwargs", {"scope": ""}, "scope"),
])
def test_invalid_remote_options(tmp_path, key, value, message):
    provider = deepcopy(PROVIDER)
    provider["remote_app"][key] = value
    with pytest.raises(AuthConfigError, match=message):
        load_auth_config(write_config(tmp_path, provider_source(provider)))


def test_invalid_remote_app(tmp_path):
    with pytest.raises(AuthConfigError, match="remote_app"):
        load_auth_config(write_config(tmp_path, provider_source({"name": "SSO", "remote_app": []})))


@pytest.mark.parametrize("hook_source, message", [
    ("", "必须提供"),
    ("OAUTH_USER_INFO = 42", "callable"),
    ("async def hook(a, b, c): pass\nOAUTH_USER_INFO = hook", "同步"),
    ("async def hook(a, b, c): yield {}\nOAUTH_USER_INFO = hook", "同步"),
    ("class Hook:\n    async def __call__(self, a, b, c): pass\nOAUTH_USER_INFO = Hook()", "同步"),
    ("def hook(a, b): pass\nOAUTH_USER_INFO = hook", "三个参数"),
    ("def hook(a, b, c, d): pass\nOAUTH_USER_INFO = hook", "三个参数"),
    ("def hook(*, a, b, c): pass\nOAUTH_USER_INFO = hook", "三个参数"),
    ("OAUTH_USER_INFO = dict", "三个参数"),
])
def test_invalid_hook(tmp_path, hook_source, message):
    source = f"OAUTH_PROVIDERS = {[PROVIDER]!r}\n" + hook_source
    with pytest.raises(AuthConfigError, match=message):
        load_auth_config(write_config(tmp_path, source))


def test_valid_sso_only_and_local_plus_sso(tmp_path):
    config = load_auth_config(write_config(tmp_path, provider_source()))
    assert config.local_users == {}
    assert config.oauth.name == "SSO"
    assert config.oauth.scope == "openid profile email"
    assert config.oauth_user_info("SSO", {}, {}) == {"sub": "example-user"}
    assert "example-secret" not in repr(config)
    config = load_auth_config(write_config(tmp_path, DEFAULT_CONFIG + provider_source()))
    assert config.local_users and config.oauth


def test_default_scope_and_provider_name_boundaries(tmp_path):
    provider = deepcopy(PROVIDER)
    provider["name"] = "_" + "A" * 62 + "-"
    provider["remote_app"].pop("client_kwargs")
    provider["remote_app"]["redirect_uri"] = "https://platform.example.com/api/v1/auth/callback/" + provider["name"]
    config = load_auth_config(write_config(tmp_path, provider_source(provider)))
    assert config.oauth.scope == "openid profile"


@pytest.mark.parametrize("source", ["", "LOCAL_USERS = []\nOAUTH_PROVIDERS = []"])
def test_no_login_method(tmp_path, source):
    with pytest.raises(AuthConfigError, match="至少配置一种"):
        load_auth_config(write_config(tmp_path, source))


def test_missing_config_setting():
    with pytest.raises(AuthConfigError, match="必须设置 ONTOFOUNDRY_AUTH_CONFIG"):
        load_auth_config(Settings(auth_mode="login", _env_file=None))


def test_missing_file_and_directory(tmp_path):
    for path in (tmp_path / "missing.py", tmp_path):
        with pytest.raises(AuthConfigError, match="不可读"):
            load_auth_config(Settings(auth_mode="login", auth_config=path, _env_file=None))


def test_unreadable_config(tmp_path, monkeypatch):
    settings = write_config(tmp_path, DEFAULT_CONFIG)
    monkeypatch.setattr(os, "access", lambda *args: False)
    with pytest.raises(AuthConfigError, match="不可读"):
        load_auth_config(settings)


@pytest.mark.parametrize("source", [
    "this is not python!", "import nonexistent_auth_config_dependency",
    "raise RuntimeError('secret-value-must-not-appear')",
])
def test_import_failures(tmp_path, source, caplog):
    with pytest.raises(AuthConfigError, match="导入失败") as error:
        load_auth_config(write_config(tmp_path, source))
    assert "secret-value-must-not-appear" not in str(error.value) + caplog.text


def test_no_module_spec(tmp_path, monkeypatch):
    settings = write_config(tmp_path, DEFAULT_CONFIG)
    monkeypatch.setattr(importlib.util, "spec_from_file_location", lambda *args: None)
    with pytest.raises(AuthConfigError, match="无法导入"):
        load_auth_config(settings)


def test_sibling_override_and_hook_imports(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    for name in ("ontofoundry_config_docker", "custom_sso_user_info"):
        monkeypatch.delitem(sys.modules, name, raising=False)
    base = Path(__file__).resolve().parents[3] / "deploy/docker/ontofoundry/ontofoundry_config.py"
    (tmp_path / "auth_config.py").write_text(base.read_text())
    (tmp_path / "custom_sso_user_info.py").write_text(HOOK)
    (tmp_path / "ontofoundry_config_docker.py").write_text(
        "LOCAL_USERS = []\n" + f"OAUTH_PROVIDERS = {[PROVIDER]!r}\n"
        + "from custom_sso_user_info import hook\nOAUTH_USER_INFO = hook\n"
    )
    try:
        config = load_auth_config(Settings(auth_mode="login", auth_config=tmp_path / "auth_config.py"))
        assert config.local_users == {}
        assert config.oauth_user_info("SSO", {}, {})["sub"] == "example-user"
    finally:
        for name in ("ontofoundry_config_docker", "custom_sso_user_info"):
            sys.modules.pop(name, None)


def test_existing_broken_override_fails_startup(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "ontofoundry_config_docker", raising=False)
    base = Path(__file__).resolve().parents[3] / "deploy/docker/ontofoundry/ontofoundry_config.py"
    (tmp_path / "ontofoundry_config_docker.py").write_text("import missing_sso_hook_module")
    settings = write_config(tmp_path, base.read_text())
    with pytest.raises(AuthConfigError, match="导入失败"):
        load_auth_config(settings)


def test_dev_does_not_read_auth_config(tmp_path):
    assert load_auth_config(Settings(auth_mode="dev", auth_config=tmp_path / "missing.py")).local_users == {}


def test_application_aborts_before_schema_creation(tmp_path):
    settings = Settings(
        auth_mode="login", auth_config=tmp_path / "missing.py",
        database_url=f"sqlite+pysqlite:///{tmp_path / 'uncreated.db'}",
        data_dir=tmp_path / "files", auto_create_schema=True,
    )
    with pytest.raises(AuthConfigError, match="不可读"), TestClient(create_app(settings)):
        pass
    assert not (tmp_path / "uncreated.db").exists()


@pytest.mark.parametrize("name", [
    "PROVIDER", "AUTHORIZE_URL", "TOKEN_URL", "USER_INFO_URL", "CLIENT_ID",
    "CLIENT_SECRET", "REDIRECT_URI", "UNKNOWN_FUTURE_KEY",
])
@pytest.mark.parametrize("value", ["", "old-value"])
def test_reject_old_environment_variables(monkeypatch, name, value):
    monkeypatch.setenv(f"ONTOFOUNDRY_OAUTH_{name}", value)
    with pytest.raises(ValidationError, match="请迁移到 ONTOFOUNDRY_AUTH_MODE=login"):
        Settings(_env_file=None)


def test_reject_old_dotenv_variables(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ONTOFOUNDRY_OAUTH_CLIENT_ID=\n")
    with pytest.raises(ValidationError, match="旧 OAuth 配置已移除"):
        Settings(_env_file=env)


@pytest.mark.parametrize("from_environment", [True, False])
def test_reject_old_oauth_mode(monkeypatch, from_environment):
    if from_environment:
        monkeypatch.setenv("ONTOFOUNDRY_AUTH_MODE", "oauth")
    with pytest.raises(ValidationError, match="请迁移"):
        Settings(**({} if from_environment else {"auth_mode": "oauth"}), _env_file=None)


def test_production_requires_login_and_keeps_session_guards():
    kwargs = dict(
        environment="production", session_secret="x" * 32,
        cookie_secure=True, seed_demo=False, _env_file=None,
    )
    with pytest.raises(ValidationError, match="production requires ONTOFOUNDRY_AUTH_MODE=login"):
        Settings(auth_mode="dev", **kwargs)
    assert Settings(auth_mode="login", **kwargs).auth_mode == "login"
    for key, value in (("session_secret", "short"), ("cookie_secure", False), ("seed_demo", True)):
        with pytest.raises(ValidationError):
            Settings(auth_mode="login", **{**kwargs, key: value})


def test_auth_contract_schema_matches_artifact():
    from jsonschema import Draft202012Validator

    from ontofoundry_api.contracts.auth import auth_schema

    schema = auth_schema()
    Draft202012Validator.check_schema(schema)
    path = Path(__file__).resolve().parents[1] / "src/ontofoundry_api/contracts/ontofoundry.auth.v1.schema.json"
    assert json.loads(path.read_text()) == schema
    validator = Draft202012Validator(schema)
    validator.validate({"local_login": True, "oauth": {"name": "SSO"}})
    validator.validate({"local_login": False, "oauth": None})
    validator.validate({"username": "admin", "password": "example"})


@pytest.mark.parametrize("raw", [None, {}, (), [""], [" "], [7]])
def test_invalid_admin_users(tmp_path, raw):
    with pytest.raises(AuthConfigError, match="ADMIN_USERS"):
        load_auth_config(write_config(tmp_path, DEFAULT_CONFIG + f"ADMIN_USERS = {raw!r}\n"))


def test_admin_users_empty_warns_and_unknown_user_is_valid(tmp_path, caplog):
    config = load_auth_config(write_config(tmp_path, DEFAULT_CONFIG + 'ADMIN_USERS = ["precreated-admin"]\n'))
    assert config.admin_users == ("precreated-admin",)
    assert "ADMIN_USERS 为空" not in caplog.text
    load_auth_config(write_config(tmp_path, DEFAULT_CONFIG + "ADMIN_USERS = []\n"))
    assert "ADMIN_USERS 为空" in caplog.text


def test_local_username_uniqueness_is_case_insensitive(tmp_path):
    source = "LOCAL_USERS = [{'username': 'Fiction', 'password': 'one'}, {'username': 'fiction', 'password': 'two'}]"
    with pytest.raises(AuthConfigError, match="唯一"):
        load_auth_config(write_config(tmp_path, source))
