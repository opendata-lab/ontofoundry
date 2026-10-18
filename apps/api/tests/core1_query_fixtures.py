"""Fictional disposable SQLite datasets, built independently for each example."""

import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

from core1_fixtures import example_draft
from sqlalchemy import create_engine

from ontofoundry_api.services.dataset_sources import DatasetSource

ROWS = json.loads((Path(__file__).parent / "fixtures/core1_data/rows.json").read_text())


def source_database(tmp_path, monkeypatch, name):
    draft = example_draft(name)
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / name}.db")
    with engine.begin() as conn:
        for ds in draft.datasets:
            cols = ds.columns or []
            if not cols:
                continue

            def sql_type(column):
                physical = (column.physical_type or "").lower()
                if "int" in physical:
                    return "INTEGER"
                if any(t in physical for t in ("decimal", "numeric", "float")):
                    return "NUMERIC"
                return "TEXT"

            columns = ", ".join(
                '"' + c.name.replace('"', '""') + '" ' + sql_type(c) for c in cols
            )
            conn.exec_driver_sql('CREATE TABLE "' + ds.table_name + '" (' + columns + ")")
            for row in ROWS.get(name, {}).get(ds.table_name, []):
                names = list(row)
                conn.exec_driver_sql(
                    'INSERT INTO "'
                    + ds.table_name
                    + '" ('
                    + ",".join('"' + n + '"' for n in names)
                    + ") VALUES ("
                    + ",".join("?" for _ in names)
                    + ")",
                    tuple(row[n] for n in names),
                )
    record = SimpleNamespace(id="fictional-disposable", kind="sqlite")

    def resolve(*args, **kwargs):
        return DatasetSource(record, "fictional_disposable", None)

    @contextmanager
    def readonly(*args, **kwargs):
        with engine.connect() as conn:
            yield conn

    for module in ["metric_query", "instance_plan", "instance_neighborhood"]:
        target = __import__(
            "ontofoundry_api.services." + module, fromlist=["resolve_dataset"]
        )
        monkeypatch.setattr(target, "resolve_dataset", resolve)
        monkeypatch.setattr(target, "connect_readonly", readonly)
    return draft, engine
