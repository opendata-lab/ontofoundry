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
    source, draft, version_id = publish(client, "library-lending")
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
        sql.execute(text("CREATE SCHEMA fiction"))
        sql.execute(
            text(
                "CREATE TABLE public.fiction_folios_daily (raw_folio_code TEXT, raw_folio_title TEXT, raw_site_code TEXT, raw_shelf_grade TEXT, raw_genre_tag TEXT, raw_promo_tag TEXT, raw_tier_code TEXT, raw_catalog_bucket TEXT, raw_curator_tag TEXT, raw_aisle_tag TEXT, raw_daystamp DATE)"
            )
        )
        sql.execute(
            text("""INSERT INTO public.fiction_folios_daily
            (raw_folio_code, raw_site_code, raw_shelf_grade, raw_genre_tag, raw_promo_tag, raw_daystamp) VALUES
            ('svc-a','PROD','service','fantasy',' spotlight ','2026-10-01'),
            ('svc-a','PROD','service','fantasy',' spotlight ','2026-10-01'),
            ('svc-b','PROD','service','fantasy','staff_pick','2026-10-01'),
            ('svc-c','PROD','service','fantasy','other','2026-10-01'),
            ('db','PROD','DAMAGED','database','spotlight','2026-10-01'),
            ('svc-d','TEST','service','fantasy','spotlight','2026-10-01'),
            ('new','PROD','service','fantasy','spotlight','2026-10-03')""")
        )
        sql.execute(
            text(
                "CREATE TABLE fiction.fiction_loans_daily (raw_site_code TEXT, raw_folio_code TEXT, raw_curator_tag TEXT, raw_catalog_bucket TEXT, raw_loan_code TEXT, raw_checkout_qty BIGINT, raw_overdue_qty BIGINT, raw_late_pct NUMERIC, raw_minutes_mean NUMERIC, raw_minutes_tail NUMERIC, raw_checkout_clock TIMESTAMP, raw_daystamp DATE)"
            )
        )
        sql.execute(
            text("""INSERT INTO fiction.fiction_loans_daily
            (raw_site_code, raw_folio_code, raw_loan_code, raw_checkout_qty, raw_overdue_qty, raw_daystamp) VALUES
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
            "folio_distinct_total",
            "COUNT(DISTINCT CASE WHEN raw_shelf_grade <> 'DAMAGED' THEN raw_folio_code END)",
            [("PROD", 3), ("TEST", 1)],
        ),
        (
            "spotlight_folio_total",
            "COUNT(DISTINCT CASE WHEN raw_shelf_grade <> 'DAMAGED' AND raw_genre_tag = 'fantasy' AND CASE WHEN LOWER(TRIM(raw_promo_tag)) IN ('spotlight','staff_pick') THEN 'Y' WHEN raw_promo_tag IS NULL OR TRIM(raw_promo_tag) = '' OR LOWER(TRIM(raw_promo_tag)) IN ('plain','archived') THEN NULL ELSE 'N' END = 'Y' THEN raw_folio_code END)",
            [("PROD", 2), ("TEST", 1)],
        ),
        (
            "loan_late_fraction",
            "SUM(raw_overdue_qty)::double precision / NULLIF(SUM(raw_checkout_qty),0)",
            [("PROD", 0.1), ("TEST", None)],
        ),
    ],
)
def test_synthetic_b_metrics_equal_handwritten_sql_and_roundtrip(
    metric_pg, name, manual, expected
):
    client, engine, _, original, draft, version_id = metric_pg
    metric = next(m for m in draft["metrics"] if m["name"] == name)
    result = call(
        client, "query_metric", metric_id=metric["id"], group_by=["library_site"], filters=DATE
    )
    assert result["executable"] and not result["warnings"] and not result["truncated"]
    table = (
        "fiction.fiction_loans_daily"
        if name == "loan_late_fraction"
        else "public.fiction_folios_daily"
    )
    with engine.connect() as sql:
        manual_rows = sql.execute(
            text(
                f"SELECT raw_site_code, {manual} FROM {table} WHERE raw_daystamp = :date GROUP BY raw_site_code ORDER BY raw_site_code"
            ),
            {"date": "2026-10-01"},
        ).all()
    actual = [(r["library_site"], r[name]) for r in result["rows"]]
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
    metric = next(m for m in draft["metrics"] if m["name"] == "folio_distinct_total")
    args = dict(metric_id=metric["id"], group_by=["library_site"])
    old = call(client, "query_metric", **args, as_of="2026-10-02")
    assert old["rows"] == [
        {"library_site": "PROD", "folio_distinct_total": 3},
        {"library_site": "TEST", "folio_distinct_total": 1},
    ]
    latest = call(client, "query_metric", **args, as_of="2026-10-03")
    assert latest["rows"] == [{"library_site": "PROD", "folio_distinct_total": 1}]
    early = call(client, "query_metric", **args, as_of="2026-09-30")
    assert early["rows"] == []
    limited = call(client, "query_metric", **args, filters=DATE, limit=1)
    assert len(limited["rows"]) == 1 and limited["truncated"] and limited["warnings"]
    malicious = "PROD'; DELETE FROM public.fiction_folios_daily;--"
    empty = call(
        client,
        "query_metric",
        **args,
        filters=[*DATE, {"field": "library_site", "op": "=", "value": malicious}],
    )
    assert empty["rows"] == [] and malicious not in empty["sql"]


def test_actual_statement_timeout_and_readonly_transaction(metric_pg):
    client, engine, item, _, draft, _ = metric_pg
    settings = client.app.state.settings
    with connect_readonly(item, settings, timeout_ms=1000) as sql:
        assert sql.exec_driver_sql("SHOW transaction_read_only").scalar() == "on"
        assert sql.exec_driver_sql("SHOW statement_timeout").scalar() == "1s"
        with pytest.raises(SQLAlchemyError):
            sql.exec_driver_sql("DELETE FROM public.fiction_folios_daily")
    with engine.begin() as sql:
        sql.execute(
            text(
                "CREATE VIEW public.p4_slow_snapshot AS SELECT 'service'::text AS raw_shelf_grade, 'slow'::text AS raw_folio_code, 'PROD'::text AS raw_site_code, DATE '2026-10-01' AS raw_daystamp FROM pg_sleep(2)"
            )
        )
    dataset = next(d for d in draft["datasets"] if d["name"] == "fable_inventory_snapshot")
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
    metric = next(m for m in draft["metrics"] if m["name"] == "folio_distinct_total")
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
                text("SELECT count(*) FROM public.fiction_folios_daily")
            ).scalar()
            == 7
        )


def test_native_percent_and_colon_literals_execute_without_bind_confusion(metric_pg):
    client, _, _, _, draft, _ = metric_pg
    metric = next(m for m in draft["metrics"] if m["name"] == "folio_distinct_total")
    metric["expression"]["dialects"][0]["expression"] = (
        "COUNT(DISTINCT CASE WHEN fable_inventory_snapshot.shelf_grade <> 'DAMAGED' THEN ':p0%s' END)"
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
    assert result["rows"] == [{"folio_distinct_total": 1}], result


def test_explicit_event_parameters_are_extensions_and_roundtrip(metric_pg):
    client, _, _, _, draft, _ = metric_pg
    metric = next(m for m in draft["metrics"] if m["name"] == "loan_late_fraction")
    metric["custom_extensions"] = [
        {
            "vendor_name": "ONTOFOUNDRY",
            "data": json.dumps({"time_semantics": "event", "time_field": "inventory_day"}),
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
        group_by=["library_site"],
        filters=[
            {
                "field": "inventory_day",
                "op": "between",
                "value": ["2026-10-01", "2026-10-03"],
            }
        ],
    )
    assert result["rows"][0]["loan_late_fraction"] == pytest.approx(540 / 1400)
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
