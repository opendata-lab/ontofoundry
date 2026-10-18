import { cleanup, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { modelingApi, workspaceRequest } from "../api/client";
import type { Workspace } from "../api/types";
import { renderWithProviders } from "../test/renderWithProviders";
import { SettingsPage } from "./SettingsPage";

const context = vi.hoisted(() => ({
  workspace: {} as Workspace,
  user: { id: "u1", subject: "dev:u1", display_name: "Admin", email: null },
  refresh: vi.fn(),
}));

vi.mock("../hooks/useWorkspaceContext", () => ({
  useWorkspaceContext: () => context,
}));
vi.mock("../hooks/usePageTab", () => ({ usePageTab: vi.fn() }));
vi.mock("../api/client", () => ({
  workspaceRequest: vi.fn(),
  modelingApi: { capabilities: vi.fn() },
}));

beforeEach(() => {
  vi.clearAllMocks();
  context.workspace = {
    id: "w1",
    slug: "test",
    name: "测试空间",
    description: "",
    role: "admin",
    visibility: "member",
    current_version: 1,
    version_id: "v1",
    version_sha256: "sha",
    object_type_count: 1,
    link_type_count: 0,
    updated_at: "",
  };
  vi.mocked(workspaceRequest).mockImplementation((_, suffix) => {
    if (suffix === "/members") return Promise.resolve({ items: [] });
    if (suffix === "/settings/dataagent-health") {
      return Promise.resolve({
        ok: false,
        checks: [
          { name: "配置完整性", ok: true, message: "配置完整", hint: "" },
          { name: "连通性", ok: true, message: "连接成功", hint: "" },
          {
            name: "站点放行",
            ok: true,
            message: "站点已放行",
            hint: "",
          },
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

describe("空间设置", () => {
  it("keeps member management and shows the read-only DataAgent checks", async () => {
    renderWithProviders(<SettingsPage />);

    expect(screen.getByRole("heading", { name: "空间设置" })).toBeInTheDocument();
    expect(screen.getByText("空间信息")).toBeInTheDocument();
    expect(screen.getByText("空间成员")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "成员身份标识" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "成员角色" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "添加成员" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "保存空间信息" })).toBeInTheDocument();
    expect(screen.queryByText("智能问数")).not.toBeInTheDocument();
    expect(screen.getByText("DataAgent 连通性")).toBeInTheDocument();
    expect(
      await screen.findByText("DataAgent 上找不到该 Agent"),
    ).toBeInTheDocument();
    expect(screen.getByText("创建 agent_id=missing-agent")).toBeInTheDocument();
    expect(screen.getAllByText("通过", { exact: true })).toHaveLength(3);
    expect(screen.getByText("需处理", { exact: true })).toBeInTheDocument();
    expect(modelingApi.capabilities).not.toHaveBeenCalled();
    expect(workspaceRequest).toHaveBeenCalledWith("w1", "/members");
    expect(workspaceRequest).toHaveBeenCalledWith(
      "w1",
      "/settings/dataagent-health",
    );
  });
});
