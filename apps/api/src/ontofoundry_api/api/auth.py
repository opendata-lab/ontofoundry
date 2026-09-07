from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ontofoundry_api.config import Settings
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import ServiceTokenRecord, UserRecord
from ontofoundry_api.services.workspaces import ensure_dev_user, upsert_oauth_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
NONCE_COOKIE = "ontofoundry_oauth_nonce"
STATE_TTL_SECONDS = 600


@dataclass(frozen=True)
class Principal:
    id: str
    subject: str
    display_name: str
    email: str | None


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _principal(user: UserRecord) -> Principal:
    return Principal(
        id=user.id,
        subject=user.subject,
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
        return _principal(ensure_dev_user(session))
    user_id = request.session.get("user_id")
    user = session.get(UserRecord, user_id) if user_id else None
    if user is None:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    return _principal(user)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def build_state(*, nonce: str, return_to: str, secret: str) -> str:
    payload = {
        "nonce": nonce,
        "return_to": return_to,
        "expires_at": int(time.time()) + STATE_TTL_SECONDS,
    }
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
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="OAuth state 无效") from exc
    if not hmac.compare_digest(str(payload.get("nonce", "")), nonce):
        raise HTTPException(status_code=400, detail="OAuth nonce 无效")
    if int(payload.get("expires_at", 0)) < int(time.time()):
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


def ontology_principal(request: Request, session: Session = Depends(get_db)) -> Principal:
    authorization = request.headers.get("authorization", "")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        record = session.scalar(
            select(ServiceTokenRecord).where(
                ServiceTokenRecord.token_hash == hashlib.sha256(token.encode()).hexdigest()
            )
        )
        if (
            scheme.lower() != "bearer"
            or not record
            or record.workspace_id != request.path_params.get("workspace_id")
        ):
            raise HTTPException(401, "本体服务令牌无效或不属于当前空间")
        user = session.get(UserRecord, record.created_by)
        return _principal(user)
    return current_principal(request, session)


@router.get("/me")
def me(principal: Principal = Depends(current_principal)) -> dict:
    return {
        "id": principal.id,
        "subject": principal.subject,
        "display_name": principal.display_name,
        "email": principal.email,
    }


@router.get("/login")
def login(request: Request, return_to: str = "/") -> Response:
    settings = _settings(request)
    if settings.auth_mode == "dev":
        return RedirectResponse(safe_return_to(return_to), status_code=302)
    nonce = secrets.token_urlsafe(24)
    state = build_state(
        nonce=nonce,
        return_to=safe_return_to(return_to),
        secret=settings.session_secret,
    )
    params = {
        "response_type": "code",
        "client_id": settings.oauth_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "state": state,
        "scope": "openid profile email",
    }
    response = RedirectResponse(
        f"{settings.oauth_authorize_url}?{urlencode(params)}", status_code=302
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


@router.get("/callback")
async def callback(
    request: Request,
    code: str,
    state: str,
    session: Session = Depends(get_db),
) -> Response:
    settings = _settings(request)
    nonce = request.cookies.get(NONCE_COOKIE)
    if not nonce:
        raise HTTPException(status_code=400, detail="OAuth nonce Cookie 缺失")
    payload = parse_state(state=state, nonce=nonce, secret=settings.session_secret)

    async with httpx.AsyncClient(timeout=15) as client:
        token_response = await client.post(
            settings.oauth_token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.oauth_redirect_uri,
                "client_id": settings.oauth_client_id,
                "client_secret": settings.oauth_client_secret,
            },
        )
        token_response.raise_for_status()
        access_token = token_response.json().get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=502, detail="OAuth Provider 未返回 access_token"
            )
        user_response = await client.get(
            settings.oauth_user_info_url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        user_response.raise_for_status()
        profile = user_response.json()

    provider_subject = profile.get("sub") or profile.get("id")
    if not provider_subject:
        raise HTTPException(status_code=502, detail="OAuth 用户信息缺少 sub")
    display_name = (
        profile.get("name")
        or profile.get("preferred_username")
        or profile.get("email")
        or str(provider_subject)
    )
    user = upsert_oauth_user(
        session,
        subject=f"{settings.oauth_provider}:{provider_subject}",
        display_name=str(display_name),
        email=profile.get("email"),
    )
    request.session.clear()
    request.session["user_id"] = user.id
    response = RedirectResponse(safe_return_to(payload["return_to"]), status_code=302)
    response.delete_cookie(NONCE_COOKIE, path="/api/v1/auth")
    return response


@router.post("/logout", status_code=204)
def logout(request: Request) -> Response:
    request.session.clear()
    return Response(status_code=204)
