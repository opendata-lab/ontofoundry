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
  vi.spyOn(api, "types").mockResolvedValue({
    items: [], workspace_id: workspace.id, version_id: "version-demo", version_sha256: "demo-sha",
    version_content_sha256: "demo-content-sha", normalized_snapshot_sha256: "demo-snapshot-sha",
    next_cursor: null, ambiguous: false,
  });
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("应用框架", () => {
  it("保留导航链接、当前页标记及收起后的提示，支持展开", async () => {
    show();
    const nav = await screen.findByRole("navigation", { name: "工作空间导航" });
    expect(within(nav).getByRole("link", { name: "数据映射" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "本体发布" })).toHaveAttribute("href", "/workspaces/ws-shell-demo/delivery");
    fireEvent.click(screen.getByRole("button", { name: "收起导航" }));
    expect(within(nav).getByTitle("数据映射")).toHaveAttribute("href", "/workspaces/ws-shell-demo/mappings");
    expect(within(nav).queryByText("本体管理")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "展开导航" }));
    expect(within(nav).getByRole("link", { name: "数据映射" })).toBeVisible();
  });

  it("访客只能看到已发布本体和发布页面", async () => {
    vi.mocked(api.workspace).mockResolvedValue({ ...workspace, role: null });
    show();
    const nav = await screen.findByRole("navigation", { name: "工作空间导航" });
    expect(within(nav).getAllByRole("link")).toHaveLength(4);
    expect(within(nav).queryByRole("link", { name: "数据映射" })).toBeNull();
    expect(within(nav).queryByRole("link", { name: "空间设置" })).toBeNull();
  });

  it("快捷键和顶栏搜索均可打开搜索，空结果与关闭保持可用", async () => {
    show();
    await screen.findByText("页面区域");
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    let dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("暂无已发布本体")).toBeVisible();
    fireEvent.change(within(dialog).getByRole("textbox", { name: "搜索关键词" }), { target: { value: "示例" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "搜索本体" }));
    dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("textbox", { name: "搜索关键词" })).toHaveValue("");
    expect(api.types).toHaveBeenCalledTimes(2);
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
