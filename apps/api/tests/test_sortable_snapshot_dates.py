"""Sortable snapshot partitions retain global latest-day semantics without casts."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from core1_fixtures import example_draft
from core1_query_fixtures import source_database

from ontofoundry_api.domain.core import (
    ColumnReference,
    DatasetColumn,
    ExpressionMetric,
    empty_draft,
)
from ontofoundry_api.domain.validation import GraphValidationError, validate_core_graph
from ontofoundry_api.services import dataset_validation, metric_query
from ontofoundry_api.services.errors import ServiceError
from ontofoundry_api.services.instance_plan import query_instances


def snapshot_dataset(physical_type):
    dataset = example_draft("12-snapshot-and-trends").datasets[0]
    dataset.columns = [DatasetColumn(name="snapshot_date", physical_type=physical_type)]
    return dataset


@pytest.mark.parametrize(
    "physical_type",
    ["date", "timestamp", "varchar(10)", "text", "integer", "bigint", None, "unknown"],
)
def test_sortable_and_unknown_snapshot_types_are_accepted(physical_type, monkeypatch):
    dataset = snapshot_dataset(physical_type)
    draft = empty_draft(uuid4())
    draft.datasets = [dataset]
    assert validate_core_graph(draft) is draft
    checked = check_source(dataset, physical_type, monkeypatch)
    assert checked["valid"], checked


def check_source(dataset, physical_type, monkeypatch, *, missing=False):
    monkeypatch.setattr(
        dataset_validation,
        "resolve_dataset",
        lambda *a, **kw: SimpleNamespace(schema="fiction"),
    )
    monkeypatch.setattr(
        dataset_validation,
        "registered_tables",
        lambda *a: {
            ("fiction", dataset.table_name): {
                "columns": []
                if missing
                else [{"name": "snapshot_date", "type": physical_type}]
            }
        },
    )
    return dataset_validation.check_dataset(None, "fiction", dataset)


@pytest.mark.parametrize("physical_type", ["boolean", "decimal(18,2)", "double"])
def test_unsuitable_snapshot_types_are_rejected(physical_type, monkeypatch):
    dataset = snapshot_dataset(physical_type)
    draft = empty_draft(uuid4())
    draft.datasets = [dataset]
    with pytest.raises(GraphValidationError, match="快照日期列必须是日期类"):
        validate_core_graph(draft)
    checked = check_source(dataset, physical_type, monkeypatch)
    assert not checked["valid"]
    assert "可按日期排序" in checked["diagnostics"][0]["message"]


def test_unknown_type_does_not_allow_a_missing_snapshot_column(monkeypatch):
    dataset = snapshot_dataset(None)
    checked = check_source(dataset, None, monkeypatch, missing=True)
    assert not checked["valid"]
    assert checked["diagnostics"][0]["code"] == "COLUMN_NOT_FOUND"
    dataset.snapshot_date_column = "fiction_missing"
    draft = empty_draft(uuid4())
    draft.datasets = [dataset]
    with pytest.raises(GraphValidationError, match="不存在列"):
        validate_core_graph(draft)


@pytest.fixture(params=["varchar(10)", "integer"])
def sortable_source(request, tmp_path, monkeypatch):
    draft, engine = source_database(tmp_path, monkeypatch, "12-snapshot-and-trends")
    physical_type = request.param
    integer = physical_type == "integer"
    try:
        with engine.begin() as conn:
            for dataset in draft.datasets:
                dataset.snapshot_date_column = "snapshot_partition"
                dataset.columns.append(
                    DatasetColumn(name="snapshot_partition", physical_type=physical_type)
                )
                # The fixture uses fictional table names from the design examples.
                table = '"' + dataset.table_name + '"'
                conn.exec_driver_sql(
                    f"ALTER TABLE {table} ADD COLUMN snapshot_partition {'INTEGER' if integer else 'TEXT'}"
                )
                value = (
                    "CAST(REPLACE(snapshot_date, '-', '') AS INTEGER)"
                    if integer
                    else "snapshot_date"
                )
                conn.exec_driver_sql(f"UPDATE {table} SET snapshot_partition = {value}")
            conn.exec_driver_sql(
                "INSERT INTO component_daily (component_id, snapshot_date, snapshot_partition, quantity, warehouse_code) VALUES (?, ?, ?, ?, ?)",
                (
                    "fiction_old_only",
                    "2026-12-29",
                    20261229 if integer else "2026-12-29",
                    99,
                    "W1",
                ),
            )
        yield draft, integer
    finally:
        engine.dispose()


def test_sortable_snapshot_instances_use_global_max_and_exact_original_value(
    sortable_source,
):
    draft, integer = sortable_source
    mapping = draft.mappings[0]
    latest = query_instances(None, str(draft.workspace_id), draft, mapping.type_id, None)
    assert len(latest["items"]) == 1
    assert latest["items"][0]["values"]["quantity"] == 10
    assert latest["items"][0]["values"]["status"] == "可用"
    assert {d["date"] for d in latest["snapshot_dates"]} == (
        {"20261231", "20261230"} if integer else {"2026-12-31", "2026-12-30"}
    )
    chosen = 20261229 if integer else "2026-12-29"
    exact = query_instances(
        None, str(draft.workspace_id), draft, mapping.type_id, None, snapshot_date=chosen
    )
    assert sorted(row["values"]["quantity"] for row in exact["items"]) == [16, 99]
    assert {d["date"] for d in exact["snapshot_dates"]} == {str(chosen)}
    absent = 20261230 if integer else "2026-12-30"
    assert (
        query_instances(
            None,
            str(draft.workspace_id),
            draft,
            mapping.type_id,
            None,
            snapshot_date=absent,
        )["items"]
        == []
    )
    if integer:
        assert (
            query_instances(
                None,
                str(draft.workspace_id),
                draft,
                mapping.type_id,
                None,
                snapshot_date="2026-12-29",
            )["items"]
            == []
        )


@pytest.mark.parametrize("kind", ["simple", "expression", "ratio"])
def test_sortable_snapshot_metrics_use_max_and_reject_snapshot_months(
    sortable_source, monkeypatch, kind
):
    draft, integer = sortable_source
    metric = draft.metrics[0]
    metric.time_field = ColumnReference(
        dataset_id=metric.dataset_id, column="snapshot_partition"
    )
    if kind == "expression":
        dataset = next(d for d in draft.datasets if d.id == metric.dataset_id)
        metric = ExpressionMetric(
            kind="expression",
            id=metric.id,
            name="fiction_quantity",
            display_name="示例数量",
            dataset_id=metric.dataset_id,
            expression=f"SUM({dataset.name}.quantity)",
            value_kind="integer",
            time_field=metric.time_field,
        )
        draft.metrics[0] = metric
    elif kind == "ratio":
        from ontofoundry_api.domain.core import RatioMetric

        denominator = metric.model_copy(
            update={"id": uuid4(), "name": "fiction_denominator"}
        )
        draft.metrics.append(denominator)
        metric = RatioMetric(
            kind="ratio",
            id=uuid4(),
            name="fiction_ratio",
            display_name="示例比率",
            numerator_id=metric.id,
            denominator_id=denominator.id,
        )
        draft.metrics.append(metric)
    result = metric_query.execute_metric_preview(
        None, str(draft.workspace_id), draft, metric, None
    )
    assert result["value"] == (1 if kind == "ratio" else 10)
    assert result["snapshot_dates"][0]["date"] == ("20261231" if integer else "2026-12-31")
    assert "MAX(" in result["total_query"]["sql"]

    def unexpected_execution(*args, **kwargs):
        pytest.fail("Unsupported snapshot trends must fail before opening a connection")

    monkeypatch.setattr(metric_query, "connect_readonly", unexpected_execution)
    with pytest.raises(ServiceError) as exc:
        metric_query.execute_metric_preview(
            None, str(draft.workspace_id), draft, metric, None, trend=True
        )
    assert exc.value.code == "snapshot_time_field_not_date"
    assert "无法直接按月归组" in exc.value.message
    assert "数据源中提供日期类列" in exc.value.message
    assert "关闭月趋势" in exc.value.message


def test_sortable_snapshot_can_group_by_a_separate_date_column(sortable_source):
    draft, _ = sortable_source
    metric = draft.metrics[0]
    assert metric.time_field.column == "snapshot_date"
    result = metric_query.execute_metric_preview(
        None, str(draft.workspace_id), draft, metric, None, trend=True
    )
    assert result["value"] == 10
    assert result["trend"] == [{"period": "2026-12-01", "value": 10}]
