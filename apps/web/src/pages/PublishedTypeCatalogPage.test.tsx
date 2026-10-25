import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { api, modelingApi } from "../api/client";
import { renderWithProviders } from "../test/renderWithProviders";
import { PublishedTypeCatalogPage } from "./PublishedTypeCatalogPage";
vi.mock("../hooks/useWorkspaceContext", () => ({ useWorkspaceContext: () => ({ workspace: { id: "w", version_id: "v7", role: "admin" }, refresh: vi.fn() }) }));
vi.mock("../api/client", async original => {
  const module = await original<typeof import("../api/client")>();
  return { ...module, api: { ...module.api, catalog: vi.fn(), presentation: vi.fn() }, modelingApi: { ...module.modelingApi, snapshot: vi.fn() } };
});
const summary = { workspace_id: "w", version_id: "v7", counts: { object_types: 30, value_types: 0, link_types: 0, metrics: 0, datasets: 0 }, tags: [], total: 30, next_cursor: "page-two", items: [{ id: "star-order", kind: "object_type", name: "fictional_orders", display_name: "星舟订单", description: "", tags: [], property_count: 4, link_count: 2, document_instance_count: 0, mapping_state: "unmapped", mapping_label: "未绑定数据集" }] };
beforeEach(() => { vi.clearAllMocks(); vi.mocked(api.catalog).mockResolvedValue(summary as never); });
afterEach(cleanup);
it("reads a fixed-version summary and navigates with the same version without a full baseline", async () => {
  renderWithProviders(<MemoryRouter><PublishedTypeCatalogPage initialKind="object_type" /></MemoryRouter>);
  const link = await screen.findByRole("link", { name: "星舟订单" });
  expect(link.getAttribute("href")).toContain("version=v7");
  expect(api.catalog).toHaveBeenCalledWith("w", expect.objectContaining({ version_id: "v7", kind: "object_type", limit: 20 }));
  expect(modelingApi.snapshot).not.toHaveBeenCalled();
  expect(api.presentation).not.toHaveBeenCalled();
  fireEvent.click(screen.getByTitle("下一页"));
  await waitFor(() => expect(api.catalog).toHaveBeenLastCalledWith("w", expect.objectContaining({ version_id: "v7", cursor: "page-two" })));
});
it("resets the cursor when the search changes", async () => {
  renderWithProviders(<MemoryRouter><PublishedTypeCatalogPage initialKind="object_type" /></MemoryRouter>);
  await screen.findByRole("link", { name: "星舟订单" });
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索目录" }), { target: { value: "星舟" } });
  await waitFor(() => expect(api.catalog).toHaveBeenLastCalledWith("w", expect.objectContaining({ q: "星舟", cursor: undefined, version_id: "v7" })));
});
