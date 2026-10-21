import { describe, expect, it } from "vitest";
import type { Metric, RatioMetric } from "../api/types";
import { example } from "../test/drafts";
import { metricErrors, newMetric, previewRequest, storedMetric, switchKind } from "./metricEditing";

const draft = example("01-basic-sales");
const ratio = draft.metrics.find((m) => m.name === "revenue_per_buyer") as RatioMetric;

describe("metric form helpers", () => {
  it("never sends a ratio's derived dataset, value kind or components", () => {
    const read = { ...ratio, dataset_id: "x", value_kind: "decimal", components: {} } as unknown as Metric;
    expect(Object.keys(storedMetric(read)).sort()).toEqual(
      ["denominator_id", "description", "evidence", "id", "kind", "display_name", "numerator_id", "synonyms", "name"].sort(),
    );
  });
  it("sends both ratio components with the unsaved form", () => {
    const request = previewRequest(draft, ratio, { expected_current_version_id: null });
    expect(request.components?.map((m) => m.id).sort()).toEqual([ratio.numerator_id, ratio.denominator_id].sort());
    expect(request.trend_grain).toBeUndefined();
    const ranged = previewRequest(draft, ratio, { expected_current_version_id: null }, { start: "2026-01-01", end: "2026-04-01" });
    expect(ranged.trend_grain).toBe("month");
  });
  it("sends a metric used as both numerator and denominator once", () => {
    const same = { ...ratio, denominator_id: ratio.numerator_id };
    expect(previewRequest(draft, same, { expected_current_version_id: null }).components?.map((m) => m.id)).toEqual([ratio.numerator_id]);
  });
  it("checks names, the dataset, measures and filter values", () => {
    const blank = newMetric("m", null);
    expect(Object.keys(metricErrors(draft, blank)).sort()).toEqual(["dataset", "name"]);
    expect(metricErrors(draft, { ...blank, name: "fictional_count", dataset_id: draft.datasets[0].id })).toEqual({});
    const orders = draft.datasets.find((d) => d.name === "orders")!;
    const sum = { ...newMetric("m", orders.id), display_name: "合计", name: "order_amount", aggregation: "sum" as const };
    expect(metricErrors(draft, sum)).toEqual({ name: "英文标识已被其他指标使用", measure: "请选择度量列" });
    const filtered = {
      ...sum,
      name: "x",
      measure: { dataset_id: orders.id, column: "amount" },
      filters: [{ column: { dataset_id: orders.id, column: "status" }, operator: "in" as const, values: [] }],
    };
    expect(metricErrors(draft, filtered)).toEqual({ "filter.0": "至少填写一个值" });

    const notInNull = {
      ...filtered,
      filters: [{ column: { dataset_id: orders.id, column: "status" }, operator: "not_in" as const, values: [null] }],
    };
    expect(metricErrors(draft, notInNull)).toEqual({ "filter.0": "“不属于”的值不能包含空值" });

    const nonNumeric = {
      ...filtered,
      filters: [{ column: { dataset_id: orders.id, column: "amount" }, operator: "gt" as const, values: ["not-a-number"] }],
    };
    expect(metricErrors(draft, nonNumeric)).toEqual({ "filter.0": "数值列的条件值必须是数字" });
  });
  it("keeps name and dataset when switching between kinds", () => {
    const simple = draft.metrics.find((m) => m.name === "order_amount")!;
    const expression = switchKind(draft, simple, "expression");
    expect(expression).toMatchObject({ kind: "expression", name: simple.name, display_name: simple.display_name, dataset_id: (simple as { dataset_id: string }).dataset_id });
    expect(switchKind(draft, ratio, "simple")).toMatchObject({ kind: "simple", dataset_id: (draft.metrics.find((m) => m.id === ratio.numerator_id) as { dataset_id: string }).dataset_id });
  });
});
