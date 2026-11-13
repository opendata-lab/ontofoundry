import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, adminApi, api } from "../api/client";
import type { AdminUser, AdminWorkspace, User } from "../api/types";
import { renderWithProviders } from "../test/renderWithProviders";
import { AdminUsersPage } from "./AdminUsersPage";

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
    id: "u-admin",
    username: "admin",
    display_name: "系统管理员",
    email: "admin@example.com",
    local_account: true,
    platform_admin: true,
    last_login_at: "2026-11-12T08:00:00Z",
    workspaces: [{ id: "w1", name: "销售空间", role: "admin" }],
  },
  {
    id: "u-zhaoliu",
    username: "zhaoliu",
    display_name: "赵六",
    email: null,
    local_account: false,
    platform_admin: false,
    last_login_at: null,
    workspaces: [{ id: "w1", name: "销售空间", role: "member" }],
  },
];

const workspacesList: AdminWorkspace[] = [
  { id: "w1", name: "销售空间", is_public: false },
  { id: "w2", name: "供应链空间", is_public: true },
];

function show() {
  const router = createMemoryRouter(
    [
      { path: "/admin/users", element: <AdminUsersPage /> },
      { path: "/", element: <p>工作空间目录</p> },
    ],
    { initialEntries: ["/admin/users"] },
  );
  renderWithProviders(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.me).mockResolvedValue(platformAdmin);
  vi.mocked(adminApi.users).mockResolvedValue({ items: usersList });
  vi.mocked(adminApi.workspaces).mockResolvedValue({ items: workspacesList });
});

afterEach(cleanup);

describe("用户管理页", () => {
  it("非平台管理员访问 /admin/users 显示 403 无权访问", async () => {
    vi.mocked(api.me).mockResolvedValue({ ...platformAdmin, is_platform_admin: false });
    show();

    expect(await screen.findByText("无权访问")).toBeInTheDocument();
    expect(screen.getByText("只有平台管理员（ADMIN_USERS）可以访问用户管理。")).toBeInTheDocument();
    expect(adminApi.users).not.toHaveBeenCalled();
  });

  it("展示用户列表、支持搜索、支持预建用户并处理 409 用户名冲突", async () => {
    vi.mocked(adminApi.createUser)
      .mockRejectedValueOnce(new ApiError("用户名已存在", 409, "USERNAME_EXISTS"))
      .mockResolvedValueOnce({
        id: "u-new",
        username: "qianqi",
        display_name: "钱七",
        email: null,
        local_account: false,
        platform_admin: false,
        last_login_at: null,
        workspaces: [],
      });

    show();

    expect(await screen.findByText("zhaoliu")).toBeInTheDocument();
    expect(screen.getByText("全部空间（超级管理员）")).toBeInTheDocument();
    expect(screen.getByText("尚未登录")).toBeInTheDocument();
    expect(screen.getAllByText("销售空间").length).toBeGreaterThanOrEqual(1);

    fireEvent.change(screen.getByRole("searchbox", { name: "搜索用户名或显示名" }), {
      target: { value: "zhao" },
    });
    await waitFor(() => expect(adminApi.users).toHaveBeenCalledWith("zhao"));

    fireEvent.click(screen.getByRole("button", { name: "新建用户" }));
    const dialog = await screen.findByRole("dialog", { name: "新建用户" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "用户名" }), {
      target: { value: "zhaoliu" },
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "显示名" }), {
      target: { value: "赵六" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "创建用户" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("用户名已存在");

    fireEvent.change(within(dialog).getByRole("textbox", { name: "用户名" }), {
      target: { value: "qianqi" },
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "显示名" }), {
      target: { value: "钱七" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "创建用户" }));

    await waitFor(() => {
      expect(adminApi.createUser).toHaveBeenLastCalledWith({
        username: "qianqi",
        display_name: "钱七",
      });
    });
  });

  it("在分配空间抽屉中添加空间、调整角色、移除成员并提示 LAST_ADMIN", async () => {
    vi.mocked(adminApi.setUserWorkspace)
      .mockResolvedValueOnce({ workspace_id: "w2", role: "viewer" })
      .mockResolvedValueOnce({ workspace_id: "w1", role: "admin" });
    vi.mocked(adminApi.removeUserWorkspace).mockRejectedValueOnce(
      new ApiError("该空间至少需要一名管理员", 409, "LAST_ADMIN"),
    );

    show();
    const row = (await screen.findByText("zhaoliu")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "分配空间" }));

    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByText(/分配空间 · 赵六 \(zhaoliu\)/)).toBeInTheDocument();

    fireEvent.mouseDown(within(drawer).getByRole("combobox", { name: "选择工作空间" }));
    fireEvent.click(
      await screen.findByText("供应链空间（公开）", { selector: ".ant-select-item-option-content" }),
    );
    fireEvent.mouseDown(within(drawer).getByRole("combobox", { name: "分配空间角色" }));
    fireEvent.click(
      await screen.findByText("可查看", { selector: ".ant-select-item-option-content" }),
    );
    fireEvent.click(within(drawer).getByRole("button", { name: "添加" }));

    await waitFor(() => {
      expect(adminApi.setUserWorkspace).toHaveBeenCalledWith("u-zhaoliu", "w2", "viewer");
    });

    fireEvent.mouseDown(within(drawer).getByRole("combobox", { name: "销售空间 角色" }));
    const adminOptions = await screen.findAllByText("管理员", {
      selector: ".ant-select-item-option-content",
    });
    fireEvent.click(adminOptions.at(-1)!);
    await waitFor(() => {
      expect(adminApi.setUserWorkspace).toHaveBeenCalledWith("u-zhaoliu", "w1", "admin");
    });

    fireEvent.click(within(drawer).getByRole("button", { name: "移除 销售空间" }));
    expect(await within(drawer).findByRole("alert")).toHaveTextContent("该空间至少需要一名管理员");
  });
});
