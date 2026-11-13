from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass, replace
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ontofoundry_api.config import Settings
from ontofoundry_api.contracts.auth import AuthOptions, LocalLoginRequest, OAuthOption
from ontofoundry_api.contracts.users import CurrentUser
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import UserRecord, WorkspaceMemberRecord
from ontofoundry_api.services.auth import login_local, login_oauth, require_provider
from ontofoundry_api.services.auth_config import (
    AuthConfig,
    is_local_account,
    is_platform_admin,
)
from ontofoundry_api.services.errors import OAuthLoginError
from ontofoundry_api.services.workspaces import ensure_dev_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
NONCE_COOKIE = "ontofoundry_oauth_nonce"
STATE_TTL_SECONDS = 600


@dataclass(frozen=True)
class Principal:
    id: str
    username: str
    display_name: str
    email: str | None
    is_platform_admin: bool = False
    local_account: bool = False
    service_token_id: str | None = None
    service_workspace_id: str | None = None
    scopes: frozenset[str] = frozenset()
    # Set for a modeling run's MCP credential: every versioned read is forced
    # onto this version ("" means the session had no base version).
    pinned_version_id: str | None = None


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _auth_config(request: Request) -> AuthConfig:
    return request.app.state.auth_config


def _principal(user: UserRecord, request: Request) -> Principal:
    return Principal(
        id=user.id,
        username=user.username,
        is_platform_admin=is_platform_admin(user.username, _auth_config(request), dev_mode=_settings(request).auth_mode == "dev"),
        local_account=is_local_account(user.username, _auth_config(request)),
        display_name=user.display_name,
        email=user.email,
    )


