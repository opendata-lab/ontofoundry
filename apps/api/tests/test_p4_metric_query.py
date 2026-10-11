"""Metric compilation uses real B expressions and adversarial native payloads."""

import json
from pathlib import Path

import pytest
from test_modeling import ROOT, mcp_request
from test_p2_mcp_synonyms import publish
from test_t7_mcp_elements import call

from ontofoundry_api.domain.models import OntologyDraft
from ontofoundry_api.ossie.importer import import_ossie
from ontofoundry_api.services.demo import DEMO_WORKSPACE_ID
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.metric_query import MetricCompiler

FIXTURES = Path(__file__).parent / "fixtures" / "REDACTED_PRIVATE_PATH"
DATE = [{"field": "snapshot_date", "op": "=", "value": "2026-10-01"}]


@pytest.fixture(scope="module")
def b_draft():
    document = json.loads((FIXTURES / "REDACTED").read_text())
    draft, _ = import_ossie(document, workspace_id=DEMO_WORKSPACE_ID, mode="replace")
    return OntologyDraft.model_validate(draft)


def compiler(draft, name="REDACTED", dialect="postgres", expression=None):
    metric = next(m for m in draft.metrics if m.name == name).model_copy(deep=True)
    if expression is not None:
        metric.expression.dialects[0].expression = expression
    return MetricCompiler(draft, metric, dialect)


@pytest.mark.parametrize("dialect", ["postgres", "mysql"])
def test_real_rewrite_derived_field_and_bound_filters(b_draft, dialect):
    c = compiler(b_draft, dialect=dialect)
    p = c.compile(
        group_by=["REDACTED"],
        filters=[
            *DATE,
            {"field": "REDACTED", "op": "=", "value": "x'; DROP TABLE secret;--"},
        ],
    )
    assert "prop_com_importance_type" in p.sql and "LOWER(TRIM(" in p.sql
    assert "prop_com_arch_type" in p.sql and "REDACTED" not in p.sql
    assert "GROUP BY" in p.sql and "LIMIT 101" in p.sql
    assert "DROP" not in p.sql and p.parameters["p1"] == "x'; DROP TABLE secret;--"
    assert '"public"' in p.sql if dialect == "postgres" else "`public`" in p.sql
    assert p.columns == ["REDACTED", "REDACTED"]


def test_mysql_concat_and_postgres_decimal_division(b_draft):
    p = compiler(b_draft, "REDACTED", "mysql").compile(filters=DATE)
    assert "CONCAT(" in p.sql and "||" not in p.sql
    p = compiler(b_draft, "REDACTED").compile(filters=DATE)
    assert "CAST(SUM(" in p.sql and "DOUBLE PRECISION" in p.sql


def test_prefers_target_dialect_before_ansi(b_draft):
    c = compiler(b_draft)
    metric = c.metric.model_copy(deep=True)
    d = metric.expression.dialects[0].model_copy(
        update={
            "dialect": "POSTGRESQL",
            "expression": "SUM(REDACTED.REDACTED)",
        }
    )
    metric.expression.dialects.append(d)
    p = MetricCompiler(b_draft, metric, "postgres").compile(filters=DATE)
    assert "SUM(" in p.sql and "COUNT(" not in p.sql
    assert "COUNT(" in MetricCompiler(b_draft, metric, "mysql").compile(filters=DATE).sql


@pytest.mark.parametrize(
    "expression",
    [
        "SUM(REDACTED.REDACTED); DROP TABLE public.secret",
        "DROP TABLE public.secret",
        "SELECT SUM(REDACTED.REDACTED)",
        "SUM((SELECT secret FROM public.secret))",
        "SUM(pg_sleep(1))",
        "SUM(public.evil(REDACTED.REDACTED))",
        "SUM(REDACTED.REDACTED) OVER ()",
        "SUM(REDACTED.REDACTED) FILTER (WHERE TRUE)",
        "SUM(REDACTED.REDACTED) + REDACTED.REDACTED",
        "SUM(SUM(REDACTED.REDACTED))",
        "COUNT(REDACTED.*)",
        "SUM(CAST(REDACTED.REDACTED AS malicious_type))",
        "SUM(unknown.REDACTED)",
        "SUM(REDACTED.secret)",
        "SUM(REDACTED)",
    ],
)
def test_ast_rejects_unsafe_or_out_of_scope_expressions(b_draft, expression):
    with pytest.raises(ServiceError):
        compiler(b_draft, expression=expression)


