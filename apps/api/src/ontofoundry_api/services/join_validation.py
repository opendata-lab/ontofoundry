"""Validate changed executable joins before accepting or saving a draft."""

from pydantic import ValidationError
from sqlalchemy import inspect, select
from sqlalchemy.exc import NoSuchTableError

from ontofoundry_api.db_models import ConnectionRecord, MetadataSnapshotRecord
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.semantic_views import SemanticViews, join_columns
from ontofoundry_api.services.errors import ServiceError


def validate_join_columns(db, workspace_id, before, after, settings):
    try:
        views = SemanticViews(OntologyDraft.model_validate(after))
        old = SemanticViews(OntologyDraft.model_validate(before))
    except ValidationError:
        # Editing permits incomplete domain drafts; existing domain validation
        # owns these errors. Executable mapping writes are fully validated.
        return
    cache = {}

    def known_columns(mapping):
        key = (mapping.connection_alias, mapping.schema_name, mapping.table_name)
        if key in cache:
            return cache[key]
        connection = db.scalar(
            select(ConnectionRecord).where(
                ConnectionRecord.workspace_id == workspace_id,
                ConnectionRecord.name == mapping.connection_alias,
            )
        )
        if connection is None:
            cache[key] = None
            return None
        snapshot = db.get(
            MetadataSnapshotRecord, (connection.id, mapping.schema_name or "")
        )
        if snapshot is not None and (
            snapshot.observed_at or snapshot.snapshot_json.get("tables")
        ):
            table = next(
                (
                    t
                    for t in snapshot.snapshot_json.get("tables", [])
                    if t["name"] == mapping.table_name
                ),
                None,
            )
            columns = {c["name"] for c in table["columns"]} if table else set()
        else:
            from ontofoundry_api.api.connections import connect_readonly

            try:
                with connect_readonly(connection, settings) as sql:
                    columns = {
                        c["name"]
                        for c in inspect(sql).get_columns(
                            mapping.table_name, schema=mapping.schema_name
                        )
                    }
            except NoSuchTableError:
                columns = set()
            except Exception:
                # Offline/unconfigured connections provide no known schema.
                # Never fabricate columns or change the original draft.
                columns = None
        cache[key] = columns
        return columns

    for link in views.draft.link_types:
        if link.source_type_id is None:
            continue
        join = views.join(link.id)
        if join is None:
            continue
        source, target = (
            views.analyze(link.source_type_id).mapping,
            views.analyze(link.target_type_id).mapping,
        )
        previous = old.join(link.id)
        if (
            previous == join
            and old.analyze(link.source_type_id).mapping == source
            and old.analyze(link.target_type_id).mapping == target
        ):
            continue
        source_columns, target_columns = join_columns(join)
        for mapping, columns, side in (
            (
                source,
                source_columns,
                "owner" if link.endpoint_direction == "forward" else "role",
            ),
            (
                target,
                target_columns,
                "role" if link.endpoint_direction == "forward" else "owner",
            ),
        ):
            known = known_columns(mapping)
            if known is None:
                continue
            missing = [column for column in columns if column not in known]
            if missing:
                table = (
                    mapping.schema_name + "." if mapping.schema_name else ""
                ) + mapping.table_name
                raise ServiceError(
                    f"{link.name}：{side} 连接列不存在：{table}." + "、".join(missing),
                    code="JOIN_COLUMN_NOT_FOUND",
                    status_code=422,
                    details={
                        "link_id": str(link.id),
                        "side": side,
                        "table": table,
                        "columns": missing,
                        "connection_alias": mapping.connection_alias,
                    },
                )
