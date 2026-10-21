import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { catalogApi } from "../api/client";
import type { Assets, SyncJob } from "../api/types";
import { renderWithProviders } from "../test/renderWithProviders";
import { MappingsPage } from "./MappingsPage";

const { workspace } = vi.hoisted(() => ({
  workspace: { id: "w", role: "admin", current_version: 1, version_id: "v1" },
}));
vi.mock("../hooks/useWorkspaceContext", () => ({ useWorkspaceContext: () => ({ workspace, refresh: vi.fn() }) }));
vi.mock("../hooks/usePageTab", () => ({ usePageTab: vi.fn(), usePageActive: () => true }));
vi.mock("react-router-dom", () => ({ useSearchParams: () => [new URLSearchParams()] }));
vi.mock("../components/DocumentMaterials", () => ({ DocumentMaterials: () => <div>文档列表</div> }));
vi.mock("../api/client", () => ({
  catalogApi: {
    connections: vi.fn(),
    schemas: vi.fn(),
    tables: vi.fn(),
    assets: vi.fn(),
    syncJobs: vi.fn(),
    syncJob: vi.fn(),
    refreshAssets: vi.fn(),
    retrySync: vi.fn(),
  },
}));

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
      columns: [{ name: "id", type: "bigint", primary_key: true, comment: "编号" }],
    },
    { name: "archived", schema: "crm", comment: "", missing: true, datasets: [], columns: [] },
  ],
};

const job = (patch: Partial<SyncJob>): SyncJob => ({
  id: "j",
  connection_id: "c",
  schema_name: "crm",
  scope: "all",
  state: "succeeded",
  duration_ms: 120,
  error: null,
  total: 45,
  processed: 45,
  available: 45,
  failed: 0,
  batches: [],
  ...patch,
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(catalogApi.connections).mockResolvedValue({ items: [{ id: "c", name: "主库", kind: "postgresql" } as never] });
  vi.mocked(catalogApi.schemas).mockResolvedValue({ items: ["crm"] });
  vi.mocked(catalogApi.tables).mockResolvedValue({
    items: [
      { name: "contacts", schema: "crm", columns: [] },
      { name: "orders", schema: "crm", columns: [] },
    ],
  });
  vi.mocked(catalogApi.assets).mockResolvedValue(assets);
  vi.mocked(catalogApi.syncJobs).mockResolvedValue({ items: [] });
});
afterEach(cleanup);

describe("data management page", () => {
  it("separates tables from documents and lists registered tables with their state", async () => {
    renderWithProviders(<MappingsPage />);
    expect(screen.getByRole("tab", { name: "数据表" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "文档" })).toBeInTheDocument();
    expect(await screen.findByText("contacts")).toBeInTheDocument();
    expect(screen.getByText("已登记")).toBeInTheDocument();
    expect(screen.getByText("当前不可见或不存在")).toBeInTheDocument();
  });

  it("runs a full sync when no table is chosen", async () => {
    vi.mocked(catalogApi.refreshAssets).mockResolvedValue(job({ state: "queued", total: null, processed: 0, available: 0 }));
    renderWithProviders(<MappingsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "全量同步" }));
    await waitFor(() => expect(catalogApi.refreshAssets).toHaveBeenCalledWith("w", "c", { schema_name: "" }, []));
    expect(await screen.findByText(/正在发现数据表/)).toBeInTheDocument();
  });

  it("offers a retry for failed batches and shows progress", async () => {
    vi.mocked(catalogApi.syncJobs).mockResolvedValue({ items: [job({ state: "partial_failed", available: 44, failed: 1 })] });
    vi.mocked(catalogApi.retrySync).mockResolvedValue(job({ state: "queued" }));
    renderWithProviders(<MappingsPage />);
    expect(await screen.findByText(/已处理 45\/45，可用 44，失败 1/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试失败批次" }));
    await waitFor(() => expect(catalogApi.retrySync).toHaveBeenCalledWith("w", "c", "j"));
  });
});
