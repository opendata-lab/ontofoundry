import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SemanticCatalog, LegacyDraft } from "../api/types";
import { emptyDraft } from "../lib/draftView";
import { SemanticCatalogView } from "./SemanticModels";
import { MappingPanel } from "./elements/ElementPanels";

const catalog: SemanticCatalog = { mapping_status: {}, items: [{ id: "model", name: "治理", connection_alias: "governance", datasets: Array.from({ length: 41 }, (_, i) => ({ id: `d${i}`, name: `dataset_${i}`, source: `public.table_${i}`, primary_key: ["id"], unique_keys: [], ai_context: { synonyms: ["组件"] }, fields: Array.from({ length: i === 0 ? 35 : 8 }, (_, j) => ({ id: `f${i}_${j}`, name: `field_${i}_${j}`, datatype: "String", dimension: { is_time: false }, expression: { dialects: [{ dialect: "ANSI_SQL", expression: `column_${j}` }] }, ai_context: { synonyms: ["字段别名"] } })) })), relationships: [{ id: "r", name: "连接", from: "dataset_0", to: "dataset_1", from_columns: ["id", "tenant"], to_columns: ["parent_id", "tenant_id"] }], metrics: Array.from({ length: 27 }, (_, i) => ({ id: `m${i}`, name: `metric_${i}`, description: "指标说明", datatype: "Integer", expression: { dialects: [{ dialect: "ANSI_SQL", expression: "COUNT(dataset_0.id)" }] }, ai_context: { synonyms: ["REDACTED"] }, concepts: i === 0 ? [{ id: "c1", name: "系统", technical_name: "system" }, { id: "c2", name: "组件", technical_name: "component" }] : [] })) }] };
function expand(text: RegExp) {
  const summary = screen.getByText(text);
  const details = summary.closest("details")!;
  details.open = true;
  fireEvent(details, new Event("toggle"));
}
afterEach(cleanup);
describe("原生语义模型只读目录", () => {
  it("defers collapsed contents and paginates datasets and metrics", () => {
    render(<SemanticCatalogView catalog={catalog} />);
    expect(screen.queryByText("metric_0 · Integer")).not.toBeInTheDocument();
    expand(/治理 · 41 数据集/);
    expect(screen.getByText(/dataset_9 ·/)).toBeInTheDocument();
    expect(screen.queryByText(/dataset_10 ·/)).not.toBeInTheDocument();
    expect(screen.getByText("metric_9 · Integer")).toBeInTheDocument();
    expect(screen.queryByText("metric_10 · Integer")).not.toBeInTheDocument();
    fireEvent.click(within(screen.getByLabelText("数据集分页")).getByText("下一页"));
    expect(screen.getByText(/dataset_10 ·/)).toBeInTheDocument();
    fireEvent.click(within(screen.getByLabelText("指标分页")).getByText("下一页"));
    expect(screen.getByText("metric_10 · Integer")).toBeInTheDocument();
    expect(screen.getByText("id = parent_id")).toBeInTheDocument();
    expect(screen.getByText("tenant = tenant_id")).toBeInTheDocument();
  });
  it("shows full expressions, dimensions, aliases and zero/many metric concepts", () => {
    render(<SemanticCatalogView catalog={catalog} />);
    expand(/治理 · 41 数据集/);
    expand(/dataset_0 ·/);
    expect(screen.getByText("ANSI_SQL: column_0")).toBeInTheDocument();
    expect(screen.getAllByText(/非时间维度 · 同义词：字段别名/)).toHaveLength(20);
    expect(screen.getByText("归属概念：系统 (system)、组件 (component)")).toBeInTheDocument();
    expect(screen.getAllByText("归属概念：无")).toHaveLength(9);
    expect(screen.getAllByText("同义词：REDACTED")).toHaveLength(10);
    fireEvent.click(within(screen.getByLabelText("dataset_0字段分页")).getByText("下一页"));
    expect(screen.getByText("ANSI_SQL: column_34")).toBeInTheDocument();
    expect(screen.queryByText("ANSI_SQL: column_0")).not.toBeInTheDocument();
  });
  it("prevents the simple form from replacing a complex tree", () => {
    const draft: LegacyDraft = { ...emptyDraft("w"), object_types: [{ id: "c", name: "组件", technical_name: "component", description: "", extends: [], tags: [], evidence: [] }], mapping_status: { c: { state: "readonly", reason: "multiple_roots", message: "复杂映射：暂只读（多根映射）", dataset_id: null } } };
    render(<MappingPanel draft={draft} type={draft.object_types[0]} editing change={vi.fn()} open={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("复杂映射：暂只读");
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
  });
});
