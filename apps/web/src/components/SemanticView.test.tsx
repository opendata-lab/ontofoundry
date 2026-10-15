import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { GraphNode, TypeGraph } from "../api/types";
import type { SelectedGraphItem } from "./OntologyGraph";
import { emptyDraft } from "../lib/draftView";
import { SemanticView } from "./SemanticView";
vi.mock("./OntologyGraph", () => ({
  OntologyGraph: ({
    graph,
    selection,
    onSelect,
  }: {
    graph: TypeGraph;
    selection: SelectedGraphItem;
    onSelect: (item: SelectedGraphItem) => void;
  }) => (
    <div data-testid="canvas" data-selection={selection?.item.id ?? ""}>
      {graph.nodes.map((item) => (
        <button
          key={item.id}
          onClick={() => onSelect({ category: "node", item })}
        >
          {item.label}
        </button>
      ))}
      {graph.edges.map((item) => (
        <button
          key={item.id}
          onClick={() => onSelect({ category: "edge", item })}
        >
          {item.label}
        </button>
      ))}
      <button onClick={() => onSelect(null)}>清空画布</button>
    </div>
  ),
}));
const node = (
  id: string,
  label: string,
  kind: GraphNode["kind"] = "object_type",
): GraphNode => ({
  id,
  label,
  technical_name: id,
  kind,
  tags: [],
  description: "",
});
const graph: TypeGraph = {
  workspace_id: "w",
  version_id: "v",
  version_sha256: "h",
  nodes: [
    node("supplier", "供应商"),
    node("product", "产品"),
    node("value", "金额", "value_type"),
  ],
  edges: [
    {
      id: "supply",
      kind: "link_type",
      source: "supplier",
      target: "product",
      label: "供应",
      technical_name: "supply",
    },
  ],
};
const onOpen = vi.fn();
beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
const explorer = () =>
  screen.getByRole("complementary", { name: "资源管理器" });

describe("semantic resource explorer", () => {
  it("filters names and technical names, keeps nonempty group headers present, and scrolls inside groups", () => {
    const { container } = render(
      <SemanticView graph={graph} onOpen={onOpen} />,
    );
    expect(
      within(explorer()).getByRole("button", { name: "业务对象 2" }),
    ).toBeInTheDocument();
    expect(
      within(explorer()).getByRole("button", { name: "本体关系 1" }),
    ).toBeInTheDocument();
    expect(
      within(explorer()).getByRole("button", { name: "值类型 1" }),
    ).toBeInTheDocument();
    expect(
      within(explorer()).queryByRole("button", { name: /^规则/ }),
    ).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox", { name: "名称筛选" }), {
      target: { value: "supplier" },
    });
    expect(
      within(explorer()).getByRole("button", { name: "供应商" }),
    ).toBeInTheDocument();
    expect(
      within(explorer()).queryByRole("button", { name: "产品" }),
    ).not.toBeInTheDocument();
    expect(
      within(explorer()).getByRole("button", { name: "本体关系 0 / 1" }),
    ).toBeInTheDocument();
    expect(container.querySelectorAll(".semantic-group-heading")).toHaveLength(
      3,
    );
    expect(container.querySelectorAll(".semantic-group-items")).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "清空名称筛选" }));
    expect(
      within(explorer()).getByRole("button", { name: "产品" }),
    ).toBeInTheDocument();
  });
  it("synchronizes tree to graph and graph to tree, restores filtered groups, and clears with Esc", () => {
    render(<SemanticView graph={graph} onOpen={onOpen} />);
    fireEvent.click(within(explorer()).getByRole("button", { name: "供应商" }));
    expect(screen.getByTestId("canvas")).toHaveAttribute(
      "data-selection",
      "supplier",
    );
    expect(onOpen).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "打开选中资源详情" }));
    expect(onOpen).toHaveBeenCalledWith(
      expect.objectContaining({
        kind: "object_type",
        id: "supplier",
        tab: "basic",
      }),
    );
    fireEvent.change(screen.getByRole("searchbox", { name: "名称筛选" }), {
      target: { value: "supplier" },
    });
    fireEvent.click(
      within(explorer()).getByRole("button", { name: "业务对象 1 / 2" }),
    );
    fireEvent.click(
      within(screen.getByTestId("canvas")).getByRole("button", {
        name: "产品",
      }),
    );
    expect(screen.getByRole("searchbox", { name: "名称筛选" })).toHaveValue("");
    expect(
      within(explorer()).getByRole("button", { name: "业务对象 2" }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(
      within(explorer()).getByRole("button", { name: "产品" }),
    ).toHaveAttribute("aria-pressed", "true");
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.getByTestId("canvas")).toHaveAttribute("data-selection", "");
    expect(
      screen.queryByRole("button", { name: "清除选择" }),
    ).not.toBeInTheDocument();
  });
  it("persists collapse and restores it without losing access to name filtering", () => {
    const view = render(<SemanticView graph={graph} onOpen={onOpen} />);
    fireEvent.click(screen.getByRole("button", { name: "收起资源管理器" }));
    expect(
      localStorage.getItem("ontofoundry.semantic.explorer.collapsed"),
    ).toBe("true");
    expect(
      screen.queryByRole("searchbox", { name: "名称筛选" }),
    ).not.toBeInTheDocument();
    view.unmount();
    render(<SemanticView graph={graph} onOpen={onOpen} />);
    expect(
      screen.getByRole("button", { name: "展开资源管理器" }),
    ).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(screen.getByRole("button", { name: "展开并筛选名称" }));
    expect(
      screen.getByRole("searchbox", { name: "名称筛选" }),
    ).toBeInTheDocument();
  });
  it("continues working when localStorage reads and writes throw", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    render(<SemanticView graph={graph} onOpen={onOpen} />);
    fireEvent.click(screen.getByRole("button", { name: "收起资源管理器" }));
    fireEvent.click(screen.getByRole("button", { name: "展开资源管理器" }));
    expect(
      screen.getByRole("searchbox", { name: "名称筛选" }),
    ).toBeInTheDocument();
  });
  it("shows real rule expressions in their own group and sends details to the owning popup", () => {
    const model = emptyDraft("w");
    model.rules = [
      {
        id: "r",
        owner_kind: "object_type",
        owner_id: "supplier",
        name: "auto·constraint1",
        technical_name: "internal",
        rule_kind: "constraint",
        expression: "count > 0",
        description: "",
        verbalizes: [],
        evidence: [],
      },
    ];
    render(<SemanticView graph={graph} model={model} onOpen={onOpen} />);
    expect(
      within(explorer()).getByRole("button", { name: "规则 1" }),
    ).toBeInTheDocument();
    fireEvent.click(
      within(explorer()).getByText("count > 0").closest("button")!,
    );
    expect(screen.queryByText("auto·constraint1")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "打开选中资源详情" }));
    expect(onOpen).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "rule", id: "r", tab: "rules" }),
    );
  });
});
