"""Bounded row preview of one synced source table."""

from sqlglot import exp

from ontofoundry_api.db_models import MetadataSnapshotRecord
from ontofoundry_api.services.dataset_sql import dialect_for
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.metadata_catalog import require_schema
from ontofoundry_api.services.metadata_sync import normalize_schema
from ontofoundry_api.services.metric_query import scalar
from ontofoundry_api.services.readonly import connect_readonly

PREVIEW_LIMIT = 100


def preview_value(value):
    # Binary values are shown as hex; JSON cannot carry raw bytes.
    if isinstance(value, (bytes, bytearray, memoryview)):
        return "0x" + bytes(value).hex()
    return scalar(value)


def preview_table(db, connection, schema_name, table_name, settings):
    schema = normalize_schema(connection, schema_name)
    require_schema(connection, schema)
    record = db.get(MetadataSnapshotRecord, (connection.id, schema))
    tables = record.snapshot_json.get("tables", []) if record else []
    table = next((t for t in tables if t["name"] == table_name and not t.get("missing")), None)
    # Only synced tables are readable, so the identifiers come from the catalog.
    if table is None:
        raise ServiceError("表未同步或已不可见，请先同步数据表", code="TABLE_NOT_REGISTERED", status_code=404)
    query = exp.select("*").from_(
        exp.Table(
            this=exp.to_identifier(table_name, quoted=True),
            db=exp.to_identifier(schema, quoted=True) if schema else None,
        )
    ).limit(PREVIEW_LIMIT)
    with connect_readonly(connection, settings, timeout_ms=5000) as conn:
        result = conn.exec_driver_sql(query.sql(dialect=dialect_for(connection.kind)))
        columns = list(result.keys())
        rows = [{k: preview_value(v) for k, v in row.items()} for row in result.mappings()]
    return {"columns": columns, "items": rows, "limit": PREVIEW_LIMIT}
