from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.database import get_db
from ontofoundry_api.domain.models import WorkspaceCreate
from ontofoundry_api.services.ontology_query import (
    current_version,
    workspace_overview,
)
from ontofoundry_api.services.workspaces import (
    create_workspace,
    get_workspace,
    list_workspaces,
    workspace_summary,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


@router.get("")
def list_all(
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    return {"items": list_workspaces(session, principal.id)}


@router.post("", status_code=201)
def create(
    payload: WorkspaceCreate,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    workspace = create_workspace(session, payload=payload, user_id=principal.id)
    return workspace_summary(session, workspace, principal.id)


@router.get("/{workspace_id}")
def get_one(
    workspace_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    return workspace_summary(session, get_workspace(session, workspace_id), principal.id)


@router.get("/{workspace_id}/overview")
def overview(
    workspace_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
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
