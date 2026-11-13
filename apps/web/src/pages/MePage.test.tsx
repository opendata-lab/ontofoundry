import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api/client";
import type { MeWorkspace, PersonalToken, User } from "../api/types";
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
      tokens: vi.fn(),
      createToken: vi.fn(),
      updateToken: vi.fn(),
      revokeToken: vi.fn(),
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
  { id: "w1", name: "星河销售空间", is_public: false, role: "admin" },
  { id: "w2", name: "云杉公开空间", is_public: true, role: "viewer" },
];

const initialTokens: PersonalToken[] = [
  {
    id: "tok-1",
    name: "家里电脑",
    permissions: ["ontology:read", "mappings:read"],
    created_at: "2026-11-12T08:00:00Z",
    updated_at: "2026-11-12T08:00:00Z",
    last_used_at: null,
  },
  {
    id: "tok-2",
    name: "笔记本",
    permissions: ["ontology:read"],
    created_at: "2026-11-11T09:30:00Z",
    updated_at: "2026-11-11T09:30:00Z",
    last_used_at: "2026-11-12T10:15:00Z",
  },
];

function show(initialEntry = "/me") {
  const router = createMemoryRouter(
    [
      { path: "/me", element: <MePage /> },
      { path: "/me/tokens", element: <MePage /> },
      { path: "/", element: <p>工作空间目录</p> },
      { path: "/workspaces/:workspaceId/view", element: <p>本体视图</p> },
    ],
    { initialEntries: [initialEntry] },
  );
  renderWithProviders(<RouterProvider router={router} />);
  return router;
}

const originalClipboardDescriptor = Object.getOwnPropertyDescriptor(
  navigator,
  "clipboard",
);
const originalExecCommand = document.execCommand;

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.me).mockResolvedValue(baseUser);
  vi.mocked(api.meWorkspaces).mockResolvedValue({ items: memberships });
  vi.mocked(api.tokens).mockResolvedValue({ items: initialTokens });
});

afterEach(() => {
  cleanup();
  if (originalClipboardDescriptor) {
    Object.defineProperty(navigator, "clipboard", originalClipboardDescriptor);
  } else {
    delete (navigator as unknown as { clipboard?: unknown }).clipboard;
  }
  document.execCommand = originalExecCommand;
});

