import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { User, Workspace } from "../api/types";
import { renderWithProviders } from "../test/renderWithProviders";
import { AppShell } from "./AppShell";

vi.mock("./WorkspaceTabs", () => ({ WorkspaceTabs: () => <div>页面区域</div> }));

const workspace: Workspace = {
  id: "ws-shell-demo", name: "星河示例空间", slug: "xinghe-demo", description: "虚构示例",
  current_version: 1, version_id: "version-demo", role: "admin",
  visibility: "member", version_sha256: "demo-sha", object_type_count: 0, link_type_count: 0,
  updated_at: "2026-10-17T00:00:00Z",
};
const user: User = { id: "user-demo", subject: "demo:user", display_name: "林晓", email: null };

function show() {
  const router = createMemoryRouter([
    { path: "/workspaces/:workspaceId/*", element: <AppShell /> },
  ], { initialEntries: ["/workspaces/ws-shell-demo/mappings"] });
  renderWithProviders(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  vi.spyOn(api, "workspace").mockResolvedValue(workspace);
  vi.spyOn(api, "me").mockResolvedValue(user);
  vi.spyOn(api, "searchOntology").mockResolvedValue({
    workspace_id: workspace.id, version_id: "version-demo", retrieval: { keyword: true, vector: false },
    items: [
      { id: "metric-demo", kind: "metric", display_name: "采购金额", name: "purchase_amount", summary: "", matched_synonyms: [], match: { by: "name_in_query", text: "采购金额" } },
      { id: "type-demo", kind: "object_type", display_name: "供应商", name: "supplier", summary: "", matched_synonyms: [], match: { by: "expansion", via: { id: "metric-demo", relation: "metric_dataset_bound_type" } } },
    ],
    unmatched_terms: ["星河电子近三个月的"], total: 2, next_cursor: null,
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("应用框架", () => {
  it("保留导航链接、当前页标记及收起后的提示，支持展开", async () => {
    show();
    const nav = await screen.findByRole("navigation", { name: "工作空间导航" });
    expect(within(nav).getByRole("link", { name: "数据管理" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "数据连接" })).toHaveAttribute("href", "/workspaces/ws-shell-demo/connections");
    fireEvent.click(screen.getByRole("button", { name: "收起导航" }));
    expect(within(nav).getByTitle("数据管理")).toHaveAttribute("href", "/workspaces/ws-shell-demo/mappings");
    expect(within(nav).queryByText("本体管理")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "展开导航" }));
    expect(within(nav).getByRole("link", { name: "数据管理" })).toBeVisible();
  });

  it("访客只能看到已发布本体和发布页面", async () => {
    vi.mocked(api.workspace).mockResolvedValue({ ...workspace, role: null });
    show();
    const nav = await screen.findByRole("navigation", { name: "工作空间导航" });
    expect(within(nav).getAllByRole("link")).toHaveLength(2);
    expect(within(nav).getByRole("link", { name: "本体视图" })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "本体对象" })).toBeInTheDocument();
    expect(within(nav).queryByRole("link", { name: "本体构建" })).toBeNull();
    expect(within(nav).queryByRole("link", { name: "数据管理" })).toBeNull();
    expect(within(nav).queryByRole("link", { name: "空间设置" })).toBeNull();
  });

  it("快捷键和顶栏搜索均可打开搜索，按问题检索并说明命中原因，关闭后清空", async () => {
    show();
    await screen.findByText("页面区域");
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    let dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("输入名称、同义词或一句业务问题")).toBeVisible();
    expect(api.searchOntology).not.toHaveBeenCalled();
    fireEvent.change(within(dialog).getByRole("textbox", { name: "搜索关键词" }), { target: { value: "星河电子近三个月的采购金额" } });
    expect(await within(dialog).findByText("命中「采购金额」")).toBeVisible();
    expect(within(dialog).getByText("由「采购金额」扩展：指标数据集绑定的实体")).toBeVisible();
    expect(within(dialog).getByText("未匹配到定义：星河电子近三个月的")).toBeVisible();
    expect(api.searchOntology).toHaveBeenCalledWith(workspace.id, { query: "星河电子近三个月的采购金额", limit: 20 });
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "搜索本体" }));
    dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("textbox", { name: "搜索关键词" })).toHaveValue("");
    expect(within(dialog).queryByText("命中「采购金额」")).toBeNull();
  });

  it("读取失败时可以重试并恢复整个框架", async () => {
    vi.mocked(api.workspace).mockRejectedValueOnce(new Error("示例读取失败"));
    show();
    expect(await screen.findByRole("alert")).toHaveTextContent("示例读取失败");
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
    await screen.findByRole("navigation", { name: "工作空间导航" });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
