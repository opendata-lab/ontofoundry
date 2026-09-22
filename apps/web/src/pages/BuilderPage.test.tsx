import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { ModelingSession, Workspace } from "../api/types";
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
  },
}));

function session(): ModelingSession {
  return {
    id: "s1",
    workspace_id: "w1",
    title: "Session",
    revision: 1,
    base_version_id: null,
    draft: {
      schema_version: "1",
      workspace_id: "w1",
      object_types: [],
      link_types: [],
      objects: [],
      links: [],
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
  expect(screen.getByRole("heading", { name: "本体自动构建" })).toBeInTheDocument();
});
