"""Execute unchanged B metrics against a disposable PostgreSQL, never business DBs."""

import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from test_modeling import mcp_request
from test_p2_mcp_synonyms import publish
from test_p4_metric_query import DATE
from test_t7_mcp_elements import call

from ontofoundry_api.api.connections import connect_readonly
from ontofoundry_api.db_models import ConnectionRecord, OntologyVersionRecord
from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.domain.semantic_views import connection_alias
from ontofoundry_api.ossie.compiler import compile_ossie
from ontofoundry_api.ossie.extensions import reverse_export_edits
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.workspaces import publish_draft


@pytest.fixture
def metric_pg(pg_client):
    client = pg_client
    settings = client.app.state.settings
    url = make_url(settings.database_url)
    # pg_client creates and drops its own database. Reject accidental use of any
    # other database even when running this fixture with custom test settings.
    assert url.database.startswith("of_t0_")
    settings.connection_key = Fernet.generate_key().decode()
    source, draft, version_id = publish(client, "architecture-governance")
    alias = connection_alias(OntologyDraft.model_validate(draft).semantic_models[0])
    secret = (
        Fernet(settings.connection_key.encode())
        .encrypt((url.password or "").encode())
        .decode()
    )
    item = ConnectionRecord(
        id="p4-source",
        workspace_id=str(DEMO_WORKSPACE_ID),
        name=alias,
        kind="postgresql",
        config_json=dict(
            host=url.host,
            port=url.port or 5432,
            username=url.username,
            database=url.database,
        ),
        secret_encrypted=secret,
    )
    with client.app.state.session_factory() as db:
        db.add(item)
        db.commit()
    engine = create_engine(settings.database_url)
    with engine.begin() as sql:
        sql.execute(text("CREATE SCHEMA tech"))
        sql.execute(
            text(
                "CREATE TABLE public.dim_tech_public_env_cmp_df (cmp_name TEXT, cn_cmp_name TEXT, env_name TEXT, component_type TEXT, prop_com_arch_type TEXT, prop_com_importance_type TEXT, system_level TEXT, system_name TEXT, dept_name TEXT, zone TEXT, ds DATE)"
            )
        )
        sql.execute(
            text("""INSERT INTO public.dim_tech_public_env_cmp_df
            (cmp_name, env_name, component_type, prop_com_arch_type, prop_com_importance_type, ds) VALUES
            ('svc-a','PROD','service','microservice',' Core ','2026-10-01'),
            ('svc-a','PROD','service','microservice',' Core ','2026-10-01'),
            ('svc-b','PROD','service','microservice','opt','2026-10-01'),
            ('svc-c','PROD','service','microservice','other','2026-10-01'),
            ('db','PROD','DB','database','core','2026-10-01'),
            ('svc-d','TEST','service','microservice','core','2026-10-01'),
            ('new','PROD','service','microservice','core','2026-10-03')""")
        )
        sql.execute(
            text(
                "CREATE TABLE tech.dws_tech_ops_interface_performance_1d_di (env_name TEXT, cmp_name TEXT, dept_name TEXT, system_name TEXT, interface TEXT, call_count BIGINT, error_count BIGINT, error_rate NUMERIC, total_time_avg NUMERIC, total_time_p99 NUMERIC, latest_invoke_time TIMESTAMP, ds DATE)"
            )
        )
        sql.execute(
            text("""INSERT INTO tech.dws_tech_ops_interface_performance_1d_di
            (env_name, cmp_name, interface, call_count, error_count, ds) VALUES
            ('PROD','svc-a','/a',100,10,'2026-10-01'),
            ('PROD','svc-b','/b',300,30,'2026-10-01'),
            ('TEST','svc-c','/a',0,0,'2026-10-01'),
            ('PROD','svc-a','/a',1000,500,'2026-10-03')""")
        )
    try:
        yield client, engine, item, source, draft, version_id
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "name,manual,expected",
    [
        (
            "component_count",
            "COUNT(DISTINCT CASE WHEN component_type <> 'DB' THEN cmp_name END)",
            [("PROD", 3), ("TEST", 1)],
        ),
        (
            "core_service_count",
            "COUNT(DISTINCT CASE WHEN component_type <> 'DB' AND prop_com_arch_type = 'microservice' AND CASE WHEN LOWER(TRIM(prop_com_importance_type)) IN ('core','opt') THEN 'Y' WHEN prop_com_importance_type IS NULL OR TRIM(prop_com_importance_type) = '' OR LOWER(TRIM(prop_com_importance_type)) IN ('base','external') THEN NULL ELSE 'N' END = 'Y' THEN cmp_name END)",
            [("PROD", 2), ("TEST", 1)],
        ),
        (
            "interface_error_rate",
            "SUM(error_count)::double precision / NULLIF(SUM(call_count),0)",
            [("PROD", 0.1), ("TEST", None)],
        ),
    ],
)
def test_real_b_metrics_equal_handwritten_sql_and_roundtrip(
    metric_pg, name, manual, expected
):
    client, engine, _, original, draft, version_id = metric_pg
    metric = next(m for m in draft["metrics"] if m["name"] == name)
    result = call(
        client, "query_metric", metric_id=metric["id"], group_by=["env_name"], filters=DATE
    )
    assert result["executable"] and not result["warnings"] and not result["truncated"]
    table = (
        "tech.dws_tech_ops_interface_performance_1d_di"
        if name == "interface_error_rate"
        else "public.dim_tech_public_env_cmp_df"
    )
    with engine.connect() as sql:
        manual_rows = sql.execute(
            text(
                f"SELECT env_name, {manual} FROM {table} WHERE ds = :date GROUP BY env_name ORDER BY env_name"
            ),
            {"date": "2026-10-01"},
        ).all()
    actual = [(r["env_name"], r[name]) for r in result["rows"]]
    assert actual == list(manual_rows) == expected
    listed = next(
        m for m in call(client, "list_metrics")["items"] if m["id"] == metric["id"]
    )
    assert listed["executable"] and listed["requires_snapshot_filter"]
    with client.app.state.session_factory() as db:
        version = db.get(OntologyVersionRecord, version_id)
        assert (
            version.snapshot_json == draft
        )  # no execution params inferred into the native file
        exported = compile_ossie(
            OntologyDraft.model_validate(draft),
            ontology_name=original["name"],
            ontology_description=original.get("description", ""),
        )
        assert reverse_export_edits(exported) == original
        assert reverse_export_edits(version.ossie_json) == original


