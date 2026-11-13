import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { adminApi, api } from "../api/client";
import type {
  AdminUser,
  AdminWorkspace,
  GatewayCallDetail,
  GatewayCallSummary,
  User,
} from "../api/types";
import { renderWithProviders } from "../test/renderWithProviders";
import { AdminAuditPage } from "./AdminAuditPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      me: vi.fn(),
      logout: vi.fn(),
    },
    adminApi: {
      users: vi.fn(),
      createUser: vi.fn(),
      workspaces: vi.fn(),
      setUserWorkspace: vi.fn(),
      removeUserWorkspace: vi.fn(),
      gatewayCalls: vi.fn(),
      gatewayCall: vi.fn(),
    },
  };
});

const platformAdmin: User = {
  id: "u-admin",
  username: "admin",
  display_name: "系统管理员",
  email: "admin@example.com",
  is_platform_admin: true,
  local_account: true,
};

const usersList: AdminUser[] = [
  {
    id: "u-1",
    username: "wangwu",
    display_name: "王五",
    email: null,
    local_account: false,
    platform_admin: false,
    last_login_at: "2026-11-12T08:00:00Z",
    workspaces: [{ id: "w1", name: "星港采购空间", role: "member" }],
  },
];

const workspacesList: AdminWorkspace[] = [
  { id: "w1", name: "星港采购空间", is_public: false },
  { id: "w2", name: "星港销售空间", is_public: true },
];

const callItems: GatewayCallSummary[] = [
  {
    id: "call-1",
    created_at: "2026-11-13T08:30:00Z",
    user: { id: "u-1", display_name: "王五" },
    tool: "search_ontology",
    workspaces: [{ id: "w1", name: "星港采购空间", version_number: 13 }],
    summary: "净采购额 含税",
    outcome: "ok",
    error_code: null,
    duration_ms: 42,
  },
  {
    id: "call-2",
    created_at: "2026-11-13T08:25:00Z",
    user: { id: "u-1", display_name: "王五" },
    tool: "get_ontology",
    workspaces: [{ id: "ws-deleted", name: null, version_number: null }],
    summary: "2 个元素",
    outcome: "error",
    error_code: "workspace_unavailable",
    duration_ms: 8,
  },
  {
    id: "call-3",
    created_at: "2026-11-13T08:20:00Z",
    user: { id: "u-1", display_name: "王五" },
    tool: "list_spaces",
    workspaces: [],
    summary: "—",
    outcome: "started",
    error_code: null,
    duration_ms: null,
  },
];

const callDetailError: GatewayCallDetail = {
  id: "call-2",
  created_at: "2026-11-13T08:25:00Z",
  user: { id: "u-1", display_name: "王五" },
  tool: "get_ontology",
  request_id: "req-99",
  workspaces: [
    {
      id: "ws-deleted",
      name: null,
      version_id: null,
      version_number: null,
    },
  ],
  arguments: { workspace_id: "ws-deleted", ids: ["el-a", "el-b"] },
  response: { error: { code: "workspace_unavailable", message: "空间不可访问" } },
  outcome: "error",
  error_code: "workspace_unavailable",
  error_message: "空间不存在或当前用户无权访问",
  duration_ms: 8,
};

function show() {
  const router = createMemoryRouter(
    [
      { path: "/admin/audit", element: <AdminAuditPage /> },
      { path: "/", element: <p>工作空间目录</p> },
    ],
    { initialEntries: ["/admin/audit"] },
  );
  renderWithProviders(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.me).mockResolvedValue(platformAdmin);
  vi.mocked(adminApi.users).mockResolvedValue({ items: usersList });
  vi.mocked(adminApi.workspaces).mockResolvedValue({ items: workspacesList });
  vi.mocked(adminApi.gatewayCalls).mockResolvedValue({
    items: callItems,
    next_cursor: null,
  });
  vi.mocked(adminApi.gatewayCall).mockResolvedValue(callDetailError);
});

afterEach(cleanup);