def current_principal(
    request: Request,
    session: Session = Depends(get_db),
) -> Principal:
    settings = _settings(request)
    if request.headers.get("authorization"):
        raise HTTPException(
            status_code=401, detail="服务令牌仅用于只读本体服务，管理操作需要用户登录"
        )
    if settings.auth_mode == "dev":
        return _principal(ensure_dev_user(session), request)
    user_id = request.session.get("user_id")
    user = session.get(UserRecord, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return _principal(user, request)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def build_state(*, nonce: str, return_to: str, secret: str, provider: str | None = None) -> str:
    payload = {
        "nonce": nonce,
        "return_to": return_to,
        "expires_at": int(time.time()) + STATE_TTL_SECONDS,
    }
    if provider is not None:
        payload["provider"] = provider
    encoded = _b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signature = _b64encode(
        hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    )
    return f"{encoded}.{signature}"


def parse_state(*, state: str, nonce: str, secret: str) -> dict:
    try:
        encoded, signature = state.split(".", 1)
        expected = _b64encode(
            hmac.new(
                secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256
            ).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature mismatch")
        payload = json.loads(_b64decode(encoded))
        if not isinstance(payload, dict):
            raise ValueError("invalid state payload")
        expires_at = int(payload.get("expires_at", 0))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail="OAuth state 无效") from exc
    if not hmac.compare_digest(str(payload.get("nonce", "")).encode(), nonce.encode()):
        raise HTTPException(status_code=400, detail="OAuth nonce 无效")
    if expires_at < int(time.time()):
        raise HTTPException(status_code=400, detail="OAuth state 已过期")
    return payload


def safe_return_to(value: str) -> str:
    return (
        value
        if value.startswith("/")
        and not value.startswith("//")
        and "\\" not in value
        and not any(ord(c) < 32 for c in value)
        else "/"
    )


def _run_principal(
    request: Request, session: Session, token: str, workspace_id: str | None
) -> Principal:
    from ontofoundry_api.db_models import ModelingSessionRecord
    from ontofoundry_api.services.run_credentials import verify
    from ontofoundry_api.services.run_status import ACTIVE_RUN_STATUSES

    grant = verify(_settings(request).session_secret, token)
    item = session.get(ModelingSessionRecord, grant.session_id) if grant else None
    if (
        grant is None
        or item is None
        or item.workspace_id != grant.workspace_id
        or grant.workspace_id != workspace_id
        or item.dataagent_run_token != grant.run_token
        or item.task_status not in ACTIVE_RUN_STATUSES
        or not __import__(
            "ontofoundry_api.services.access", fromlist=["can_read_workspace"]
        ).can_read_workspace(session, grant.workspace_id, grant.user_id)
    ):
        raise HTTPException(401, "建模运行凭据无效、已失效或不属于当前空间")
    user = session.get(UserRecord, grant.user_id)
    if not user:
        raise HTTPException(401, "运行发起用户不存在")
    return replace(
        _principal(user, request),
        service_token_id=f"run:{grant.run_token}",
        service_workspace_id=grant.workspace_id,
        scopes=frozenset(["ontology:read", "instances:read", "mappings:read"]),
        pinned_version_id=grant.version_id or "",
    )


# Read scopes granted to the deployment's fixed MCP token.
STATIC_SCOPES = frozenset(["ontology:read", "mappings:read", "instances:read"])


def _static_principal(session: Session, workspace_id: str | None, request: Request) -> Principal:
    """The fixed MCP token reads one workspace as its earliest admin, read-only."""
    if workspace_id is None:
        raise HTTPException(401, "固定 MCP 令牌只能用于指定空间的本体接口")
    admin = session.scalar(
        select(WorkspaceMemberRecord.user_id)
        .where(
            WorkspaceMemberRecord.workspace_id == workspace_id,
            WorkspaceMemberRecord.role == "admin",
        )
        .order_by(WorkspaceMemberRecord.created_at, WorkspaceMemberRecord.id)
    )
    user = session.get(UserRecord, admin) if admin else None
    if not user:
        raise HTTPException(401, "该空间没有管理员，固定 MCP 令牌无法访问")
    return replace(
        _principal(user, request),
        service_token_id="static",
        service_workspace_id=workspace_id,
        scopes=STATIC_SCOPES,
    )


def _ontology_principal(
    request: Request,
    session: Session,
    *,
    workspace_id: str | None,
    allow_run: bool = False,
) -> Principal:
    authorization = request.headers.get("authorization", "")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if token.startswith("ofrun."):
            # Run credentials are for MCP and run-scoped proposal checks only.
            if not allow_run or scheme.lower() != "bearer":
                raise HTTPException(401, "建模运行凭据只能用于本体 MCP")
            return _run_principal(request, session, token, workspace_id)
        static = _settings(request).mcp_token
        if static and scheme.lower() == "bearer" and hmac.compare_digest(token.encode(), static.encode()):
            return _static_principal(session, workspace_id, request)
        # Only the deployment's fixed token and modeling run credentials are accepted.
        raise HTTPException(401, "本体令牌无效")
    return current_principal(request, session)


def ontology_principal(request: Request, session: Session = Depends(get_db)) -> Principal:
    principal = _ontology_principal(request, session, workspace_id=request.path_params.get("workspace_id"))
    from ontofoundry_api.services.access import require_read

    require_read(session, request.path_params["workspace_id"], principal)
    return principal


def mcp_principal(request: Request, session: Session = Depends(get_db)) -> Principal:
    principal = _ontology_principal(request, session, workspace_id=request.path_params.get("workspace_id"), allow_run=True)
    from ontofoundry_api.services.access import require_read

    require_read(session, request.path_params["workspace_id"], principal)
    return principal


def ontology_directory_principal(
    request: Request, session: Session = Depends(get_db)
) -> Principal:
    return _ontology_principal(request, session, workspace_id=None)


@router.get("/me", response_model=CurrentUser)
def me(principal: Principal = Depends(current_principal)) -> dict:
    return {
        "id": principal.id,
        "username": principal.username,
        "is_platform_admin": principal.is_platform_admin,
        "local_account": principal.local_account,
        "display_name": principal.display_name,
        "email": principal.email,
    }


@router.get("/options", response_model=AuthOptions)
def options(request: Request) -> AuthOptions:
    config = _auth_config(request)
    return AuthOptions(
        local_login=bool(config.local_users),
        oauth=OAuthOption(name=config.oauth.name) if config.oauth else None,
    )


@router.post("/login/local", status_code=204)
def local_login(
    payload: LocalLoginRequest,
    request: Request,
    session: Session = Depends(get_db),
) -> Response:
    if _settings(request).auth_mode != "login":
        raise HTTPException(status_code=404, detail="未启用登录")
    user = login_local(
        session, _auth_config(request), username=payload.username, password=payload.password
    )
    request.session.clear()
    request.session["user_id"] = user.id
    return Response(status_code=204)


@router.get("/login/{provider}")
def login(provider: str, request: Request, return_to: str = "/") -> Response:
    settings = _settings(request)
    if settings.auth_mode == "dev":
        return RedirectResponse(safe_return_to(return_to), status_code=302)
    oauth = require_provider(_auth_config(request), provider)
    nonce = secrets.token_urlsafe(24)
    state = build_state(
        nonce=nonce,
        return_to=safe_return_to(return_to),
        secret=settings.session_secret,
        provider=provider,
    )
    params = {
        "response_type": "code",
        "client_id": oauth.client_id,
        "redirect_uri": oauth.redirect_uri,
        "state": state,
        "scope": oauth.scope,
    }
    separator = "&" if "?" in oauth.authorize_url else "?"
    response = RedirectResponse(
        f"{oauth.authorize_url}{separator}{urlencode(params)}", status_code=302
    )
    response.set_cookie(
        NONCE_COOKIE,
        nonce,
        max_age=STATE_TTL_SECONDS,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/v1/auth",
    )
    return response


def _terminal_oauth_redirect(error: str) -> Response:
    response = RedirectResponse(f"/login?error={error}", status_code=302)
    response.delete_cookie(NONCE_COOKIE, path="/api/v1/auth")
    return response


@router.get("/callback/{provider}")
async def callback(
    provider: str,
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    session: Session = Depends(get_db),
) -> Response:
    settings = _settings(request)
    require_provider(_auth_config(request), provider)
    nonce = request.cookies.get(NONCE_COOKIE)
    if not nonce:
        raise HTTPException(status_code=400, detail="OAuth nonce Cookie 缺失")
    payload = parse_state(state=state, nonce=nonce, secret=settings.session_secret)
    if payload.get("provider") != provider:
        raise HTTPException(status_code=400, detail="OAuth state 认证服务不匹配")
    if error:
        return _terminal_oauth_redirect("oauth_denied")
    if not code:
        return _terminal_oauth_redirect("oauth_exchange_failed")
    try:
        user = await login_oauth(session, _auth_config(request), provider=provider, code=code)
    except OAuthLoginError as exc:
        return _terminal_oauth_redirect(exc.code.lower())
    request.session.clear()
    request.session["user_id"] = user.id
    response = RedirectResponse(safe_return_to(payload.get("return_to", "/")), status_code=302)
    response.delete_cookie(NONCE_COOKIE, path="/api/v1/auth")
    return response


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)
