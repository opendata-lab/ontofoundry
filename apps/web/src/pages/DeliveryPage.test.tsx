import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ModelingSession, Workspace } from "../api/types";
import { modelingApi } from "../api/client";
import { DeliveryPage } from "./DeliveryPage";

const workspace = {
  id: "w1",
  slug: "test",
  name: "Test",
  description: "",
  role: "admin",
  visibility: "member",
  current_version: 1,
  version_id: "v1",
  version_sha256: "sha",
  object_type_count: 0,
  link_type_count: 0,
  updated_at: "",
} as Workspace;

vi.mock("../hooks/useWorkspaceContext", () => ({
  useWorkspaceContext: () => ({ workspace, refresh: vi.fn() }),
}));
vi.mock("../hooks/usePageTab", () => ({
  usePageTab: vi.fn(),
  usePageActive: () => true,
}));
vi.mock("../components/publish/PublishPanel", () => ({
  PublishPanel: ({ session }: { session: ModelingSession }) => (
    <p>发布面板 {session.title}</p>
  ),
}));
vi.mock("../api/client", () => ({
  modelingApi: { get: vi.fn(), sessions: vi.fn() },
  workspaceRequest: vi.fn().mockResolvedValue({ items: [] }),
  api: {},
}));

function session(): ModelingSession {
  return {
    id: "s1",
    workspace_id: "w1",
    title: "直达会话",
    revision: 1,
    base_version_id: "v1",
    draft: {} as ModelingSession["draft"],
    graph: { workspace_id: "w1", version_id: "", version_sha256: "", nodes: [], edges: [] },
    candidates: [],
    material_ids: [],
    task_status: "idle",
    task_detail: "",
    updated_at: "",
  };
}

beforeEach(() => {
  vi.mocked(modelingApi.sessions).mockResolvedValue({
    items: [{ id: "s1", title: "直达会话", task_status: "idle", updated_at: "" }],
  });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

it("opens the session named by ?session= instead of offering the chooser", async () => {
  let resolve!: (value: ModelingSession) => void;
  vi.mocked(modelingApi.get).mockReturnValue(
    new Promise<ModelingSession>((r) => {
      resolve = r;
    }),
  );
  render(
    <MemoryRouter initialEntries={["/workspaces/w1/delivery?session=s1"]}>
      <DeliveryPage />
    </MemoryRouter>,
  );

  // While a large session loads, the page says so rather than asking the
  // user to pick one.
  expect(screen.getByRole("status")).toHaveTextContent("正在加载会话…");
  expect(screen.queryByText("选择待发布的本体")).toBeNull();
  expect(modelingApi.get).toHaveBeenCalledWith("w1", "s1");

  resolve(session());
  expect(await screen.findByText("发布面板 直达会话")).toBeInTheDocument();
});

it("offers the chooser when no session is named", async () => {
  render(
    <MemoryRouter initialEntries={["/workspaces/w1/delivery"]}>
      <DeliveryPage />
    </MemoryRouter>,
  );
  expect(await screen.findByText("选择待发布的本体")).toBeInTheDocument();
  expect(screen.getByText("选择建模会话")).toBeInTheDocument();
  expect(modelingApi.get).not.toHaveBeenCalled();
});

it("falls back to the chooser with the error when the named session fails to load", async () => {
  vi.mocked(modelingApi.get).mockRejectedValue(new Error("建模会话不存在"));
  render(
    <MemoryRouter initialEntries={["/workspaces/w1/delivery?session=gone"]}>
      <DeliveryPage />
    </MemoryRouter>,
  );
  expect(await screen.findByText("建模会话不存在")).toBeInTheDocument();
  expect(screen.getByText("选择待发布的本体")).toBeInTheDocument();
});
