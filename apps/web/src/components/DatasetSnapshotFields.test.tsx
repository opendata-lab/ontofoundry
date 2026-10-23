import { cleanup, fireEvent, screen } from "@testing-library/react";
import { Form } from "antd";
import { afterEach, expect, it, vi } from "vitest";
import { renderWithProviders } from "../test/renderWithProviders";
import { DatasetSnapshotFields } from "./DatasetSnapshotFields";

afterEach(cleanup);

const columns = [
  { name: "fiction_date", physical_type: "date" },
  { name: "fiction_timestamp", physical_type: "timestamp" },
  { name: "fiction_text", physical_type: "varchar(10)" },
  { name: "fiction_integer", physical_type: "bigint" },
  { name: "fiction_unknown", physical_type: null },
  { name: "fiction_boolean", physical_type: "boolean" },
  { name: "fiction_decimal", physical_type: "decimal(18,2)" },
  { name: "fiction_float", physical_type: "double" },
];

it.each(["fiction_date", "fiction_timestamp", "fiction_text", "fiction_integer", "fiction_unknown"])(
  "allows selecting %s and excludes unsuitable types", async (name) => {
    const onChange = vi.fn();
    renderWithProviders(<Form><DatasetSnapshotFields dataset={{ columns, snapshot_date_column: "" }} onChange={onChange} /></Form>);
    expect(screen.getByText("日期类，或可按日期排序的文本/整数列（如 2026-10-23、20261023）")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "快照日期字段" }));
    for (const excluded of ["fiction_boolean", "fiction_decimal", "fiction_float"]) {
      expect(screen.queryByText(excluded)).not.toBeInTheDocument();
    }
    fireEvent.click(await screen.findByText(name, { selector: ".ant-select-item-option-content" }));
    expect(onChange).toHaveBeenCalledWith({ snapshot_date_column: name });
  },
);

it("keeps an unavailable column list disabled until metadata is loaded", () => {
  renderWithProviders(<Form><DatasetSnapshotFields dataset={{ columns: null, snapshot_date_column: "" }} onChange={vi.fn()} /></Form>);
  expect(screen.getByRole("combobox", { name: "快照日期字段" })).toBeDisabled();
  expect(screen.getByText("请先选择表并读取字段。")).toBeInTheDocument();
});

it("enables and clears the snapshot declaration", () => {
  const onChange = vi.fn();
  const { rerender } = renderWithProviders(<Form><DatasetSnapshotFields dataset={{ columns, snapshot_date_column: null }} onChange={onChange} /></Form>);
  fireEvent.click(screen.getByRole("checkbox", { name: "快照表" }));
  expect(onChange).toHaveBeenLastCalledWith({ snapshot_date_column: "" });
  rerender(<Form><DatasetSnapshotFields dataset={{ columns, snapshot_date_column: "fiction_integer" }} onChange={onChange} /></Form>);
  fireEvent.click(screen.getByRole("checkbox", { name: "快照表" }));
  expect(onChange).toHaveBeenLastCalledWith({ snapshot_date_column: null });
});
