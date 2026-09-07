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
    messages: [],
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
