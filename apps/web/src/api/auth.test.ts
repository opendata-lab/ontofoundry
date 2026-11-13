import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, authOptions, loginLocal, logout, navigation, workspaceRequest } from "./client";
import { definitionReads } from "./definitionReads";

beforeEach(() => {
  window.history.replaceState({}, "", "/workspaces/ws-demo/mappings?tab=datasets");
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  definitionReads.clear();
  window.history.replaceState({}, "", "/");
});

describe("auth client and 401 handling", () => {
  it("fetches auth options, posts local login, posts logout, and builds oauth URL", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ local_login: true, oauth: { name: "SSO" } }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetcher);

    const options = await api.authOptions();
    expect(options).toEqual({ local_login: true, oauth: { name: "SSO" } });
    expect(fetcher).toHaveBeenNthCalledWith(
      1,
      "/api/v1/auth/options",
      expect.objectContaining({ credentials: "include" }),
    );

    await expect(api.loginLocal({ username: "linxiao", password: "secret" })).resolves.toBeUndefined();
    expect(fetcher).toHaveBeenNthCalledWith(
      2,
      "/api/v1/auth/login/local",
      expect.objectContaining({
        method: "POST",
        credentials: "include",
        body: JSON.stringify({ username: "linxiao", password: "secret" }),
      }),
    );

    const clearSpy = vi.spyOn(definitionReads, "clear");
    await expect(api.logout()).resolves.toBeUndefined();
    expect(fetcher).toHaveBeenNthCalledWith(
      3,
      "/api/v1/auth/logout",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
    expect(clearSpy).toHaveBeenCalledTimes(1);

    expect(api.oauthLoginUrl("SSO", "/workspaces/ws-demo/view?tab=objects")).toBe(
      "/api/v1/auth/login/SSO?return_to=%2Fworkspaces%2Fws-demo%2Fview%3Ftab%3Dobjects",
    );
  });

  it("redirects to /login?return_to=<current path> on 401 from API requests", async () => {
    const assignSpy = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    const clearSpy = vi.spyOn(definitionReads, "clear");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "登录已失效" }), { status: 401 })),
    );

    const result = api.me();
    await expect(result).rejects.toBeInstanceOf(ApiError);
    await expect(result).rejects.toMatchObject({ status: 401 });
    expect(clearSpy).toHaveBeenCalled();
    expect(assignSpy).toHaveBeenCalledWith(
      "/login?return_to=%2Fworkspaces%2Fws-demo%2Fmappings%3Ftab%3Ddatasets",
    );
  });

  it("also redirects on 401 from workspaceRequest", async () => {
    window.history.replaceState({}, "", "/workspaces/ws-demo/builder#draft");
    const assignSpy = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

    await expect(workspaceRequest("ws-demo", "/sessions")).rejects.toMatchObject({ status: 401 });
    expect(assignSpy).toHaveBeenCalledWith(
      "/login?return_to=%2Fworkspaces%2Fws-demo%2Fbuilder%23draft",
    );
  });

  it("does not redirect on 401 from /auth/options or /auth/login/local", async () => {
    const assignSpy = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "用户名或密码错误" }), { status: 401 }))
        .mockResolvedValueOnce(new Response(null, { status: 401 })),
    );

    await expect(api.loginLocal({ username: "linxiao", password: "wrong" })).rejects.toMatchObject({
      status: 401,
      message: "用户名或密码错误",
    });
    await expect(api.authOptions()).rejects.toMatchObject({ status: 401 });
    expect(assignSpy).not.toHaveBeenCalled();
  });

  it("does not redirect when already on /login", async () => {
    window.history.replaceState({}, "", "/login?return_to=%2F");
    const assignSpy = vi.spyOn(navigation, "assign").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

    await expect(api.me()).rejects.toMatchObject({ status: 401 });
    expect(assignSpy).not.toHaveBeenCalled();
  });

  it("exports standalone typed authOptions, loginLocal, and logout helpers", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ local_login: true, oauth: null }), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetcher);

    await expect(authOptions()).resolves.toEqual({ local_login: true, oauth: null });
    await expect(loginLocal({ username: "linxiao", password: "secret" })).resolves.toBeUndefined();
    await expect(logout()).resolves.toBeUndefined();
    expect(fetcher).toHaveBeenCalledTimes(3);
  });
});
