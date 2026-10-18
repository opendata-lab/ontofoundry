"""Database neighborhood route; compilation lives in services."""

from datetime import date

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.modeling import get_modeling_session, published_snapshot
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
