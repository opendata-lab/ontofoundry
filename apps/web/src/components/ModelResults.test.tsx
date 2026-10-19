import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ModelingSession } from "../api/types";
import { example } from "../test/drafts";
import { renderWithProviders } from "../test/renderWithProviders";
import { ModelResults } from "./ModelResults";

vi.mock("./OntologyGraph", () => ({
  OntologyGraph: ({ graph }: { graph: { nodes: unknown[] } }) => <div data-testid="semantic-graph">{graph.nodes.length}</div>,
}));
afterEach(cleanup);

function session(extra: Partial<ModelingSession> = {}): ModelingSession {
  return {
    id: "s",
    title: "测试",
    workspace_id: "w",
    base_version_id: null,
    revision: 0,
    draft: example("01-basic-sales"),
    graph: { workspace_id: "w", version_id: "", version_sha256: "", nodes: [], edges: [] },
    base_diff: [],
    pending_proposal_count: 0,
    latest_batch_id: null,
    result_warnings: [],
    ...extra,
  } as unknown as ModelingSession;
}
const show = (s: ModelingSession | null) =>
  renderWithProviders(
    <MemoryRouter>
      <ModelResults session={s} />
    </MemoryRouter>,
  );

describe("modeling results", () => {
  it("counts every kind in the draft and searches within one", () => {
    show(session());
    expect(screen.getByRole("button", { name: "实体 2" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "指标 10" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "数据集 2" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "属性 8" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索模型" }), { target: { value: "region" } });
    expect(screen.getAllByRole("row")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "所在地区" })).toBeInTheDocument();
  });

  it("marks changes against the base version, including deletions", () => {
    const s = session();
    const customer = s.draft.object_types[0];
    show(
      session({
        base_diff: [
          { element_kind: "object_type", element_id: customer.id, label: customer.name, change: "updated", field_changes: [], before: null, after: null },
          { element_kind: "object_type", element_id: "gone", label: "旧对象", change: "deleted", field_changes: [], before: { technical_name: "old" } as never, after: null },
        ],
      }),
    );
    expect(within(screen.getByRole("button", { name: customer.name }).closest("tr")!).getByText("已修改")).toBeInTheDocument();
    expect(within(screen.getByText("旧对象").closest("tr")!).getByText("待删除")).toBeInTheDocument();
  });

  it("draws the draft when the server graph is empty and shows notes from the last run", () => {
    show(session({ result_warnings: ["有 1 张表没有主键"] }));
    expect(screen.getByText("有 1 张表没有主键")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "语义图谱" }));
    expect(screen.getByTestId("semantic-graph")).toHaveTextContent("2");
  });

  it("has an honest empty state before generation", () => {
    show(null);
    expect(screen.getByText("暂无构建结果")).toBeInTheDocument();
  });

  it("shows material_link rows with endpoint display names and Chinese binding mode labels for mappings", () => {
    show(session({ draft: example("07-instances-and-evidence") }));
    fireEvent.click(screen.getByRole("button", { name: /^文档关系 \d+$/ }));
    expect(screen.getByRole("button", { name: /RT-0103 → C001/ })).toBeInTheDocument();

    cleanup();
    show(session({ draft: example("06-inheritance") }));
    fireEvent.click(screen.getByRole("button", { name: /^映射 \d+$/ }));
    expect(screen.getAllByText("独立绑定").length).toBeGreaterThan(0);
    expect(screen.getAllByText("共用父对象数据").length).toBeGreaterThan(0);
    expect(screen.queryByText("independent")).not.toBeInTheDocument();
    expect(screen.queryByText("shared_parent")).not.toBeInTheDocument();
  });
});
