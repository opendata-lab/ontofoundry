"""Personal token, feedback and gateway audit HTTP contracts."""

from datetime import datetime
from typing import Literal

from pydantic import Field, TypeAdapter, field_validator, model_validator

from ontofoundry_api.contracts.users import Contract

Permission = Literal["ontology:read", "mappings:read"]


class TokenCreate(Contract):
    name: str = Field(min_length=1, max_length=100)
    permissions: list[Permission]

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if not value.strip():
            raise ValueError("名称不能为空")
        return value

    @field_validator("permissions")
    @classmethod
    def valid_permissions(cls, value):
        if "ontology:read" not in value:
            raise ValueError("权限必须包含 ontology:read")
        return list(dict.fromkeys(value))


class TokenPatch(Contract):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    permissions: list[Permission] | None = None

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if value is None:
            raise ValueError("名称不能为空")
        return TokenCreate.valid_name(value)

    @field_validator("permissions")
    @classmethod
    def valid_permissions(cls, value):
        if value is None:
            raise ValueError("权限不能为空")
        return TokenCreate.valid_permissions(value)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.model_fields_set:
            raise ValueError("请提供名称或权限")
        return self


class TokenCreated(Contract):
    id: str
    name: str
    permissions: list[Permission]
    created_at: datetime
    token: str


class TokenItem(Contract):
    id: str
    name: str
    permissions: list[Permission]
    created_at: datetime
    updated_at: datetime
    last_used_at: datetime | None


class TokenList(Contract):
    items: list[TokenItem]


class GatewayUser(Contract):
    id: str
    display_name: str


class FeedbackElement(Contract):
    id: str
    name: str | None = None
    display_name: str | None = None


class FeedbackItem(Contract):
    id: str
    created_at: datetime
    user: GatewayUser
    kind: Literal["correction", "suggestion"]
    user_text: str
    agent_text: str
    elements: list[FeedbackElement]
    version_number: int | None


class FeedbackList(Contract):
    items: list[FeedbackItem]
    next_cursor: str | None


class CallWorkspace(Contract):
    id: str
    name: str | None
    version_number: int | None


class CallWorkspaceDetail(CallWorkspace):
    version_id: str | None


class GatewayCallItem(Contract):
    id: str
    created_at: datetime
    user: GatewayUser
    tool: str
    workspaces: list[CallWorkspace]
    summary: str
    outcome: Literal["started", "ok", "error"]
    error_code: str | None
    duration_ms: int | None


class GatewayCallList(Contract):
    items: list[GatewayCallItem]
    next_cursor: str | None


class GatewayCallDetail(Contract):
    id: str
    created_at: datetime
    user: GatewayUser
    tool: str
    request_id: str
    workspaces: list[CallWorkspaceDetail]
    arguments: dict
    response: dict | None
    outcome: Literal["started", "ok", "error"]
    error_code: str | None
    error_message: str | None
    duration_ms: int | None


def gateway_schema():
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "ontofoundry.gateway.v1.schema.json",
        **TypeAdapter(TokenCreate | TokenPatch | TokenCreated | TokenItem | TokenList | FeedbackList | GatewayCallList | GatewayCallDetail).json_schema(mode="serialization"),
    }
