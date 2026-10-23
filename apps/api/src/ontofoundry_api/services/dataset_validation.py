"""Derived validation, LIMIT 0 probing and bounded preview for dataset sources."""

from sqlglot import exp

from ontofoundry_api.domain.core import DatasetColumn
from ontofoundry_api.services.dataset_sources import (
    registered_tables,
    relation_sql,
    resolve_dataset,
)
from ontofoundry_api.services.dataset_sql import (
    dialect_for,
    parse_query,
    physical_tables,
)
from ontofoundry_api.services.errors import DatasetSourceError, ServiceError
from ontofoundry_api.services.readonly import connect_readonly

TYPE_CODES = {
    "postgresql": {16: "boolean", 20: "bigint", 21: "smallint", 23: "integer", 25: "text", 700: "float", 701: "double", 1043: "varchar", 1082: "date", 1083: "time", 1114: "timestamp", 1184: "timestamptz", 1700: "decimal"},
    "mysql": {0: "decimal", 1: "tinyint", 2: "smallint", 3: "integer", 4: "float", 5: "double", 7: "timestamp", 8: "bigint", 9: "integer", 10: "date", 11: "time", 12: "datetime", 15: "varchar", 246: "decimal", 252: "text", 253: "varchar", 254: "char"},
}


def check_dataset(db, workspace_id, dataset, settings=None, *, probe=False):
    result = {"diagnostics": [], "columns": None, "referenced_tables": []}
    try:
        source = resolve_dataset(db, workspace_id, dataset, registered=False)
        tables = registered_tables(db, dataset, source)
        if dataset.source_kind == "query":
            tree = parse_query(dataset.query_sql, source.connection.kind)
            result["referenced_tables"] = [{"schema_name": r.schema or source.schema, "table_name": r.name} for r in physical_tables(tree)]
        else:
            result["referenced_tables"] = [{"schema_name": source.schema, "table_name": dataset.table_name}]
            columns = next(iter(tables.values()))["columns"]
            result["columns"] = [{"name": c["name"], "physical_type": c.get("type"), "comment": c.get("comment") or ""} for c in columns]
        if probe:
            sql = relation_sql(db, workspace_id, dataset, source=source)
            query = exp.select("*").from_(exp.Subquery(this=parse_query(sql, source.connection.kind), alias=exp.TableAlias(this=exp.to_identifier("dataset_probe")))).limit(0)
            with connect_readonly(source.connection, settings, timeout_ms=5000) as conn:
                cursor = conn.exec_driver_sql(query.sql(dialect=dialect_for(source.connection.kind)))
                description = cursor.cursor.description
                names = list(cursor.keys())
                if len(names) != len(set(names)):
                    raise DatasetSourceError("输出列重名，请为 SQL 输出指定唯一别名", code="COLUMN_ALIAS_REQUIRED")
                known = {c["name"]: c for c in result["columns"] or []}
                types = TYPE_CODES.get(source.connection.kind, TYPE_CODES["mysql"])
                result["columns"] = [{"name": name, "physical_type": types.get(description[i][1]) or known.get(name, {}).get("physical_type"), "comment": known.get(name, {}).get("comment", "")} for i, name in enumerate(names)]
        if dataset.snapshot_date_column and result["columns"] is not None:
            from ontofoundry_api.domain.validation import physical_value_kind
            snap = next((c for c in result["columns"] if c["name"] == dataset.snapshot_date_column), None)
            if not snap or physical_value_kind(snap["physical_type"]) not in {None, "date", "datetime", "string", "integer"}:
                raise DatasetSourceError("快照日期列不存在，或不是日期类、可按日期排序的文本/整数列", code="COLUMN_NOT_FOUND")
    except ServiceError as exc:
        result["diagnostics"].append({"code": exc.code, "severity": "error", "path": "/connection_id" if exc.code == "CONNECTION_UNBOUND" else "/query_sql" if dataset.source_kind == "query" else "/table_name", "message": exc.message, "details": exc.details})
    result["valid"] = not any(d["severity"] == "error" for d in result["diagnostics"])
    return result


def enforce_dataset(db, workspace_id, dataset, settings):
    checked = check_dataset(db, workspace_id, dataset, settings, probe=dataset.source_kind == "query")
    if not checked["valid"]:
        raise DatasetSourceError("数据集来源未就绪", details={"diagnostics": checked["diagnostics"]})
    return dataset.model_copy(update={"columns": [DatasetColumn.model_validate(c) for c in checked["columns"]] if checked["columns"] is not None else dataset.columns})


def preview_dataset(db, workspace_id, dataset, settings):
    checked = check_dataset(db, workspace_id, dataset, settings, probe=True)
    if not checked["valid"]:
        raise DatasetSourceError("来源校验失败，无法预览", details=checked)
    source = resolve_dataset(db, workspace_id, dataset)
    query = exp.select("*").from_(exp.Subquery(this=parse_query(relation_sql(db, workspace_id, dataset, source=source), source.connection.kind), alias=exp.TableAlias(this=exp.to_identifier("dataset_preview")))).limit(20)
    from ontofoundry_api.services.metric_query import scalar
    with connect_readonly(source.connection, settings, timeout_ms=5000) as conn:
        rows = list(conn.exec_driver_sql(query.sql(dialect=dialect_for(source.connection.kind))).mappings())
    return {"columns": checked["columns"], "items": [{k: scalar(v) for k, v in row.items()} for row in rows], "limit": 20, "diagnostics": checked["diagnostics"]}
