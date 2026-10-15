import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { modelingApi } from "../api/client";
import { useSnapshot } from "../hooks/useSnapshot";
import { toView } from "../lib/draftView";
import { nativeMappingFixture } from "../lib/objectMapping.fixture";
import { MappingsPage } from "./MappingsPage";

const { open, workspace } = vi.hoisted(() => ({
  open: vi.fn(),
  workspace: { id: "w", role: "admin", current_version: 1 },
}));
vi.mock("../hooks/useWorkspaceContext", () => ({
  useWorkspaceContext: () => ({ workspace }),
}));
vi.mock("../hooks/useElementInspector", () => ({
  useElementInspector: () => ({ open }),
}));
vi.mock("../hooks/useSnapshot", () => ({ useSnapshot: vi.fn() }));
vi.mock("../hooks/usePageTab", () => ({
  usePageTab: vi.fn(),
  usePageActive: () => true,
}));
vi.mock("../api/client", () => ({
  modelingApi: { connections: vi.fn(), tables: vi.fn() },
}));
vi.mock("../components/SemanticModels", () => ({
  SemanticModels: () => <h3>语义模型管理</h3>,
}));
vi.mock("../components/DataAssets", () => ({
  DataAssets: () => <h3>资产管理</h3>,
}));
beforeEach(() => {
  vi.clearAllMocks();
  const sourceDraft = nativeMappingFixture();
  vi.mocked(useSnapshot).mockReturnValue({
    sourceDraft,
    draft: toView(sourceDraft),
    error: "",
    sessionId: "s",
    suffix: "?session=s",
    load: vi.fn(),
    setDraft: vi.fn(),
  });
  vi.mocked(modelingApi.connections).mockResolvedValue({ items: [] });
  vi.mocked(modelingApi.tables).mockResolvedValue({ items: [] });
});
afterEach(cleanup);

describe("approved mapping index", () => {
  it("shows a single business object table with identifier tag and coverage status", () => {
    render(<MappingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "本体映射" }));
    expect(screen.getAllByRole("table")).toHaveLength(1);
    const headers = screen.getAllByRole("columnheader");
    expect(headers.slice(0, 3).map((h) => h.textContent)).toEqual([
      "业务对象",
      "标识字段",
      "来源表",
    ]);
    expect(headers[3]).toHaveTextContent("覆盖");
    const row = screen.getByRole("button", { name: "供应商" }).closest("tr")!;
    expect(within(row).getByText("标识")).toHaveClass("om-tag-key");
    expect(row).toHaveTextContent("public.dim_supplier");
    expect(row).toHaveTextContent("1/2");
    expect(row).toHaveTextContent("部分映射");
    expect(screen.queryByText("复杂映射")).not.toBeInTheDocument();
    expect(screen.queryByText("语义模型管理")).not.toBeInTheDocument();
    expect(screen.queryByText("资产管理")).not.toBeInTheDocument();
  });
  it("filters by coverage and searches names, technical names and source tables", () => {
    render(<MappingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "本体映射" }));
    const statuses = screen.getByRole("group", { name: "映射状态" });
    expect(
      within(statuses)
        .getAllByRole("button")
        .map((b) => b.textContent),
    ).toEqual(["全部2", "已映射1", "部分映射1", "未映射0"]);
    fireEvent.click(
      within(statuses).getByRole("button", { name: "部分映射 1" }),
    );
    expect(
      screen.queryByRole("button", { name: "产品" }),
    ).not.toBeInTheDocument();
    fireEvent.click(within(statuses).getByRole("button", { name: "全部 2" }));
    const search = screen.getByRole("textbox", {
      name: "搜索对象、英文名或表",
    });
    fireEvent.change(search, { target: { value: "DIM_PRODUCT" } });
    // Supplier also references this table through its relation target only when physically mapped there;
    // the index searches actual source tables, not the target object's own table.
    expect(screen.getByRole("button", { name: "产品" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "供应商" }),
    ).not.toBeInTheDocument();
    fireEvent.change(search, { target: { value: "SUPPLIER" } });
    expect(screen.getByRole("button", { name: "供应商" })).toBeInTheDocument();
    fireEvent.change(search, { target: { value: "不存在" } });
    expect(screen.getByText("没有匹配对象")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "清除筛选" }));
    expect(search).toHaveValue("");
  });
  it("opens a row on 属性与映射 and retains the session source", () => {
    render(<MappingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "本体映射" }));
    const row = screen.getByRole("button", { name: "供应商" }).closest("tr")!;
    fireEvent.click(within(row).getAllByRole("cell")[1]);
    expect(open).toHaveBeenCalledWith({
      kind: "object_type",
      id: nativeMappingFixture().object_types[0].id,
      tab: "properties",
      sessionId: "s",
    });
  });
  it("keeps 数据源与资产 / 本体映射 / 语义模型 as page tabs without 高级", async () => {
    render(<MappingsPage />);
    const tabs = screen.getByRole("group", { name: "数据映射视图" });
    expect(within(tabs).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "数据源与资产",
      "本体映射",
      "语义模型",
    ]);
    expect(screen.getByRole("heading", { name: "资产管理" })).toBeInTheDocument();
    fireEvent.click(within(tabs).getByRole("button", { name: "语义模型" }));
    expect(screen.getByRole("heading", { name: "语义模型管理" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "高级" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "查找表" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "浏览数据目录" }));
    const browser = await screen.findByRole("dialog", { name: "浏览数据目录" });
    expect(within(browser).getByText("public.fact_calls")).toBeInTheDocument();
    const search = within(browser).getByRole("textbox", {
      name: "搜索表或字段",
    });
    fireEvent.change(search, { target: { value: "supplier_name" } });
    expect(within(browser).getByText("public.fact_calls")).toBeInTheDocument();
    expect(
      within(browser).queryByText("public.dim_product"),
    ).not.toBeInTheDocument();
  });
});
