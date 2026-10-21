"""Connection-bound registered dataset relations and safe public projections."""

from dataclasses import dataclass

from sqlalchemy import MetaData, Table, column, text

from ontofoundry_api.db_models import ConnectionRecord, MetadataSnapshotRecord
from ontofoundry_api.services.dataset_sql import (
    dialect_for,
    parse_query,
    physical_tables,
    qualified_query,
)
from ontofoundry_api.services.errors import DatasetSourceError, ServiceError


@dataclass(frozen=True)
class DatasetSource:
    connection: ConnectionRecord
    database: str
    schema: str | None


def resolve_dataset(db, workspace_id, dataset, *, registered=True):
    connection = db.get(ConnectionRecord, dataset.connection_id) if dataset.connection_id else None
    if connection is None or connection.workspace_id != workspace_id:
        raise DatasetSourceError("未绑定连接，请选择本空间的数据连接", code="CONNECTION_UNBOUND")
    if dataset.dialect and dialect_for(dataset.dialect) != dialect_for(connection.kind):
        raise DatasetSourceError("数据集方言与连接引擎不一致", code="DIALECT_MISMATCH")
    config = connection.config_json
    default = config.get("schema_name") or ("public" if connection.kind == "postgresql" else config.get("database"))
    source = DatasetSource(connection, config.get("database", ""), dataset.schema_name or default)
    if registered:
        registered_tables(db, dataset, source)
    return source


def registered_tables(db, dataset, source):
    tree = parse_query(dataset.query_sql, source.connection.kind) if dataset.source_kind == "query" else None
    from ontofoundry_api.services.dataset_sql import TableReference

    refs = physical_tables(tree) if tree is not None else [TableReference(dataset.schema_name, dataset.table_name)]
    result = {}
    for ref in refs:
        schema = ref.schema or source.schema or ""
        config = source.connection.config_json
        allowed = config.get("schemas") or ([source.schema] if source.connection.kind != "postgresql" else None)
        if ref.catalog and ref.catalog != source.database:
            raise DatasetSourceError("数据集不能跨连接或数据库引用", code="SOURCE_NOT_REGISTERED")
        if schema.lower() in {"information_schema", "pg_catalog", "mysql", "sys", "performance_schema"} or (allowed and schema not in allowed):
            raise DatasetSourceError("来源不在连接允许的业务范围", code="SOURCE_NOT_REGISTERED")
        snapshot = db.get(MetadataSnapshotRecord, (source.connection.id, schema))
        table = next((t for t in snapshot.snapshot_json.get("tables", []) if t["name"] == ref.name), None) if snapshot else None
        if table is None:
            raise DatasetSourceError("表未同步，请先同步指定表", code="SOURCE_NOT_REGISTERED", details={"connection_id": source.connection.id, "schema_name": schema, "table_name": ref.name})
        if table.get("missing"):
            raise DatasetSourceError("已登记表当前不可见或不存在", code="SOURCE_REMOVED", details={"schema_name": schema, "table_name": ref.name})
        result[(schema, ref.name)] = table
        if not ref.schema:
            result[("", ref.name)] = table
    return result


def relation_sql(db, workspace_id, dataset, *, source=None):
    source = source or resolve_dataset(db, workspace_id, dataset)
    if dataset.source_kind == "query":
        tree = parse_query(dataset.query_sql, source.connection.kind)
        return qualified_query(tree, source.schema, source.connection.kind)
    from sqlglot import exp

    return exp.select("*").from_(exp.Table(this=exp.to_identifier(dataset.table_name, quoted=True), db=exp.to_identifier(source.schema, quoted=True) if source.schema else None)).sql(dialect=dialect_for(source.connection.kind))


def dataset_relation(db, workspace_id, dataset, connection, alias, *, source=None):
    source = source or resolve_dataset(db, workspace_id, dataset)
    if dataset.source_kind == "table":
        schema = None if connection.dialect.name == "sqlite" else source.schema
        return Table(dataset.table_name, MetaData(), schema=schema, autoload_with=connection).alias(alias)
    from sqlalchemy import Boolean, Date, DateTime, Float, Integer, Numeric, String

    from ontofoundry_api.domain.validation import physical_value_kind

    types = {"boolean": Boolean, "date": Date, "datetime": DateTime, "float": Float, "integer": Integer, "decimal": Numeric, "string": String}
    sql = relation_sql(db, workspace_id, dataset, source=source)
    # Escape SQLAlchemy bind syntax inside user SQL; the SQL has no parameters.
    return text(sql.replace(":", r"\:")).columns(*[column(c.name, types.get(physical_value_kind(c.physical_type), String)()) for c in dataset.columns or []]).subquery(alias)


