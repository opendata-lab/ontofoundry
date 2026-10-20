import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, catalogApi, modelingApi } from "../api/client";
import type { Assets, Draft } from "../api/types";
import { useSnapshot } from "../hooks/useSnapshot";
import { example } from "../test/drafts";
import { renderWithProviders } from "../test/renderWithProviders";
import { MappingsPage } from "./MappingsPage";

const { open, workspace, refresh } = vi.hoisted(() => ({
  open: vi.fn(),
  refresh: vi.fn(),
  workspace: { id: "w", role: "admin", current_version: 1, version_id: "v1" },
}));
vi.mock("../hooks/useWorkspaceContext", () => ({ useWorkspaceContext: () => ({ workspace, refresh }) }));
vi.mock("../hooks/useElementDetail", () => ({ useElementDetail: () => ({ open }) }));
vi.mock("../hooks/useSnapshot", () => ({ useSnapshot: vi.fn() }));
vi.mock("../hooks/usePageTab", () => ({ usePageTab: vi.fn(), usePageActive: () => true }));
vi.mock("react-router-dom", () => ({ Link: ({ children }: { children: unknown }) => children }));
vi.mock("../api/client", () => ({
  api: { workspace: vi.fn() },
  modelingApi: { saveElement: vi.fn(), get: vi.fn() },
  catalogApi: { connections: vi.fn(), schemas: vi.fn(), tables: vi.fn(), assets: vi.fn(), refreshAssets: vi.fn() },
  ApiError: class extends Error {},
}));

let draft: Draft;
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(catalogApi.tables).mockResolvedValue({ items: [] });
  draft = example("06-inheritance");
  vi.mocked(useSnapshot).mockReturnValue({
    draft,
    error: "",
    sessionId: null,
    suffix: "",
    load: vi.fn(),
    setDraft: vi.fn(),
  });
});
afterEach(cleanup);

describe("data mapping page", () => {
  it("lists registered datasets with their usage and opens one", () => {
    renderWithProviders(<MappingsPage />);
    const parties = screen.getByRole("button", { name: "parties" }).closest("tr")!;
    expect(within(parties).getByText("6")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "parties" }));
    expect(open).toHaveBeenCalledWith({ kind: "dataset", id: draft.datasets[0].id, sessionId: null });
  });

  it("filters registered datasets by name or physical table", () => {
    renderWithProviders(<MappingsPage />);
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索数据集" }), { target: { value: "parties" } });
    expect(screen.getByRole("button", { name: "parties" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "vehicles" })).toBeNull();
  });

  it("registers a catalog table as a dataset through an element save", async () => {
    const assets: Assets = {
      connection_id: "c",
      version_id: "v1",
      metadata_snapshot_id: "m",
      observed_at: "2026-10-16T00:00:00Z",
      error: null,
      changes: [],
      status: "ready",
      items: [
        {
          name: "contacts",
          schema: "crm",
          comment: "联系人",
          missing: false,
          datasets: [],
          columns: [
            { name: "id", type: "bigint", primary_key: true, comment: "编号" },
            { name: "snapshot_on", type: "date", primary_key: false, comment: "快照日" },
          ],
        },
      ],
    };
    vi.mocked(catalogApi.connections).mockResolvedValue({ items: [{ id: "c", name: "主库", kind: "postgresql" } as never] });
    vi.mocked(catalogApi.schemas).mockResolvedValue({ items: ["crm"] });
    vi.mocked(catalogApi.assets).mockResolvedValue(assets);
    vi.mocked(api.workspace).mockResolvedValue({ version_id: "v1" } as never);
    vi.mocked(modelingApi.saveElement).mockResolvedValue({ version: {} as never, draft, session: null });
    renderWithProviders(<MappingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "从数据目录登记" }));
    fireEvent.click(await screen.findByRole("button", { name: "登记" }));
    const form = (await screen.findAllByRole("dialog")).find((d) => d.textContent?.includes("将带入"))!;
    expect(within(form).getByRole("textbox", { name: "数据集名称" })).toHaveValue("联系人");
    fireEvent.click(within(form).getByRole("button", { name: "登记" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalled());
    const [, payload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
    expect(payload).toMatchObject({ target_kind: "dataset", expected_current_version_id: "v1", session_id: null });
    expect(payload.draft.datasets.find((d) => d.id === payload.target_id)).toMatchObject({
      name: "联系人",
      dialect: "postgresql",
      schema_name: "crm",
      table_name: "contacts",
      columns: [
        { name: "id", physical_type: "bigint", comment: "编号" },
        { name: "snapshot_on", physical_type: "date", comment: "快照日" },
      ],
    });
    expect(refresh).toHaveBeenCalled();
  });

  it("refreshes only the selected table and labels the action accordingly", async () => {
    const assets: Assets = {
      connection_id: "c",
      version_id: null,
      metadata_snapshot_id: "m",
      observed_at: "2026-10-16T00:00:00Z",
      error: null,
      changes: [],
      status: "ready",
      items: [
        {
          name: "contacts",
          schema: "crm",
          comment: "联系人",
          missing: false,
          datasets: [],
          columns: [{ name: "id", type: "bigint", primary_key: true, comment: "编号" }],
        },
      ],
    };
    vi.mocked(catalogApi.connections).mockResolvedValue({ items: [{ id: "c", name: "主库", kind: "postgresql" } as never] });
    vi.mocked(catalogApi.schemas).mockResolvedValue({ items: ["crm"] });
    vi.mocked(catalogApi.tables).mockResolvedValue({
      items: [
        { name: "contacts", schema: "crm", columns: [] },
        { name: "orders", schema: "crm", columns: [] },
      ],
    });
    vi.mocked(catalogApi.assets).mockResolvedValue(assets);
    vi.mocked(catalogApi.refreshAssets).mockResolvedValue(assets);
    renderWithProviders(<MappingsPage />);
    fireEvent.click(screen.getByRole("button", { name: "从数据目录登记" }));
    const dialog = await screen.findByRole("dialog", { name: "从数据目录登记数据集" });
    await waitFor(() => expect(catalogApi.tables).toHaveBeenCalled());
    fireEvent.mouseDown(within(dialog).getByRole("combobox", { name: "选择数据表" }));
    fireEvent.click(await screen.findByText("orders", { selector: ".ant-select-item-option-content" }));
    fireEvent.click(within(dialog).getByRole("button", { name: "刷新" }));
    await waitFor(() =>
      expect(catalogApi.refreshAssets).toHaveBeenCalledWith("w", "c", { schema_name: "" }, ["orders"]),
    );
  });
});
