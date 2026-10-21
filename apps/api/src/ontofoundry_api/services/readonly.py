"""Server-managed read-only database sessions with bounded execution."""

from contextlib import contextmanager

from sqlalchemy import URL, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from ontofoundry_api.services.errors import ServiceError


@contextmanager
def connect_readonly(item, settings, *, timeout_ms=None):
    try:
        password = item.secret_encrypted
        config = item.config_json
        driver = "postgresql+psycopg" if item.kind == "postgresql" else "mysql+pymysql"
        statement_ms = 10000 if timeout_ms is None else int(timeout_ms)
        args = (
            {"connect_timeout": 5, "options": f"-c statement_timeout={statement_ms}"}
            if item.kind == "postgresql"
            else {
                "connect_timeout": 5,
                "read_timeout": 10
                if timeout_ms is None
                else (statement_ms + 999) // 1000 + 2,
                "write_timeout": 5,
            }
        )
        engine = create_engine(
            URL.create(
                driver,
                # Incomplete settings fail as a connection error, not a server crash.
                username=config.get("username"),
                password=password,
                host=config.get("host"),
                port=config.get("port"),
                database=config.get("database"),
            ),
            connect_args=args,
            pool_pre_ping=False,
        )
        try:
            with engine.connect() as connection:
                # Catalog readers pick the right statements for the source.
                connection.info["source_kind"] = item.kind
                if item.kind == "postgresql":
                    connection.execute(text("SET TRANSACTION READ ONLY"))
                elif item.kind == "mysql":
                    connection.execute(text("SET SESSION TRANSACTION READ ONLY"))
                    connection.execute(
                        text(f"SET SESSION MAX_EXECUTION_TIME={statement_ms}")
                    )
                else:
                    connection.execute(
                        text(f"SET query_timeout = {(statement_ms + 999) // 1000}")
                    )
                yield connection
                connection.rollback()
        finally:
            engine.dispose()
    except (SQLAlchemyError, ValueError) as exc:
        timeout = "timeout" in str(exc).lower() or "canceling statement" in str(exc).lower()
        raise ServiceError(
            "只读查询超时"
            if timeout
            else "连接或只读查询失败，请检查网络、字段和服务器配置",
            code="QUERY_TIMEOUT" if timeout else "QUERY_FAILED",
            status_code=504 if timeout else 502,
        ) from exc
