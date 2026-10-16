import { cleanup, fireEvent, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, modelingApi } from "../api/client";
import type { ModelingSession, Workspace } from "../api/types";
import { modelingSession, sessionSummary, versionSummary, workspace } from "../test/apiRecords";
import { example } from "../test/drafts";
import { renderWithProviders } from "../test/renderWithProviders";
import { DeliveryPage } from "./DeliveryPage";

const context = vi.hoisted(() => ({ workspace: {} as Workspace }));

vi.mock("../hooks/useWorkspaceContext", () => ({
  useWorkspaceContext: () => ({ workspace: context.workspace, refresh: vi.fn() }),
}));
vi.mock("../hooks/usePageTab", () => ({
  usePageTab: vi.fn(),
  usePageActive: () => true,
}));
vi.mock("../components/publish/PublishPanel", () => ({
  PublishPanel: ({ session }: { session: ModelingSession }) => <p>发布面板 {session.title}</p>,
}));
vi.mock("../api/client", () => ({
  modelingApi: { get: vi.fn(), sessions: vi.fn() },
  api: { versions: vi.fn(), comparison: vi.fn() },
}));

const session = () => modelingSession({ title: "直达会话", base_version_id: "v1" }, example("01-basic-sales"));

beforeEach(() => {
  context.workspace = workspace();
  vi.mocked(modelingApi.sessions).mockResolvedValue({
    items: [sessionSummary({ id: "s1", title: "直达会话" })],
  });
  vi.mocked(api.versions).mockResolvedValue({ items: [] });
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const show = (entry: string) =>
  renderWithProviders(
    <MemoryRouter initialEntries={[entry]}>
      <DeliveryPage />
    </MemoryRouter>,
  );

it("opens the session named by ?session= instead of offering the chooser", async () => {
  let resolve!: (value: ModelingSession) => void;
  vi.mocked(modelingApi.get).mockReturnValue(
    new Promise<ModelingSession>((r) => {
      resolve = r;
    }),
  );
  show("/workspaces/w1/delivery?session=s1");

  // While a large session loads, the page says so rather than asking the
  // user to pick one.
  expect(screen.getByRole("status")).toHaveTextContent("正在加载会话…");
  expect(screen.queryByText("选择待发布的本体")).toBeNull();
  expect(modelingApi.get).toHaveBeenCalledWith("w1", "s1");

  resolve(session());
  expect(await screen.findByText("发布面板 直达会话")).toBeInTheDocument();
});

it("offers the chooser when no session is named", async () => {
  show("/workspaces/w1/delivery");
  expect(await screen.findByText("选择待发布的本体")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "选择建模会话" })).toBeInTheDocument();
  expect(modelingApi.get).not.toHaveBeenCalled();
});

it("falls back to the chooser with the error when the named session fails to load", async () => {
  vi.mocked(modelingApi.get).mockRejectedValue(new Error("建模会话不存在"));
  show("/workspaces/w1/delivery?session=gone");
  expect(await screen.findByText("建模会话不存在")).toBeInTheDocument();
  expect(screen.getByText("选择待发布的本体")).toBeInTheDocument();
});

it("lists published versions with their message and counts, without an Ossie download", async () => {
  vi.mocked(api.versions).mockResolvedValue({
    items: [
      versionSummary(2, {
        message: "补充客户关系",
        counts: { object_types: 2, link_types: 1, attributes: 9, rules: 0, metrics: 10 },
      }),
      versionSummary(1, { message: "初始版本" }),
    ],
  });
  show("/workspaces/w1/delivery?tab=history");
  const latest = (await screen.findByText("补充客户关系")).closest("tr")!;
  expect(latest).toHaveTextContent("v2");
  expect(latest).toHaveTextContent("2 / 1 / 10");
  expect(screen.getByText("初始版本")).toBeInTheDocument();
  expect(screen.getByText("比较历史版本")).toBeInTheDocument();
  expect(api.versions).toHaveBeenCalledWith("w1");
  expect(screen.queryByText(/Ossie/)).toBeNull();
  expect(screen.queryByRole("button", { name: /下载/ })).toBeNull();
});

it("shows only history and service access to readers", async () => {
  context.workspace = workspace({ role: null });
  show("/workspaces/w1/delivery");
  expect(await screen.findByText("还没有已发布版本")).toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "发布" })).toBeNull();
  expect(screen.queryByText("比较历史版本")).toBeNull();
  expect(modelingApi.sessions).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("tab", { name: "服务接入" }));
  expect(await screen.findByText(`${window.location.origin}/api/v1/ontology/workspaces/w1/mcp`)).toBeInTheDocument();
  for (const tool of ["search_ontology", "get_ontology", "search_objects", "get_object"])
    expect(screen.getByText(tool)).toBeInTheDocument();
});
