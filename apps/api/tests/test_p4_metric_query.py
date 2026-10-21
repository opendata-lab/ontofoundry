"""Preview execution allowlist rejects queries, unsafe functions and windows."""

import pytest

from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.metric_query import check_ast, parse_expression


@pytest.mark.parametrize(
    "text",
    [
        "SUM(x)",
        "COUNT(DISTINCT x)",
        "SUM(CASE WHEN x > 0 THEN x ELSE 0 END)",
        "SUM(x)/NULLIF(COUNT(*),0)",
    ],
)
def test_allowed_aggregate_scalar_combinations(text):
    check_ast(parse_expression(text, ""), aggregate=True)


@pytest.mark.parametrize(
    "text",
    [
        "(SELECT SUM(x) FROM secret)",
        "pg_sleep(10)",
        "SUM(x) OVER ()",
        "SUM(SUM(x))",
        "x+SUM(x)",
    ],
)
def test_ast_rejects_unsafe_or_out_of_scope_expressions(text):
    with pytest.raises(ServiceError):
        check_ast(parse_expression(text, ""), aggregate=True)


@pytest.mark.parametrize("dialect", ["postgres", "mysql"])
@pytest.mark.parametrize("aggregation", ["sum", "count_distinct"])
@pytest.mark.parametrize("snapshot", [False, True])
def test_metric_identifiers_escape_driver_percent_without_touching_binds(
    dialect, aggregation, snapshot
):
    from types import SimpleNamespace

    from core1_fixtures import example_draft
    from sqlglot import exp

    from ontofoundry_api.services.dataset_sources import DatasetSource
    from ontofoundry_api.services.metric_query import MetricCompiler, serialize

    draft = example_draft("13-dataset-metrics")
    dataset = draft.datasets[0]
    dataset.table_name = "daily%amount"
    renamed = {"commit_count": "amount%", "repo": "repo%", "stat_date": "stat%date"}
    for column in dataset.columns:
        column.name = renamed[column.name]
    if snapshot:
        dataset.snapshot_date_column = "stat%date"
    metric = next(m for m in draft.metrics if m.name == "core_commit_count")
    metric.aggregation = aggregation
    metric.measure.column = "amount%"
    metric.filters[0].column.column = "repo%"
    metric.filters[0].values = ["core%"]
    metric.time_field.column = "stat%date"
    source = DatasetSource(
        SimpleNamespace(kind="postgresql" if dialect == "postgres" else "mysql"),
        "fictional",
        "schema%name",
    )
    for trend in (False, True):
        compiler = MetricCompiler(
            draft,
            metric,
            source=source,
            time_range={"start": "2026-10-01", "end": "2026-11-01"},
        )
        compiled = compiler.compile(trend=trend)
        sql, params = compiled["sql"], compiled["params"]
        for name in ["amount%", "repo%", "stat%date", "daily%amount", "schema%name"]:
            quoted = serialize(exp.to_identifier(name, quoted=True), dialect)
            assert quoted in sql
            assert "%%" in quoted
        assert "core%" in params.values()
        assert all(f"%({name})s" in sql for name in params)
        rendered = sql % params
        if dialect == "postgres":
            from psycopg._queries import _query2pg

            driver_sql, _, order, _ = _query2pg(sql.encode(), "utf-8")
            assert "amount%" in driver_sql.decode()
            assert set(order) == params.keys()
            assert b"$1" in driver_sql
        assert "amount%" in rendered and "schema%name" in rendered
        assert "%%" not in rendered
        assert "core%" in rendered
