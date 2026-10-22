"""Observed source schemas and their links to a published ontology."""

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.connections import connect_readonly, get_connection
from ontofoundry_api.contracts.metadata_sync import SyncRequest
from ontofoundry_api.contracts.read_models import TableRowsRead
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import MetadataSnapshotRecord
from ontofoundry_api.services.access import require_instances, require_mappings
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.metadata_catalog import require_schema, visible_schemas
from ontofoundry_api.services.metadata_sync import (
    create_job,
    get_job,
    job_response,
    latest_jobs,
    retry_job,
    run_job,
)
from ontofoundry_api.services.ontology_query import current_version, snapshot_of
from ontofoundry_api.services.workspaces import get_workspace

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/connections/{connection_id}", tags=["assets"]
)



@router.get("/schemas")
def schemas(
    workspace_id: str,
    connection_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_mappings(db, workspace_id, user)
    connection = get_connection(db, workspace_id, connection_id)
    with connect_readonly(connection, request.app.state.settings) as conn:
        return {"items": visible_schemas(connection, conn)}


def asset_response(db, wid, connection, record, version_id=None, schema_name=""):
    from ontofoundry_api.domain.core import Dataset
    from ontofoundry_api.services.dataset_sources import (
        authorized_dataset_projection,
        resolve_dataset,
    )

    space = get_workspace(db, wid)
    version = (
        current_version(db, wid, version_id)
        if version_id or space.current_version_id
        else None
    )
    snapshot = snapshot_of(version) if version else {}
    schema = record.schema_name if record else schema_name
    datasets = []
    for raw in snapshot.get("datasets", []):
        dataset = Dataset.model_validate(raw)
        try:
            # A removed table still lists the datasets that depend on it.
            source = resolve_dataset(db, wid, dataset, registered=False)
        except ServiceError:
            continue
        if dataset.source_kind == "table" and source.connection.id == connection.id and (source.schema or "") == schema:
            datasets.append(authorized_dataset_projection(db, wid, dataset))
    tables = (
        {t["name"]: t for t in record.snapshot_json.get("tables", [])} if record else {}
    )
    items = [
        {
            **tables.get(name, {"name": name, "schema": schema or None, "columns": []}),
            # Keep a recorded missing observation; only dataset-only placeholders are derived.
            "missing": bool(tables[name].get("missing"))
            if name in tables
            else bool(record and record.observed_at),
            "datasets": [d for d in datasets if d["table_name"] == name],
        }
        for name in sorted(set(tables) | {d["table_name"] for d in datasets})
    ]
    return {
        "connection_id": connection.id,
        "version_id": version.id if version else None,
        "items": items,
        "metadata_snapshot_id": f"{connection.id}:{schema}" if record else None,
        "observed_at": record.observed_at if record else None,
        "error": record.error if record else None,
        "changes": record.changes_json if record else [],
        "status": "stale"
        if record and record.error
        else "ready"
        if record and record.observed_at
        else "unobserved",
    }


@router.get("/assets")
def assets(
    workspace_id: str,
    connection_id: str,
    schema_name: str = Query(default="", max_length=240),
    version_id: str | None = None,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_mappings(db, workspace_id, user)
    connection = get_connection(db, workspace_id, connection_id)
    from ontofoundry_api.services.metadata_sync import normalize_schema
    schema_name = normalize_schema(connection, schema_name)
    require_schema(connection, schema_name)
    record = db.get(MetadataSnapshotRecord, (connection_id, schema_name))
    return asset_response(db, workspace_id, connection, record, version_id, schema_name)


@router.get("/assets/rows", response_model=TableRowsRead)
def table_rows(workspace_id: str, connection_id: str, request: Request, table_name: str = Query(min_length=1, max_length=240), schema_name: str = Query(default="", max_length=240), db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_mappings(db, workspace_id, user)
    require_instances(db, workspace_id, user)
    from ontofoundry_api.services.table_preview import preview_table
    return preview_table(db, get_connection(db, workspace_id, connection_id), schema_name, table_name, request.app.state.settings)


@router.delete("/assets/tables")
def delete_table(workspace_id: str, connection_id: str, table_name: str = Query(min_length=1, max_length=240), schema_name: str = Query(default="", max_length=240), db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    """Remove a table from the registered catalog; datasets bound to it then show it as unsynced."""
    from ontofoundry_api.services.metadata_sync import remove_table

    require_mappings(db, workspace_id, user)
    return remove_table(db, get_connection(db, workspace_id, connection_id), schema_name, table_name)


@router.post("/assets/sync-jobs", status_code=202)
def sync_job(workspace_id: str, connection_id: str, body: SyncRequest, request: Request, background: BackgroundTasks, schema_name: str = Query(default="", max_length=240), db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_mappings(db, workspace_id, user)
    connection = get_connection(db, workspace_id, connection_id)
    job = create_job(db, workspace_id, connection, schema_name, body, user.id)
    background.add_task(run_job, request.app.state.session_factory, job.id, request.app.state.settings)
    return job_response(db, job)


@router.get("/assets/sync-jobs")
def jobs(workspace_id: str, connection_id: str, schema_name: str = "", db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_mappings(db, workspace_id, user)
    get_connection(db, workspace_id, connection_id)
    return {"items": [job_response(db, job) for job in latest_jobs(db, connection_id, schema_name)]}


@router.get("/assets/sync-jobs/{job_id}")
def read_job(workspace_id: str, connection_id: str, job_id: str, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_mappings(db, workspace_id, user)
    get_connection(db, workspace_id, connection_id)
    return job_response(db, get_job(db, workspace_id, connection_id, job_id))


@router.post("/assets/sync-jobs/{job_id}/retry", status_code=202)
def retry(workspace_id: str, connection_id: str, job_id: str, request: Request, background: BackgroundTasks, db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    require_mappings(db, workspace_id, user)
    get_connection(db, workspace_id, connection_id)
    job = retry_job(db, get_job(db, workspace_id, connection_id, job_id))
    background.add_task(run_job, request.app.state.session_factory, job.id, request.app.state.settings)
    return job_response(db, job)


@router.post("/assets/refresh", status_code=202)
def refresh(workspace_id: str, connection_id: str, request: Request, background: BackgroundTasks, body: SyncRequest, schema_name: str = Query(default="", max_length=240), db: Session = Depends(get_db), user: Principal = Depends(current_principal)):
    return sync_job(workspace_id, connection_id, body, request, background, schema_name, db, user)
