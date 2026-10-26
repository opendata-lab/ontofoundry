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
    batch: vi.fn().mockResolvedValue(null),
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

it("turns the plan switch on for modeling and leaves it out of daily mode", async () => {
  context.model.session = { ...session(), mode: "model" };
  const { container, unmount } = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await screen.findByRole("button", { name: "发送" });
  const el = container.querySelector("dataagent-conversation") as AgentConversationElement;
  expect(el.composerConfig).toEqual({ planMode: { enabled: true, default: true } });
  unmount();

  context.model.session = { ...session(), mode: "chat" };
  const daily = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await screen.findByRole("button", { name: "发送" });
  const chat = daily.container.querySelector("dataagent-conversation") as AgentConversationElement;
  expect(chat.composerConfig).toEqual({});
});

it("opens an expanded plan in the results column and closes back", async () => {
  context.model.session = { ...session(), mode: "model" };
  const { container } = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await screen.findByRole("button", { name: "发送" });
  const el = container.querySelector("dataagent-conversation") as AgentConversationElement;
  const event = new CustomEvent("dataagent-plan-open", {
    cancelable: true,
    detail: {
      title: "星河采购建模计划",
      body: "## 步骤\n1. 新建对象 **供应商**",
      markdown: "# 星河采购建模计划\n\n## 步骤\n1. 新建对象 **供应商**",
      requestId: "plan-1",
    },
  });
  act(() => { el.dispatchEvent(event); });

  // The page claims the plan, so the card does not also expand in place.
  expect(event.defaultPrevented).toBe(true);
  expect(await screen.findByRole("heading", { name: "星河采购建模计划" })).toBeInTheDocument();
  expect(screen.getByText("供应商")).toBeInTheDocument();
  expect(screen.getAllByText("星河采购建模计划")).toHaveLength(1);
  fireEvent.click(screen.getByRole("button", { name: "关闭计划" }));
  expect(screen.queryByRole("heading", { name: "星河采购建模计划" })).toBeNull();
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

it("shows the platform reason in the conversation and retries only 重试 in model mode", async () => {
  context.model.session = { ...session(), task_status: "finished", proposal_notice: {
    run_token: "fictional-run", batch_id: "fictional-batch", summary: "目标连接列不是唯一属性或完整标识", affected_count: 2, reviewable_count: 3,
  } };
  const { container } = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  const retry = await screen.findByRole("button", { name: "重试" });
  await waitFor(() => expect(retry).toBeEnabled());
  expect(screen.getByText("3 条可审，2 条受影响。")).toBeInTheDocument();
  expect(screen.getByText("平台消息")).toBeInTheDocument();
  expect(container.querySelector('[slot="composer-overlay"]')).toHaveTextContent("目标连接列");
  fireEvent.change(screen.getByRole("textbox", { name: "业务场景描述" }), { target: { value: "另一个场景" } });
  const conversation = container.querySelector("dataagent-conversation") as AgentConversationElement;
  const sendMessage = vi.fn();
  Object.defineProperty(conversation, "sendMessage", { value: sendMessage });
  fireEvent.click(retry);
  expect(conversation.value).toBe("重试");
  expect(sendMessage).toHaveBeenCalledWith("重试", { metadata: { mode: "model" } });
});


it("shows only the failure reason and retry when this run has no batch", async () => {
  context.model.session = { ...session(), latest_batch_id: "previous-batch", task_status: "failed", proposal_notice: {
    run_token: "fictional-run", batch_id: null, summary: "修正次数已用完", affected_count: 0, reviewable_count: 0,
  } };
  renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  expect(await screen.findByText("修正次数已用完")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "重试" })).toBeInTheDocument();
  expect(screen.queryByText(/条可审，.*条受影响/)).toBeNull();
});

it("switches an unstarted session's mode and shows chat without builder side panels", async () => {
  const chat = { ...session(), mode: "chat" as const };
  vi.mocked(modelingApi.save).mockResolvedValue(chat);
  renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  expect(screen.getByRole("heading", { name: "构建配置" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "选择会话模式" }));
  fireEvent.click(await screen.findByText("日常模式"));
  await waitFor(() => expect(modelingApi.save).toHaveBeenCalledWith(expect.objectContaining({ id: "s1" }), expect.anything(), { mode: "chat" }));
  expect(context.model.setSession).toHaveBeenCalledWith(chat);
});

it("fixes the mode once the conversation has started", () => {
  context.model.session = { ...session(), mode: "chat", dataagent_topic_id: "topic-1" };
  renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  expect(screen.getByText("日常模式 · 模式已固定")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "选择会话模式" })).toBeNull();
  expect(screen.queryByRole("heading", { name: "构建配置" })).toBeNull();
});
