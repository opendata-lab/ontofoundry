"""Persistent batch progress with in-process execution and explicit restart retry."""

from copy import deepcopy
from threading import Lock
from time import monotonic
from uuid import uuid4

from sqlalchemy import inspect, select, update

from ontofoundry_api.db_models import (
    ConnectionRecord,
    MetadataSnapshotRecord,
    MetadataSyncBatchRecord,
    MetadataSyncJobRecord,
    utc_now,
)
from ontofoundry_api.services.errors import MetadataSyncError, ServiceError
from ontofoundry_api.services.metadata_catalog import (
    is_doris,
    list_tables,
    read_doris_table,
    require_schema,
    require_source_schema,
)
from ontofoundry_api.services.readonly import connect_readonly

_LOCKS = {}
_LOCKS_GUARD = Lock()
ACTIVE = {"queued", "running"}

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


def merge_structure(previous, observed, tables):
    """Replace only the selected tables, keeping the rest of the snapshot."""
    if tables is None:
        return observed
    selected = set(tables)
    kept = [
        table for table in previous.get("tables", []) if table["name"] not in selected
    ]
    return {"tables": sorted(kept + observed["tables"], key=lambda t: t["name"])}


def previous_selection(previous, tables):
    if tables is None:
        return previous
    selected = set(tables)
    return {
        "tables": [
            table for table in previous.get("tables", []) if table["name"] in selected
        ]
    }



def read_table(connection, schema_name, name, kind=None):
    require_source_schema(connection, schema_name)
    if is_doris(connection):
        return read_doris_table(connection, schema_name, name, utc_now().isoformat())
    inspector = inspect(connection)
    if not inspector.has_table(name, schema=schema_name):
        return {"name": name, "schema": schema_name, "missing": True, "observed_at": utc_now().isoformat()}
    primary = inspector.get_pk_constraint(name, schema=schema_name).get("constrained_columns", []) or []
    try:
        comment = inspector.get_table_comment(name, schema=schema_name).get("text")
    except NotImplementedError:
        comment = None
    try:
        foreign = inspector.get_foreign_keys(name, schema=schema_name)
    except NotImplementedError:
        foreign = []
    if kind is None:
        kind = "view" if name in inspector.get_view_names(schema=schema_name) else "table"
    return {"name": name, "schema": schema_name, "kind": kind, "comment": comment, "primary_key": primary, "foreign_keys": foreign, "missing": False, "observed_at": utc_now().isoformat(), "columns": [{"name": c["name"], "type": str(c["type"]), "primary_key": c["name"] in primary, "nullable": c.get("nullable"), "comment": c.get("comment")} for c in inspector.get_columns(name, schema=schema_name)]}


def read_structure(connection, schema_name, tables=None):
    names = tables if tables is not None else list_tables(connection, schema_name)
    return {"tables": [read_table(connection, schema_name, name) for name in names]}


def normalize_schema(connection, schema):
    # MySQL and Doris have no default library: callers name one (see require_schema).
    if schema:
        return schema
    return (connection.config_json.get("schema_name") or "public") if connection.kind == "postgresql" else ""


def create_job(db, workspace_id, connection, schema_name, body, user_id):
    schema = normalize_schema(connection, schema_name)
    require_schema(connection, schema)
    active = db.scalar(select(MetadataSyncJobRecord).where(MetadataSyncJobRecord.connection_id == connection.id, MetadataSyncJobRecord.schema_name == schema, MetadataSyncJobRecord.state.in_(ACTIVE)))
    if active:
        raise MetadataSyncError("该连接和 Schema 已有同步任务", code="SYNC_ALREADY_RUNNING", details={"job_id": active.id})
    job = MetadataSyncJobRecord(id=str(uuid4()), workspace_id=workspace_id, connection_id=connection.id, schema_name=schema, scope=body.scope, selected_json=sorted(set(body.tables)), state="queued", created_by=user_id)
    db.add(job)
    db.commit()
    return job


def get_job(db, workspace_id, connection_id, job_id):
    job = db.get(MetadataSyncJobRecord, job_id)
    if not job or job.workspace_id != workspace_id or job.connection_id != connection_id:
        raise MetadataSyncError("同步任务不存在", code="SYNC_JOB_NOT_FOUND", status_code=404)
    return job


