import { afterEach, describe, expect, it, vi } from "vitest";
import { adminApi, api } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("external-agent gateway API client", () => {
  it("manages personal access tokens against /api/v1/auth/tokens", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [] }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "t1",
            name: "办公电脑",
            permissions: ["ontology:read", "mappings:read"],
            created_at: "2026-11-13T00:00:00Z",
            token: "ofpat.secret",
          }),
          { status: 201 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "t1",
            name: "新名称",
            permissions: ["ontology:read"],
            created_at: "2026-11-13T00:00:00Z",
            updated_at: "2026-11-13T00:01:00Z",
            last_used_at: null,
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetcher);

    await expect(api.tokens()).resolves.toEqual({ items: [] });
    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "/api/v1/auth/tokens",
      expect.objectContaining({ credentials: "include" }),
    );

    const created = await api.createToken({
      name: "办公电脑",
      permissions: ["ontology:read", "mappings:read"],
    });
    expect(created.token).toBe("ofpat.secret");
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      "/api/v1/auth/tokens",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          name: "办公电脑",
          permissions: ["ontology:read", "mappings:read"],
        }),
      }),
    );

    await api.updateToken("t1", { name: "新名称" });
    expect(fetcher).toHaveBeenNthCalledWith(
      3,
      "/api/v1/auth/tokens/t1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ name: "新名称" }),
      }),
    );

    await expect(api.revokeToken("t1")).resolves.toBeUndefined();
    expect(fetcher).toHaveBeenNthCalledWith(
      4,
      "/api/v1/auth/tokens/t1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it("queries workspace feedback and admin gateway audit endpoints", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [], next_cursor: null }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [], next_cursor: "c2" }), {
          status: 200,
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "call-1",
            created_at: "2026-11-13T00:00:00Z",
            user: { id: "u1", display_name: "张三" },
            tool: "list_spaces",
            request_id: "r1",
            workspaces: [],
            arguments: {},
            response: { spaces: [] },
            outcome: "ok",
            error_code: null,
            error_message: null,
            duration_ms: 12,
          }),
          { status: 200 },
        ),
      );
    vi.stubGlobal("fetch", fetcher);

    await api.feedback("ws-1", { cursor: "cur-1", limit: 20 });
    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "/api/v1/workspaces/ws-1/feedback?cursor=cur-1&limit=20",
      expect.objectContaining({ credentials: "include" }),
    );

    await adminApi.gatewayCalls({
      user_id: "u1",
      workspace_id: "ws-1",
      tool: "search_ontology",
      outcome: "ok",
      from: "2026-11-12T00:00:00Z",
      to: "2026-11-13T00:00:00Z",
      limit: 20,
    });
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      "/api/v1/admin/gateway-calls?user_id=u1&workspace_id=ws-1&tool=search_ontology&outcome=ok&from=2026-11-12T00%3A00%3A00Z&to=2026-11-13T00%3A00%3A00Z&limit=20",
      expect.objectContaining({ credentials: "include" }),
    );

    await adminApi.gatewayCall("call-1");
    expect(fetcher).toHaveBeenNthCalledWith(
      3,
      "/api/v1/admin/gateway-calls/call-1",
      expect.objectContaining({ credentials: "include" }),
    );
  });
});