def test_snapshot_as_of_latest_global_and_bound_values_and_limit(metric_pg):
    client, _, _, _, draft, _ = metric_pg
    metric = next(m for m in draft["metrics"] if m["name"] == "component_count")
    args = dict(metric_id=metric["id"], group_by=["env_name"])
    old = call(client, "query_metric", **args, as_of="2026-10-02")
    assert old["rows"] == [
        {"env_name": "PROD", "component_count": 3},
        {"env_name": "TEST", "component_count": 1},
    ]
    latest = call(client, "query_metric", **args, as_of="2026-10-03")
    assert latest["rows"] == [{"env_name": "PROD", "component_count": 1}]
    early = call(client, "query_metric", **args, as_of="2026-09-30")
    assert early["rows"] == []
    limited = call(client, "query_metric", **args, filters=DATE, limit=1)
    assert len(limited["rows"]) == 1 and limited["truncated"] and limited["warnings"]
    malicious = "PROD'; DELETE FROM public.dim_tech_public_env_cmp_df;--"
    empty = call(
        client,
        "query_metric",
        **args,
        filters=[*DATE, {"field": "env_name", "op": "=", "value": malicious}],
    )
    assert empty["rows"] == [] and malicious not in empty["sql"]


def test_actual_statement_timeout_and_readonly_transaction(metric_pg):
    client, engine, item, _, draft, _ = metric_pg
    settings = client.app.state.settings
    with connect_readonly(item, settings, timeout_ms=1000) as sql:
        assert sql.exec_driver_sql("SHOW transaction_read_only").scalar() == "on"
        assert sql.exec_driver_sql("SHOW statement_timeout").scalar() == "1s"
        with pytest.raises(SQLAlchemyError):
            sql.exec_driver_sql("DELETE FROM public.dim_tech_public_env_cmp_df")
    with engine.begin() as sql:
        sql.execute(
            text(
                "CREATE VIEW public.p4_slow_snapshot AS SELECT 'service'::text AS component_type, 'slow'::text AS cmp_name, 'PROD'::text AS env_name, DATE '2026-10-01' AS ds FROM pg_sleep(2)"
            )
        )
    dataset = next(d for d in draft["datasets"] if d["name"] == "component_snapshot")
    dataset["source"] = "public.p4_slow_snapshot"
    with client.app.state.session_factory() as db:
        publish_draft(
            db,
            workspace_id=str(DEMO_WORKSPACE_ID),
            draft=OntologyDraft.model_validate(draft),
            user_id="00000000-0000-0000-0000-000000000001",
            message="timeout fixture",
        )
    settings.metric_query_timeout_seconds = 1
    metric = next(m for m in draft["metrics"] if m["name"] == "component_count")
    response = mcp_request(
        client,
        "tools/call",
        {"name": "query_metric", "arguments": {"metric_id": metric["id"], "filters": DATE}},
    ).json()["result"]
    assert (
        response["isError"]
        and response["structuredContent"]["code"] == "METRIC_QUERY_TIMEOUT"
    ), response
    with engine.connect() as sql:
        assert (
            sql.execute(
                text("SELECT count(*) FROM public.dim_tech_public_env_cmp_df")
            ).scalar()
            == 7
        )


