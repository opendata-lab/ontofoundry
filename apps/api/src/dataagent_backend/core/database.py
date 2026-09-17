"""PostgreSQL connection helpers for DataAgent's internal persistence."""

from __future__ import annotations

import re

import psycopg
from dataagent_backend.config import get_settings
from psycopg.rows import dict_row

_SCHEMA_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def dataagent_schema() -> str:
    schema = str(get_settings().dataagent_database_schema or "public").strip()
    if not _SCHEMA_RE.fullmatch(schema):
        raise ValueError("DATAAGENT_DATABASE_SCHEMA must be a PostgreSQL identifier")
    return schema


def connect_dataagent():
    settings = get_settings()
    schema = dataagent_schema()
    url = str(settings.dataagent_database_url or "").strip()
    if not url:
        raise RuntimeError("DATAAGENT_DATABASE_URL is required")
    if url.startswith("postgresql+psycopg://"):
        url = "postgresql://" + url.removeprefix("postgresql+psycopg://")
    return psycopg.connect(
        url,
        autocommit=False,
        row_factory=dict_row,
        options=f"-c search_path={schema},public",
    )
