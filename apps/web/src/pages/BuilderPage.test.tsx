import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { modelingApi } from "../api/client";
import type { Material, ModelingSession, Workspace } from "../api/types";
import { modelingSession, workspace } from "../test/apiRecords";
import { renderWithProviders } from "../test/renderWithProviders";
import type { AgentConversationElement } from "../types/agent-conversation";
import { BuilderPage } from "./BuilderPage";

const context = vi.hoisted(() => ({
  workspace: {} as Workspace,
  reload: vi.fn(),
  setError: vi.fn(),
  model: {} as Record<string, unknown>,
}));

vi.mock("../hooks/useWorkspaceContext", () => ({
  useWorkspaceContext: () => ({ workspace: context.workspace }),
}));
vi.mock("../hooks/usePageTab", () => ({ usePageTab: vi.fn() }));
vi.mock("../hooks/useModeling", () => ({
  useModeling: () => context.model,
}));
vi.mock("../components/ModelResults", () => ({
  ModelResults: () => null,
}));
vi.mock("../api/client", () => ({
  modelingApi: {
    materials: vi.fn().mockResolvedValue({ items: [] }),
    capabilities: vi.fn().mockResolvedValue({
      agent_configured: true,
      model: "DataAgent",
      max_file_mb: 256,
      connections_configured: false,
      skills: [],
    }),
    upload: vi.fn(),
    save: vi.fn(),
  },
  catalogApi: {
    connections: vi.fn().mockResolvedValue({ items: [] }),
    tables: vi.fn().mockResolvedValue({ items: [] }),
    tableMaterial: vi.fn(),
  },
  proposalsApi: {
    batches: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    batch: vi.fn(),
    decide: vi.fn(),
  },
  ApiError: class extends Error {},
}));

function session(): ModelingSession {
  return modelingSession({ title: "Session" });
}

beforeEach(() => {
  vi.clearAllMocks();
  context.workspace = workspace({ name: "Test", slug: "test" });
  context.model = {
    session: session(),
    sessionId: "s1",
    setSession: vi.fn(),
    sessions: [],
    error: "",
    setError: context.setError,
    select: vi.fn(),
    create: vi.fn(),
    ensure: vi.fn().mockResolvedValue(session()),
    reload: context.reload,
  };
});

afterEach(cleanup);

it("reloads the session after an agent error advances the backend revision", async () => {
  const { container } = renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  const conversation = container.querySelector("dataagent-conversation");
  expect(conversation).not.toBeNull();
  const conversationElement = conversation as AgentConversationElement;
  expect(conversationElement.endpoint).toBe(
    "/api/v1/workspaces/w1/sessions/s1/agent-conversation",
  );
  expect(conversationElement.endpointResolver).toBeTypeOf("function");
  expect(conversationElement.transportFactory).toBeTypeOf("function");
  expect(conversation?.hasAttribute("transportFactory")).toBe(false);
  expect(conversation?.hasAttribute("endpointResolver")).toBe(false);

  await act(async () => {
    conversation?.dispatchEvent(
      new CustomEvent("dataagent-error", {
        detail: {
          code: "transport_unreachable",
          message: "DataAgent unavailable",
          hint: "retry later",
        },
      }),
    );
  });

  await waitFor(() => expect(context.reload).toHaveBeenCalledTimes(1));
  expect(context.setError).toHaveBeenCalledWith(
    "DataAgent unavailable（retry later）",
  );
  expect(screen.getByRole("heading", { name: "本体构建" })).toBeInTheDocument();
});

it("starts a modeling run from the composer 发送 action, tagged so the BFF expects proposals", async () => {
  context.model.session = { ...session(), material_ids: ["m1"] };
  const { container } = renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  const conversation = container.querySelector(
    "dataagent-conversation",
  ) as AgentConversationElement;
  const sendMessage = vi.fn();
  Object.defineProperty(conversation, "sendMessage", { value: sendMessage });
  Object.defineProperty(conversation, "value", { value: "", configurable: true });
  const start = await screen.findByRole("button", { name: "发送" });
  await waitFor(() => expect(start).toBeEnabled());

  fireEvent.change(screen.getByRole("textbox", { name: "业务场景描述" }), {
    target: { value: "渠道销售" },
  });
  fireEvent.click(start);

  expect(sendMessage).toHaveBeenCalledWith("渠道销售", {
    metadata: { mode: "model" },
  });
});

it("keeps 发送 disabled without material or a scenario", async () => {
  renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("button", { name: "发送" })).toBeDisabled();
});

it("uploads business knowledge files through Upload.Dragger and switches to the material library", async () => {
  const uploaded: Material = {
    id: "m-new",
    name: "采购制度.md",
    byte_size: 128,
    chunk_count: 3,
    sha256: "f".repeat(64),
  };
  vi.mocked(modelingApi.upload).mockResolvedValue(uploaded);
  vi.mocked(modelingApi.save).mockResolvedValue({ ...session(), material_ids: ["m-new"] });
  const { container } = renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  expect(await screen.findByText("点击或拖拽文件至此上传")).toBeInTheDocument();
  expect(screen.getByText(/单文件不超过 256 MB/)).toBeInTheDocument();

  const file = new File(["# 采购制度"], "采购制度.md", { type: "text/markdown" });
  const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
  expect(fileInput).not.toBeNull();
  expect(fileInput.accept).toBe(".md,.markdown,.txt,.json,.yaml,.yml,.csv");

  fireEvent.change(fileInput, { target: { files: [file] } });

  await waitFor(() => expect(modelingApi.upload).toHaveBeenCalledWith("w1", file));
  expect(modelingApi.save).toHaveBeenCalled();
  expect(await screen.findByText("采购制度.md")).toBeInTheDocument();
});

it("says when the last modeling run is waiting for the user's reply", async () => {
  context.model.session = {
    ...session(),
    task_status: "finished",
    result_state: "awaiting_reply",
    task_detail: "智能体需要你确认后才能生成提案，请在对话中回复",
  };
  renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  expect(
    await screen.findByText("智能体需要你确认后才能生成提案，请在对话中回复"),
  ).toBeInTheDocument();
});

it("lists the questions that came with the proposals", async () => {
  context.model.session = {
    ...session(),
    task_status: "finished",
    result_state: "awaiting_reply",
    task_detail: "已生成 77 条提案，请在“提案”中审阅；另有 1 个问题待你回复",
    open_questions: ["一次预约能开几张处方？提案按可开多张（多对一）处理，如只能一张请回复。"],
  };
  renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  expect(
    await screen.findByText("一次预约能开几张处方？提案按可开多张（多对一）处理，如只能一张请回复。"),
  ).toBeInTheDocument();
});

it("shows no reply hint for a run that produced its result", async () => {
  context.model.session = { ...session(), task_status: "finished", result_state: "done" };
  renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  await screen.findByRole("button", { name: "发送" });
  expect(screen.queryByText(/请在对话中回复/)).toBeNull();
});


it("preserves a scenario while toggling the configuration panel", async () => {
  renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  const input = await screen.findByRole("textbox", { name: "业务场景描述" });
  fireEvent.change(input, { target: { value: "星河采购协同" } });
  fireEvent.click(screen.getByRole("button", { name: "收起构建配置" }));
  expect(screen.queryByRole("textbox", { name: "业务场景描述" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "展开构建配置" }));
  expect(screen.getByRole("textbox", { name: "业务场景描述" })).toHaveValue("星河采购协同");
  await waitFor(() => expect(screen.getByRole("button", { name: "发送" })).toBeEnabled());
});
