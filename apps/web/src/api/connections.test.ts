import { afterEach, expect, it, vi } from "vitest";
import { ApiError, workspaceRequest } from "./client";

afterEach(() => vi.unstubAllGlobals());

it("sends DELETE through workspaceRequest and accepts an empty 204 response", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetcher);
  await expect(workspaceRequest<void>("fiction", "/connections/fiction-source", undefined, "DELETE")).resolves.toBeUndefined();
  expect(fetcher).toHaveBeenCalledWith("/api/v1/workspaces/fiction/connections/fiction-source", expect.objectContaining({ method: "DELETE" }));
});

it("retains structured connection references from the service error envelope", async () => {
  const error = {
    code: "CONNECTION_IN_USE", message: "该连接仍被引用，请先改用其他连接或删除这些数据集",
    references: [{ type: "dataset", name: "虚构订单", location: "已发布版本" }],
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error }), { status: 409 })));
  const result = workspaceRequest("fiction", "/connections/fiction-source", undefined, "DELETE");
  await expect(result).rejects.toBeInstanceOf(ApiError);
  await expect(result).rejects.toMatchObject({ status: 409, ...error });
});
