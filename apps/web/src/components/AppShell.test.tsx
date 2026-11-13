import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "../api/client";
import type { User, Workspace } from "../api/types";
import { renderWithProviders } from "../test/renderWithProviders";
import { AppShell } from "./AppShell";

vi.mock("./WorkspaceTabs", () => ({ WorkspaceTabs: () => <div>页面区域</div> }));

const workspace: Workspace = {
  id: "ws-shell-demo", name: "星河示例空间", slug: "xinghe-demo", description: "虚构示例",
  current_version: 1, version_id: "version-demo", is_public: false, role: "admin",
  visibility: "member", version_sha256: "demo-sha", object_type_count: 0, link_type_count: 0,
  updated_at: "2026-10-17T00:00:00Z",
};
const user: User = {
  id: "user-demo", username: "linxiao", display_name: "林晓", email: null,
  is_platform_admin: false, local_account: true,
};

function show() {
  const router = createMemoryRouter([
    { path: "/workspaces/:workspaceId/*", element: <AppShell /> },
    { path: "/me", element: <p>个人中心页</p> },
    { path: "/admin/users", element: <p>用户管理页</p> },
    { path: "/admin/audit", element: <p>用户审计页</p> },
    { path: "/login", element: <p>登录页</p> },
    { path: "/", element: <p>目录页</p> },
  ], { initialEntries: ["/workspaces/ws-shell-demo/mappings"] });
  renderWithProviders(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  vi.spyOn(api, "workspace").mockResolvedValue(workspace);
  vi.spyOn(api, "me").mockResolvedValue(user);
  vi.spyOn(api, "logout").mockResolvedValue(undefined);
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

  it("管理员看到本体管理末尾的用户反馈，以及不带分组标题的一级空间设置", async () => {
    show();
    const nav = await screen.findByRole("navigation", { name: "工作空间导航" });
    const ontologyGroup = within(nav).getByRole("group", { name: "本体管理" });
    const ontologyLinks = within(ontologyGroup).getAllByRole("link");
    expect(ontologyLinks.map((el) => el.textContent?.trim())).toEqual([
      "本体视图",
      "本体对象",
      "本体构建",
      "用户反馈",
    ]);
    expect(within(ontologyGroup).getByRole("link", { name: "用户反馈" })).toHaveAttribute(
      "href",
      "/workspaces/ws-shell-demo/feedback",
    );

    const settingsLink = within(nav).getByRole("link", { name: "空间设置" });
    expect(settingsLink).toHaveAttribute("href", "/workspaces/ws-shell-demo/settings");
    expect(within(nav).queryByRole("heading", { name: "空间设置" })).toBeNull();
    expect(within(nav).queryByRole("group", { name: "空间设置" })).toBeNull();
  });

  it("可编辑成员、可查看成员与公开非成员隐藏用户反馈和空间设置", async () => {
    vi.mocked(api.workspace).mockResolvedValueOnce({ ...workspace, role: "member" });
    show();
    const memberNav = await screen.findByRole("navigation", { name: "工作空间导航" });
    expect(within(memberNav).getAllByRole("link")).toHaveLength(5);
    expect(within(memberNav).queryByRole("link", { name: "用户反馈" })).toBeNull();
    expect(within(memberNav).queryByRole("link", { name: "空间设置" })).toBeNull();

    cleanup();
    vi.mocked(api.workspace).mockResolvedValueOnce({ ...workspace, role: "viewer" });
    const first = show();
    const viewerNav = await screen.findByRole("navigation", { name: "工作空间导航" });
    expect(within(viewerNav).getAllByRole("link")).toHaveLength(5);
    expect(within(viewerNav).getByRole("link", { name: "本体构建" })).toBeInTheDocument();
    expect(within(viewerNav).getByRole("link", { name: "数据连接" })).toBeInTheDocument();
    expect(within(viewerNav).getByRole("link", { name: "数据管理" })).toBeInTheDocument();
    expect(within(viewerNav).queryByRole("link", { name: "用户反馈" })).toBeNull();
    expect(within(viewerNav).queryByRole("link", { name: "空间设置" })).toBeNull();
    expect(screen.getByText("你是本空间的可查看成员，只能查看")).toBeInTheDocument();
    expect(first.state.location.pathname).toBe("/workspaces/ws-shell-demo/mappings");

    cleanup();
    vi.mocked(api.workspace).mockResolvedValueOnce({
      ...workspace, role: null, is_public: true, visibility: "public",
    });
    show();
    const publicNav = await screen.findByRole("navigation", { name: "工作空间导航" });
    expect(within(publicNav).getAllByRole("link")).toHaveLength(5);
    expect(within(publicNav).queryByRole("link", { name: "用户反馈" })).toBeNull();
    expect(within(publicNav).queryByRole("link", { name: "空间设置" })).toBeNull();
    expect(screen.getByText("你不是本空间成员，只能阅读")).toBeInTheDocument();

    cleanup();
    vi.mocked(api.workspace).mockResolvedValueOnce({ ...workspace, role: null, is_public: true, visibility: "public" });
    vi.mocked(api.me).mockResolvedValueOnce({ ...user, is_platform_admin: true });
    show();
    const platformAdminNav = await screen.findByRole("navigation", { name: "工作空间导航" });
    expect(within(platformAdminNav).getByRole("link", { name: "用户反馈" })).toBeInTheDocument();
    expect(within(platformAdminNav).getByRole("link", { name: "空间设置" })).toBeInTheDocument();
  });

  it("私有非成员收到 403 时展示无权限结果并保留平台导航", async () => {
    vi.mocked(api.workspace).mockRejectedValueOnce(new ApiError("无权限", 403));
    show();
    expect(await screen.findByText("无权访问")).toBeInTheDocument();
    expect(screen.getByText("该工作空间不存在，或你不是该私有空间的成员。")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "返回工作空间目录" })).toBeInTheDocument();
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

  it("普通用户菜单展示个人中心与退出登录，不展示用户管理，点击退出后跳转登录页", async () => {
    const router = show();
    const userButton = await screen.findByRole("button", { name: /林晓/ });
    fireEvent.click(userButton);

    const menu = await screen.findByRole("menu");
    const items = within(menu).getAllByRole("menuitem");
    expect(items.map((item) => item.textContent?.trim())).toEqual(["个人中心", "退出登录"]);

    fireEvent.click(within(menu).getByRole("menuitem", { name: /退出登录/ }));
    await waitFor(() => {
      expect(api.logout).toHaveBeenCalledTimes(1);
      expect(router.state.location.pathname).toBe("/login");
    });
  });

  it("平台管理员菜单展示用户管理与用户审计并可跳转到对应页面", async () => {
    vi.mocked(api.me).mockResolvedValue({ ...user, is_platform_admin: true });
    const router = show();
    fireEvent.click(await screen.findByRole("button", { name: /林晓/ }));

    const menu = await screen.findByRole("menu");
    const items = within(menu).getAllByRole("menuitem");
    expect(items.map((item) => item.textContent?.trim())).toEqual([
      "个人中心",
      "用户管理",
      "用户审计",
      "退出登录",
    ]);

    fireEvent.click(within(menu).getByRole("menuitem", { name: /用户审计/ }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/admin/audit"));
  });
});

describe("侧栏顶部的工作空间切换", () => {
  it("列出可读空间并切换，另可回到全部工作空间", async () => {
    const other: Workspace = { ...workspace, id: "ws-other-demo", name: "北辰示例空间", is_public: true, role: null, visibility: "public" };
    const list = vi.spyOn(api, "workspaces").mockResolvedValue({ items: [workspace, other] });
    const router = show();
    const switcher = await screen.findByRole("button", { name: "切换工作空间（当前：星河示例空间）" });
    expect(screen.queryByRole("link", { name: /星河示例空间/ })).toBeNull();
    fireEvent.click(switcher);
    expect(await screen.findByText("北辰示例空间")).toBeVisible();
    expect(screen.getByText("公开")).toBeVisible();
    expect(list).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByText("北辰示例空间"));
    await waitFor(() => expect(router.state.location.pathname).toBe("/workspaces/ws-other-demo/view"));
  });

  it("“全部工作空间”回到目录", async () => {
    vi.spyOn(api, "workspaces").mockResolvedValue({ items: [workspace] });
    const router = show();
    fireEvent.click(await screen.findByRole("button", { name: "切换工作空间（当前：星河示例空间）" }));
    fireEvent.click(await screen.findByText("全部工作空间"));
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });
});
