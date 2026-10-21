"""Visible source schemas, constrained by the connection configuration."""

from sqlalchemy import inspect


def visible_schemas(connection, source):
    config = connection.config_json
    names = inspect(source).get_schema_names()
    allowed = config.get("schemas")
    if connection.kind == "mysql":
        database = config.get("database")
        names = [name for name in names if name == database]
    if allowed:
        names = [name for name in names if name in allowed]
    return sorted(set(names))
