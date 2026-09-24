from fastapi import HTTPException

from ontofoundry_api.services.workspaces import membership_role


def can_read_instances(db, workspace_id, principal):
    return bool(membership_role(db, workspace_id, principal.id)) and (
        principal.service_token_id is None or "instances:read" in principal.scopes
    )


def can_read_mappings(db, workspace_id, principal):
    return bool(membership_role(db, workspace_id, principal.id)) and (
        principal.service_token_id is None
        or bool({"mappings:read", "instances:read"} & principal.scopes)
    )


def require_instances(db, workspace_id, principal):
    if not can_read_instances(db, workspace_id, principal):
        raise HTTPException(
            403,
            {"code": "INSTANCES_FORBIDDEN", "message": "需要空间成员身份及实例读取授权"},
        )
