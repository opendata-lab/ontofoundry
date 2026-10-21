from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, ontology_directory_principal
from ontofoundry_api.api.auth import ontology_principal as current_principal
from ontofoundry_api.contracts.read_models import OntologySearchRead, OntologySearchRequest
from ontofoundry_api.database import get_db
from ontofoundry_api.services.access import (
    authorization_fingerprint,
    can_read_instances,
    can_read_mappings,
    require_instances,
    require_mappings,
)
from ontofoundry_api.services.instance_query import (
    ObjectSearch,
    get_object,
    object_neighborhood,
    search_objects,
)
from ontofoundry_api.services.ontology_query import (
    current_version,
    get_type,
    search_types,
    type_graph,
    version_summary,
)
from ontofoundry_api.services.ontology_search import search_ontology
from ontofoundry_api.services.workspaces import list_accessible_workspaces

router = APIRouter(prefix="/api/v1/ontology/workspaces", tags=["ontology"])


@router.get("")
def accessible_workspaces(
    session: Session = Depends(get_db),
    principal: Principal = Depends(ontology_directory_principal),
) -> dict:
    items = list_accessible_workspaces(
        session,
        principal.id,
        workspace_id=principal.service_workspace_id,
    )
    return {
        "items": [
            {
                **item,
                "mcp_endpoint": f"/api/v1/ontology/workspaces/{item['id']}/mcp",
            }
            for item in items
        ]
    }


@router.post(
    "/{workspace_id}/search",
    response_model=OntologySearchRead,
    response_model_exclude_unset=True,
)
def search(
    workspace_id: str,
    options: OntologySearchRequest,
    request: Request,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    return search_ontology(
        session, workspace_id, principal, options, request.app.state.settings
    )


@router.get("/{workspace_id}/objects")
def objects(
    workspace_id: str,
    request: Request,
    version_id: str | None = None,
    options: ObjectSearch = Depends(),
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    require_instances(session, workspace_id, principal)
    if options.source == "database":
        require_mappings(session, workspace_id, principal)
    return search_objects(
        session,
        current_version(session, workspace_id, version_id),
        options,
        request.app.state.settings,
        permission_fingerprint=authorization_fingerprint(session, workspace_id, principal),
    )


@router.get("/{workspace_id}/objects/{ref}")
def object_detail(
    workspace_id: str,
    ref: str,
    request: Request,
    version_id: str | None = None,
    snapshot_date: str | None = None,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    require_instances(session, workspace_id, principal)
    if ref.startswith("db."):
        require_mappings(session, workspace_id, principal)
    return get_object(
        session,
        current_version(session, workspace_id, version_id),
        ref,
        request.app.state.settings,
        snapshot_date=snapshot_date,
    )


@router.get("/{workspace_id}/objects/{ref}/neighborhood")
def object_graph(
    workspace_id: str,
    ref: str,
    request: Request,
    version_id: str | None = None,
    snapshot_date: str | None = None,
    depth: int = Query(default=1, ge=1, le=3),
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    require_instances(session, workspace_id, principal)
    if ref.startswith("db."):
        require_mappings(session, workspace_id, principal)
    return object_neighborhood(
        session,
        current_version(session, workspace_id, version_id),
        ref,
        depth,
        request.app.state.settings,
        snapshot_date=snapshot_date,
    )


@router.get("/{workspace_id}/version")
def version(
    workspace_id: str,
    version_id: str | None = None,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    return version_summary(
        current_version(session, workspace_id, version_id),
        include_mappings=can_read_mappings(session, workspace_id, principal),
        include_instances=can_read_instances(session, workspace_id, principal),
    )


@router.get("/{workspace_id}/types")
def types(
    workspace_id: str,
    version_id: str | None = None,
    q: str = "",
    kind: str | None = Query(
        default=None, pattern="^(object_type|link_type|metric|dataset)$"
    ),
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    return search_types(
        current_version(session, workspace_id, version_id),
        query=q,
        kind=kind,
        include_context_elements=can_read_mappings(session, workspace_id, principal),
        include_instances=can_read_instances(session, workspace_id, principal),
        db=session,
    )


@router.get("/{workspace_id}/types/{type_id}")
def type_detail(
    workspace_id: str,
    type_id: str,
    version_id: str | None = None,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> dict:
    return get_type(
        current_version(session, workspace_id, version_id),
        type_id,
        include_context_elements=can_read_mappings(session, workspace_id, principal),
        include_instances=can_read_instances(session, workspace_id, principal),
        db=session,
    )


@router.get("/{workspace_id}/type-graph/neighborhood")
def neighborhood(
    workspace_id: str,
    version_id: str | None = None,
    focus_id: str | None = None,
    depth: int = Query(default=1, ge=1, le=3),
    session: Session = Depends(get_db),
    _: Principal = Depends(current_principal),
) -> dict:
    return type_graph(
        current_version(session, workspace_id, version_id), focus_id=focus_id, depth=depth
    )