def test_native_percent_and_colon_literals_execute_without_bind_confusion(metric_pg):
    client, _, _, _, draft, _ = metric_pg
    metric = next(m for m in draft["metrics"] if m["name"] == "component_count")
    metric["expression"]["dialects"][0]["expression"] = (
        "COUNT(DISTINCT CASE WHEN component_snapshot.component_type <> 'DB' THEN ':p0%s' END)"
    )
    with client.app.state.session_factory() as db:
        publish_draft(
            db,
            workspace_id=str(DEMO_WORKSPACE_ID),
            draft=OntologyDraft.model_validate(draft),
            user_id="00000000-0000-0000-0000-000000000001",
            message="literal bind fixture",
        )
    result = call(client, "query_metric", metric_id=metric["id"], filters=DATE)
    assert result["rows"] == [{"component_count": 1}], result


def test_explicit_event_parameters_are_extensions_and_roundtrip(metric_pg):
    client, _, _, _, draft, _ = metric_pg
    metric = next(m for m in draft["metrics"] if m["name"] == "interface_error_rate")
    metric["custom_extensions"] = [
        {
            "vendor_name": "ONTOFOUNDRY",
            "data": json.dumps({"time_semantics": "event", "time_field": "snapshot_date"}),
        }
    ]
    metric["native_presence"].append("custom_extensions")
    with client.app.state.session_factory() as db:
        version = publish_draft(
            db,
            workspace_id=str(DEMO_WORKSPACE_ID),
            draft=OntologyDraft.model_validate(draft),
            user_id="00000000-0000-0000-0000-000000000001",
            message="explicit event parameters",
        )
    result = call(
        client,
        "query_metric",
        metric_id=metric["id"],
        group_by=["env_name"],
        filters=[
            {
                "field": "snapshot_date",
                "op": "between",
                "value": ["2026-10-01", "2026-10-03"],
            }
        ],
    )
    assert result["rows"][0]["interface_error_rate"] == pytest.approx(540 / 1400)
    from ontofoundry_api.ossie.importer import import_ossie

    restored, _ = import_ossie(
        version.ossie_json, workspace_id=DEMO_WORKSPACE_ID, mode="replace"
    )
    assert (
        compile_ossie(
            OntologyDraft.model_validate(restored),
            ontology_name=version.ossie_json["name"],
            ontology_description=version.ossie_json.get("description", ""),
        )
        == version.ossie_json
    )
