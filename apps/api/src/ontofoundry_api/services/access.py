"""Workspace authorization shared by HTTP, MCP, projections and caches."""

import hashlib
import json

from ontofoundry_api.db_models import UserRecord, WorkspaceRecord
from ontofoundry_api.services.auth_config import AuthConfig, is_platform_admin
from ontofoundry_api.services.errors import ForbiddenError, NotFoundError
from ontofoundry_api.services.workspaces import membership_role


def platform_admin(db, principal):
    if not isinstance(principal, str):
        return principal.is_platform_admin
    user = db.get(UserRecord, principal)
    return bool(user and is_platform_admin(
        user.username, db.info.get("auth_config", AuthConfig()),
        dev_mode=db.info.get("dev_mode", False),
    ))


def _id(principal):
    return principal if isinstance(principal, str) else principal.id


def can_read_workspace(db, workspace_id, principal):
    space = db.get(WorkspaceRecord, str(workspace_id))
    return bool(space and (platform_admin(db, principal) or space.is_public or membership_role(db, str(workspace_id), _id(principal))))


def can_edit_workspace(db, workspace_id, principal):
    return platform_admin(db, principal) or membership_role(db, str(workspace_id), _id(principal)) in {"admin", "member"}


def can_manage_workspace(db, workspace_id, principal):
    return platform_admin(db, principal) or membership_role(db, str(workspace_id), _id(principal)) == "admin"


def require_read(db, workspace_id, principal):
    if not can_read_workspace(db, workspace_id, principal):
        raise NotFoundError("没有找到该工作空间", code="WORKSPACE_NOT_FOUND")


def require_edit(db, workspace_id, principal):
    if not can_edit_workspace(db, workspace_id, principal):
        raise ForbiddenError("需要空间编辑权限", code="WORKSPACE_EDIT_REQUIRED")


def require_manage(db, workspace_id, principal):
    if not can_manage_workspace(db, workspace_id, principal):
        raise ForbiddenError("需要空间管理员权限", code="WORKSPACE_MANAGE_REQUIRED")


def can_read_instances(db, workspace_id, principal):
    return can_read_workspace(db, workspace_id, principal) and (
        principal.service_token_id is None or "instances:read" in principal.scopes
    )


def can_read_mappings(db, workspace_id, principal):
    return can_read_workspace(db, workspace_id, principal) and (
        principal.service_token_id is None or "mappings:read" in principal.scopes
    )


def require_instances(db, workspace_id, principal):
    if not can_read_instances(db, workspace_id, principal):
        raise ForbiddenError("需要空间读取权限及实例读取授权", code="INSTANCES_FORBIDDEN")


def require_mappings(db, workspace_id, principal):
    if not can_read_mappings(db, workspace_id, principal):
        raise ForbiddenError("需要映射读取授权", code="MAPPINGS_FORBIDDEN")


def authorization_fingerprint(db, workspace_id, principal):
    return hashlib.sha256(json.dumps([
        principal.id, principal.service_token_id,
        membership_role(db, workspace_id, principal.id),
        platform_admin(db, principal), can_read_workspace(db, workspace_id, principal),
        sorted(principal.scopes), can_read_instances(db, workspace_id, principal),
        can_read_mappings(db, workspace_id, principal),
    ]).encode()).hexdigest()
