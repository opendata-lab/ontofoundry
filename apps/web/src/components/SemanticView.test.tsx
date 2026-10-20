import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { draftGraph } from "../lib/semanticExplorer";
import { example } from "../test/drafts";
import { renderWithProviders } from "../test/renderWithProviders";
import { SemanticView } from "./SemanticView";

vi.mock("./OntologyGraph", () => ({
  OntologyGraph: ({ graph }: { graph: { nodes: unknown[]; edges: unknown[] } }) => (
    <div data-testid="graph">
      {graph.nodes.length} 节点 {graph.edges.length} 边
    </div>
  ),
}));
afterEach(cleanup);

const draft = example("01-basic-sales");
const graph = draftGraph(draft);

describe("semantic view", () => {
  it("groups objects, relations, metrics and datasets and only draws the ontology", () => {
    renderWithProviders(<SemanticView graph={graph} model={draft} onOpen={vi.fn()} onOpenPage={vi.fn()} />);
    const tree = screen.getByLabelText("本体资源");
    for (const [label, count] of [["对象", 2], ["关系", 1], ["指标", 10], ["数据集", 2]] as const)
      expect(within(tree).getByText(label).parentElement).toHaveTextContent(`${label}${count}`);
    expect(screen.getByTestId("graph")).toHaveTextContent("2 节点 1 边");
  });

  it("lists metrics in a table with a create entry and opens details", () => {
    const onOpen = vi.fn();
    renderWithProviders(<SemanticView graph={graph} model={draft} onOpen={vi.fn()} onOpenPage={onOpen} canCreate />);
    fireEvent.click(screen.getByText("指标", { selector: ".ant-segmented-item-label" }));
    expect(screen.queryByTestId("graph")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "新建指标" }));
    expect(onOpen).toHaveBeenCalledWith({ kind: "metric", id: "new", mode: "edit", sessionId: null });
    const table = screen.getByRole("table");
    fireEvent.click(within(table).getByRole("button", { name: "订单金额" }));
    expect(onOpen).toHaveBeenLastCalledWith(expect.objectContaining({ kind: "metric" }));
  });

  it("filters by name and technical name", () => {
    renderWithProviders(<SemanticView graph={graph} model={draft} onOpen={vi.fn()} onOpenPage={vi.fn()} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "名称筛选" }), { target: { value: "order_amount" } });
    const tree = screen.getByLabelText("本体资源");
    expect(within(tree).getByText("指标").parentElement).toHaveTextContent("指标3 / 10");
    expect(within(tree).getByText("订单金额")).toBeInTheDocument();
  });

  it("keeps working when storage throws", () => {
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    renderWithProviders(<SemanticView graph={graph} model={draft} onOpen={vi.fn()} onOpenPage={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /收起资源管理器|展开资源管理器/ }));
    expect(screen.getByRole("button", { name: /资源管理器/ })).toBeInTheDocument();
    get.mockRestore();
    set.mockRestore();
  });
});
