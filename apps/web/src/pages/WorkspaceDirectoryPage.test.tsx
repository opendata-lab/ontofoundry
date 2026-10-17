import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api } from "../api/client";
import { workspace } from "../test/apiRecords";
import { renderWithProviders } from "../test/renderWithProviders";
import { WorkspaceDirectoryPage } from "./WorkspaceDirectoryPage";

vi.mock("../api/client", () => ({ api: { workspaces: vi.fn(), me: vi.fn(), createWorkspace: vi.fn() } }));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.me).mockResolvedValue({ id: "u1", subject: "demo:linxiao", display_name: "林晓", email: null });
  vi.mocked(api.workspaces).mockResolvedValue({
    items: [
      workspace({ name: "星河示例空间" }),
      workspace({ id: "w2", name: "云杉示例空间", role: null, visibility: "published_only", current_version: null }),
    ],
  });
});
afterEach(cleanup);

const show = () => {
  const router = createMemoryRouter([
    { path: "/", element: <WorkspaceDirectoryPage /> },
    { path: "/workspaces/:id/view", element: <p>本体视图</p> },
  ]);
  renderWithProviders(<RouterProvider router={router} />);
  return router;
};

it("keeps workspace links, publication states and reader access", async () => {
  show();
  expect(await screen.findByRole("link", { name: /^星河示例空间/ })).toHaveAttribute("href", "/workspaces/w1/view");
  expect(screen.getByText("v1 · 已发布")).toBeInTheDocument();
  expect(screen.getByText("尚未发布")).toBeInTheDocument();
  expect(screen.getByText("仅本体可见")).toBeInTheDocument();
});

it("creates a workspace and enters its ontology view", async () => {
  vi.mocked(api.createWorkspace).mockResolvedValue(workspace({ id: "w-new", name: "青禾示例空间" }));
  const router = show();
  fireEvent.click(await screen.findByRole("button", { name: "创建工作空间" }));
  fireEvent.change(screen.getByRole("textbox", { name: "空间名称" }), { target: { value: "青禾示例空间" } });
  fireEvent.change(screen.getByRole("textbox", { name: "空间标识" }), { target: { value: "qinghe-demo" } });
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "创建工作空间" }));
  await waitFor(() => expect(router.state.location.pathname).toBe("/workspaces/w-new/view"));
  expect(api.createWorkspace).toHaveBeenCalledWith({ name: "青禾示例空间", slug: "qinghe-demo", description: "" });
});
