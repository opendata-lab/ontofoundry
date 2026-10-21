"""Authorized dataset validation and row previews."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.contracts.dataset_sources import DatasetCheck
from ontofoundry_api.database import get_db
from ontofoundry_api.services.access import require_instances, require_mappings
from ontofoundry_api.services.dataset_validation import check_dataset, preview_dataset

router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}/datasets", tags=["datasets"])
tables_router = APIRouter(prefix="/api/v1/workspaces/{workspace_id}", tags=["datasets"])


@tables_router.get("/registered-tables")
def registered_tables(workspace_id: str, session_id: str | None = None, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    """Tables synced in data management, the only tables modeling may use."""
    require_mappings(db, workspace_id, user)
    from ontofoundry_api.services.dataset_sources import registered_table_catalog
    from ontofoundry_api.services.ontology_query import current_version, snapshot_of

    draft = None
    if session_id:
        from ontofoundry_api.db_models import ModelingSessionRecord

        session = db.get(ModelingSessionRecord, session_id)
        if session is not None and session.workspace_id == workspace_id:
            draft = session.draft_json
    if draft is None:
        from ontofoundry_api.services.errors import ServiceError

        try:
            draft = snapshot_of(current_version(db, workspace_id, None))
        except ServiceError:
            draft = None  # An unpublished workspace simply has no datasets yet.
    return {"items": registered_table_catalog(db, workspace_id, draft)}


@router.post("/validate")
def validate(workspace_id: str, body: DatasetCheck, request: Request, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_mappings(db, workspace_id, user)
    return check_dataset(db, workspace_id, body.dataset, request.app.state.settings, probe=True)


@router.post("/preview")
def preview(workspace_id: str, body: DatasetCheck, request: Request, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_mappings(db, workspace_id, user)
    require_instances(db, workspace_id, user)
    return preview_dataset(db, workspace_id, body.dataset, request.app.state.settings)
