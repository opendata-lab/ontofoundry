"""Visible source schemas and table listings, constrained by the connection configuration."""

from sqlalchemy import inspect, text

from ontofoundry_api.services.errors import ServiceError

# Doris lists its own system databases next to business ones.
DORIS_SYSTEM_SCHEMAS = {"information_schema", "mysql", "performance_schema", "sys", "__internal_schema"}


def is_doris(source):
    return getattr(source, "info", {}).get("source_kind") == "doris"


def schema_allowed(connection, schema):
    """Whether the connection's configuration lets the platform read this schema.

    An empty schema means the connection's default one.
    """
    if not schema:
        return True
    config = connection.config_json
    if connection.kind == "mysql" and schema != config.get("database"):
        return False
    if connection.kind == "doris" and schema in DORIS_SYSTEM_SCHEMAS:
        return False
    allowed = config.get("schemas")
    return not allowed or schema in allowed


def require_schema(connection, schema):
    if not schema_allowed(connection, schema):
        raise ServiceError("该库不在连接允许的范围内", code="SCHEMA_NOT_ALLOWED", status_code=403)


def visible_schemas(connection, source):
    names = inspect(source).get_schema_names()
    return sorted({name for name in names if schema_allowed(connection, name)})


def list_tables(source, schema):
    """Table and view names of one schema.

    Doris is read through information_schema with an explicit schema filter
    instead of the MySQL dialect's SHOW statements.
    """
    if is_doris(source):
        rows = source.execute(
            text("SELECT TABLE_NAME FROM information_schema.tables WHERE TABLE_SCHEMA = :schema"),
            {"schema": schema},
        )
        return sorted({row[0] for row in rows})
    inspector = inspect(source)
    return sorted(set(inspector.get_table_names(schema=schema) + inspector.get_view_names(schema=schema)))


def read_doris_table(source, schema, name, observed_at):
    params = {"schema": schema, "name": name}
    table = source.execute(
        text("SELECT TABLE_TYPE, TABLE_COMMENT FROM information_schema.tables WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :name"),
        params,
    ).first()
    if table is None:
        return {"name": name, "schema": schema, "missing": True, "observed_at": observed_at}
    columns = source.execute(
        text(
            "SELECT COLUMN_NAME, COLUMN_TYPE, DATA_TYPE, IS_NULLABLE, COLUMN_COMMENT, COLUMN_KEY FROM information_schema.columns "
            "WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = :name ORDER BY ORDINAL_POSITION"
        ),
        params,
    ).all()
    types = {c[0]: c[1] or c[2] for c in columns}
    # Some Doris versions leave both type columns empty; SHOW FULL COLUMNS still has them.
    if not all(types.values()):
        quote = lambda value: "`" + value.replace("`", "``") + "`"  # noqa: E731
        try:
            shown = source.exec_driver_sql(f"SHOW FULL COLUMNS FROM {quote(schema)}.{quote(name)}").mappings().all()
            fallback = {str(row.get("Field") or row.get("field")): row.get("Type") or row.get("type") for row in shown}
            types = {key: value or fallback.get(key) or "" for key, value in types.items()}
        except Exception:
            pass
    primary = [c[0] for c in columns if (c[5] or "").upper() == "PRI"]
    return {
        "name": name,
        "schema": schema,
        "kind": "view" if table[0] == "VIEW" else "table",
        "comment": table[1] or None,
        "primary_key": primary,
        "foreign_keys": [],
        "missing": False,
        "observed_at": observed_at,
        "columns": [
            {"name": c[0], "type": types[c[0]], "primary_key": c[0] in primary, "nullable": c[3] == "YES", "comment": c[4] or None}
            for c in columns
        ],
    }
