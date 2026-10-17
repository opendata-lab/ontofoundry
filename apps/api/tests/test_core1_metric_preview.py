"""Execute aggregate previews against disposable fictional physical rows."""

import pytest
from core1_query_fixtures import source_database
from test_modeling import ROOT, create_session, save

from ontofoundry_api.domain.core import Condition
from ontofoundry_api.services.metric_query import execute_metric_preview


@pytest.mark.parametrize(
    "example,expected",
    [
        (
            "01-basic-sales",
            {
                "order_amount": 350,
                "order_count": 3,
                "buyer_count": 2,
                "q1_valid_order_amount": 100,
            },
        ),
        ("02-many-to-many", {"avg_score": 80, "enrollment_count": 2}),
        ("03-n-ary-reified", {"supply_quantity": 30, "active_supplier_count": 2}),
        (
            "04-composite-key",
            {"units_sold": 9, "shipment_count": 4, "line_sales_amount": 200},
        ),
        (
            "05-self-and-parallel-links",
            {"trade_amount": 300, "employee_count": 2, "desk_count": 3},
        ),
        ("06-inheritance", {"person_count": 1, "vip_party_count": 1}),
        ("10-partial", {"total_store_area": 30}),
        ("11-multi-source-and-unique-link", {"account_available_amount": 1000}),
        (
            "13-dataset-metrics",
            {
                "commit_count": 10,
                "core_commit_count": 8,
                "core_commit_share": 0.8,
                "active_repos": 2,
                "eligible_commit_count": 10,
                "stat_row_count": 3,
            },
        ),
    ],
)
def test_metrics_execute_actual_aggregate_sql(tmp_path, monkeypatch, example, expected):
    draft, engine = source_database(tmp_path, monkeypatch, example)
    try:
        for name, value in expected.items():
            metric = next(m for m in draft.metrics if m.technical_name == name)
            result = execute_metric_preview(
                None, str(draft.workspace_id), draft, metric, None
            )
            assert float(result["value"]) == pytest.approx(value), (name, result)
            assert "SELECT" in result["total_query"]["sql"]
    finally:
        engine.dispose()


def test_snapshot_global_last_day_and_monthly_recompute(tmp_path, monkeypatch):
    draft, engine = source_database(tmp_path, monkeypatch, "12-snapshot-and-trends")
    try:
        metric = draft.metrics[0]
        result = execute_metric_preview(
            None,
            str(draft.workspace_id),
            draft,
            metric,
            None,
            time_range={"start": "2026-11-01", "end": "2027-01-01"},
            trend=True,
        )
        assert result["value"] == 10
        assert [p["value"] for p in result["trend"]] == [14, 10]
        assert result["snapshot_dates"][0]["date"] == "2026-12-31"
    finally:
        engine.dispose()


