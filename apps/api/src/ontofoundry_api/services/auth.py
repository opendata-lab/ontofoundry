"""Local credentials and the DataAgent-compatible OAuth user-info hook."""

from __future__ import annotations

import hmac
import logging

import anyio
import httpx
from sqlalchemy.orm import Session

from ontofoundry_api.db_models import UserRecord
from ontofoundry_api.services.auth_config import AuthConfig, OAuthProvider
from ontofoundry_api.services.errors import (
    InvalidCredentialsError,
    NotFoundError,
    OAuthLoginError,
    OAuthUserInfoError,
)
from ontofoundry_api.services.workspaces import upsert_oauth_user

logger = logging.getLogger(__name__)
OAUTH_TIMEOUT_SECONDS = 15


def login_local(
    session: Session, config: AuthConfig, *, username: str, password: str
) -> UserRecord:
    username = next((name for name in config.local_users if name.lower() == username.lower()), username)
    expected = config.local_users.get(username)
    matches = hmac.compare_digest(password.encode("utf-8"), (expected or "").encode("utf-8"))
    if expected is None or not matches:
        logger.warning("Local login failed username=%r", username)
        raise InvalidCredentialsError("用户名或密码错误")
    return upsert_oauth_user(
        session, username=username, display_name=username, email=None, update_profile=False
    )


def require_provider(config: AuthConfig, name: str) -> OAuthProvider:
    if config.oauth is None or config.oauth.name != name:
        raise NotFoundError("认证服务未配置")
    return config.oauth


def _valid_text(value: object, *, limit: int) -> bool:
    return (
        isinstance(value, str) and bool(value.strip()) and len(value) <= limit
        and not any(ord(c) < 32 or ord(c) == 127 for c in value)
    )


async def _userinfo(config: AuthConfig, provider: OAuthProvider, code: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=OAUTH_TIMEOUT_SECONDS) as client:
            response = await client.post(
                provider.access_token_url,
                data={
                    "grant_type": "authorization_code", "code": code,
                    "client_id": provider.client_id, "client_secret": provider.client_secret,
                    "redirect_uri": provider.redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            token_payload = response.json()
        if not isinstance(token_payload, dict):
            raise ValueError("invalid token payload")
        access_token = token_payload.get("access_token")
        token_type = token_payload.get("token_type") or "Bearer"
        if not _valid_text(access_token, limit=8192):
            raise ValueError("invalid access token")
        if not isinstance(token_type, str) or token_type.lower() != "bearer":
            raise ValueError("unsupported token type")
    except Exception as exc:
        # HTTP exceptions may include URLs or secret response bodies.
        logger.error("OAuth exchange failed provider=%s error_type=%s", provider.name, type(exc).__name__)
        raise OAuthLoginError("认证服务令牌交换失败，请重新登录") from None

    def call_hook() -> object:
        with httpx.Client(
            base_url=provider.api_base_url,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=OAUTH_TIMEOUT_SECONDS,
        ) as remote:
            return config.oauth_user_info(provider.name, token_payload, {provider.name: remote})

    try:
        profile = await anyio.to_thread.run_sync(call_hook)
        if not isinstance(profile, dict):
            raise ValueError("OAUTH_USER_INFO must return a dict")
        return profile
    except Exception as exc:
        logger.error("OAUTH_USER_INFO failed provider=%s error_type=%s", provider.name, type(exc).__name__)
        raise OAuthUserInfoError("认证服务用户信息获取失败，请重新登录") from None


async def login_oauth(
    session: Session, config: AuthConfig, *, provider: str, code: str
) -> UserRecord:
    oauth = require_provider(config, provider)
    profile = await _userinfo(config, oauth, code)
    subject = profile.get("sub")
    if not _valid_text(subject, limit=255 - len(provider) - 1):
        raise OAuthUserInfoError("认证服务用户信息缺少有效的 sub")
    username = profile.get("username", subject)
    if "username" in profile and not _valid_text(username, limit=120):
        raise OAuthUserInfoError("认证服务用户信息的用户名无效")
    display_name = subject
    for claim in ("display_name", "preferred_username", "name", "email"):
        candidate = profile.get(claim)
        if candidate in (None, ""):
            continue
        display_name = candidate
        break
    email = profile.get("email") or None
    if not _valid_text(display_name, limit=120) or (
        email is not None and not _valid_text(email, limit=255)
    ):
        raise OAuthUserInfoError("认证服务用户信息的名称或邮箱无效")
    # Workspace membership, never profile.role, determines authorization.
    return upsert_oauth_user(
        session, username=username, display_name=display_name, email=email
    )
