from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal
from ontofoundry_api.api.auth import ontology_principal as current_principal
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import OntologyVersionRecord
from ontofoundry_api.services.access import can_read_instances, require_instances
from ontofoundry_api.services.errors import NotFoundError
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

router = APIRouter(prefix="/api/v1/ontology/workspaces", tags=["ontology"])


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
    return search_objects(
        session,
        current_version(session, workspace_id, version_id),
        options,
        request.app.state.settings,
    )


@router.get("/{workspace_id}/objects/{ref}")
def object_detail(
    workspace_id: str,
    ref: str,
    request: Request,
    version_id: str | None = None,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    require_instances(session, workspace_id, principal)
    return get_object(
        session,
        current_version(session, workspace_id, version_id),
        ref,
        request.app.state.settings,
    )


@router.get("/{workspace_id}/objects/{ref}/neighborhood")
def object_graph(
    workspace_id: str,
    ref: str,
    request: Request,
    version_id: str | None = None,
    depth: int = Query(default=1, ge=1, le=3),
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
):
    require_instances(session, workspace_id, principal)
    return object_neighborhood(
        session,
        current_version(session, workspace_id, version_id),
        ref,
        depth,
        request.app.state.settings,
    )


@router.get("/{workspace_id}/version")
def version(
    workspace_id: str,
    version_id: str | None = None,
    session: Session = Depends(get_db),
    _: Principal = Depends(current_principal),
) -> dict:
    return version_summary(current_version(session, workspace_id, version_id))


@router.get("/{workspace_id}/types")
def types(
    workspace_id: str,
    version_id: str | None = None,
    q: str = "",
    kind: str | None = Query(default=None, pattern="^(object_type|link_type)$"),
    session: Session = Depends(get_db),
    _: Principal = Depends(current_principal),
) -> dict:
    return search_types(
        current_version(session, workspace_id, version_id), query=q, kind=kind
    )


@router.get("/{workspace_id}/types/{type_id}")
def type_detail(
    workspace_id: str,
    type_id: str,
    version_id: str | None = None,
    session: Session = Depends(get_db),
    _: Principal = Depends(current_principal),
) -> dict:
    return get_type(current_version(session, workspace_id, version_id), type_id)


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


@router.get("/{workspace_id}/versions/{version_id}/export")
def export_version(
    workspace_id: str,
    version_id: str,
    session: Session = Depends(get_db),
    principal: Principal = Depends(current_principal),
) -> JSONResponse:
    version = session.get(OntologyVersionRecord, version_id)
    if version is None or version.workspace_id != workspace_id:
        raise NotFoundError("没有找到该本体版本")
    return JSONResponse(
        content={
            key: value
            for key, value in version.ossie_json.items()
            if key != "ontology_mappings"
            or can_read_instances(session, workspace_id, principal)
        },
        headers={
            "Content-Disposition": (
                f'attachment; filename="ontofoundry-v{version.version_number}.ossie.json"'
            )
        },
    )
