import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { catalogApi } from "../api/client";
import type { Assets, Dataset, SyncJob, ProposalItem } from "../api/types";
import { useState } from "react";
import { renderWithProviders } from "../test/renderWithProviders";
import { TableSyncDialog } from "../components/TableSyncDialog";
import { useSourceIssues } from "../components/proposals/ProposalSourceIssues";
import { MappingsPage } from "./MappingsPage";
import { DatasetLocationFields } from "../components/elements/DatasetLocationFields";

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
    syncedAssets: vi.fn(),
    syncJobs: vi.fn(),
    syncJob: vi.fn(),
    refreshAssets: vi.fn(),
    retrySync: vi.fn(),
    deleteTable: vi.fn(),
    tableRows: vi.fn(),
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
  vi.mocked(catalogApi.schemas).mockResolvedValue({ items: ["crm", "sales"] });
  vi.mocked(catalogApi.tables).mockResolvedValue({
    items: [
      { name: "contacts", schema: "crm", columns: [] },
      { name: "orders", schema: "crm", columns: [] },
    ],
  });
  vi.mocked(catalogApi.assets).mockImplementation(async (_w, _c, params) => params?.schema_name === "sales" ? { ...assets, items: [{ ...assets.items[0], name: "sales_orders", schema: "sales", comment: "虚构订单", columns: [], observed_at: "2026-10-20T00:00:00Z" }] } : { ...assets, items: assets.items.map((t) => ({ ...t, observed_at: "2026-10-16T00:00:00Z" })) });
  // The page reads every synced schema in one call; build it from the per-schema
  // fixtures without recording calls on schemas/assets.
  vi.mocked(catalogApi.syncedAssets).mockImplementation(async (w, c) => {
    const { items } = await vi.mocked(catalogApi.schemas).getMockImplementation()!(w, c);
    return { items: await Promise.all(items.map(async (schema) => ({ schema, assets: await vi.mocked(catalogApi.assets).getMockImplementation()!(w, c, { schema_name: schema }) }))) };
  });
  vi.mocked(catalogApi.syncJobs).mockResolvedValue({ items: [] });
});
afterEach(cleanup);

async function choose(label: string, option: string) {
  fireEvent.mouseDown(screen.getByRole("combobox", { name: label }));
  fireEvent.click(await screen.findByText(option, { selector: ".ant-select-item-option-content" }));
}
async function openTables() {
  fireEvent.click(await screen.findByRole("button", { name: "同步数据表" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "下一步" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "下一步" }));
  fireEvent.click(await screen.findByRole("checkbox", { name: "crm" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "sales" }));
  fireEvent.click(screen.getByRole("button", { name: "下一步" }));
  await screen.findByRole("checkbox", { name: "crm.contacts" });
}

