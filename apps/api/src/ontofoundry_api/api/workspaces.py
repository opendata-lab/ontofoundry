from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.service_validation import ServiceValidationRoute
from ontofoundry_api.contracts.gateway import FeedbackList
from ontofoundry_api.contracts.users import (
    MemberCreate,
    MemberItem,
    MemberList,
    RoleUpdate,
    SpaceUpdate,
    UserSearchList,
    WorkspaceItem,
    WorkspaceList,
)
from ontofoundry_api.database import get_db
from ontofoundry_api.domain.models import WorkspaceCreate
from ontofoundry_api.services import gateway_records, users
from ontofoundry_api.services.access import require_manage, require_read
from ontofoundry_api.services.dataagent_health import dataagent_health
from ontofoundry_api.services.ontology_query import current_version, workspace_overview
from ontofoundry_api.services.workspaces import (
    create_workspace,
    get_workspace,
    list_workspaces,
    workspace_summary,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])
feedback_router = APIRouter(
    prefix="/api/v1/workspaces", tags=["gateway-history"], route_class=ServiceValidationRoute
)


@router.get("", response_model=WorkspaceList)
def list_all(
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    return {"items": list_workspaces(session, principal.id)}


@router.post("", status_code=201, response_model=WorkspaceItem)
def create(
    payload: WorkspaceCreate,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    workspace = create_workspace(session, payload=payload, user_id=principal.id)
    return workspace_summary(session, workspace, principal.id)


@router.get("/{workspace_id}", response_model=WorkspaceItem)
def get_one(
    workspace_id: str,
    request: Request,
    response: Response,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    require_read(session, str(workspace_id), principal)
    from ontofoundry_api.services.access import authorization_fingerprint
    from ontofoundry_api.services.http_reads import conditional, validator

    workspace = get_workspace(session, workspace_id)
    permission = authorization_fingerprint(session, workspace_id, principal)
    response.headers["X-Ontology-Authorization"] = permission
    tag = validator(
        [
            workspace.id,
            workspace.current_version_id,
            workspace.updated_at,
            workspace.name,
            workspace.description,
            permission,
            "workspace-1",
        ]
    )
    unchanged = conditional(request, response, tag)
    if unchanged is not None:
        unchanged.headers["X-Ontology-Authorization"] = permission
        return unchanged
    return workspace_summary(session, workspace, principal.id)


@router.get("/{workspace_id}/overview")
def overview(
    workspace_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    require_read(session, str(workspace_id), principal)
    from ontofoundry_api.services.access import can_read_instances, can_read_mappings

    workspace = get_workspace(session, workspace_id)
    version = (
        current_version(session, workspace_id) if workspace.current_version_id else None
    )
    return workspace_overview(
        version,
        db=session,
        include_mappings=can_read_mappings(session, workspace_id, principal),
        include_instances=can_read_instances(session, workspace_id, principal),
    )


@router.get("/{workspace_id}/settings/dataagent-health")
async def get_dataagent_health(workspace_id: str, request: Request, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    return await dataagent_health(request.app.state.settings, workspace_id)


@router.patch("/{workspace_id}", response_model=WorkspaceItem)
def update_space(workspace_id: str, body: SpaceUpdate, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    return users.update_workspace(db, workspace_id, body, user.id)


@router.get("/{workspace_id}/members", response_model=MemberList)
def members(workspace_id: str, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    return {"items": users.list_members(db, workspace_id)}


@router.get("/{workspace_id}/users/search", response_model=UserSearchList)
def search_users(workspace_id: str, q: str = "", db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    return {"items": users.search_users(db, workspace_id, q)}


@router.post("/{workspace_id}/members", status_code=201, response_model=MemberItem)
def add_member(workspace_id: str, body: MemberCreate, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    return users.membership(db, workspace_id, body.user_id, body.role, create_only=True)


@router.patch("/{workspace_id}/members/{member_id}", response_model=MemberItem)
def change_member(workspace_id: str, member_id: int, body: RoleUpdate, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    target = users.member_by_id(db, workspace_id, member_id)
    return users.membership(db, workspace_id, target.user_id, body.role)


@router.delete("/{workspace_id}/members/{member_id}")
def remove_member(workspace_id: str, member_id: int, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_manage(db, workspace_id, user)
    target = users.member_by_id(db, workspace_id, member_id)
    users.membership(db, workspace_id, target.user_id, None)
    return {"ok": True}


@router.get("/{workspace_id}/capabilities")
def capabilities(
    workspace_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_read(db, str(workspace_id), user)
    config = request.app.state.settings
    configured = bool(config.dataagent_base_url)
    return {
        "agent_configured": configured,
        "model": f"DataAgent · {config.dataagent_agent_id}" if configured else "",
        "max_file_mb": config.max_file_mb,
        "connections_configured": True,
        "skills": ["ontology-discovery", "entity-extraction"],
    }


@feedback_router.get(
    "/{workspace_id}/feedback",
    response_model=FeedbackList,
    response_model_exclude_unset=True,
)
def feedback(
    workspace_id: str,
    request: Request,
    cursor: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    require_manage(db, workspace_id, principal)
    return gateway_records.list_feedback(
        db, workspace_id, principal, request.app.state.settings, cursor=cursor, limit=limit
    )
