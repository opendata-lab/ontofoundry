import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { MeWorkspace, User } from "../api/types";
import { renderWithProviders } from "../test/renderWithProviders";
import { MePage } from "./MePage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      me: vi.fn(),
      meWorkspaces: vi.fn(),
      logout: vi.fn(),
    },
  };
});

const baseUser: User = {
  id: "u1",
  username: "zhangsan",
  display_name: "张三",
  email: "zhangsan@example.com",
  is_platform_admin: false,
  local_account: true,
};

const memberships: MeWorkspace[] = [
  { id: "w1", name: "销售示范空间", is_public: false, role: "admin" },
  { id: "w2", name: "公共示范空间", is_public: true, role: "viewer" },
];

function show() {
  const router = createMemoryRouter(
    [
      { path: "/me", element: <MePage /> },
      { path: "/", element: <p>工作空间目录</p> },
      { path: "/workspaces/:workspaceId/view", element: <p>本体视图</p> },
    ],
    { initialEntries: ["/me"] },
  );
  renderWithProviders(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.me).mockResolvedValue(baseUser);
  vi.mocked(api.meWorkspaces).mockResolvedValue({ items: memberships });
});

afterEach(cleanup);

describe("个人中心", () => {
  it("展示只读个人信息、所在空间及角色与禁用的个人令牌选项卡", async () => {
    const router = show();

    expect(await screen.findByText("zhangsan")).toBeInTheDocument();
    expect(screen.getAllByText("张三").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("zhangsan@example.com")).toBeInTheDocument();
    expect(screen.getByText("是")).toBeInTheDocument();
    expect(screen.getByText("销售示范空间")).toBeInTheDocument();
    expect(screen.getByText("管理员")).toBeInTheDocument();
    expect(screen.getByText("公共示范空间")).toBeInTheDocument();
    expect(screen.getByText("可查看")).toBeInTheDocument();
    expect(screen.queryByText("全部空间（超级管理员）")).toBeNull();

    const tokensTab = screen.getByRole("tab", { name: /个人令牌/ });
    expect(tokensTab).toHaveAttribute("aria-disabled", "true");
    expect(within(tokensTab).getByText("随外部智能体网关上线")).toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "进入空间" })[0]);
    expect(router.state.location.pathname).toBe("/workspaces/w1/view");
  });

  it("平台管理员额外显示全部空间（超级管理员）标签", async () => {
    vi.mocked(api.me).mockResolvedValue({ ...baseUser, is_platform_admin: true, local_account: false });
    show();

    expect(await screen.findByText("全部空间（超级管理员）")).toBeInTheDocument();
    expect(screen.getByText("否")).toBeInTheDocument();
  });
});
