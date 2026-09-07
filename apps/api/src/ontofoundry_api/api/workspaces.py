from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.database import get_db
from ontofoundry_api.domain.models import PublishRequest, WorkspaceCreate
from ontofoundry_api.services.ontology_query import (
    current_version,
    version_summary,
    workspace_overview,
)
from ontofoundry_api.services.workspaces import (
    create_workspace,
    get_workspace,
    list_workspaces,
    membership_role,
    publish_draft,
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


@router.post("/{workspace_id}/publish", status_code=201)
def publish(
    workspace_id: str,
    payload: PublishRequest,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    version = publish_draft(
        session,
        workspace_id=workspace_id,
        draft=payload.draft,
        user_id=principal.id,
        message=payload.message,
    )
    return version_summary(version)


@router.get("/{workspace_id}/overview")
def overview(
    workspace_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    version = current_version(session, workspace_id)
    return workspace_overview(
        version,
        include_private=membership_role(session, workspace_id, principal.id) is not None,
    )
