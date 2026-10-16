"""Opt-in MySQL checks use an explicitly disposable connection configuration."""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from core1_fixtures import example_draft
from sqlalchemy import URL, create_engine

from ontofoundry_api.db_models import ConnectionRecord
from ontofoundry_api.services.metric_query import execute_metric_preview


@pytest.mark.skipif(
    not os.environ.get("ONTOFOUNDRY_TEST_MYSQL_CONFIG"),
    reason="Disposable MySQL configuration not supplied",
)
def test_mysql_metric_preview_uses_actual_aggregate(client):
    config = json.loads(Path(os.environ["ONTOFOUNDRY_TEST_MYSQL_CONFIG"]).read_text())
    # The supplied environment is explicitly disposable; use a unique fictional
    # table and clean it even when an assertion fails.
    name = "fictional_code_" + uuid4().hex[:12]
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
                f"CREATE TABLE {name}(repo varchar(20),stat_date date,commit_count int)"
            )
            c.exec_driver_sql(
                f"INSERT INTO {name} VALUES ('core','2026-10-01',8),('web','2026-10-01',2)"
            )
        draft = example_draft("13-dataset-metrics")
        for ds in draft.datasets:
            ds.table_name = name
            ds.dialect = "mysql"
            ds.schema_name = config["database"]
        with client.app.state.session_factory() as db:
            db.add(
                ConnectionRecord(
                    id=str(uuid4()),
                    workspace_id=wid,
                    name="虚构一次性来源",
                    kind="mysql",
                    config_json={
                        k: config[k] for k in ("host", "port", "database", "username")
                    },
                    secret_encrypted=config["password"],
                )
            )
            db.commit()
            ratio = next(m for m in draft.metrics if m.kind == "ratio")
            assert float(
                execute_metric_preview(db, wid, draft, ratio, client.app.state.settings)[
                    "value"
                ]
            ) == pytest.approx(0.8)
    finally:
        with engine.begin() as c:
            c.exec_driver_sql(f"DROP TABLE IF EXISTS {name}")
        engine.dispose()