@pytest.mark.parametrize(
    "expression",
    [
        "(SELECT secret FROM public.secret)",
        "pg_sleep(1)",
        "name;DROP TABLE x",
        "other_table.secret",
        "SUM(cmp_name)",
    ],
)
def test_field_expression_is_also_validated(b_draft, expression):
    draft = b_draft.model_copy(deep=True)
    ds = next(d for d in draft.datasets if d.name == "REDACTED")
    field = next(
        f
        for f in draft.dataset_fields
        if f.dataset_id == ds.id and f.name == "REDACTED"
    )
    field.expression.dialects[0].expression = expression
    with pytest.raises(ServiceError):
        compiler(draft)


def test_unused_complex_field_does_not_block_metric(b_draft):
    draft = b_draft.model_copy(deep=True)
    next(f for f in draft.dataset_fields if f.name == "zone").expression.dialects[
        0
    ].expression = "unknown(zone)"
    c = compiler(draft)
    assert c.compile(filters=DATE).sql
    with pytest.raises(ServiceError):
        c.compile(group_by=["zone"], filters=DATE)


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"filters": [{"field": "snapshot_date", "op": "in", "value": ["2026-10-01"]}]},
        {
            "filters": [
                {
                    "field": "snapshot_date",
                    "op": "between",
                    "value": ["2026-10-01", "2026-10-02"],
                }
            ]
        },
        {"group_by": ["snapshot_date"]},
        {"as_of": "2026-10-02", "filters": DATE},
        {"filters": DATE * 2},
    ],
)
def test_snapshot_requires_single_date_even_with_time_group(b_draft, arguments):
    with pytest.raises(ServiceError) as exc:
        compiler(b_draft).compile(**arguments)
    assert exc.value.code in ("METRIC_SNAPSHOT_REQUIRED", "METRIC_TIME_INVALID")


def test_as_of_is_controlled_latest_snapshot_subquery(b_draft):
    p = compiler(b_draft).compile(as_of="2026-10-03", group_by=["REDACTED"])
    assert "SELECT MAX(" in p.sql and "<= %(p0)s" in p.sql
    assert p.parameters == {"p0": "2026-10-03"}
    assert "ds" in p.sql and "snapshot_date" not in p.sql


def test_event_override_and_rolling_extension(b_draft):
    c = compiler(b_draft, "REDACTED")
    metric = c.metric.model_copy(deep=True)
    from ontofoundry_api.domain.models_v3 import CustomExtension

    metric.custom_extensions = [
        CustomExtension(
            vendor_name="ONTOFOUNDRY",
            data=json.dumps({"time_semantics": "event", "time_field": "snapshot_date"}),
        )
    ]
    event = MetricCompiler(b_draft, metric, "postgres")
    assert (
        "BETWEEN"
        in event.compile(
            filters=[
                {
                    "field": "snapshot_date",
                    "op": "between",
                    "value": ["2026-10-01", "2026-10-02"],
                }
            ]
        ).sql
    )
    with pytest.raises(ServiceError):
        event.compile(as_of="2026-10-02")
    metric.custom_extensions[0].data = json.dumps(
        {"time_semantics": "rolling", "time_field": "snapshot_date"}
    )
    with pytest.raises(ServiceError):
        MetricCompiler(b_draft, metric, "postgres").compile()
    assert MetricCompiler(b_draft, metric, "postgres").compile(as_of="2026-10-02").sql


@pytest.mark.parametrize(
    "op,value",
    [
        ("=", "PROD"),
        ("!=", "TEST"),
        ("<", 1),
        ("<=", 2),
        (">", 3),
        (">=", 4),
        ("in", ["PROD", "TEST"]),
        ("between", [1, 4]),
        ("is_null", None),
        ("not_null", None),
    ],
)
def test_all_structured_filter_operators(b_draft, op, value):
    p = compiler(b_draft).compile(
        filters=[*DATE, {"field": "REDACTED", "op": op, "value": value}]
    )
    assert p.parameters["p0"] == "2026-10-01"
    assert len(p.parameters) == (
        1 if value is None else 3 if isinstance(value, list) else 2
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {"group_by": ["other.REDACTED"]},
        {"group_by": ["REDACTED", "REDACTED"]},
        {"filters": [{"field": "secret", "op": "=", "value": 1}]},
        {"filters": [{"field": "REDACTED", "op": "like", "value": "%"}]},
        {"filters": [{"field": "REDACTED", "op": "=", "value": {"sql": "evil"}}]},
        {"filters": [{"field": "REDACTED", "op": "in", "value": []}]},
        {"filters": [{"field": "REDACTED", "op": "between", "value": [1]}]},
        {"limit": 0},
        {"limit": 1001},
        {"limit": True},
    ],
)
def test_bad_request_fields_values_and_bounds(b_draft, arguments):
    with pytest.raises(ServiceError):
        compiler(b_draft).compile(**{**{"filters": DATE}, **arguments})


