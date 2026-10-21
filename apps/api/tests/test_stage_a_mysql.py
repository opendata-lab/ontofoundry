"""Opt-in MySQL checks use an explicitly disposable connection configuration."""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from core1_fixtures import example_draft
from dataset_binding import _register
from sqlalchemy import URL, create_engine

from ontofoundry_api.db_models import ConnectionRecord
from ontofoundry_api.services.metric_query import execute_metric_preview


@pytest.mark.skipif(
    not os.environ.get("ONTOFOUNDRY_TEST_MYSQL_CONFIG"),
    reason="Disposable MySQL configuration not supplied",
)
@pytest.mark.parametrize("percent_names", [False, True])
def test_mysql_metric_preview_uses_actual_aggregate(client, percent_names):
    config = json.loads(Path(os.environ["ONTOFOUNDRY_TEST_MYSQL_CONFIG"]).read_text())
    # The supplied environment is explicitly disposable; use a unique fictional
    # table and clean it even when an assertion fails.
    name = "fictional_code_" + uuid4().hex[:12]
    if percent_names:
        name += "%daily"
    table = "`" + name.replace("%", "%%") + "`"
    column = "`amount%%`" if percent_names else "commit_count"
    engine = create_engine(
        URL.create(
            "mysql+pymysql",
            username=config["username"],
            password=config["password"],
            host=config["host"],
            port=config["port"],
            database=config["database"],
        )
    )
    wid = client.get("/api/v1/workspaces").json()["items"][0]["id"]
    try:
        with engine.begin() as c:
            c.exec_driver_sql(
                f"CREATE TABLE {table}(repo varchar(20),stat_date date,{column} int)", {}
            )
            c.exec_driver_sql(
                f"INSERT INTO {table} VALUES ('core','2026-10-01',8),('web','2026-10-01',2)",
                {},
            )
        draft = example_draft("13-dataset-metrics")
        connection_id = str(uuid4())
        for ds in draft.datasets:
            ds.connection_id = connection_id
            ds.table_name = name
            ds.dialect = "mysql"
            ds.schema_name = config["database"]
            if percent_names:
                next(c for c in ds.columns if c.name == "commit_count").name = "amount%"
        if percent_names:
            for metric in draft.metrics:
                if (
                    metric.kind == "simple"
                    and metric.measure
                    and metric.measure.column == "commit_count"
                ):
                    metric.measure.column = "amount%"
        with client.app.state.session_factory() as db:
            db.add(
                ConnectionRecord(
                    id=connection_id,
                    workspace_id=wid,
                    name="虚构一次性来源",
                    kind="mysql",
                    config_json={
                        k: config[k] for k in ("host", "port", "database", "username")
                    },
                    secret_encrypted=config["password"],
                )
            )
            db.flush()
            connection = db.get(ConnectionRecord, connection_id)
            for dataset in draft.datasets:
                _register(db, connection, dataset.schema_name, dataset.table_name, [column.model_dump() for column in dataset.columns or []])
            db.commit()
            ratio = next(m for m in draft.metrics if m.kind == "ratio")
            assert float(
                execute_metric_preview(db, wid, draft, ratio, client.app.state.settings)[
                    "value"
                ]
            ) == pytest.approx(0.8)
    finally:
        with engine.begin() as c:
            c.exec_driver_sql(f"DROP TABLE IF EXISTS {table}", {})
        engine.dispose()
