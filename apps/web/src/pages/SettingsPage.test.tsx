import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, modelingApi, workspaceRequest } from "../api/client";
import type { Member, User, Workspace } from "../api/types";
import { workspace as makeWorkspace } from "../test/apiRecords";
import { renderWithProviders } from "../test/renderWithProviders";
import { SettingsPage } from "./SettingsPage";

const context = vi.hoisted(() => ({
  workspace: {} as Workspace,
  user: {} as User,
  refresh: vi.fn(),
}));

vi.mock("../hooks/useWorkspaceContext", () => ({
  useWorkspaceContext: () => context,
}));
vi.mock("../hooks/usePageTab", () => ({ usePageTab: vi.fn() }));
vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      updateWorkspace: vi.fn(),
      members: vi.fn(),
      addMember: vi.fn(),
      updateMemberRole: vi.fn(),
      removeMember: vi.fn(),
      searchWorkspaceUsers: vi.fn(),
    },
    workspaceRequest: vi.fn(),
    modelingApi: {
      ...actual.modelingApi,
      capabilities: vi.fn(),
    },
  };
});

const adminUser: User = {
  id: "u1",
  username: "admin",
  display_name: "Admin",
  email: null,
  is_platform_admin: false,
  local_account: true,
};

const defaultMembers: Member[] = [
  {
    id: 1,
    user_id: "u1",
    username: "admin",
    display_name: "Admin",
    role: "admin",
    last_login_at: "2026-11-12T08:00:00Z",
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  context.user = adminUser;
  context.workspace = makeWorkspace({ id: "w1", slug: "test", name: "测试空间" });
  vi.mocked(api.members).mockResolvedValue({ items: defaultMembers });
  vi.mocked(api.updateWorkspace).mockResolvedValue(context.workspace);
  vi.mocked(api.searchWorkspaceUsers).mockResolvedValue({ items: [] });
  vi.mocked(workspaceRequest).mockImplementation((_, suffix) => {
    if (suffix === "/settings/dataagent-health") {
      return Promise.resolve({
        ok: false,
        checks: [
          { name: "配置完整性", ok: true, message: "配置完整", hint: "" },
          { name: "连通性", ok: true, message: "连接成功", hint: "" },
          { name: "站点放行", ok: true, message: "站点已放行", hint: "" },
          {
            name: "Agent 存在性",
            ok: false,
            message: "DataAgent 上找不到该 Agent",
            hint: "创建 agent_id=missing-agent",
          },
        ],
      });
    }
    return Promise.reject(new Error("unexpected request"));
  });
  vi.mocked(modelingApi.capabilities).mockResolvedValue({
    agent_configured: true,
    model: "DataAgent · Pi",
    max_file_mb: 256,
    connections_configured: false,
    skills: ["md2ossie"],
  });
});

afterEach(cleanup);

function show() {
  return renderWithProviders(
    <MemoryRouter>
      <SettingsPage />
    </MemoryRouter>,
  );
}

