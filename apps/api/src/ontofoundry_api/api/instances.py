"""Database neighborhood route; compilation lives in services."""

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import get_modeling_session, published_snapshot
from ontofoundry_api.contracts.instances import AbandonSessionRead, InstanceBaseline
from ontofoundry_api.database import get_db
from ontofoundry_api.domain.core import Strict
from ontofoundry_api.domain.snapshot import read_snapshot
from ontofoundry_api.services.access import require_instances, require_mappings
from ontofoundry_api.services.instance_neighborhood import database_neighborhood

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
    require_instances(db, workspace_id, user)
    require_mappings(db, workspace_id, user)
    raw = (
        get_modeling_session(db, workspace_id, body.session_id).draft_json
        if body.session_id
        else published_snapshot(workspace_id, db, user)
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
    from ontofoundry_api.api.modeling import require_member
    from ontofoundry_api.services.instance_store import baseline

    require_member(db, workspace_id, user.id)
    require_instances(db, workspace_id, user)
    return baseline(db, workspace_id, None)


@router.get("/sessions/{session_id}/instances", response_model=InstanceBaseline)
def staged_instances(
    workspace_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    from ontofoundry_api.api.modeling import require_member
    from ontofoundry_api.services.instance_store import baseline

    require_member(db, workspace_id, user.id)
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
    from ontofoundry_api.api.modeling import require_member
    from ontofoundry_api.services.instance_store import baseline

    require_member(db, workspace_id, user.id)
    require_instances(db, workspace_id, user)
    get_modeling_session(db, workspace_id, session_id)
    return baseline(db, workspace_id, session_id)


@router.post("/sessions/{session_id}/abandon", response_model=AbandonSessionRead)
def abandon_session(
    workspace_id: str,
    session_id: str,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    from ontofoundry_api.api.modeling import require_member
    from ontofoundry_api.services.instance_store import abandon

    require_member(db, workspace_id, user.id)
    result = abandon(db, workspace_id, session_id, user.id)
    db.commit()
    return result


@router.get("/instances/{kind}/{instance_id}/history")
def instance_history(
    workspace_id: str,
    kind: Literal["material_object", "material_link"],
    instance_id: str,
    session_id: str | None = None,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    from ontofoundry_api.api.modeling import require_member
    from ontofoundry_api.contracts.instances import InstanceHistoryRead
    from ontofoundry_api.services.instance_store import history

    require_member(db, workspace_id, user.id)
    require_instances(db, workspace_id, user)
    if session_id:
        get_modeling_session(db, workspace_id, session_id)
    rows = history(db, workspace_id, kind, instance_id, session_id)
    return {
        "items": [
            InstanceHistoryRead.model_validate(row, from_attributes=True) for row in rows
        ]
    }
