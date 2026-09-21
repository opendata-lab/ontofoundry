import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { modelingApi, workspaceRequest } from "../api/client";
import type { Workspace } from "../api/types";
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

describe("DataAgent diagnostics", () => {
  it("renders every read-only health check and its repair hint", async () => {
    render(<SettingsPage />);

    expect(
      await screen.findByRole("heading", { name: "DataAgent 连通性" }),
    ).toBeInTheDocument();
    expect(screen.getByText("配置完整性")).toBeInTheDocument();
    expect(screen.getByText("连通性")).toBeInTheDocument();
    expect(screen.getByText("站点放行")).toBeInTheDocument();
    expect(screen.getByText("Agent 存在性")).toBeInTheDocument();
    expect(screen.getByText("DataAgent 上找不到该 Agent")).toBeInTheDocument();
    expect(screen.getByText("创建 agent_id=missing-agent")).toBeInTheDocument();
    expect(screen.queryByLabelText(/密钥/)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/密钥/)).not.toBeInTheDocument();
  });
});