describe("data management page", () => {
  it("opens a table's details, columns and first rows on demand", async () => {
    vi.mocked(catalogApi.tableRows).mockResolvedValue({ columns: ["id", "name"], items: [{ id: 1, name: "虚构联系人" }, { id: 2, name: null }], limit: 100 });
    renderWithProviders(<MappingsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "contacts" }, { timeout: 10000 }));
    const dialog = await screen.findByRole("dialog", { name: "表详情 · contacts" });
    expect(within(dialog).getByText("联系人")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("tab", { name: "字段（1）" }));
    expect(within(dialog).getByText("编号")).toBeInTheDocument();
    expect(catalogApi.tableRows).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("tab", { name: "数据" }));
    expect(await within(dialog).findByText("虚构联系人")).toBeInTheDocument();
    expect(within(dialog).getByText("NULL")).toBeInTheDocument();
    expect(catalogApi.tableRows).toHaveBeenCalledWith("w", "c", { table_name: "contacts", schema_name: "crm" });
  });

  it("keeps the schema and table when the new connection has synced them, and clears them otherwise", async () => {
    vi.mocked(catalogApi.connections).mockResolvedValue({ items: [{ id: "c", name: "主库" }, { id: "c2", name: "备库" }, { id: "c3", name: "归档库" }] as never });
    vi.mocked(catalogApi.schemas).mockImplementation(async (_w, id) => ({ items: id === "c3" ? ["sales"] : ["crm", "sales"] }));
    let latest: Dataset = { source_kind: "table", connection_id: "c", schema_name: "crm", table_name: "contacts", columns: [] } as never;
    function Controlled() {
      const [dataset, setDataset] = useState<Dataset>(latest);
      latest = dataset;
      return <DatasetLocationFields workspaceId="w" dataset={dataset} nameField={null} onChange={(patch) => setDataset((d) => ({ ...d, ...patch }))} />;
    }
    renderWithProviders(<Controlled />);
    await choose("数据库连接", "备库");
    await waitFor(() => expect(latest.columns).toEqual([{ name: "id", physical_type: "bigint", comment: "编号" }]));
    expect(latest).toMatchObject({ connection_id: "c2", schema_name: "crm", table_name: "contacts" });
    await choose("数据库连接", "归档库");
    await waitFor(() => expect(latest).toMatchObject({ connection_id: "c3", schema_name: null, table_name: "", columns: null }));
  });

  it("browses all schemas, switches libraries, searches names and comments, and sorts", async () => {
    renderWithProviders(<MappingsPage />);
    expect(await screen.findByText("sales_orders", {}, { timeout: 10000 })).toBeInTheDocument();
    expect(screen.getByText("当前不可见或不存在")).toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "库" }));
    fireEvent.click(await screen.findByText(/^crm ·/, { selector: ".ant-select-item-option-content" }));
    expect(screen.queryByText("sales_orders")).not.toBeInTheDocument();
    fireEvent.mouseDown(screen.getByRole("combobox", { name: "库" }));
    fireEvent.click(await screen.findByText(/^全部库/, { selector: ".ant-select-item-option-content" }));
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索表名或注释" }), { target: { value: "虚构订单" } });
    expect(screen.getByText("sales_orders")).toBeInTheDocument();
    expect(screen.queryByText("contacts")).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索表名或注释" }), { target: { value: "contacts" } });
    expect(screen.getByText("contacts")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索表名或注释" }), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "升序" }));
    const firstName = () => within(screen.getAllByRole("row")[1]).getAllByRole("cell")[0].textContent;
    expect(firstName()).toBe("sales_orders");
    await choose("排序字段", "按列数");
    expect(firstName()).toBe("contacts");
    await choose("排序字段", "按同步时间");
    expect(firstName()).toBe("sales_orders");
    expect(catalogApi.tables).not.toHaveBeenCalled();
  });

  it("removes a table from the registered catalog after confirming", async () => {
    vi.mocked(catalogApi.deleteTable).mockResolvedValue({ schema_name: "crm", table_name: "contacts" });
    renderWithProviders(<MappingsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "移除 contacts" }, { timeout: 10000 }));
    expect(await screen.findByText("移除 crm.contacts 的登记？")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "移除" }));
    await waitFor(() => expect(catalogApi.deleteTable).toHaveBeenCalledWith("w", "c", "crm", "contacts"));
    await waitFor(() => expect(catalogApi.syncedAssets).toHaveBeenCalledTimes(2));
    expect(catalogApi.assets).not.toHaveBeenCalled();
  });

  it("submits one full and one partial task, allows back navigation and refreshes on close", async () => {
    vi.mocked(catalogApi.refreshAssets).mockImplementation(async (_w, _c, params) => job({ id: params?.schema_name ?? "", schema_name: params?.schema_name }));
    renderWithProviders(<MappingsPage />);
    await openTables();
    fireEvent.click(screen.getByRole("button", { name: "全选全部" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "sales.orders" }));
    fireEvent.click(screen.getByRole("button", { name: "上一步" }));
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));
    expect(await screen.findByRole("checkbox", { name: "sales.contacts" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "sales.orders" })).not.toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "开始同步" }));
    await waitFor(() => expect(catalogApi.refreshAssets).toHaveBeenCalledTimes(2));
    expect(catalogApi.refreshAssets).toHaveBeenCalledWith("w", "c", { schema_name: "crm" }, []);
    expect(catalogApi.refreshAssets).toHaveBeenCalledWith("w", "c", { schema_name: "sales" }, ["contacts"]);
    const count = vi.mocked(catalogApi.syncedAssets).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    await waitFor(() => expect(vi.mocked(catalogApi.syncedAssets).mock.calls.length).toBeGreaterThan(count));
  });

  it("polls progress, prevents duplicate submission, retries failures and expands table results", async () => {
    vi.mocked(catalogApi.refreshAssets).mockResolvedValue(job({ state: "queued", total: null, processed: 0, available: 0 }));
    vi.mocked(catalogApi.syncJob).mockResolvedValue(job({ state: "partial_failed", available: 44, failed: 1, batches: [{ id: "batch", ordinal: 0, state: "failed", attempt: 1, duration_ms: 20, error: "虚构读取失败", tables: ["contacts"], results: [{ table_name: "contacts", state: "failed", error: "虚构表权限不足" }] }] }));
    vi.mocked(catalogApi.retrySync).mockResolvedValue(job({ state: "succeeded" }));
    renderWithProviders(<MappingsPage />);
    await openTables();
    fireEvent.click(screen.getByRole("button", { name: "全选全部" }));
    fireEvent.click(screen.getByRole("button", { name: "开始同步" }));
    await waitFor(() => expect(catalogApi.refreshAssets).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("button", { name: "上一步" })).toBeDisabled();
    expect(screen.queryByRole("button", { name: "开始同步" })).not.toBeInTheDocument();
    await screen.findAllByText(/成功 44，失败 1/, {}, { timeout: 4000 });
    fireEvent.click(screen.getAllByText("查看每张表结果")[0]);
    expect(await screen.findByText("虚构表权限不足")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "重试失败批次" })[0]);
    await waitFor(() => expect(catalogApi.retrySync).toHaveBeenCalledWith("w", "c", "j"));
    expect(await screen.findByText("同步完成")).toBeInTheDocument();
  });

  it("only retries the schema whose task creation failed", async () => {
    vi.mocked(catalogApi.refreshAssets).mockResolvedValueOnce(job({})).mockRejectedValueOnce(new Error("虚构网络错误")).mockResolvedValue(job({}));
    renderWithProviders(<MappingsPage />);
    await openTables();
    fireEvent.click(screen.getByRole("button", { name: "全选全部" }));
    fireEvent.click(screen.getByRole("button", { name: "开始同步" }));
    fireEvent.click(await screen.findByRole("button", { name: "重试创建任务" }));
    await waitFor(() => expect(catalogApi.refreshAssets).toHaveBeenCalledTimes(3));
    expect(vi.mocked(catalogApi.refreshAssets).mock.calls[2][2]).toEqual({ schema_name: "sales" });
  });

  it("preselects connection, schema and table through the proposal sync entry", async () => {
    const item = { status: "pending", operation: "create", target_kind: "property", source_diagnostics: [{ severity: "error", code: "SOURCE_NOT_REGISTERED", message: "虚构表未登记", path: "source", details: { connection_id: "c", schema_name: "crm", table_name: "contacts" } }] } as ProposalItem;
    function Issues() {
      const source = useSourceIssues({ item, workspaceId: "w", busy: false, fields: new Set(), onReviseDataset: vi.fn() });
      return <>{source.notes}{source.dialogs}</>;
    }
    renderWithProviders(<Issues />);
    fireEvent.click(screen.getByRole("button", { name: "去同步" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "下一步" })).toBeEnabled());
    expect(screen.getByRole("combobox", { name: "同步连接" }).closest(".ant-select")).toHaveTextContent("主库");
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));
    expect(screen.getByRole("checkbox", { name: "crm" })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));
    expect(await screen.findByRole("checkbox", { name: "crm.contacts" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "crm.orders" })).not.toBeChecked();
  });

  it("paginates registered tables after twenty rows", async () => {
    vi.mocked(catalogApi.schemas).mockResolvedValue({ items: ["crm"] });
    vi.mocked(catalogApi.assets).mockResolvedValue({ ...assets, items: Array.from({ length: 25 }, (_, i) => ({ ...assets.items[0], name: `fiction_${String(i).padStart(2, "0")}` })) });
    renderWithProviders(<MappingsPage />);
    expect(await screen.findByText("fiction_00")).toBeInTheDocument();
    expect(screen.queryByText("fiction_24")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTitle("2"));
    expect(await screen.findByText("fiction_24")).toBeInTheDocument();
  });

  it("allows full sync of an empty schema to update missing observations", async () => {
    vi.mocked(catalogApi.tables).mockResolvedValue({ items: [] });
    vi.mocked(catalogApi.refreshAssets).mockResolvedValue(job({ total: 0, processed: 0, available: 0 }));
    renderWithProviders(<TableSyncDialog workspaceId="w" initialConnection="c" initialSchema="crm" onClose={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "下一步" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));
    fireEvent.click(screen.getByRole("button", { name: "下一步" }));
    fireEvent.click(await screen.findByRole("checkbox", { name: "全选当前库 crm" }));
    fireEvent.click(screen.getByRole("button", { name: "开始同步" }));
    await waitFor(() => expect(catalogApi.refreshAssets).toHaveBeenCalledWith("w", "c", { schema_name: "crm" }, []));
  });

  it("restores an active task when reopening the dialog", async () => {
    vi.mocked(catalogApi.syncJobs).mockResolvedValue({ items: [job({ state: "running" })] });
    renderWithProviders(<TableSyncDialog workspaceId="w" initialConnection="c" onClose={vi.fn()} />);
    expect(await screen.findAllByText("同步中")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "上一步" })).toBeDisabled();
  });
});