def batches(db, job):
    return list(db.scalars(select(MetadataSyncBatchRecord).where(MetadataSyncBatchRecord.job_id == job.id).order_by(MetadataSyncBatchRecord.ordinal)))


def job_response(db, job):
    items = []
    for batch in batches(db, job):
        items.append({k: getattr(batch, k) for k in ("id", "ordinal", "state", "attempt", "duration_ms", "error", "started_at", "finished_at")} | {"tables": batch.table_names_json, "results": batch.results_json, "history": batch.history_json})
    results = [r for b in items for r in b["results"]]
    return {**{k: getattr(job, k) for k in ("id", "connection_id", "schema_name", "scope", "state", "created_at", "started_at", "finished_at", "duration_ms", "error")}, "total": len(job.inventory_json) if job.inventory_json is not None else None, "processed": len(results), "available": sum(r["state"] == "succeeded" for r in results), "failed": sum(r["state"] == "failed" for r in results), "batches": items}


def retry_job(db, job):
    if job.state in ACTIVE:
        raise MetadataSyncError("任务仍在执行", code="SYNC_ALREADY_RUNNING")
    for batch in batches(db, job):
        if batch.state != "succeeded":
            batch.history_json = [*batch.history_json, {"attempt": batch.attempt, "duration_ms": batch.duration_ms, "error": batch.error, "results": batch.results_json}]
            batch.state, batch.error = "queued", None
    job.state, job.error, job.finished_at = "queued", None, None
    db.commit()
    return job


def interrupt_jobs(db):
    db.execute(update(MetadataSyncJobRecord).where(MetadataSyncJobRecord.state.in_(ACTIVE)).values(state="interrupted", error="服务已重启，任务已中断，可重试", finished_at=utc_now()))
    db.execute(update(MetadataSyncBatchRecord).where(MetadataSyncBatchRecord.state.in_(ACTIVE)).values(state="interrupted", error="服务已重启，批次已中断，可重试", finished_at=utc_now()))
    db.commit()


def save_observation(db, job, table):
    if table.get("schema") != job.schema_name:
        raise MetadataSyncError("读取结果的库与同步任务不一致", code="SYNC_SCHEMA_MISMATCH")
    record = db.get(MetadataSnapshotRecord, (job.connection_id, job.schema_name))
    if not record:
        record = MetadataSnapshotRecord(connection_id=job.connection_id, schema_name=job.schema_name, snapshot_json={"tables": []}, changes_json=[])
        db.add(record)
    old = deepcopy(record.snapshot_json)
    previous = next((t for t in old.get("tables", []) if t["name"] == table["name"]), None)
    if table.get("missing"):
        if previous is None:
            return
        table = {**previous, **table}
    merged = merge_structure(old, {"tables": [table]}, [table["name"]])
    record.changes_json = retain_schema_changes(record.changes_json or [], schema_diff(old, merged)) if record.observed_at else []
    record.snapshot_json, record.observed_at, record.error = merged, utc_now(), None


