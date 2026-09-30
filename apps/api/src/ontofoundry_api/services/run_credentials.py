"""Run-scoped, read-only MCP credentials for a modeling run (design §6.3).

A run may read exactly one thing: the ontology version its session was based
on, in its own workspace. The credential is signed, names that workspace,
session, run token and version, and is honoured only while the session still
holds the same run token — a new run or a finished one revokes it.
"""

from __future__ import annotations

from dataclasses import dataclass

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

PREFIX = "ofrun."
MAX_AGE_SECONDS = 12 * 3600


@dataclass(frozen=True)
class RunGrant:
    workspace_id: str
    session_id: str
    run_token: str
    version_id: str | None
    user_id: str


def _serializer(secret: str) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret, salt="ontofoundry-run-mcp-v1")


def issue(secret: str, grant: RunGrant) -> str:
    return PREFIX + _serializer(secret).dumps(
        {
            "w": grant.workspace_id,
            "s": grant.session_id,
            "r": grant.run_token,
            "v": grant.version_id,
            "u": grant.user_id,
        }
    )


def verify(secret: str, credential: str) -> RunGrant | None:
    if not credential.startswith(PREFIX):
        return None
    try:
        data = _serializer(secret).loads(credential[len(PREFIX) :], max_age=MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    return RunGrant(data["w"], data["s"], data["r"], data.get("v"), data["u"])
