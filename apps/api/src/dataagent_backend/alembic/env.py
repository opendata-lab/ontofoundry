from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from dataagent_backend.config import get_settings
from dataagent_backend.core.database import dataagent_schema
from sqlalchemy import create_engine, pool, text

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers defaults to True, which silences every logger
    # already configured by the host process. That is harmless for the `alembic`
    # CLI, which owns its process, but not when migrations run in-process — a
    # test calling command.upgrade() would take pytest's caplog down with it and
    # the failure surfaces far away, as an unrelated assertion on empty log text.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = None


def _database_url() -> str:
    url = str(get_settings().dataagent_database_url or "").strip()
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


def run_migrations_offline() -> None:
    schema = dataagent_schema()
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        version_table_schema=schema,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    schema = dataagent_schema()
    connectable = create_engine(_database_url(), poolclass=pool.NullPool)

    # Schema creation, search-path selection and migrations must share the
    # outer transaction. SQLAlchemy 2 starts a transaction for SET; opening
    # Alembic's transaction afterwards on a plain connect() would otherwise
    # leave the migration transaction to be rolled back when the connection
    # closes.
    with connectable.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        connection.execute(text(f'SET search_path TO "{schema}", public'))
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            version_table_schema=schema,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
