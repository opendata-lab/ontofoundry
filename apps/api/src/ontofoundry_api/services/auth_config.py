"""Load and validate the deployment's Python authentication configuration."""

from __future__ import annotations

import importlib.util
import inspect
import logging
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from urllib.parse import unquote, urlparse

from ontofoundry_api.config import Settings

logger = logging.getLogger(__name__)


class AuthConfigError(RuntimeError):
    """Invalid deployment configuration; abort application startup."""


@dataclass(frozen=True)
class OAuthProvider:
    name: str
    client_id: str
    client_secret: str = field(repr=False)
    authorize_url: str
    access_token_url: str
    redirect_uri: str
    api_base_url: str
    scope: str = "openid profile"


@dataclass(frozen=True)
class AuthConfig:
    local_users: dict[str, str] = field(default_factory=dict, repr=False)
    oauth: OAuthProvider | None = None
    oauth_user_info: Callable | None = None


def _local_users(raw: object) -> dict[str, str]:
    if not isinstance(raw, list):
        raise AuthConfigError("LOCAL_USERS 必须是列表")
    users: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise AuthConfigError("LOCAL_USERS 条目必须是字典")
        username, password = item.get("username"), item.get("password")
        if not isinstance(username, str) or not username.strip():
            raise AuthConfigError("LOCAL_USERS.username 必须是非空字符串")
        if len(username) > 120 or any(ord(c) < 32 or ord(c) == 127 for c in username):
            raise AuthConfigError("LOCAL_USERS.username 不能含控制字符，且不能超过 120 字符")
        if not isinstance(password, str) or not password:
            raise AuthConfigError("LOCAL_USERS.password 必须是非空明文字符串")
        if username in users:
            raise AuthConfigError("LOCAL_USERS.username 必须唯一")
        users[username] = password
    return users


def _http_url(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AuthConfigError(f"OAUTH_PROVIDERS.remote_app.{name} 必须是非空字符串")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise AuthConfigError(f"OAUTH_PROVIDERS.remote_app.{name} 必须是绝对 HTTP(S) URL")
    return value


def _oauth_provider(raw: object) -> OAuthProvider | None:
    if not isinstance(raw, list) or len(raw) > 1:
        raise AuthConfigError("OAUTH_PROVIDERS 必须是列表，且最多配置一项")
    if not raw:
        return None
    provider = raw[0]
    if not isinstance(provider, dict):
        raise AuthConfigError("OAUTH_PROVIDERS 条目必须是字典")
    name = provider.get("name")
    if (
        not isinstance(name, str)
        or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) is None
        or name.casefold() == "local"
    ):
        raise AuthConfigError("OAUTH_PROVIDERS.name 必须是 1～64 位字母、数字、下划线或连字符，不能为 local")
    remote = provider.get("remote_app")
    if not isinstance(remote, dict):
        raise AuthConfigError("OAUTH_PROVIDERS.remote_app 必须是字典")
    for key in ("client_id", "client_secret"):
        if not isinstance(remote.get(key), str) or not remote[key].strip():
            raise AuthConfigError(f"OAUTH_PROVIDERS.remote_app.{key} 必须是非空字符串")
    authorize_url = _http_url(remote.get("authorize_url"), "authorize_url")
    token_url = _http_url(remote.get("access_token_url"), "access_token_url")
    redirect_uri = _http_url(remote.get("redirect_uri"), "redirect_uri")
    redirect = urlparse(redirect_uri)
    if (
        unquote(redirect.path) != f"/api/v1/auth/callback/{name}"
        or redirect.params or redirect.query or redirect.fragment
    ):
        raise AuthConfigError(f"OAUTH_PROVIDERS.remote_app.redirect_uri 的路径必须为 /api/v1/auth/callback/{name}，不能带参数")
    api_base_url = _http_url(remote.get("api_base_url"), "api_base_url")
    api_base = urlparse(api_base_url)
    if not api_base_url.endswith("/") or api_base.params or api_base.query or api_base.fragment:
        raise AuthConfigError("OAUTH_PROVIDERS.remote_app.api_base_url 必须以 / 结尾，不能带参数")
    if remote.get("response_type", "code") != "code" or remote.get("grant_type", "authorization_code") != "authorization_code":
        raise AuthConfigError("OAUTH_PROVIDERS 只支持授权码模式：response_type=code，grant_type=authorization_code")
    client_kwargs = remote.get("client_kwargs", {})
    if not isinstance(client_kwargs, dict):
        raise AuthConfigError("OAUTH_PROVIDERS.remote_app.client_kwargs 必须是字典")
    scope = client_kwargs.get("scope", "openid profile")
    if not isinstance(scope, str) or not scope.strip():
        raise AuthConfigError("OAUTH_PROVIDERS.remote_app.client_kwargs.scope 必须是非空字符串")
    return OAuthProvider(
        name=name, client_id=remote["client_id"], client_secret=remote["client_secret"],
        authorize_url=authorize_url, access_token_url=token_url, redirect_uri=redirect_uri,
        api_base_url=api_base_url, scope=scope,
    )


def _build_config(module: ModuleType) -> AuthConfig:
    users = _local_users(getattr(module, "LOCAL_USERS", []))
    oauth = _oauth_provider(getattr(module, "OAUTH_PROVIDERS", []))
    hook = getattr(module, "OAUTH_USER_INFO", None)
    if hook is not None:
        if not callable(hook):
            raise AuthConfigError("OAUTH_USER_INFO 必须是同步 callable")
        if any(
            check(candidate)
            for check in (inspect.iscoroutinefunction, inspect.isasyncgenfunction)
            for candidate in (hook, type(hook).__call__)
        ):
            raise AuthConfigError("OAUTH_USER_INFO 必须同步，钩子在线程中执行")
        try:
            inspect.signature(hook).bind("provider", {}, {})
        except (TypeError, ValueError) as exc:
            raise AuthConfigError("OAUTH_USER_INFO 必须接受 (provider, token_response, oauth_remotes) 三个参数") from exc
    if oauth and hook is None:
        raise AuthConfigError("配置 OAUTH_PROVIDERS 时必须提供 OAUTH_USER_INFO")
    if not users and oauth is None:
        raise AuthConfigError("login 模式至少配置一种登录方式：LOCAL_USERS 或 OAUTH_PROVIDERS")
    if users.get("admin") == "admin123":
        logger.warning("本地账号 admin 仍使用默认密码，请在现场覆盖配置中修改密码")
    return AuthConfig(local_users=users, oauth=oauth, oauth_user_info=hook)


def load_auth_config(settings: Settings) -> AuthConfig:
    if settings.auth_mode == "dev":
        return AuthConfig()
    if settings.auth_config is None:
        raise AuthConfigError("login 模式必须设置 ONTOFOUNDRY_AUTH_CONFIG")
    path = Path(settings.auth_config).resolve()
    if not path.is_file() or not os.access(path, os.R_OK):
        raise AuthConfigError(f"ONTOFOUNDRY_AUTH_CONFIG 指向的配置文件不可读：{path}")
    config_dir = str(path.parent)
    if config_dir not in sys.path:
        sys.path.insert(0, config_dir)
    try:
        spec = importlib.util.spec_from_file_location("ontofoundry_external_auth_config", path)
        if spec is None or spec.loader is None:
            raise AuthConfigError(f"无法导入 ONTOFOUNDRY_AUTH_CONFIG：{path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except AuthConfigError:
        raise
    except Exception as exc:
        # Configuration exceptions can contain client secrets; log only their type.
        raise AuthConfigError(f"认证配置导入失败：{path}（{type(exc).__name__}）") from None
    return _build_config(module)
