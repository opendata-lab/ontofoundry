"""User management and workspace membership API contracts."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

Role = Literal["admin", "member", "viewer"]
Username = Annotated[str, Field(min_length=1, max_length=120)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CurrentUser(Contract):
    id: str
    username: str
    display_name: str
    email: str | None
    is_platform_admin: bool
    local_account: bool


class UserCreate(Contract):
    username: Username
    display_name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=255)

    @field_validator("username", "display_name")
    @classmethod
    def valid_text(cls, value):
        if not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError("不能包含控制字符或仅为空白")
        return value


class RoleUpdate(Contract):
    role: Role


class MemberCreate(RoleUpdate):
    user_id: str = Field(min_length=1)


class MemberItem(Contract):
    id: int
    user_id: str
    username: str
    display_name: str
    role: Role
    last_login_at: datetime | None


class MemberList(Contract):
    items: list[MemberItem]


class UserSearchItem(Contract):
    id: str
    username: str
    display_name: str
    last_login_at: datetime | None


class UserSearchList(Contract):
    items: list[UserSearchItem]


class UserWorkspace(Contract):
    id: str
    name: str
    role: Role


class MyWorkspace(UserWorkspace):
    is_public: bool


class MyWorkspaces(Contract):
    items: list[MyWorkspace]


class AdminUser(Contract):
    id: str
    username: str
    display_name: str
    email: str | None
    local_account: bool
    platform_admin: bool
    last_login_at: datetime | None
    workspaces: list[UserWorkspace]


class AdminUsers(Contract):
    items: list[AdminUser]


class AdminWorkspace(Contract):
    id: str
    name: str
    is_public: bool


class AdminWorkspaces(Contract):
    items: list[AdminWorkspace]


class Assignment(Contract):
    workspace_id: str
    role: Role


class SpaceUpdate(Contract):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1200)
    is_public: bool | None = None

    @field_validator("name", "description", "is_public")
    @classmethod
    def not_null(cls, value):
        if value is None:
            raise ValueError("不能为 null")
        return value


class WorkspaceItem(Contract):
    id: str
    slug: str
    name: str
    description: str
    is_public: bool
    role: Role | None
    visibility: Literal["member", "public"]
    current_version: int | None
    version_id: str | None
    version_sha256: str | None
    object_type_count: int
    link_type_count: int
    updated_at: datetime


class WorkspaceList(Contract):
    items: list[WorkspaceItem]


def users_schema():
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "ontofoundry.users.v1.schema.json",
        **TypeAdapter(CurrentUser | UserCreate | RoleUpdate | MemberCreate | MemberList | MemberItem | UserSearchList | MyWorkspaces | AdminUsers | AdminUser | AdminWorkspaces | Assignment | SpaceUpdate | WorkspaceItem | WorkspaceList).json_schema(mode="serialization"),
    }