def test_preview_unsaved_ratio_is_readonly_and_guarded(client, tmp_path, monkeypatch):
    draft, engine = source_database(tmp_path, monkeypatch, "13-dataset-metrics")
    try:
        s = create_session(client)
        raw = draft.model_dump(mode="json")
        raw["workspace_id"] = s["workspace_id"]
        s = save(client, s, raw).json()
        ratio = next(m for m in draft.metrics if m.kind == "ratio")
        components = [
            m.model_dump(mode="json")
            for m in draft.metrics
            if m.id in {ratio.numerator_id, ratio.denominator_id}
        ]
        body = {
            "session_id": s["id"],
            "expected_session_revision": s["revision"],
            "metric": ratio.model_dump(mode="json"),
            "components": components,
            "trend_grain": "month",
        }
        path = f"/api/v1/modeling/workspaces/{s['workspace_id']}/metrics/preview"
        response = client.post(path, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ok", response.text
        assert float(response.json()["value"]) == pytest.approx(0.8)
        assert client.get(ROOT + f"/sessions/{s['id']}").json()["revision"] == s["revision"]
        body["expected_session_revision"] -= 1
        assert client.post(path, json=body).status_code == 409
    finally:
        engine.dispose()


def test_engine_unsupported_and_zero_denominator_have_no_fake_value(tmp_path, monkeypatch):
    from ontofoundry_api.services.errors import ServiceError

    draft, engine = source_database(tmp_path, monkeypatch, "01-basic-sales")
    try:
        median = next(
            m for m in draft.metrics if getattr(m, "aggregation", None) == "median"
        )
        with pytest.raises(ServiceError) as exc:
            execute_metric_preview(None, str(draft.workspace_id), draft, median, None)
        assert exc.value.code == "dialect_unsupported"
        ratio = next(m for m in draft.metrics if m.technical_name == "completion_rate")
        for metric in draft.metrics:
            if metric.id in {ratio.numerator_id, ratio.denominator_id}:
                metric.filters = [
                    Condition.model_validate(
                        {
                            "column": {
                                "dataset_id": str(metric.dataset_id),
                                "column": "status",
                            },
                            "operator": "eq",
                            "values": ["不存在"],
                        }
                    )
                ]
        result = execute_metric_preview(None, str(draft.workspace_id), draft, ratio, None)
        assert result["value"] is None
    finally:
        engine.dispose()


@pytest.mark.parametrize("kind", ["simple", "expression"])
def test_snapshot_selected_before_grouping_by_launch_month(tmp_path, monkeypatch, kind):
    from ontofoundry_api.domain.core import ColumnReference, DatasetColumn, ExpressionMetric

    draft, engine = source_database(tmp_path, monkeypatch, "12-snapshot-and-trends")
    try:
        metric = draft.metrics[0]
        dataset = next(d for d in draft.datasets if d.id == metric.dataset_id)
        dataset.columns.append(DatasetColumn(name="launch_date", physical_type="DATE"))
        metric.time_field = ColumnReference(dataset_id=dataset.id, column="launch_date")
        metric.aggregation = "count"
        metric.measure = None
        if kind == "expression":
            metric = ExpressionMetric.model_validate(
                {
                    "id": str(metric.id),
                    "name": metric.name,
                    "technical_name": metric.technical_name,
                    "kind": "expression",
                    "dataset_id": str(dataset.id),
                    "expression": "COUNT(*)",
                    "value_kind": "integer",
                    "time_field": metric.time_field.model_dump(mode="json"),
                }
            )
            draft.metrics[0] = metric
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE component_daily ADD COLUMN launch_date TEXT")
            conn.exec_driver_sql("DELETE FROM component_daily")
            for snapshot, component, launch in [
                ("2026-12-30", "A", "2026-10-05"),
                ("2026-12-30", "B", "2026-12-20"),
                ("2026-12-31", "A", "2026-10-05"),
                ("2026-12-31", "B", "2026-12-20"),
                ("2026-12-31", "C", "2026-12-31"),
            ]:
                conn.exec_driver_sql(
                    "INSERT INTO component_daily (snapshot_date, component_id, launch_date) VALUES (?, ?, ?)",
                    (snapshot, component, launch),
                )
        result = execute_metric_preview(
            None,
            str(draft.workspace_id),
            draft,
            metric,
            None,
            time_range={"start": "2026-12-01", "end": "2027-01-01"},
            trend=True,
        )
        assert result["value"] == 3
        assert result["trend"] == [
            {"period": "2026-10-01", "value": 1},
            {"period": "2026-12-01", "value": 2},
        ]
        assert {d["date"] for d in result["snapshot_dates"]} == {"2026-12-31"}
    finally:
        engine.dispose()


def test_snapshot_without_business_time_returns_total_and_warning(
    client, tmp_path, monkeypatch
):
    draft, engine = source_database(tmp_path, monkeypatch, "12-snapshot-and-trends")
    try:
        s = create_session(client)
        raw = draft.model_dump(mode="json")
        raw["workspace_id"] = s["workspace_id"]
        s = save(client, s, raw).json()
        metric = draft.metrics[0].model_dump(mode="json")
        metric["time_field"] = None
        response = client.post(
            f"/api/v1/modeling/workspaces/{s['workspace_id']}/metrics/preview",
            json={
                "session_id": s["id"],
                "expected_session_revision": s["revision"],
                "metric": metric,
                "trend_grain": "month",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["status"] == "ok" and result["value"] == 10
        assert result["trend"] is None and result["trend_query"] is None
        assert result["warnings"] == ["缺少时间字段，仅返回总值，无法生成月趋势"]
        assert result["snapshot_dates"][0]["date"] == "2026-12-31"
    finally:
        engine.dispose()


def test_ratio_months_report_actual_snapshot_dates(tmp_path, monkeypatch):
    draft, engine = source_database(tmp_path, monkeypatch, "13-dataset-metrics")
    try:
        draft.datasets[0].snapshot_date_column = "stat_date"
        with engine.begin() as conn:
            conn.exec_driver_sql(
                "INSERT INTO code_lines_daily (repo, stat_date, commit_count) VALUES ('core', '2026-11-29', 99), ('core', '2026-11-30', 10), ('web', '2026-11-30', 10)"
            )
        ratio = next(m for m in draft.metrics if m.kind == "ratio")
        result = execute_metric_preview(
            None, str(draft.workspace_id), draft, ratio, None, trend=True
        )
        assert float(result["value"]) == pytest.approx(0.5)
        assert [float(p["value"]) for p in result["trend"]] == pytest.approx([5 / 7, 0.5])
        assert result["snapshot_dates"] == [
            {"dataset_id": str(draft.datasets[0].id), "period": None, "date": "2026-11-30"},
            {
                "dataset_id": str(draft.datasets[0].id),
                "period": "2026-10-01",
                "date": "2026-10-02",
            },
            {
                "dataset_id": str(draft.datasets[0].id),
                "period": "2026-11-01",
                "date": "2026-11-30",
            },
        ]
    finally:
        engine.dispose()


def test_same_simple_component_covers_both_ratio_references(client, tmp_path, monkeypatch):
    draft, engine = source_database(tmp_path, monkeypatch, "13-dataset-metrics")
    try:
        s = create_session(client)
        raw = draft.model_dump(mode="json")
        raw["workspace_id"] = s["workspace_id"]
        s = save(client, s, raw).json()
        ratio = next(m.model_dump(mode="json") for m in draft.metrics if m.kind == "ratio")
        ratio["denominator_id"] = ratio["numerator_id"]
        component = next(
            m.model_dump(mode="json")
            for m in draft.metrics
            if str(m.id) == ratio["numerator_id"]
        )
        body = {
            "session_id": s["id"],
            "expected_session_revision": s["revision"],
            "metric": ratio,
            "components": [component],
            "trend_grain": "month",
        }
        path = f"/api/v1/modeling/workspaces/{s['workspace_id']}/metrics/preview"
        response = client.post(path, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "ok" and float(response.json()["value"]) == 1
        assert [float(p["value"]) for p in response.json()["trend"]] == [1]
        for components in ([], [component, component]):
            invalid = client.post(path, json={**body, "components": components})
            assert invalid.status_code == 422, invalid.text
    finally:
        engine.dispose()
