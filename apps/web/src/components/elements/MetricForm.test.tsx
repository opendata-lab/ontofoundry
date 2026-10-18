import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";
import type { Scalar, SimpleMetric } from "../../api/types";
import { metricErrors, newMetric, storedMetric } from "../../lib/metricEditing";
import { example } from "../../test/drafts";
import { renderWithProviders } from "../../test/renderWithProviders";
import { MetricForm } from "./MetricForm";

const draft = example("01-basic-sales");
const dataset = draft.datasets[0];
dataset.columns = [
  { name: "code", physical_type: "varchar" },
  { name: "enabled", physical_type: "boolean" },
  { name: "amount", physical_type: "decimal" },
  { name: "count", physical_type: "integer" },
  { name: "day", physical_type: "date" },
];

function show(column: string, values: Scalar[] = [], operator: "eq" | "in" | "between" = "eq") {
  let latest: SimpleMetric;
  function Harness() {
    const [metric, setMetric] = useState<SimpleMetric>({
      ...newMetric("typed_metric", dataset.id), name: "条件指标", technical_name: "typed_metric",
      filters: [{ column: { dataset_id: dataset.id, column }, operator, values }],
    });
    latest = metric;
    return <MetricForm draft={draft} metric={metric} onChange={(next) => setMetric(next as SimpleMetric)} showErrors={false} />;
  }
  renderWithProviders(<Harness />);
  return () => latest!;
}

afterEach(cleanup);

describe("typed metric conditions", () => {
  it("preserves text identifiers, leading zeroes and whitespace", () => {
    const metric = show("code");
    fireEvent.change(screen.getByRole("textbox", { name: "条件 1 的值" }), { target: { value: "001" } });
    expect((storedMetric(metric()) as SimpleMetric).filters[0].values).toEqual(["001"]);
    fireEvent.change(screen.getByRole("textbox", { name: "条件 1 的值" }), { target: { value: " 001 " } });
    expect(metric().filters[0].values).toEqual([" 001 "]);
    expect(metricErrors(draft, metric())).toEqual({});
  });

  it.each([["是", true], ["否", false]] as const)("saves boolean %s as a boolean", (label, value) => {
    const metric = show("enabled");
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "条件 1 的值" }));
    fireEvent.click(screen.getByText(label, { selector: ".ant-select-item-option-content" }));
    expect((storedMetric(metric()) as SimpleMetric).filters[0].values).toEqual([value]);
    expect(metricErrors(draft, metric())).toEqual({});
  });

  it("parses numeric values and range bounds as numbers", () => {
    const metric = show("amount", [], "between");
    fireEvent.change(screen.getByRole("spinbutton", { name: "条件 1 的值起" }), { target: { value: "1.5" } });
    fireEvent.change(screen.getByRole("spinbutton", { name: "条件 1 的值止" }), { target: { value: "20" } });
    expect(metric().filters[0].values).toEqual([1.5, 20]);
    expect(metricErrors(draft, metric())).toEqual({});
  });

  it("revalidates retained values when switching to an incompatible column", () => {
    const metric = show("code", ["001"]);
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "条件 1 的列" }));
    fireEvent.click(screen.getByText("count", { selector: ".ant-select-item-option-content" }));
    expect(metric().filters[0].values).toEqual(["001"]);
    expect(screen.getByText("数值列的条件值必须是数字")).toBeInTheDocument();
    expect(metricErrors(draft, metric())).toHaveProperty("filter.0");
    fireEvent.change(screen.getByRole("spinbutton", { name: "条件 1 的值" }), { target: { value: "2" } });
    expect(metricErrors(draft, metric())).toEqual({});
  });

  it("revalidates a numeric value after switching to text or boolean", () => {
    const metric = show("count", [1]);
    const select = screen.getByRole("combobox", { name: "条件 1 的列" });
    for (const column of ["code", "enabled"]) {
      fireEvent.mouseDown(select);
      fireEvent.click(screen.getByText(column, { selector: ".ant-select-item-option-content" }));
      expect(metric().filters[0].values).toEqual([1]);
      expect(screen.getByText("条件值与列类型不匹配，请重新填写")).toBeInTheDocument();
    }
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "条件 1 的值" }));
    fireEvent.click(screen.getByText("否", { selector: ".ant-select-item-option-content" }));
    expect(metric().filters[0].values).toEqual([false]);
    expect(metricErrors(draft, metric())).toEqual({});
  });

  it("keeps boolean multi-value choices typed", () => {
    const metric = show("enabled", [], "in");
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "条件 1 的值" }));
    for (const label of ["是", "否"])
      fireEvent.click(screen.getByText(label, { selector: ".ant-select-item-option-content" }));
    expect(metric().filters[0].values).toEqual([true, false]);
    expect(metricErrors(draft, metric())).toEqual({});
  });

  it("retains the existing date string convention", () => {
    const metric = show("day", ["2026-10-17"]);
    expect(within(screen.getByRole("textbox", { name: "条件 1 的值" }).closest(".ant-picker")!).getByRole("textbox")).toHaveValue("2026-10-17");
    expect((storedMetric(metric()) as SimpleMetric).filters[0].values).toEqual(["2026-10-17"]);
    expect(metricErrors(draft, metric())).toEqual({});
  });
});