def authorized_dataset_projection(db, workspace_id, dataset, *, allowed=True):
    if not allowed:
        raise ServiceError("没有映射读取授权", code="MAPPINGS_FORBIDDEN", status_code=403)
    result = {**dataset.model_dump(mode="json", exclude={"connection_id"}), "binding_status": "unbound"}
    try:
        source = resolve_dataset(db, workspace_id, dataset)
    except ServiceError as exc:
        result["diagnostic"] = {"code": exc.code, "message": exc.message}
        return result
    result.update(database=source.database, schema=source.schema, binding_status="bound")
    return result


def dataset_references(draft, dataset_id):
    from ontofoundry_api.domain.core import MappingTableJoin
    from ontofoundry_api.services.metric_query import dataset_for

    identity = str(dataset_id)
    objects = {str(o.id): o for o in draft.object_types}
    object_ids = {str(m.type_id) for m in draft.mappings if any(str(s.dataset_id) == identity for s in m.sources)}
    links = [link for link in draft.link_types if isinstance(link.data_join, MappingTableJoin) and str(link.data_join.dataset_id) == identity]
    inherited = {str(lid) for m in draft.mappings for lid, j in m.inherited_link_bindings.items() if isinstance(j, MappingTableJoin) and str(j.dataset_id) == identity}
    links = {str(link.id): link for link in [*links, *[link for link in draft.link_types if str(link.id) in inherited]]}
    def item(kind, element):
        return {"kind": kind, "id": str(element.id), "name": element.name, "display_name": element.display_name}
    metrics = []
    for m in draft.metrics:
        try:
            if str(dataset_for(draft, m).id) == identity:
                metrics.append(item("metric", m))
        except (KeyError, StopIteration):
            continue
    return {"object_mappings": [item("object_type", objects[i]) for i in sorted(object_ids) if i in objects], "relationship_mappings": [item("link_type", link) for link in links.values()], "metrics": metrics}


def registered_table_catalog(db, workspace_id, draft=None):
    """Every registered (synced, present) table in the workspace, with dataset usage."""
    from sqlalchemy import select

    connections = {
        c.id: c for c in db.scalars(select(ConnectionRecord).where(ConnectionRecord.workspace_id == workspace_id))
    }
    used = {}
    for dataset in (draft or {}).get("datasets", []):
        if dataset.get("source_kind", "table") == "table" and dataset.get("connection_id"):
            key = (dataset["connection_id"], dataset.get("schema_name") or "", dataset.get("table_name"))
            used.setdefault(key, []).append({"id": dataset["id"], "name": dataset["name"], "display_name": dataset.get("display_name")})
    items = []
    snapshots = db.scalars(select(MetadataSnapshotRecord).where(MetadataSnapshotRecord.connection_id.in_(list(connections)))) if connections else []
    for snapshot in snapshots:
        connection = connections[snapshot.connection_id]
        for table in snapshot.snapshot_json.get("tables", []):
            if table.get("missing"):
                continue
            key = (connection.id, snapshot.schema_name, table["name"])
            items.append({
                "connection_id": connection.id,
                "connection_name": connection.name,
                "schema_name": snapshot.schema_name,
                "table_name": table["name"],
                "kind": table.get("kind", "table"),
                "comment": table.get("comment") or "",
                "column_count": len(table.get("columns", [])),
                "datasets": used.get(key, []) + used.get((connection.id, "", table["name"]), []),
            })
    items.sort(key=lambda i: (i["connection_name"], i["schema_name"], i["table_name"]))
    return items


def linked_table_details(db, workspace_id, linked):
    """Validate linked tables and return their registered structure, in link order."""
    details, seen = [], set()
    for entry in linked:
        key = (entry["connection_id"], entry.get("schema_name") or "", entry["table_name"])
        if key in seen:
            continue
        seen.add(key)
        connection = db.get(ConnectionRecord, key[0])
        if connection is None or connection.workspace_id != workspace_id:
            raise DatasetSourceError("关联的数据表不属于当前空间的数据连接", code="CONNECTION_UNBOUND")
        snapshot = db.get(MetadataSnapshotRecord, (key[0], key[1]))
        table = next((t for t in (snapshot.snapshot_json.get("tables", []) if snapshot else []) if t["name"] == key[2]), None)
        if table is None or table.get("missing"):
            raise DatasetSourceError("关联的数据表尚未同步或已不存在，请先在数据管理同步", code="SOURCE_NOT_REGISTERED", details={"schema_name": key[1], "table_name": key[2]})
        details.append({"connection": connection, "schema_name": key[1], "table": table})
    return details