def run_job(factory, job_id, settings):
    with factory() as db:
        job = db.get(MetadataSyncJobRecord, job_id)
        if not job or job.state != "queued":
            return
        key = (job.connection_id, job.schema_name)
    with _LOCKS_GUARD:
        lock = _LOCKS.setdefault(key, Lock())
    with lock, factory() as db:
        job = db.get(MetadataSyncJobRecord, job_id)
        if not job or job.state != "queued":
            return
        started = monotonic()
        try:
            connection = db.get(ConnectionRecord, job.connection_id)
            if connection is None or connection.workspace_id != job.workspace_id:
                raise MetadataSyncError("连接已删除", code="CONNECTION_UNBOUND")
            # Recheck persisted jobs, including retries after configuration changes.
            require_schema(connection, job.schema_name)
            job.state, job.started_at = "running", utc_now()
            db.commit()
            # Only a first run of a full job lists the schema; a retry just re-reads
            # its failed tables and never decides that a table is gone.
            fresh = job.inventory_json is None
            if fresh:
                if job.scope == "selected":
                    names = job.selected_json
                else:
                    with connect_readonly(connection, settings, timeout_ms=15000) as conn:
                        names = list_tables(conn, job.schema_name)
                job.inventory_json = names
                for ordinal, offset in enumerate(range(0, len(names), 20)):
                    db.add(MetadataSyncBatchRecord(id=str(uuid4()), job_id=job.id, ordinal=ordinal, table_names_json=names[offset:offset + 20], state="queued", results_json=[], history_json=[]))
                db.commit()
            for batch in batches(db, job):
                if batch.state == "succeeded":
                    continue
                batch.state, batch.started_at = "running", utc_now()
                batch.attempt += 1
                batch_start = monotonic()
                results = {r["table_name"]: r for r in batch.results_json if r["state"] == "succeeded"}
                db.commit()
                pending = [name for name in batch.table_names_json if name not in results]
                try:
                    # One source connection per batch, not per table.
                    with connect_readonly(connection, settings, timeout_ms=15000) as conn:
                        for name in pending:
                            # End the platform read transaction before waiting on a source.
                            db.commit()
                            try:
                                observed = read_table(conn, job.schema_name, name)
                                save_observation(db, job, observed)
                                results[name] = {"table_name": name, "state": "missing" if observed.get("missing") else "succeeded"}
                            except Exception as exc:
                                db.rollback()
                                message = exc.message if isinstance(exc, ServiceError) else "读取表结构失败，请检查连接和权限"
                                results[name] = {"table_name": name, "state": "failed", "error": message}
                            batch.results_json = list(results.values())
                            db.commit()
                except Exception as exc:
                    db.rollback()
                    message = exc.message if isinstance(exc, ServiceError) else "连接数据源失败，请检查连接和权限"
                    for name in pending:
                        results.setdefault(name, {"table_name": name, "state": "failed", "error": message})
                    batch.results_json = list(results.values())
                    db.commit()
                batch.state = "failed" if any(r["state"] == "failed" for r in results.values()) else "succeeded"
                batch.error = "部分表同步失败，可重试" if batch.state == "failed" else None
                batch.finished_at, batch.duration_ms = utc_now(), int((monotonic() - batch_start) * 1000)
                db.commit()
            if job.scope == "all" and fresh:
                record = db.get(MetadataSnapshotRecord, (job.connection_id, job.schema_name))
                for table in list(record.snapshot_json.get("tables", [])) if record else []:
                    if table["name"] not in job.inventory_json:
                        save_observation(db, job, {"name": table["name"], "schema": job.schema_name, "missing": True, "observed_at": utc_now().isoformat()})
            job.state = "partial_failed" if any(b.state == "failed" for b in batches(db, job)) else "succeeded"
        except Exception as exc:
            db.rollback()
            job = db.get(MetadataSyncJobRecord, job_id)
            job.state = "failed"
            job.error = exc.message if isinstance(exc, ServiceError) else "同步失败，请检查连接和权限后重试"
        job.finished_at, job.duration_ms = utc_now(), job.duration_ms + int((monotonic() - started) * 1000)
        db.commit()


def remove_table(db, connection, schema_name, table_name):
    """Unregister one synced table; the source database is untouched."""
    schema = normalize_schema(connection, schema_name)
    require_schema(connection, schema)
    if db.scalar(select(MetadataSyncJobRecord).where(MetadataSyncJobRecord.connection_id == connection.id, MetadataSyncJobRecord.schema_name == schema, MetadataSyncJobRecord.state.in_(ACTIVE))):
        raise ServiceError("该库正在同步，请等同步结束后再删除", code="SYNC_RUNNING", status_code=409)
    record = db.get(MetadataSnapshotRecord, (connection.id, schema))
    tables = record.snapshot_json.get("tables", []) if record else []
    if not any(t["name"] == table_name for t in tables):
        raise ServiceError("数据表未登记", code="TABLE_NOT_REGISTERED", status_code=404)
    # Reassign so SQLAlchemy notices the JSON change.
    record.snapshot_json = {**record.snapshot_json, "tables": [t for t in tables if t["name"] != table_name]}
    record.changes_json = [c for c in record.changes_json or [] if c.get("table") != table_name]
    db.commit()
    return {"schema_name": schema, "table_name": table_name}
