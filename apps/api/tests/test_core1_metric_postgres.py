"""Real PostgreSQL aggregate execution on a test-created disposable database."""

import os
from uuid import uuid4

import pytest
from core1_fixtures import example_draft
from sqlalchemy.engine import make_url

from ontofoundry_api.db_models import ConnectionRecord
from ontofoundry_api.services.metric_query import execute_metric_preview

pytestmark = pytest.mark.skipif(
    not os.environ.get("ONTOFOUNDRY_TEST_POSTGRES_URL"),
    reason="Disposable PostgreSQL not supplied",
)


@pytest.mark.parametrize("percent_names", [False, True])
def test_unsaved_ratio_aggregates_and_readonly_timeout_path(pg_client, percent_names):
    app = pg_client.app
    url = make_url(app.state.settings.database_url)
    draft = example_draft("13-dataset-metrics")
    for ds in draft.datasets:
        ds.dialect = "postgresql"
        ds.schema_name = "public"
        if percent_names:
            ds.table_name = "code%lines_daily"
            next(c for c in ds.columns if c.name == "commit_count").name = "amount%"
    if percent_names:
        for metric in draft.metrics:
            if (
                metric.kind == "simple"
                and metric.measure
                and metric.measure.column == "commit_count"
            ):
                metric.measure.column = "amount%"
    table = '"code%%lines_daily"' if percent_names else "code_lines_daily"
    column = '"amount%%"' if percent_names else "commit_count"
    wid = pg_client.get("/api/v1/workspaces").json()["items"][0]["id"]
    with app.state.engine.begin() as c:
        c.exec_driver_sql(
            f"CREATE TABLE {table}(repo text,stat_date date,{column} integer)", {}
        )
        c.exec_driver_sql(
            f"INSERT INTO {table} VALUES ('core','2026-10-01',3),('core','2026-10-02',5),('web','2026-10-02',2)",
            {},
        )
    with app.state.session_factory() as db:
        db.add(
            ConnectionRecord(
                id=str(uuid4()),
                workspace_id=wid,
                name="虚构测试连接",
                kind="postgresql",
                config_json={
                    "host": url.host,
                    "port": url.port,
                    "database": url.database,
                    "username": url.username,
                },
                secret_encrypted=url.password or "",
            )
        )
        db.commit()
        metric = next(m for m in draft.metrics if m.kind == "ratio")
        result = execute_metric_preview(
            db, wid, draft, metric, app.state.settings, trend=True
        )
        assert float(result["value"]) == pytest.approx(0.8)
        assert float(result["trend"][0]["value"]) == pytest.approx(0.8)