def test_multi_dataset_only_explains_connections(b_draft, client, monkeypatch):
    def mutate(d):
        metric = next(m for m in d["metrics"] if m["name"] == "REDACTED")
        metric["expression"]["dialects"][0]["expression"] = (
            "SUM(REDACTED.REDACTED) + SUM(REDACTED.REDACTED)"
        )

    _, draft, _ = publish(client, "REDACTED", mutate)
    from ontofoundry_api.api import connections

    monkeypatch.setattr(
        connections, "connect_readonly", lambda *a, **k: pytest.fail("must not execute")
    )
    metric = next(m for m in draft["metrics"] if m["name"] == "REDACTED")
    result = call(client, "query_metric", metric_id=metric["id"])
    assert result["executable"] is False and result["sql"] is None
    assert {d["name"] for d in result["datasets"]} == {
        "REDACTED",
        "REDACTED",
    }
    assert result["dataset_relationships"] and "多个数据集" in result["reason"]


def test_mcp_catalog_no_connection_sql_only_and_clean_projection(client):
    _, _, _ = publish(client, "REDACTED")
    catalog = call(client, "list_metrics", query="REDACTED")
    metric = catalog["items"][0]
    assert metric["name"] == "REDACTED" and metric["display_name"] == "REDACTED"
    assert not metric["executable"] and metric["requires_snapshot_filter"]
    assert any(f["name"] == "REDACTED" for f in metric["group_by_fields"])
    assert not any(
        k in json.dumps(metric) for k in ("native_presence", '"position"', '"origin"')
    )
    result = call(client, "query_metric", metric_id=metric["id"], filters=DATE)
    assert not result["executable"] and result["sql"] and not result["rows"]
    error = mcp_request(
        client,
        "tools/call",
        {"name": "query_metric", "arguments": {"metric_id": metric["id"]}},
    ).json()["result"]
    assert (
        error["isError"]
        and error["structuredContent"]["code"] == "METRIC_SNAPSHOT_REQUIRED"
    )
    model = metric["semantic_model"]
    assert call(client, "list_metrics", semantic_model=model["id"])["items"]
    assert not call(client, "list_metrics", semantic_model="missing")["items"]


def test_metric_tools_reuse_existing_scopes(client):
    publish(client, "REDACTED")
    for scopes, available in (
        (["ontology:read"], set()),
        (["ontology:read", "mappings:read"], {"list_metrics"}),
        (["ontology:read", "instances:read"], {"list_metrics", "query_metric"}),
    ):
        token = client.post(
            ROOT + "/service-tokens",
            json={"name": "metric-" + scopes[-1], "scopes": scopes},
        ).json()["token"]
        headers = {"Authorization": "Bearer " + token}
        names = {
            t["name"]
            for t in mcp_request(client, "tools/list", {}, headers=headers).json()[
                "result"
            ]["tools"]
        }
        assert names & {"list_metrics", "query_metric"} == available
        if not available:
            error = mcp_request(
                client,
                "tools/call",
                {"name": "list_metrics", "arguments": {}},
                headers=headers,
            ).json()
            assert error["result"]["isError"]


def test_percent_and_colon_literals_are_not_bound_or_replaced(b_draft):
    p = compiler(
        b_draft,
        expression="COUNT(DISTINCT CASE WHEN REDACTED.REDACTED <> 'DB' THEN ':p0%s' END)",
    ).compile(filters=DATE)
    assert "':p0%%s'" in p.sql and p.parameters == {"p0": "2026-10-01"}
    p = compiler(b_draft, expression="SUM(REDACTED.REDACTED % 2)").compile(
        filters=DATE
    )
    assert " %% 2" in p.sql


@pytest.mark.parametrize(
    "source",
    [
        "public.table; DROP TABLE other",
        "(SELECT * FROM other)",
        "public.table AS fake",
        "generate_series(1,10)",
    ],
)
def test_dataset_source_must_be_one_physical_table(b_draft, source):
    draft = b_draft.model_copy(deep=True)
    next(d for d in draft.datasets if d.name == "REDACTED").source = source
    with pytest.raises(ServiceError):
        compiler(draft)


