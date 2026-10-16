"""Observed source schemas and their links to a published ontology."""

from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.connections import connect_readonly, get_connection
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import MetadataSnapshotRecord, utc_now
from ontofoundry_api.services.access import require_mappings
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.ontology_query import current_version, snapshot_of
from ontofoundry_api.services.workspaces import get_workspace

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/connections/{connection_id}", tags=["assets"]
)


def schema_diff(before, after):
    changes = []
    old = {table["name"]: table for table in before.get("tables", [])}
    new = {table["name"]: table for table in after.get("tables", [])}
    for name in sorted(old.keys() | new.keys()):
        if name not in old or name not in new:
            changes.append(
                {
                    "table": name,
                    "column": None,
                    "kind": "added" if name in new else "removed",
                    "before": old.get(name),
                    "after": new.get(name),
                }
            )
            continue
        left, right = (
            {c["name"]: c for c in tables[name]["columns"]} for tables in (old, new)
        )
        for column in sorted(left.keys() | right.keys()):
            if left.get(column) != right.get(column):
                changes.append(
                    {
                        "table": name,
                        "column": column,
                        "kind": "added"
                        if column not in left
                        else "removed"
                        if column not in right
                        else "changed",
                        "before": left.get(column),
                        "after": right.get(column),
                    }
                )
    return changes


def retain_schema_changes(previous, latest):
    """Keep unresolved drift across refreshes, reverting only an exact restoration.

    A second refresh proves freshness, not mapping compatibility. Retain the
    earliest observed definition of each changed field until it is restored.
    """
    pending = {(c["table"], c["column"]): c for c in previous}
    for change in latest:
        key = (change["table"], change["column"])
        earlier = pending.get(key)
        combined = (
            {**change, "before": earlier["before"]}
            if earlier and "before" in earlier
            else change
        )
        if "before" in combined and combined["before"] == combined.get("after"):
            pending.pop(key, None)
        else:
            pending[key] = combined
    return list(pending.values())


def read_structure(connection, schema_name):
    inspector = inspect(connection)
    names = sorted(
        set(
            inspector.get_table_names(schema=schema_name)
            + inspector.get_view_names(schema=schema_name)
        )
    )
    if len(names) > 200:
        raise HTTPException(422, "当前 schema 超过 200 张表，请选择更小的 schema")
    tables, started = [], monotonic()
    for name in names:
        if monotonic() - started > 15:
            raise HTTPException(422, "结构读取超过时间预算，上次快照已保留")
        primary = inspector.get_pk_constraint(name, schema=schema_name).get(
            "constrained_columns", []
        )
        try:
            comment = inspector.get_table_comment(name, schema=schema_name).get("text")
        except NotImplementedError:
            comment = None
        tables.append(
            {
                "name": name,
                "schema": schema_name,
                "comment": comment,
                "columns": [
                    {
                        "name": col["name"],
                        "type": str(col["type"]),
                        "primary_key": col["name"] in primary,
                        "nullable": col.get("nullable"),
                        "comment": col.get("comment"),
                    }
                    for col in inspector.get_columns(name, schema=schema_name)
                ],
            }
        )
    return {"tables": tables}


@router.get("/schemas")
def schemas(
    workspace_id: str,
    connection_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_mappings(db, workspace_id, user)
    with connect_readonly(
        get_connection(db, workspace_id, connection_id), request.app.state.settings
    ) as conn:
        return {"items": inspect(conn).get_schema_names()}


def asset_response(db, wid, connection, record, version_id=None, schema_name=""):
    from ontofoundry_api.domain.core import Dataset
    from ontofoundry_api.services.dataset_sources import (
        authorized_dataset_projection,
        resolve_dataset,
    )
    from ontofoundry_api.services.errors import ServiceError

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
            source = resolve_dataset(db, wid, dataset)
        except ServiceError:
            continue
        if source.connection.id == connection.id and (source.schema or "") == (
            schema or source.schema or ""
        ):
            datasets.append(authorized_dataset_projection(db, wid, dataset))
    tables = (
        {t["name"]: t for t in record.snapshot_json.get("tables", [])} if record else {}
    )
    items = [
        {
            **tables.get(name, {"name": name, "schema": schema or None, "columns": []}),
            "missing": name not in tables and bool(record and record.observed_at),
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
    record = db.get(MetadataSnapshotRecord, (connection_id, schema_name))
    return asset_response(db, workspace_id, connection, record, version_id, schema_name)


@router.post("/assets/refresh")
def refresh(
    workspace_id: str,
    connection_id: str,
    request: Request,
    schema_name: str = Query(default="", max_length=240),
    version_id: str | None = None,
    db: Session = Depends(get_db),
    user: Principal = Depends(current_principal),
):
    require_mappings(db, workspace_id, user)
    connection = get_connection(db, workspace_id, connection_id)
    record = db.get(MetadataSnapshotRecord, (connection_id, schema_name))
    if not record:
        record = MetadataSnapshotRecord(
            connection_id=connection_id,
            schema_name=schema_name,
            snapshot_json={},
            changes_json=[],
        )
        db.add(record)
    try:
        with connect_readonly(connection, request.app.state.settings) as conn:
            observed = read_structure(conn, schema_name or None)
        record.changes_json = (
            retain_schema_changes(
                record.changes_json,
                schema_diff(record.snapshot_json, observed),
            )
            if record.observed_at
            else []
        )
        record.snapshot_json, record.observed_at, record.error = observed, utc_now(), None
    except (HTTPException, ServiceError) as exc:
        record.error = str(exc)
    db.commit()
    return asset_response(db, workspace_id, connection, record, version_id, schema_name)
