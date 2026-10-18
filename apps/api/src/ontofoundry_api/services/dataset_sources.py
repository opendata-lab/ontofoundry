"""Resolve physical datasets from server-managed connections without aliases."""

from dataclasses import dataclass

from sqlalchemy import select

from ontofoundry_api.db_models import ConnectionRecord, MetadataSnapshotRecord
from ontofoundry_api.services.errors import ServiceError


@dataclass(frozen=True)
class DatasetSource:
    connection: ConnectionRecord
    database: str
    schema: str | None


def resolve_dataset(db, workspace_id, dataset):
    connections = db.scalars(
        select(ConnectionRecord).where(ConnectionRecord.workspace_id == workspace_id)
    ).all()
    dialect = (dataset.dialect or "").lower()
    kinds = {
        "postgres": "postgresql",
        "postgresql": "postgresql",
        "mysql": "mysql",
        "doris": "doris",
    }
    selected = []
    for connection in connections:
        if dialect and connection.kind != kinds.get(dialect, dialect):
            continue
        config = connection.config_json
        default = config.get("schema_name") or (
            "public" if connection.kind == "postgresql" else config.get("database")
        )
        schema = dataset.schema_name or default
        if dataset.schema_name:
            allowed = config.get("schemas") or [default]
            if (
                config.get("schemas") or connection.kind != "postgresql"
            ) and dataset.schema_name not in allowed:
                continue
        selected.append(DatasetSource(connection, config["database"], schema))
    if not selected:
        raise ServiceError(
            "数据集尚无可用来源连接", code="BINDING_NOT_READY", status_code=422
        )
    if len(selected) != 1:
        raise ServiceError(
            "数据集匹配多个连接，需明确服务端来源配置",
            code="SOURCE_AMBIGUOUS",
            status_code=422,
        )
    return selected[0]


def authorized_dataset_projection(db, workspace_id, dataset, *, allowed=True):
    if not allowed:
        raise ServiceError("没有映射读取授权", code="MAPPINGS_FORBIDDEN", status_code=403)
    result = {**dataset.model_dump(mode="json"), "binding_status": "unbound"}
    try:
        source = resolve_dataset(db, workspace_id, dataset)
    except ServiceError:
        return result
    result.update(database=source.database, schema=source.schema, binding_status="bound")
    snapshot = db.get(MetadataSnapshotRecord, (source.connection.id, source.schema or ""))
    if snapshot:
        result.update(
            metadata_snapshot_id=f"{source.connection.id}:{source.schema or ''}",
            observed_at=snapshot.observed_at,
        )
        if snapshot.error:
            result["binding_status"] = "metadata_stale"
    return result
