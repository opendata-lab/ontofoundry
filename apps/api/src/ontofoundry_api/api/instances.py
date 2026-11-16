"""Database neighborhood route; compilation lives in services."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal, ontology_principal
from ontofoundry_api.contracts.instances import InstanceBaseline
from ontofoundry_api.database import get_db
from ontofoundry_api.domain.core import Strict
from ontofoundry_api.domain.snapshot import read_snapshot
from ontofoundry_api.services.access import (
    authorization_fingerprint,
    require_instances,
    require_mappings,
    require_read,
)
from ontofoundry_api.services.instance_neighborhood import database_neighborhood
from ontofoundry_api.services.instance_query import (
    ObjectSearch,
    get_object,
    object_neighborhood,
    search_objects,
)
from ontofoundry_api.services.ontology_query import current_version
from ontofoundry_api.services.sessions import get_modeling_session, published_snapshot

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["instances"])


class NeighborhoodRequest(Strict):
    type_id: str
    key: list[dict]
    session_id: str | None = None
    depth: int = Field(default=1, ge=1, le=3)
    snapshot_date: date | None = None


@router.post("/instance-neighborhood")
def neighborhood(
    workspace_id: str,
    body: NeighborhoodRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_read(db, str(workspace_id), user)
    require_instances(db, workspace_id, user)
    require_mappings(db, workspace_id, user)
    raw = (
        get_modeling_session(db, workspace_id, body.session_id).draft_json
        if body.session_id
        else published_snapshot(workspace_id, db)
    )
    return database_neighborhood(
        db, workspace_id, read_snapshot(raw, workspace_id), body, request.app.state.settings
    )


@router.get("/instances", response_model=InstanceBaseline)
def active_instances(
    workspace_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    """Active document instances of the workspace, for views outside a session."""
    require_read(db, str(workspace_id), user)
    from ontofoundry_api.services.instance_store import baseline

    require_instances(db, workspace_id, user)
    return baseline(db, workspace_id, None)


@router.get("/sessions/{session_id}/instances", response_model=InstanceBaseline)
def staged_instances(
    workspace_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_read(db, str(workspace_id), user)
    from ontofoundry_api.services.instance_store import baseline

    require_instances(db, workspace_id, user)
    get_modeling_session(db, workspace_id, session_id)
    result = baseline(db, workspace_id, session_id)
    result["items"] = [i for i in result["items"] if i["state"] == "staged"]
    return result


@router.get("/sessions/{session_id}/instance-baseline", response_model=InstanceBaseline)
def session_instance_baseline(
    workspace_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_read(db, str(workspace_id), user)
    from ontofoundry_api.services.instance_store import baseline

    require_instances(db, workspace_id, user)
    get_modeling_session(db, workspace_id, session_id)
    return baseline(db, workspace_id, session_id)




@router.get("/instances/{kind}/{instance_id}/history")
def instance_history(
    workspace_id: str,
    kind: Literal["material_object", "material_link"],
    instance_id: str,
    session_id: str | None = None,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_read(db, str(workspace_id), user)
    from ontofoundry_api.contracts.instances import InstanceHistoryRead
    from ontofoundry_api.services.instance_store import history

    require_instances(db, workspace_id, user)
    if session_id:
        get_modeling_session(db, workspace_id, session_id)
    rows = history(db, workspace_id, kind, instance_id, session_id)
    return {
        "items": [
            InstanceHistoryRead.model_validate(row, from_attributes=True) for row in rows
        ]
    }


@router.get("/objects")
def objects(
    workspace_id: str,
    request: Request,
    version_id: str | None = None,
    options: ObjectSearch = Depends(),
    session: Session = Depends(get_db),
    principal: Principal = Depends(ontology_principal),
):
    require_read(session, str(workspace_id), principal)
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


@router.get("/objects/{ref}")
def object_detail(
    workspace_id: str,
    ref: str,
    request: Request,
    version_id: str | None = None,
    snapshot_date: str | None = None,
    session: Session = Depends(get_db),
    principal: Principal = Depends(ontology_principal),
):
    require_read(session, str(workspace_id), principal)
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


@router.get("/objects/{ref}/neighborhood")
def object_graph(
    workspace_id: str,
    ref: str,
    request: Request,
    version_id: str | None = None,
    snapshot_date: str | None = None,
    depth: int = Query(default=1, ge=1, le=3),
    session: Session = Depends(get_db),
    principal: Principal = Depends(ontology_principal),
):
    require_read(session, str(workspace_id), principal)
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
