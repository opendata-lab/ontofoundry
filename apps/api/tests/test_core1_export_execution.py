"""Recompute exported and reimported metrics on actual disposable data sources."""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
import sqlglot
from core1_query_fixtures import source_database
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import make_url
from sqlglot import exp
from test_core1_ossie_roundtrip import metric_container, roundtrip

from ontofoundry_api.db_models import ConnectionRecord
from ontofoundry_api.services.metric_query import execute_metric_preview


def compare(db, wid, settings, original, restored):
    returned = {m.technical_name: m for m in restored.metrics}
    for metric in original.metrics:
        expected = execute_metric_preview(db, wid, original, metric, settings)["value"]
        actual = execute_metric_preview(
            db, wid, restored, returned[metric.technical_name], settings
        )["value"]
        assert (
            actual is None
            if expected is None
            else float(actual) == pytest.approx(float(expected))
        ), metric.technical_name


def test_metric_algorithms_recompute_after_export_import_on_sqlite(
    client, tmp_path, monkeypatch
):
    _, engine = source_database(tmp_path, monkeypatch, "13-dataset-metrics")
    model = metric_container()
    _, imported = roundtrip(model)
    try:
        with client.app.state.session_factory() as db:
            compare(
                db,
                str(model.workspace_id),
                client.app.state.settings,
                model,
                imported.model,
            )
    finally:
        engine.dispose()


def run_external(client, config, dialect, engine):
    model = metric_container()
    name = "fiction_export_" + uuid4().hex[:10]
    quote = '"' if dialect == "postgresql" else "`"
    table = quote + name + quote
    wid = client.get("/api/v1/workspaces").json()["items"][0]["id"]
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"CREATE TABLE {table}(repo varchar(20),stat_date date,commit_count decimal(20,4))"
            )
            connection.exec_driver_sql(
                f"INSERT INTO {table} VALUES ('core','2026-10-01',3.25),('core','2026-10-02',5.5),('web','2026-10-02',0.25),(NULL,'2026-10-03',NULL)"
            )
        for ds in model.datasets:
            ds.table_name, ds.schema_name, ds.dialect = (
                name,
                config["database"] if dialect == "mysql" else "public",
                dialect,
            )
            next(
                c for c in ds.columns if c.name == "commit_count"
            ).physical_type = "decimal(20,4)"
        artifact, imported = roundtrip(model)
        # RT-66 explicitly loses physical engine metadata; a user-supplied dialect
        # is required before execution, never guessed from ANSI_SQL.
        assert all(ds.dialect is None for ds in imported.model.datasets)
        for ds in imported.model.datasets:
            ds.dialect = dialect
        with client.app.state.session_factory() as db:
            db.add(
                ConnectionRecord(
                    id=str(uuid4()),
                    workspace_id=wid,
                    name="虚构导出复算来源",
                    kind=dialect,
                    config_json={
                        k: config[k] for k in ("host", "port", "database", "username")
                    },
                    secret_encrypted=config["password"],
                )
            )
            db.commit()
            compare(db, wid, client.app.state.settings, model, imported.model)
            semantic = json.loads(artifact.document)["ontology_mappings"][0][
                "semantic_model"
            ]
            exported_dataset = semantic["datasets"][0]
            physical = {
                f["name"]: f["expression"]["dialects"][0]["expression"]
                for f in exported_dataset["fields"]
            }
            formulas = {
                m["name"]: m["expression"]["dialects"][0]["expression"]
                for m in semantic["metrics"]
            }
            with engine.connect() as readonly:
                for metric in model.metrics:
                    ast = sqlglot.parse_one(formulas[metric.technical_name])
                    for column in list(ast.find_all(exp.Column)):
                        value = sqlglot.parse_one(physical[column.name])
                        for ref in value.find_all(exp.Column):
                            ref.set(
                                "table",
                                exp.to_identifier(exported_dataset["name"], quoted=True),
                            )
                        column.replace(value)
                    query = sqlglot.parse_one(
                        f"SELECT {ast.sql()} FROM {exported_dataset['source']} AS {exp.to_identifier(exported_dataset['name'], quoted=True).sql()}"
                    ).sql(dialect="postgres" if dialect == "postgresql" else dialect)
                    actual = readonly.exec_driver_sql(query).scalar()
                    expected = execute_metric_preview(
                        db, wid, model, metric, client.app.state.settings
                    )["value"]
                    assert (
                        actual is None
                        if expected is None
                        else float(actual) == pytest.approx(float(expected))
                    ), metric.technical_name
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(f"DROP TABLE IF EXISTS {table}")


def test_metric_algorithms_recompute_after_export_import_on_postgresql(pg_client):
    url = make_url(pg_client.app.state.settings.database_url)
    config = dict(
        host=url.host,
        port=url.port,
        database=url.database,
        username=url.username,
        password=url.password or "",
    )
    run_external(pg_client, config, "postgresql", pg_client.app.state.engine)


@pytest.mark.skipif(
    not os.environ.get("ONTOFOUNDRY_TEST_MYSQL_CONFIG"),
    reason="Disposable MySQL configuration not supplied",
)
def test_metric_algorithms_recompute_after_export_import_on_mysql(client):
    config = json.loads(Path(os.environ["ONTOFOUNDRY_TEST_MYSQL_CONFIG"]).read_text())
    engine = create_engine(
        URL.create(
            "mysql+pymysql",
            **{k: config[k] for k in ("host", "port", "database", "username", "password")},
        )
    )
    try:
        run_external(client, config, "mysql", engine)
    finally:
        engine.dispose()
