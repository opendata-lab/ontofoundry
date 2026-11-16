import { afterEach, describe, expect, it, vi } from "vitest";
import {
  api,
  catalogApi,
  exportApi,
  importApi,
  instancesApi,
  metricsApi,
  modelingApi,
  proposalsApi,
  publishApi,
} from "./client";
import type { ModelingSession } from "./types";
import { modelingSession } from "../test/apiRecords";

describe("api client endpoint routes (step 1)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  const session: ModelingSession = modelingSession({
    id: "session-1",
    workspace_id: "ws-1",
    title: "Session 1",
    revision: 1,
  });

  it("points ontology and instance calls to /api/v1/workspaces/{w}", async () => {
    const fetcher = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/objects/ref-1/neighborhood")) {
        return new Response(JSON.stringify({ center: null, neighbors: [] }));
      }
      if (url.includes("/objects/ref-1")) {
        return new Response(JSON.stringify({ id: "ref-1", data: {} }));
      }
      if (url.includes("/objects")) {
        return new Response(JSON.stringify({ items: [] }));
      }
      if (url.includes("/version?")) {
        return new Response(JSON.stringify({ version_id: "v-1" }));
      }
      if (url.includes("/types/type-1/presentation")) {
        return new Response(
          JSON.stringify({
            workspace_id: "ws-1",
            version_id: "v-1",
            complete: false,
            representation: "element-1",
            model: session.draft,
          }),
        );
      }
      if (url.includes("/types/type-1/document-context")) {
        return new Response(
          JSON.stringify({
            workspace_id: "ws-1",
            version_id: "v-1",
            material_objects: [],
            material_links: [],
          }),
        );
      }
      if (url.includes("/types/type-1")) {
        return new Response(JSON.stringify({ id: "type-1" }));
      }
      if (url.includes("/types")) {
        return new Response(JSON.stringify({ items: [] }));
      }
      if (url.includes("/catalog")) {
        return new Response(JSON.stringify({ items: [] }));
      }
      if (url.includes("/search")) {
        return new Response(JSON.stringify({ items: [] }));
      }
      if (url.includes("/type-graph/neighborhood")) {
        return new Response(JSON.stringify({ nodes: [], edges: [] }));
      }
      return new Response(JSON.stringify({}));
    });
    vi.stubGlobal("fetch", fetcher);

    await api.version("ws-1", "v-1");
    expect(fetcher).toHaveBeenLastCalledWith(
      "/api/v1/workspaces/ws-1/version?version_id=v-1",
      expect.anything(),
    );

    await api.types("ws-1");
    expect(fetcher).toHaveBeenLastCalledWith(
      "/api/v1/workspaces/ws-1/types",
      expect.anything(),
    );

    await api.catalog("ws-1", { version_id: "v-1" });
    expect(fetcher).toHaveBeenLastCalledWith(
      "/api/v1/workspaces/ws-1/catalog?version_id=v-1",
      expect.anything(),
    );

    await api.type("ws-1", "type-1");
    expect(fetcher).toHaveBeenLastCalledWith(
      "/api/v1/workspaces/ws-1/types/type-1",
      expect.anything(),
    );

    await api.graph("ws-1");
    expect(fetcher).toHaveBeenLastCalledWith(
      "/api/v1/workspaces/ws-1/type-graph/neighborhood",
      expect.anything(),
    );

    await api.searchOntology("ws-1", { query: "order" });
    expect(fetcher).toHaveBeenLastCalledWith(
      "/api/v1/workspaces/ws-1/search",
      expect.objectContaining({ method: "POST" }),
    );

    await api.elementPresentation("ws-1", "object_type", "type-1", "v-1");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/workspaces/ws-1/types/type-1/presentation?kind=object_type&version_id=v-1",
      expect.anything(),
    );

    await api.elementDocuments("ws-1", "object_type", "type-1", "v-1");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/workspaces/ws-1/types/type-1/document-context?kind=object_type&version_id=v-1",
      expect.anything(),
    );

    await instancesApi.list("ws-1", {});
    expect(fetcher).toHaveBeenLastCalledWith(
      "/api/v1/workspaces/ws-1/objects",
      expect.anything(),
    );

    await instancesApi.get("ws-1", "ref-1");
    expect(fetcher).toHaveBeenLastCalledWith(
      "/api/v1/workspaces/ws-1/objects/ref-1",
      expect.anything(),
    );

    await instancesApi.neighborhood("ws-1", "ref-1");
    expect(fetcher).toHaveBeenLastCalledWith(
      "/api/v1/workspaces/ws-1/objects/ref-1/neighborhood",
      expect.anything(),
    );
  });

  it("points publish-preview and proposals fact-revision to new paths", async () => {
    const fetcher = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/publish-preview")) {
        return new Response(
          JSON.stringify({
            session_revision: 1,
            current_version_id: null,
            merged_snapshot_sha256: "sha",
            instance_change_sequence: 0,
            merged_model: session.draft,
            changes: [],
            auto_merged: [],
            conflicts: [],
          }),
        );
      }
      if (url.includes("/fact-revision")) {
        return new Response(JSON.stringify({ id: "batch-1", items: [] }));
      }
      return new Response(JSON.stringify({}));
    });
    vi.stubGlobal("fetch", fetcher);

    await publishApi.preview(session);
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/workspaces/ws-1/sessions/session-1/publish-preview",
      expect.objectContaining({ method: "POST" }),
    );

    await proposalsApi.reviseFact(session, "prop-1", {
      expected_session_revision: 1,
      target_id: "obj-1",
      expected_target_hash: "hash-1",
      after: {
        id: "obj-1",
        type_id: "type-1",
        values: {},
        evidence: [],
      },
    });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/workspaces/ws-1/sessions/session-1/proposals/prop-1/fact-revision",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("points metrics, imports, and exports to /api/v1/workspaces/{w}", async () => {
    const fetcher = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/metrics/preview")) {
        return new Response(JSON.stringify({ value: 42 }));
      }
      if (url.includes("/imports")) {
        return new Response(JSON.stringify({ import_id: "imp-1" }));
      }
      if (url.includes("/exports")) {
        return new Response(JSON.stringify({ version_id: "v-1" }));
      }
      return new Response(JSON.stringify({}));
    });
    vi.stubGlobal("fetch", fetcher);

    await metricsApi.preview("ws-1", {
      metric: {
        id: "m-1",
        name: "metric_1",
        kind: "expression",
        dataset_id: "ds-1",
        expression: "1",
        description: "",
        evidence: [],
        synonyms: [],
        time_field: null,
        value_kind: null,
      },
    });
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/workspaces/ws-1/metrics/preview",
      expect.objectContaining({ method: "POST" }),
    );

    const file = new File(["{}"], "test.json", { type: "application/json" });
    await importApi.preview("ws-1", "ossie-0.2", file);
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/workspaces/ws-1/imports/ossie-0.2?name=test.json",
      expect.objectContaining({ method: "POST" }),
    );

    await exportApi.preview("ws-1", "ossie-0.2", "v-1");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/workspaces/ws-1/exports/ossie-0.2?version_id=v-1",
      expect.anything(),
    );
  });

  it("verifies catalogApi has no tableMaterial method", () => {
    expect("tableMaterial" in catalogApi).toBe(false);
  });

  it("routes personal session, PATCH settings, and session-scoped element saves", async () => {
    const fetcher = vi.fn().mockImplementation(async (url: string) => {
      if (url.endsWith("/element-saves/preview")) {
        return new Response(JSON.stringify({ session_revision: 1, affected_items: [] }));
      }
      if (url.endsWith("/instance-baseline")) {
        return new Response(JSON.stringify({ change_sequence: 0, items: [] }));
      }
      return new Response(JSON.stringify(session));
    });
    vi.stubGlobal("fetch", fetcher);

    await modelingApi.personal("ws-1");
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/workspaces/ws-1/sessions/personal",
      expect.objectContaining({ method: "GET" }),
    );

    await modelingApi.updateSettings(session, { mode: "chat" });
    const patchCall = fetcher.mock.calls.find(([u]) => u === "/api/v1/workspaces/ws-1/sessions/session-1");
    expect(patchCall).toBeDefined();
    expect(patchCall![1]).toMatchObject({ method: "PATCH" });
    expect(JSON.parse(patchCall![1].body as string)).toEqual({ revision: 1, mode: "chat" });

    await modelingApi.previewElementSave("ws-1", "session-1", {
      target_kind: "object_type",
      target_id: "obj-1",
      expected_session_revision: 1,
      draft: session.draft,
    });
    const previewCall = fetcher.mock.calls.find(([u]) => u === "/api/v1/workspaces/ws-1/sessions/session-1/element-saves/preview");
    expect(previewCall).toBeDefined();
    expect(previewCall![1]).toMatchObject({ method: "POST" });
    const previewBody = JSON.parse(previewCall![1].body as string);
    expect(previewBody.draft).not.toHaveProperty("material_objects");
    expect(previewBody.draft).not.toHaveProperty("material_links");

    await modelingApi.saveElement("ws-1", "session-1", {
      target_kind: "object_type",
      target_id: "obj-1",
      expected_session_revision: 1,
      draft: session.draft,
    });
    const saveCall = fetcher.mock.calls.find(([u]) => u === "/api/v1/workspaces/ws-1/sessions/session-1/element-saves");
    expect(saveCall).toBeDefined();
    expect(saveCall![1]).toMatchObject({ method: "POST" });
    const saveBody = JSON.parse(saveCall![1].body as string);
    expect(saveBody.idempotency_key).toEqual(expect.any(String));
    expect(saveBody.idempotency_key.length).toBeGreaterThanOrEqual(8);
    expect(saveBody.idempotency_key.length).toBeLessThanOrEqual(64);
    expect(saveBody.draft).not.toHaveProperty("material_objects");
    expect(saveBody.draft).not.toHaveProperty("material_links");
  });
});
