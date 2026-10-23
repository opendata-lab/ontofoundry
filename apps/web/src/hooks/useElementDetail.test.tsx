import { act, cleanup } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { renderWithProviders } from "../test/renderWithProviders";
import { useElementDetail } from "./useElementDetail";

const context = vi.hoisted(() => ({ workspace: { id: "fictional-space" } }));
vi.mock("./useWorkspaceContext", () => ({ useWorkspaceContext: () => context }));
afterEach(cleanup);

it("keeps callbacks stable and updates workspace and default session dependencies", async () => {
  let detail!: ReturnType<typeof useElementDetail>;
  function Probe() {
    detail = useElementDetail();
    return null;
  }
  const router = createMemoryRouter([{ path: "*", element: <Probe /> }], {
    initialEntries: ["/workspaces/fictional-space/view?session=s1"],
  });
  renderWithProviders(<RouterProvider router={router} />);
  const first = detail;
  const request = { kind: "object_type", id: "fictional-order" } as const;
  await act(() => router.navigate("/workspaces/fictional-space/view?session=s1&tab=basic"));
  expect(detail.href).toBe(first.href);
  expect(detail.open).toBe(first.open);
  expect(detail.href(request)).toContain("session=s1");
  expect(detail.href({ ...request, sessionId: null })).not.toContain("session=");
  expect(detail.href({ ...request, sessionId: "explicit" })).toContain("session=explicit");
  await act(() => router.navigate("/workspaces/fictional-space/view?session=s2"));
  expect(detail.href).not.toBe(first.href);
  expect(detail.href(request)).toContain("session=s2");
  context.workspace = { id: "fictional-harbor" };
  await act(() => router.navigate("/workspaces/fictional-harbor/view"));
  expect(detail.href(request)).toContain("/workspaces/fictional-harbor/");
  expect(detail.href(request)).not.toContain("session=");
  await act(() => detail.open(request));
  expect(router.state.location.pathname).toBe("/workspaces/fictional-harbor/elements/object_type/fictional-order");
});