describe("个人中心", () => {
  it("展示只读个人信息、所在空间及角色，并支持切换到启用的个人令牌页签", async () => {
    const router = show("/me");

    expect(await screen.findByText("zhangsan")).toBeInTheDocument();
    expect(screen.getAllByText("张三").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("zhangsan@example.com")).toBeInTheDocument();
    expect(screen.getByText("是")).toBeInTheDocument();
    expect(screen.getByText("星河销售空间")).toBeInTheDocument();
    expect(screen.getByText("管理员")).toBeInTheDocument();
    expect(screen.getByText("云杉公开空间")).toBeInTheDocument();
    expect(screen.getByText("可查看")).toBeInTheDocument();
    expect(screen.queryByText("全部空间（超级管理员）")).toBeNull();

    const tokensTab = screen.getByRole("tab", { name: "个人令牌" });
    expect(tokensTab).not.toHaveAttribute("aria-disabled", "true");
    expect(within(tokensTab).queryByText("随外部智能体网关上线")).toBeNull();

    fireEvent.click(tokensTab);
    await waitFor(() => expect(router.state.location.pathname).toBe("/me/tokens"));
    expect(await screen.findByText("家里电脑")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "个人信息" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/me"));
    fireEvent.click(screen.getAllByRole("button", { name: "进入空间" })[0]);
    expect(router.state.location.pathname).toBe("/workspaces/w1/view");
  });

  it("平台管理员额外显示全部空间（超级管理员）标签", async () => {
    vi.mocked(api.me).mockResolvedValue({
      ...baseUser,
      is_platform_admin: true,
      local_account: false,
    });
    show("/me");

    expect(await screen.findByText("全部空间（超级管理员）")).toBeInTheDocument();
    expect(screen.getByText("否")).toBeInTheDocument();
  });

  it("个人令牌列表展示权限标签和最近使用时间，新建令牌仅展示一次且支持非 HTTPS 降级复制", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
    });
    const execCommandMock = vi.fn().mockReturnValue(true);
    document.execCommand = execCommandMock;

    const secret = "ofpat.demo-secret-value-123456";
    const createdMeta: PersonalToken = {
      id: "tok-3",
      name: "办公电脑",
      permissions: ["ontology:read", "mappings:read"],
      created_at: "2026-11-13T01:00:00Z",
      updated_at: "2026-11-13T01:00:00Z",
      last_used_at: null,
    };
    vi.mocked(api.createToken).mockResolvedValueOnce({
      id: "tok-3",
      name: "办公电脑",
      permissions: ["ontology:read", "mappings:read"],
      created_at: "2026-11-13T01:00:00Z",
      token: secret,
    });
    vi.mocked(api.tokens)
      .mockResolvedValueOnce({ items: initialTokens })
      .mockResolvedValueOnce({ items: [createdMeta, ...initialTokens] });

    show("/me/tokens");

    const row1 = (await screen.findByText("家里电脑")).closest("tr")!;
    expect(within(row1).getByText("读取语义")).toBeInTheDocument();
    expect(within(row1).getByText("读取映射")).toBeInTheDocument();
    expect(within(row1).getByText("—")).toBeInTheDocument();

    const row2 = screen.getByText("笔记本").closest("tr")!;
    expect(within(row2).getByText("读取语义")).toBeInTheDocument();
    expect(within(row2).queryByText("读取映射")).toBeNull();
    expect(within(row2).queryByText("—")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "新建令牌" }));
    const dialog = await screen.findByRole("dialog", { name: "新建令牌" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "令牌名称" }), {
      target: { value: "办公电脑" },
    });
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /包含读取映射/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "生成令牌" }));

    await waitFor(() => {
      expect(api.createToken).toHaveBeenCalledWith({
        name: "办公电脑",
        permissions: ["ontology:read", "mappings:read"],
      });
    });

    const tokenInput = await screen.findByRole("textbox", { name: "生成的个人令牌" });
    expect(tokenInput).toHaveValue(secret);
    expect(tokenInput).toHaveAttribute("readonly");
    expect(screen.getByText(/MCP 配置/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "复制令牌" }));
    await waitFor(() => expect(execCommandMock).toHaveBeenCalledWith("copy"));
    expect(await screen.findByRole("button", { name: /已复制/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "我已保存，关闭" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(screen.queryByDisplayValue(secret)).toBeNull();
    expect(await screen.findByText("办公电脑")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "新建令牌" }));
    const nextDialog = await screen.findByRole("dialog", { name: "新建令牌" });
    expect(within(nextDialog).queryByDisplayValue(secret)).toBeNull();
  });

  it("非 HTTPS 环境下 execCommand 复制失败时仍保留明文令牌供手动复制", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: undefined,
      configurable: true,
    });
    document.execCommand = vi.fn().mockReturnValue(false);
    vi.mocked(api.createToken).mockResolvedValueOnce({
      id: "tok-4",
      name: "只读令牌",
      permissions: ["ontology:read"],
      created_at: "2026-11-13T01:30:00Z",
      token: "ofpat.manual-copy-token",
    });

    show("/me/tokens");
    await screen.findByText("家里电脑");

    fireEvent.click(screen.getByRole("button", { name: "新建令牌" }));
    const dialog = await screen.findByRole("dialog", { name: "新建令牌" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "令牌名称" }), {
      target: { value: "只读令牌" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "生成令牌" }));

    await waitFor(() => {
      expect(api.createToken).toHaveBeenCalledWith({
        name: "只读令牌",
        permissions: ["ontology:read"],
      });
    });

    const tokenInput = await screen.findByRole("textbox", { name: "生成的个人令牌" });
    fireEvent.click(screen.getByRole("button", { name: "复制令牌" }));
    expect(
      await screen.findByText("当前浏览器限制自动复制，请直接手动复制上方文本框中的令牌。"),
    ).toBeInTheDocument();
    expect(tokenInput).toHaveValue("ofpat.manual-copy-token");
  });

  it("支持行内重命名、切换读取映射权限与确认撤销令牌", async () => {
    vi.mocked(api.updateToken)
      .mockResolvedValueOnce({
        ...initialTokens[0],
        name: "公司台式机",
        updated_at: "2026-11-13T02:00:00Z",
      })
      .mockResolvedValueOnce({
        ...initialTokens[0],
        name: "公司台式机",
        permissions: ["ontology:read"],
        updated_at: "2026-11-13T02:05:00Z",
      });
    vi.mocked(api.revokeToken).mockResolvedValueOnce(undefined);

    show("/me/tokens");

    await screen.findByText("家里电脑");
    fireEvent.click(screen.getByRole("button", { name: "重命名 家里电脑" }));
    const renameInput = screen.getByRole("textbox", { name: "令牌名称" });
    fireEvent.change(renameInput, { target: { value: "公司台式机" } });
    fireEvent.click(screen.getByRole("button", { name: "保存名称" }));

    await waitFor(() => {
      expect(api.updateToken).toHaveBeenCalledWith("tok-1", { name: "公司台式机" });
    });
    expect(await screen.findByText("公司台式机")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "编辑 公司台式机 权限" }));
    const semanticCheckbox = screen.getByRole("checkbox", { name: "读取语义" });
    expect(semanticCheckbox).toBeChecked();
    expect(semanticCheckbox).toBeDisabled();
    const mappingsCheckbox = screen.getByRole("checkbox", { name: "读取映射" });
    expect(mappingsCheckbox).toBeChecked();
    fireEvent.click(mappingsCheckbox);
    fireEvent.click(screen.getByRole("button", { name: "保存权限" }));

    await waitFor(() => {
      expect(api.updateToken).toHaveBeenCalledWith("tok-1", {
        permissions: ["ontology:read"],
      });
    });
    const updatedRow = screen.getByText("公司台式机").closest("tr")!;
    await waitFor(() => {
      expect(within(updatedRow).queryByText("读取映射")).toBeNull();
    });

    fireEvent.click(screen.getByRole("button", { name: "撤销 公司台式机" }));
    const confirmBtn = await screen.findByRole("button", { name: "确认撤销" });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(api.revokeToken).toHaveBeenCalledWith("tok-1");
    });
    await waitFor(() => expect(screen.queryByText("公司台式机")).toBeNull());
    expect(screen.getByText("笔记本")).toBeInTheDocument();
  });
});
