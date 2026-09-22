import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { modelingApi } from "../api/client";
import type { ModelingSession } from "../api/types";
import { useModeling } from "./useModeling";

vi.mock("../api/client", () => ({
  modelingApi: { get: vi.fn(), sessions: vi.fn() },
}));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

function session(id: string): ModelingSession {
  return {
    id,
    workspace_id: "w",
    title: id,
    revision: 0,
    base_version_id: null,
    draft: {
      schema_version: "1",
      workspace_id: "w",
      object_types: [],
      link_types: [],
      objects: [],
      links: [],
      mappings: [],
    },
    graph: {
      workspace_id: "w",
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

it.each(["resolve", "reject"])(
  "ignores a previous session's late %s after navigation",
  async (outcome) => {
    let resolveOld!: (value: ModelingSession) => void;
    let rejectOld!: (reason: Error) => void;
    const oldRequest = new Promise<ModelingSession>((resolve, reject) => {
      resolveOld = resolve;
      rejectOld = reject;
    });
    vi.mocked(modelingApi.sessions).mockResolvedValue({ items: [] });
    vi.mocked(modelingApi.get).mockImplementation((_workspace, id) =>
      id === "old" ? oldRequest : Promise.resolve(session(id)),
    );
    const { result } = renderHook(() => useModeling("w"), {
      wrapper: ({ children }) => (
        <MemoryRouter initialEntries={["/?session=old"]}>
          {children}
        </MemoryRouter>
      ),
    });
    act(() => result.current.select("new"));
    await waitFor(() => expect(result.current.session?.id).toBe("new"));
    await act(async () => {
      if (outcome === "resolve") resolveOld(session("old"));
      else rejectOld(new Error("old request failed"));
    });
    expect(result.current.session?.id).toBe("new");
    expect(result.current.error).toBe("");
  },
);

it("automatically resumes the latest active session when the URL has none", async () => {
  vi.mocked(modelingApi.sessions).mockResolvedValue({
    items: [
      {
        id: "active",
        title: "电商核心业务本体构建",
        task_status: "running",
        updated_at: "2026-09-22T07:00:00Z",
      },
      {
        id: "idle",
        title: "空白会话",
        task_status: "idle",
        updated_at: "2026-09-22T08:00:00Z",
      },
    ],
  });
  vi.mocked(modelingApi.get).mockImplementation((_workspace, id) =>
    Promise.resolve(session(id)),
  );

  const { result } = renderHook(() => useModeling("w"), {
    wrapper: ({ children }) => (
      <MemoryRouter initialEntries={["/"]}>{children}</MemoryRouter>
    ),
  });

  await waitFor(() => expect(result.current.sessionId).toBe("active"));
  await waitFor(() => expect(result.current.session?.id).toBe("active"));
  expect(modelingApi.get).toHaveBeenCalledWith("w", "active");
});
