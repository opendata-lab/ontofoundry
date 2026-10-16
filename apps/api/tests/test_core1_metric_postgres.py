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


def test_unsaved_ratio_aggregates_and_readonly_timeout_path(pg_client):
    app = pg_client.app
    url = make_url(app.state.settings.database_url)
    draft = example_draft("13-dataset-metrics")
    for ds in draft.datasets:
        ds.dialect = "postgresql"
        ds.schema_name = "public"
    wid = pg_client.get("/api/v1/workspaces").json()["items"][0]["id"]
    with app.state.engine.begin() as c:
        c.exec_driver_sql(
            "CREATE TABLE code_lines_daily(repo text,stat_date date,commit_count integer)"
        )
        c.exec_driver_sql(
            "INSERT INTO code_lines_daily VALUES ('core','2026-10-01',3),('core','2026-10-02',5),('web','2026-10-02',2)"
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