describe("用户审计页", () => {
  it("非平台管理员访问 /admin/audit 显示 403 无权访问", async () => {
    vi.mocked(api.me).mockResolvedValue({
      ...platformAdmin,
      is_platform_admin: false,
    });
    show();

    expect(await screen.findByText("无权访问")).toBeInTheDocument();
    expect(
      screen.getByText("只有平台管理员（ADMIN_USERS）可以访问用户审计。"),
    ).toBeInTheDocument();
    expect(adminApi.gatewayCalls).not.toHaveBeenCalled();
  });

  it("展示调用列表、空间标签与结果状态，并支持按用户/空间/工具/结果/时间范围筛选", async () => {
    show();

    expect(await screen.findByText("净采购额 含税")).toBeInTheDocument();
    expect(screen.getByText("星港采购空间 · v13")).toBeInTheDocument();
    expect(screen.getByText("ws-deleted")).toBeInTheDocument();
    expect(screen.getByText("成功")).toBeInTheDocument();
    expect(screen.getByText("失败 (workspace_unavailable)")).toBeInTheDocument();
    expect(screen.getByText("未完成")).toBeInTheDocument();
    expect(screen.getByText("42 ms")).toBeInTheDocument();

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "筛选用户" }));
    fireEvent.click(
      await screen.findByText("王五 (wangwu)", {
        selector: ".ant-select-item-option-content",
      }),
    );
    await waitFor(() =>
      expect(adminApi.gatewayCalls).toHaveBeenLastCalledWith(
        expect.objectContaining({ user_id: "u-1", limit: 20 }),
      ),
    );

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "筛选空间" }));
    fireEvent.click(
      await screen.findByText("星港销售空间", {
        selector: ".ant-select-item-option-content",
      }),
    );
    await waitFor(() =>
      expect(adminApi.gatewayCalls).toHaveBeenLastCalledWith(
        expect.objectContaining({
          user_id: "u-1",
          workspace_id: "w2",
        }),
      ),
    );

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "筛选工具" }));
    fireEvent.click(
      await screen.findByText("search_ontology", {
        selector: ".ant-select-item-option-content",
      }),
    );
    await waitFor(() =>
      expect(adminApi.gatewayCalls).toHaveBeenLastCalledWith(
        expect.objectContaining({ tool: "search_ontology" }),
      ),
    );

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "筛选结果" }));
    fireEvent.click(
      await screen.findByText("失败", {
        selector: ".ant-select-item-option-content",
      }),
    );
    await waitFor(() =>
      expect(adminApi.gatewayCalls).toHaveBeenLastCalledWith(
        expect.objectContaining({ outcome: "error" }),
      ),
    );

    // Pick time range via RangePicker popup.
    const startInput = screen.getByPlaceholderText("开始时间");
    fireEvent.click(startInput);
    const picker = await screen.findByText("确定");
    const cells = document.querySelectorAll(".ant-picker-cell-in-view");
    fireEvent.click(cells[0]);
    fireEvent.click(picker.closest("button")!);
    const endCells = document.querySelectorAll(".ant-picker-cell-in-view");
    fireEvent.click(endCells[1]);
    fireEvent.click((await screen.findByText("确定")).closest("button")!);
    await waitFor(() =>
      expect(adminApi.gatewayCalls).toHaveBeenLastCalledWith(
        expect.objectContaining({
          from: expect.any(String),
          to: expect.any(String),
        }),
      ),
    );

    fireEvent.click(screen.getByRole("button", { name: "重置筛选" }));
    await waitFor(() =>
      expect(adminApi.gatewayCalls).toHaveBeenLastCalledWith({
        user_id: undefined,
        workspace_id: undefined,
        tool: undefined,
        outcome: undefined,
        from: undefined,
        to: undefined,
        cursor: undefined,
        limit: 20,
      }),
    );
  });

  it("点击调用行打开详情抽屉，展示格式化 JSON 请求与返回及错误信息", async () => {
    show();

    const row = (await screen.findByText("2 个元素")).closest("tr")!;
    fireEvent.click(row);

    await waitFor(() =>
      expect(adminApi.gatewayCall).toHaveBeenCalledWith("call-2"),
    );

    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText("调用详情 · get_ontology")).toBeInTheDocument();
    expect(within(drawer).getByText("req-99")).toBeInTheDocument();
    expect(within(drawer).getByText("错误码：workspace_unavailable")).toBeInTheDocument();
    expect(within(drawer).getByText("空间不存在或当前用户无权访问")).toBeInTheDocument();
    expect(within(drawer).getByText(/"workspace_id": "ws-deleted"/)).toBeInTheDocument();
    expect(within(drawer).getByText(/"message": "空间不可访问"/)).toBeInTheDocument();
  });

  it("未完成调用详情不展示返回内容", async () => {
    vi.mocked(adminApi.gatewayCall).mockResolvedValueOnce({
      ...callDetailError,
      id: "call-3",
      tool: "list_spaces",
      workspaces: [],
      arguments: {},
      response: null,
      outcome: "started",
      error_code: null,
      error_message: null,
      duration_ms: null,
    });
    show();

    const row = (await screen.findByText("list_spaces")).closest("tr")!;
    fireEvent.click(row);

    const startedDrawer = await screen.findByRole("dialog");
    expect(await within(startedDrawer).findByText("调用尚未完成，暂无返回内容")).toBeInTheDocument();
  });

  it("支持游标翻页（下一页 / 上一页）", async () => {
    vi.mocked(adminApi.gatewayCalls)
      .mockResolvedValueOnce({ items: [callItems[0]], next_cursor: "cur-2" })
      .mockResolvedValueOnce({ items: [callItems[1]], next_cursor: null })
      .mockResolvedValueOnce({ items: [callItems[0]], next_cursor: "cur-2" });

    show();
    expect(await screen.findByText("净采购额 含税")).toBeInTheDocument();

    const nextBtn = screen.getByRole("button", { name: "下一页" });
    const prevBtn = screen.getByRole("button", { name: "上一页" });
    expect(prevBtn).toBeDisabled();
    expect(nextBtn).toBeEnabled();

    fireEvent.click(nextBtn);
    await waitFor(() =>
      expect(adminApi.gatewayCalls).toHaveBeenLastCalledWith(
        expect.objectContaining({ cursor: "cur-2", limit: 20 }),
      ),
    );
    expect(await screen.findByText("2 个元素")).toBeInTheDocument();
    expect(screen.getByText("第 2 页")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "下一页" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "上一页" }));
    await waitFor(() =>
      expect(adminApi.gatewayCalls).toHaveBeenLastCalledWith(
        expect.objectContaining({ cursor: undefined, limit: 20 }),
      ),
    );
    expect(await screen.findByText("净采购额 含税")).toBeInTheDocument();
  });
});