describe("空间设置", () => {
  it("展示空间信息、公开开关、成员管理和只读 DataAgent 检查", async () => {
    show();

    expect(screen.getByRole("heading", { name: "空间设置" })).toBeInTheDocument();
    expect(screen.getByText("空间信息")).toBeInTheDocument();
    expect(screen.getByText("空间公开")).toBeInTheDocument();
    expect(screen.getByText("空间成员")).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "对平台全部登录用户公开" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "搜索已有用户" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "成员角色" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "添加成员" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存空间信息" })).toBeInTheDocument();
    expect(screen.queryByText("智能问数")).not.toBeInTheDocument();
    expect(screen.getByText("DataAgent 连通性")).toBeInTheDocument();
    expect(await screen.findByText("DataAgent 上找不到该 Agent")).toBeInTheDocument();
    expect(screen.getByText("创建 agent_id=missing-agent")).toBeInTheDocument();
    expect(screen.getAllByText("通过", { exact: true })).toHaveLength(3);
    expect(screen.getByText("需处理", { exact: true })).toBeInTheDocument();
    expect(modelingApi.capabilities).not.toHaveBeenCalled();
    expect(api.members).toHaveBeenCalledWith("w1");
    expect(workspaceRequest).toHaveBeenCalledWith("w1", "/settings/dataagent-health");
  });

  it("非管理员进入空间设置时展示 403 无权限页", () => {
    context.workspace = makeWorkspace({ role: "viewer" });
    show();
    expect(screen.getByText("无权访问")).toBeInTheDocument();
    expect(screen.getByText("只有该工作空间的管理员可以打开「空间设置」。")).toBeInTheDocument();
    expect(api.members).not.toHaveBeenCalled();
  });

  it("开启空间公开需弹窗确认后提交 PATCH，关闭时直接生效", async () => {
    show();
    const toggle = await screen.findByRole("switch", { name: "对平台全部登录用户公开" });
    fireEvent.click(toggle);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("确认将「测试空间」设为公开？")).toBeInTheDocument();
    expect(api.updateWorkspace).not.toHaveBeenCalled();

    fireEvent.click(within(dialog).getByRole("button", { name: "确认公开" }));
    await waitFor(() => {
      expect(api.updateWorkspace).toHaveBeenCalledWith("w1", { is_public: true });
      expect(context.refresh).toHaveBeenCalledTimes(1);
    });

    cleanup();
    vi.clearAllMocks();
    context.workspace = makeWorkspace({ id: "w1", name: "测试空间", is_public: true, visibility: "public" });
    vi.mocked(api.members).mockResolvedValue({ items: defaultMembers });
    vi.mocked(api.updateWorkspace).mockResolvedValue(context.workspace);
    show();
    fireEvent.click(await screen.findByRole("switch", { name: "对平台全部登录用户公开" }));
    await waitFor(() => {
      expect(api.updateWorkspace).toHaveBeenCalledWith("w1", { is_public: false });
    });
  });

  it("支持按用户名搜索添加成员、无结果提示，以及修改角色时的 LAST_ADMIN 处理", async () => {
    vi.mocked(api.searchWorkspaceUsers).mockResolvedValue({
      items: [{ id: "u2", username: "lisi", display_name: "李四", last_login_at: null }],
    });
    vi.mocked(api.addMember).mockResolvedValue({
      id: 2,
      user_id: "u2",
      username: "lisi",
      display_name: "李四",
      role: "viewer",
      last_login_at: null,
    });
    vi.mocked(api.updateMemberRole).mockRejectedValueOnce(
      new ApiError("该空间至少需要一名管理员", 409, "LAST_ADMIN"),
    );

    show();
    expect(await screen.findByText("admin")).toBeInTheDocument();

    const searchInput = screen.getByRole("combobox", { name: "搜索已有用户" });
    fireEvent.change(searchInput, { target: { value: "lisi" } });
    await waitFor(() => expect(api.searchWorkspaceUsers).toHaveBeenCalledWith("w1", "lisi"));
    fireEvent.click(await screen.findByText("李四"));

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "成员角色" }));
    fireEvent.click(await screen.findByText("可查看", { selector: ".ant-select-item-option-content" }));
    fireEvent.click(screen.getByRole("button", { name: "添加成员" }));

    await waitFor(() => {
      expect(api.addMember).toHaveBeenCalledWith("w1", { user_id: "u2", role: "viewer" });
    });

    fireEvent.mouseDown(screen.getByRole("combobox", { name: "Admin 角色" }));
    const memberOptions = await screen.findAllByText("可编辑", {
      selector: ".ant-select-item-option-content",
    });
    fireEvent.click(memberOptions.at(-1)!);
    expect(await screen.findByRole("alert")).toHaveTextContent("该空间至少需要一名管理员");

    vi.mocked(api.searchWorkspaceUsers).mockResolvedValue({ items: [] });
    fireEvent.change(screen.getByRole("combobox", { name: "搜索已有用户" }), { target: { value: "nobody" } });
    fireEvent.click(screen.getByRole("button", { name: "添加成员" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "用户不存在，请联系平台管理员在用户管理中创建",
    );
  });
});
