import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, navigation } from "../api/client";
import { renderWithProviders } from "../test/renderWithProviders";
import { LoginPage } from "./LoginPage";

vi.mock("../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/client")>();
  return {
    ...actual,
    api: {
      ...actual.api,
      authOptions: vi.fn(),
      loginLocal: vi.fn(),
    },
    navigation: {
      assign: vi.fn(),
    },
  };
});

function show(initialEntry = "/login") {
  const router = createMemoryRouter(
    [
      { path: "/login", element: <LoginPage /> },
      { path: "/", element: <p>工作空间目录</p> },
      { path: "/workspaces/:workspaceId/mappings", element: <p>数据管理页</p> },
    ],
    { initialEntries: [initialEntry] },
  );
  renderWithProviders(<RouterProvider router={router} />);
  return router;
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(cleanup);

describe("登录页", () => {
  it("只开启本地登录时显示用户名密码表单，不显示分割线与单点登录按钮", async () => {
    vi.mocked(api.authOptions).mockResolvedValue({ local_login: true, oauth: null });
    show();

    expect(await screen.findByRole("heading", { name: "OntoFoundry" })).toBeInTheDocument();
    expect(screen.getByText("请登录后继续")).toBeInTheDocument();
    expect(screen.getByLabelText("用户名")).toBeInTheDocument();
    expect(screen.getByLabelText("密码")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "登录" })).toBeInTheDocument();
    expect(screen.queryByText("或")).toBeNull();
    expect(screen.queryByRole("button", { name: /通过 .* 登录/ })).toBeNull();
  });

  it("只开启单点登录时只显示通过提供商登录按钮并触发浏览器跳转", async () => {
    vi.mocked(api.authOptions).mockResolvedValue({ local_login: false, oauth: { name: "SSO" } });
    show("/login?return_to=%2Fworkspaces%2Fws-demo%2Fview");

    const ssoButton = await screen.findByRole("button", { name: "通过 SSO 登录" });
    expect(screen.queryByLabelText("用户名")).toBeNull();
    expect(screen.queryByLabelText("密码")).toBeNull();
    expect(screen.queryByText("或")).toBeNull();

    fireEvent.click(ssoButton);
    expect(navigation.assign).toHaveBeenCalledWith(
      "/api/v1/auth/login/SSO?return_to=%2Fworkspaces%2Fws-demo%2Fview",
    );
  });

  it("同时开启本地与单点登录时显示表单、或分割线与单点登录按钮", async () => {
    vi.mocked(api.authOptions).mockResolvedValue({ local_login: true, oauth: { name: "统一认证" } });
    show();

    expect(await screen.findByRole("button", { name: "登录" })).toBeInTheDocument();
    expect(screen.getByText("或")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "通过 统一认证 登录" })).toBeInTheDocument();
  });

  it("本地登录返回 401 时显示用户名或密码错误并停留在登录页", async () => {
    vi.mocked(api.authOptions).mockResolvedValue({ local_login: true, oauth: null });
    vi.mocked(api.loginLocal).mockRejectedValue(new ApiError("Unauthorized", 401));
    const router = show("/login?return_to=%2Fworkspaces%2Fws-demo%2Fmappings");

    fireEvent.change(await screen.findByLabelText("用户名"), { target: { value: "linxiao" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "wrong-password" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("用户名或密码错误");
    expect(api.loginLocal).toHaveBeenCalledWith({ username: "linxiao", password: "wrong-password" });
    expect(router.state.location.pathname).toBe("/login");
  });

  it("本地登录成功后跳转到 return_to，缺省或不安全地址回退到根路径", async () => {
    vi.mocked(api.authOptions).mockResolvedValue({ local_login: true, oauth: null });
    vi.mocked(api.loginLocal).mockResolvedValue(undefined);

    const routerWithTarget = show("/login?return_to=%2Fworkspaces%2Fws-demo%2Fmappings%3Ftab%3Ddatasets");
    fireEvent.change(await screen.findByLabelText("用户名"), { target: { value: "linxiao" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => {
      expect(routerWithTarget.state.location.pathname).toBe("/workspaces/ws-demo/mappings");
      expect(routerWithTarget.state.location.search).toBe("?tab=datasets");
    });

    cleanup();

    const routerDefault = show("/login");
    fireEvent.change(await screen.findByLabelText("用户名"), { target: { value: "linxiao" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => expect(routerDefault.state.location.pathname).toBe("/"));

    cleanup();

    const routerUnsafe = show("/login?return_to=%2F%2Fevil.invalid");
    fireEvent.change(await screen.findByLabelText("用户名"), { target: { value: "linxiao" } });
    fireEvent.change(screen.getByLabelText("密码"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "登录" }));

    await waitFor(() => expect(routerUnsafe.state.location.pathname).toBe("/"));
  });
});

describe("LoginPage SSO errors", () => {
  it("shows the message for an error code returned by the SSO callback", async () => {
    vi.mocked(api.authOptions).mockResolvedValue({ local_login: false, oauth: { name: "SSO" } });
    show("/login?error=oauth_user_info_failed");
    expect(await screen.findByRole("alert")).toHaveTextContent("认证服务用户信息获取失败，请重新登录");
  });

  it("ignores unknown error codes", async () => {
    vi.mocked(api.authOptions).mockResolvedValue({ local_login: false, oauth: { name: "SSO" } });
    show("/login?error=<script>");
    await screen.findByRole("button", { name: "通过 SSO 登录" });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