@pytest.mark.parametrize(
    "params",
    [
        {"time_field": []},
        {"time_semantics": "unknown"},
        {"time_semantics": "rolling", "time_field": "unknown"},
    ],
)
def test_invalid_vendor_time_settings_rejected(b_draft, params):
    from ontofoundry_api.domain.models_v3 import CustomExtension

    c = compiler(b_draft)
    c.metric.custom_extensions = [
        CustomExtension(vendor_name="ONTOFOUNDRY", data=json.dumps(params))
    ]
    with pytest.raises(ServiceError):
        MetricCompiler(b_draft, c.metric)


@pytest.mark.parametrize(
    "timeout,code", [(True, "METRIC_QUERY_TIMEOUT"), (False, "METRIC_QUERY_FAILED")]
)
def test_driver_failures_and_timeout_mapping_without_external_pg(
    client, monkeypatch, timeout, code
):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from sqlalchemy.exc import DBAPIError

    from ontofoundry_api.api import connections
    from ontofoundry_api.services import metric_query

    _, draft, _ = publish(client, "REDACTED")
    metric = next(m for m in draft["metrics"] if m["name"] == "REDACTED")
    monkeypatch.setattr(
        metric_query, "connection_for", lambda *a: SimpleNamespace(kind="postgresql")
    )

    class DriverError(Exception):
        sqlstate = "57014" if timeout else "42703"

    class FailedSQL:
        def exec_driver_sql(self, sql, parameters):
            raise DBAPIError(sql, parameters, DriverError("test-only failure"))

    @contextmanager
    def readonly(item, settings, *, timeout_ms):
        assert timeout_ms == 15000
        yield FailedSQL()

    monkeypatch.setattr(connections, "connect_readonly", readonly)
    result = mcp_request(
        client,
        "tools/call",
        {"name": "query_metric", "arguments": {"metric_id": metric["id"], "filters": DATE}},
    ).json()["result"]
    assert result["isError"] and result["structuredContent"]["code"] == code


def test_mcp_invalid_bounds_have_chinese_error(client):
    result = mcp_request(
        client,
        "tools/call",
        {"name": "query_metric", "arguments": {"metric_id": "id", "limit": 1001}},
    ).json()
    assert (
        result["error"]["code"] == -32602 and "指标参数无效" in result["error"]["message"]
    )


def test_dataset_time_params_and_metric_override(b_draft):
    from ontofoundry_api.domain.models_v3 import CustomExtension

    draft = b_draft.model_copy(deep=True)
    dataset = next(d for d in draft.datasets if d.name == "REDACTED")
    dataset.custom_extensions = [
        CustomExtension(
            vendor_name="ONTOFOUNDRY",
            data=json.dumps({"time_semantics": "event", "time_field": "snapshot_date"}),
        )
    ]
    c = compiler(draft)
    assert c.compile(group_by=["snapshot_date"]).sql
    c.metric.custom_extensions = [
        CustomExtension(
            vendor_name="ONTOFOUNDRY", data=json.dumps({"time_semantics": "snapshot"})
        )
    ]
    with pytest.raises(ServiceError) as exc:
        MetricCompiler(draft, c.metric).compile()
    assert exc.value.code == "METRIC_SNAPSHOT_REQUIRED"


@pytest.mark.parametrize("vendor,conflict", [("OTHER", False), ("ONTOFOUNDRY", True)])
def test_conflicting_extension_keys_and_unrelated_vendors(b_draft, vendor, conflict):
    from ontofoundry_api.domain.models_v3 import CustomExtension

    c = compiler(b_draft)
    c.metric.custom_extensions = [
        CustomExtension(vendor_name="ONTOFOUNDRY", data='{"time_semantics":"snapshot"}'),
        CustomExtension(vendor_name=vendor, data='{"time_semantics":"event"}'),
    ]
    if conflict:
        with pytest.raises(ServiceError) as exc:
            MetricCompiler(b_draft, c.metric)
        assert exc.value.code == "METRIC_TIME_INVALID"
    else:
        assert MetricCompiler(b_draft, c.metric).compile(filters=DATE).sql


@pytest.mark.parametrize(
    "expression",
    [
        "COALESCE(SUM(REDACTED.REDACTED),0)",
        "CASE WHEN SUM(REDACTED.REDACTED)>0 THEN CAST(SUM(REDACTED.REDACTED) AS DECIMAL(10,2)) ELSE NULL END",
        "AVG(REDACTED.REDACTED) + MIN(REDACTED.REDACTED) + MAX(REDACTED.REDACTED)",
    ],
)
def test_allowed_aggregate_scalar_combinations_and_max_limit(b_draft, expression):
    p = compiler(b_draft, expression=expression).compile(filters=DATE, limit=1000)
    assert p.sql.endswith("LIMIT 1001") and p.limit == 1000
