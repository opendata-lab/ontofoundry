import { act, cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { datasetApi, modelingApi } from "../api/client";
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
  datasetApi: {
    registeredTables: vi.fn().mockResolvedValue({ items: [] }),
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

// The page is ready once it has read the workspace's capabilities.
const ready = () => waitFor(() => expect(modelingApi.capabilities).toHaveBeenCalled());

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

it("sends messages as typed, tagged with the session's mode", async () => {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ task_id: "t-1", status: "running" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchMock);
  try {
    const { container } = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
    await ready();
    const conversation = container.querySelector("dataagent-conversation") as AgentConversationElement;
    const transport = conversation.transportFactory!("/api/v1/workspaces/w1/sessions/s1/agent-conversation");

    await act(async () => { await transport.sendMessage({ content: "只建采购订单" }); });
    const body = JSON.parse(fetchMock.mock.calls.at(-1)![1].body as string);
    expect(body.content).toBe("只建采购订单");
    expect(body.metadata).toEqual({ mode: "model" });
  } finally {
    vi.unstubAllGlobals();
  }
});

it("blocks sending while proposals are pending and allows it otherwise", async () => {
  const { container, unmount } = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
  const el = container.querySelector("dataagent-conversation") as AgentConversationElement;
  await waitFor(() => expect(el.beforeSend!({ content: "建模", settings: {}, attachments: [] })).toBe(true));
  expect(screen.queryByRole("status")).toBeNull();
  unmount();

  context.model.session = { ...session(), pending_proposal_count: 1 };
  const pending = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
  const blocked = pending.container.querySelector("dataagent-conversation") as AgentConversationElement;
  expect(blocked.beforeSend!({ content: "建模", settings: {}, attachments: [] })).toBe(false);
  // The reason is shown above the input, inside the composer.
  const notice = await screen.findByText("请先处理完待审提案，或在提案上修订");
  expect(notice.closest('[slot="composer-overlay"]')).not.toBeNull();
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

it("offers permission modes for modeling and leaves them out of daily mode", async () => {
  context.model.session = { ...session(), mode: "model" };
  const { container, unmount } = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
  const el = container.querySelector("dataagent-conversation") as AgentConversationElement;
  expect(el.composerConfig).toEqual({ permissionModes: expect.any(Array), permissionMode: "plan" });
  expect(el.composerConfig?.permissionModes?.map((m) => m.value)).toEqual(["plan", "default", "acceptEdits", "bypassPermissions"]);
  unmount();

  context.model.session = { ...session(), mode: "model", dataagent_topic_id: "topic-1" };
  const executed = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
  const executedEl = executed.container.querySelector("dataagent-conversation") as AgentConversationElement;
  expect(executedEl.composerConfig).toEqual({ permissionModes: expect.any(Array), permissionMode: "default" });
  executed.unmount();

  context.model.session = { ...session(), mode: "chat" };
  const daily = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
  const chat = daily.container.querySelector("dataagent-conversation") as AgentConversationElement;
  expect(chat.composerConfig).toEqual({});
});

it("keeps the user's pick when the first send creates the session and its topic", async () => {
  context.model.session = { ...session(), mode: "model" };
  const { container, rerender } = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
  const el = container.querySelector("dataagent-conversation") as AgentConversationElement;
  const before = el.composerConfig;

  context.model.session = { ...session(), mode: "model", dataagent_topic_id: "topic-1" };
  rerender(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
  expect(el.composerConfig).toBe(before);
  expect(el.composerConfig).toEqual({ permissionModes: expect.any(Array), permissionMode: "plan" });
});

it("keeps the picker when a new session is created by its first send", async () => {
  context.model.session = null;
  context.model.sessionId = null;
  const { container, rerender } = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
  const el = container.querySelector("dataagent-conversation") as AgentConversationElement;
  const before = el.composerConfig;
  expect(before).toEqual({ permissionModes: expect.any(Array), permissionMode: "plan" });

  context.model.session = { ...session(), mode: "model" };
  context.model.sessionId = "s1";
  rerender(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
  expect(el.composerConfig).toBe(before);
});

it("resets the picker when another session is opened", async () => {
  context.model.session = { ...session(), mode: "model" };
  const { container, rerender } = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
  const el = container.querySelector("dataagent-conversation") as AgentConversationElement;

  context.model.session = { ...session(), id: "s2", mode: "model", dataagent_topic_id: "topic-2" };
  context.model.sessionId = "s2";
  rerender(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
  expect(el.composerConfig).toEqual({ permissionModes: expect.any(Array), permissionMode: "default" });
});

it("opens an expanded plan in the results column and closes back", async () => {
  context.model.session = { ...session(), mode: "model" };
  const { container } = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
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


it("uses the SDK composer alone, without a scenario box or a page send button", async () => {
  const { container } = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
  expect(screen.queryByRole("textbox", { name: "业务场景描述" })).toBeNull();
  expect(screen.queryByRole("button", { name: "发送" })).toBeNull();
  expect(container.querySelector('[slot="composer-actions"]')).toBeNull();
  expect(container.querySelector("dataagent-conversation")!.className).not.toContain("send-button");
});

it("adds no platform message or retry button for a failed run", async () => {
  context.model.session = { ...session(), task_status: "failed", task_detail: "提案结果被拒收：目标连接列不是唯一属性" };
  const { container } = renderWithProviders(<MemoryRouter><BuilderPage /></MemoryRouter>);
  await ready();
  expect(container.querySelector('[slot="composer-overlay"]')).toBeNull();
  expect(screen.queryByText("平台消息")).toBeNull();
  expect(screen.queryByRole("button", { name: "重试" })).toBeNull();
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

it("shows 全部已同步数据表 summary when table_scope is all", async () => {
  vi.mocked(datasetApi.registeredTables).mockResolvedValue({
    items: [
      { connection_id: "c1", connection_name: "连接A", schema_name: "s", table_name: "t1", kind: "table", comment: "", column_count: 3, datasets: [], observed_at: null },
      { connection_id: "c1", connection_name: "连接A", schema_name: "s", table_name: "t2", kind: "table", comment: "", column_count: 5, datasets: [], observed_at: null },
    ],
  });
  context.model.session = { ...session(), table_scope: "all", linked_tables: [] };
  renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  expect(await screen.findByText("全部已同步数据表（2 张）")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "选择数据表…" })).toBeInTheDocument();
});

it("shows secondary text when selected scope has 0 tables", () => {
  context.model.session = { ...session(), table_scope: "selected", linked_tables: [] };
  renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  expect(screen.getByText("未关联数据表（仅从文档建模）")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "选择数据表…" })).toBeInTheDocument();
});

it("lists removable tables when 1 to 5 tables are selected", async () => {
  const currentSession = {
    ...session(),
    table_scope: "selected" as const,
    linked_tables: [
      { connection_id: "c1", schema_name: "dw", table_name: "orders" },
      { connection_id: "c1", schema_name: "dw", table_name: "customers" },
    ],
  };
  context.model.session = currentSession;
  context.model.ensure = vi.fn().mockResolvedValue(currentSession);
  vi.mocked(modelingApi.save).mockResolvedValue({
    ...currentSession,
    linked_tables: [{ connection_id: "c1", schema_name: "dw", table_name: "customers" }],
  });

  renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  const ordersBox = screen.getByRole("checkbox", { name: "dw.orders" });
  expect(ordersBox).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "dw.customers" })).toBeChecked();

  fireEvent.click(ordersBox);
  await waitFor(() => {
    expect(modelingApi.save).toHaveBeenCalledWith(
      currentSession,
      currentSession.draft,
      {
        table_scope: "selected",
        linked_tables: [{ connection_id: "c1", schema_name: "dw", table_name: "customers" }],
      },
    );
  });
});

it("shows grouped count summary when more than 5 tables are selected", () => {
  context.model.session = {
    ...session(),
    table_scope: "selected" as const,
    linked_tables: [
      { connection_id: "c1", schema_name: "dw", table_name: "t1" },
      { connection_id: "c1", schema_name: "dw", table_name: "t2" },
      { connection_id: "c1", schema_name: "dw", table_name: "t3" },
      { connection_id: "c1", schema_name: "dw", table_name: "t4" },
      { connection_id: "c2", schema_name: "dw", table_name: "t5" },
      { connection_id: "c2", schema_name: "dw", table_name: "t6" },
    ],
  };
  renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  expect(screen.getByText("已选 6 张（c1 4、c2 2）")).toBeInTheDocument();
});

it.each([
  ["viewer member", { role: "viewer" as const, is_public: false, visibility: "member" as const }],
  ["public non-member", { role: null, is_public: true, visibility: "public" as const }],
])("disables editing and conversation sending for %s", async (_label, patch) => {
  context.workspace = workspace(patch);
  vi.mocked(modelingApi.materials).mockResolvedValue({
    items: [{ id: "m1", name: "制度.md", byte_size: 120, chunk_count: 2, sha256: "a".repeat(64) } as Material],
  });
  const currentSession = { ...session(), material_ids: ["m1"] };
  context.model.session = currentSession;

  const { container } = renderWithProviders(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  await ready();

  expect(await screen.findByText("制度.md")).toBeInTheDocument();
  expect(screen.getByRole("checkbox")).toBeDisabled();
  expect(screen.queryByRole("button", { name: "新建会话" })).toBeNull();
  expect(screen.queryByRole("button", { name: "选择会话模式" })).toBeNull();
  expect(screen.queryByRole("button", { name: "放弃会话" })).toBeNull();
  expect(screen.queryByRole("button", { name: "选择数据表…" })).toBeNull();
  expect(screen.queryByText("点击或拖拽文件至此上传")).toBeNull();

  const conversation = container.querySelector("dataagent-conversation") as AgentConversationElement;
  expect(conversation).toHaveAttribute("disabled");
  expect(conversation).toHaveAttribute("placeholder", "只读模式下不可发送消息");
  expect(conversation.beforeSend?.({ text: "hello" } as never)).toBe(false);
});
