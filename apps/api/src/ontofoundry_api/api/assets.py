"""Observed source schemas and their links to a published ontology."""

from datetime import UTC
from time import monotonic

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from ontofoundry_api.api.auth import Principal, current_principal
from ontofoundry_api.api.connections import connect_readonly, get_connection
from ontofoundry_api.api.modeling import require_member
from ontofoundry_api.database import get_db
from ontofoundry_api.db_models import MetadataSnapshotRecord, utc_now
from ontofoundry_api.services.ontology_query import current_version
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
    require_member(db, workspace_id, user.id)
    with connect_readonly(
        get_connection(db, workspace_id, connection_id), request.app.state.settings
    ) as conn:
        return {"items": inspect(conn).get_schema_names()}


def asset_response(db, wid, connection, record, version_id=None, schema_name=""):
    space = get_workspace(db, wid)
    version = (
        current_version(db, wid, version_id)
        if version_id or space.current_version_id
        else None
    )
    snapshot = version.snapshot_json if version else {}
    types = {t["id"]: t for t in snapshot.get("object_types", [])}
    schema = record.schema_name if record else schema_name
    mappings = [
        m
        for m in snapshot.get("mappings", [])
        if m["connection_alias"] == connection.name
        and (m.get("schema_name") or "") == schema
    ]
    tables = record.snapshot_json.get("tables", []) if record else []
    by_name = {table["name"]: table for table in tables}
    items = []
    for name in sorted(by_name.keys() | {m["table_name"] for m in mappings}):
        table = by_name.get(name)
        columns = {c["name"] for c in table["columns"]} if table else set()
        bound = []
        for mapping in mappings:
            if mapping["table_name"] != name:
                continue
            used_columns = {mapping["key_column"]} | set(mapping["fields"].values())
            for relation in snapshot.get("link_types", []):
                join = relation.get("data_join")
                if not join:
                    continue
                if relation["source_type_id"] == mapping["type_id"]:
                    used_columns.add(join["source_column"])
                if relation["target_type_id"] == mapping["type_id"]:
                    used_columns.add(join["target_column"])
            missing = sorted(used_columns - columns)
            changed = [
                change
                for change in (record.changes_json if record else [])
                if change["table"] == name
                and (change["column"] is None or change["column"] in used_columns)
            ]
            bound.append(
                {
                    "id": mapping["id"],
                    "type_id": mapping["type_id"],
                    "name": types.get(mapping["type_id"], {}).get("name", "未知对象"),
                    "fields": mapping["fields"],
                    "key_column": mapping["key_column"],
                    "missing_columns": missing,
                    "changed_columns": changed,
                    "status": "unverified"
                    if not record or not record.observed_at
                    else "invalid"
                    if missing
                    else "review"
                    if changed
                    else "valid",
                }
            )
        items.append(
            {
                **(
                    table
                    or {
                        "name": name,
                        "schema": schema or None,
                        "columns": [],
                        "comment": None,
                    }
                ),
                "missing": table is None and bool(record and record.observed_at),
                "mappings": bound,
            }
        )
    return {
        "connection_id": connection.id,
        "version_id": version.id if version else None,
        "items": items,
        "observed_at": (
            record.observed_at
            if record.observed_at.tzinfo
            else record.observed_at.replace(tzinfo=UTC)
        )
        if record and record.observed_at
        else None,
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
    require_member(db, workspace_id, user.id)
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
    require_member(db, workspace_id, user.id)
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
    except HTTPException as exc:
        record.error = str(exc.detail)
    db.commit()
    return asset_response(db, workspace_id, connection, record, version_id, schema_name)
