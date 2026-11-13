import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { workspace } from "../test/apiRecords";
import { renderWithProviders } from "../test/renderWithProviders";
import { WorkspaceDirectoryPage } from "./WorkspaceDirectoryPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      workspaces: vi.fn(),
      me: vi.fn(),
      createWorkspace: vi.fn(),
      logout: vi.fn(),
    },
  };
});
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.me).mockResolvedValue({
    id: "u1",
    username: "linxiao",
    display_name: "林晓",
    email: null,
    is_platform_admin: false,
    local_account: true,
  });
  vi.mocked(api.workspaces).mockResolvedValue({
    items: [
      workspace({ name: "星河示例空间" }),
      workspace({ id: "w2", name: "云杉示例空间", is_public: true, role: null, visibility: "public", current_version: null }),
      workspace({ id: "w3", name: "青禾只读空间", is_public: false, role: "viewer", visibility: "member", current_version: 2 }),
    ],
  });
});
afterEach(cleanup);

const show = () => {
  const router = createMemoryRouter([
    { path: "/", element: <WorkspaceDirectoryPage /> },
    { path: "/workspaces/:id/view", element: <p>本体视图</p> },
    { path: "/me", element: <p>个人中心</p> },
    { path: "/admin/users", element: <p>用户管理</p> },
  ]);
  renderWithProviders(<RouterProvider router={router} />);
  return router;
};

it("keeps workspace links, publication states, public tags and reader access", async () => {
  show();
  expect(await screen.findByRole("link", { name: /^星河示例空间/ })).toHaveAttribute("href", "/workspaces/w1/view");
  expect(screen.getByText("v1 · 已发布")).toBeInTheDocument();
  expect(screen.getByText("尚未发布")).toBeInTheDocument();
  expect(screen.getByText("公开")).toBeInTheDocument();
  expect(screen.getByText("只读访问")).toBeInTheDocument();
  expect(screen.getByText("可查看")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: /林晓/ }));
  const menu = await screen.findByRole("menu");
  expect(within(menu).getByRole("menuitem", { name: /个人中心/ })).toBeInTheDocument();
  expect(within(menu).queryByRole("menuitem", { name: /用户管理/ })).toBeNull();
});

it("shows 用户管理 in directory header menu for platform admins", async () => {
  vi.mocked(api.me).mockResolvedValue({
    id: "u1",
    username: "admin",
    display_name: "管理员",
    email: null,
    is_platform_admin: true,
    local_account: true,
  });
  show();
  fireEvent.click(await screen.findByRole("button", { name: /管理员/ }));
  const menu = await screen.findByRole("menu");
  expect(within(menu).getByRole("menuitem", { name: /用户管理/ })).toBeInTheDocument();
});

it("creates a workspace and enters its ontology view", async () => {
  vi.mocked(api.createWorkspace).mockResolvedValue(workspace({ id: "w-new", name: "青禾示例空间" }));
  const router = show();
  fireEvent.click(await screen.findByRole("button", { name: "创建工作空间" }));
  fireEvent.change(screen.getByRole("textbox", { name: "空间名称" }), { target: { value: "青禾示例空间" } });
  fireEvent.change(screen.getByRole("textbox", { name: "空间标识" }), { target: { value: "qinghe-demo" } });
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "创建工作空间" }));
  await waitFor(() => expect(router.state.location.pathname).toBe("/workspaces/w-new/view"));
  expect(api.createWorkspace).toHaveBeenCalledWith({ name: "青禾示例空间", slug: "qinghe-demo", description: "" });
});
