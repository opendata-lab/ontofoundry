import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ModelingSession, Workspace } from "../api/types";
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
    connections: vi.fn().mockResolvedValue({ items: [] }),
    capabilities: vi.fn().mockResolvedValue({
      agent_configured: true,
      model: "DataAgent",
      max_file_mb: 256,
      connections_configured: false,
      skills: [],
    }),
  },
  proposalsApi: {
    batches: vi.fn().mockResolvedValue({ items: [], next_cursor: null }),
    batch: vi.fn(),
    decide: vi.fn(),
  },
  ApiError: class extends Error {},
}));

function session(): ModelingSession {
  return {
    id: "s1",
    workspace_id: "w1",
    title: "Session",
    revision: 1,
    base_version_id: null,
    draft: {
      schema_version: "2",
      workspace_id: "w1",
      ontology_requires: [],
      object_types: [],
      properties: [],
      link_types: [],
      rules: [],
      actions: [],
      material_objects: [],
      material_links: [],
      mappings: [],
    },
    graph: {
      workspace_id: "w1",
      version_id: "",
      version_sha256: "",
      nodes: [],
      edges: [],
    },
    candidates: [],
    material_ids: [],
    task_status: "idle",
    task_detail: "",
    updated_at: "",
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  context.workspace = {
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
  };
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
  const { container } = render(
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

it("starts a modeling run only from 开始建模, tagged so the BFF expects proposals", async () => {
  context.model.session = { ...session(), material_ids: ["m1"] };
  const { container } = render(
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
  const start = await screen.findByRole("button", { name: "开始建模" });
  await waitFor(() => expect(start).toBeEnabled());

  fireEvent.change(screen.getByPlaceholderText(/描述你希望构建的业务本体/), {
    target: { value: "渠道销售" },
  });
  fireEvent.click(start);

  expect(sendMessage).toHaveBeenCalledWith("渠道销售", {
    metadata: { mode: "model" },
  });
});

it("keeps 开始建模 disabled without material or a scenario", async () => {
  render(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("button", { name: "开始建模" })).toBeDisabled();
});

it("says when the last modeling run is waiting for the user's reply", async () => {
  context.model.session = {
    ...session(),
    task_status: "finished",
    result_state: "awaiting_reply",
    task_detail: "智能体需要你确认后才能生成提案，请在对话中回复",
  };
  render(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("status")).toHaveTextContent(
    "智能体需要你确认后才能生成提案，请在对话中回复",
  );
});

it("shows no reply hint for a run that produced its result", async () => {
  context.model.session = { ...session(), task_status: "finished", result_state: "done" };
  render(
    <MemoryRouter>
      <BuilderPage />
    </MemoryRouter>,
  );
  await screen.findByRole("button", { name: "开始建模" });
  expect(screen.queryByText(/请在对话中回复/)).toBeNull();
});
