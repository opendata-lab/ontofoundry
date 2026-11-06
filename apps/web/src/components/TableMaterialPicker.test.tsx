import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { datasetApi } from "../api/client";
import type { LinkedTable, RegisteredTable } from "../api/types";
import { renderWithProviders } from "../test/renderWithProviders";
import { TableMaterialPicker } from "./TableMaterialPicker";

vi.mock("../api/client", () => ({ datasetApi: { registeredTables: vi.fn() } }));

// Antd modal render can be slower in CI environments.
vi.setConfig({ testTimeout: 20_000 });

beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

const table = (name: string, patch: Partial<RegisteredTable> = {}): RegisteredTable => ({
  connection_id: "c1",
  connection_name: "星港只读库",
  schema_name: "dw",
  table_name: name,
  kind: "table",
  comment: "",
  column_count: 4,
  datasets: [],
  observed_at: "2026-11-05T12:00:00Z",
  ...patch,
});

function renderPicker({
  tableScope,
  linked = [],
  onSave = vi.fn().mockResolvedValue(undefined),
}: {
  tableScope?: "all" | "selected";
  linked?: LinkedTable[];
  onSave?: ReturnType<typeof vi.fn>;
} = {}) {
  renderWithProviders(
    <MemoryRouter>
      <TableMaterialPicker
        workspaceId="w1"
        sessionId="s1"
        tableScope={tableScope}
        linked={linked}
        disabled={false}
        onSave={onSave}
      />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "选择数据表…" }));
  return onSave;
}

it("defaults to all tables selected when scope is all", async () => {
  vi.mocked(datasetApi.registeredTables).mockResolvedValue({
    items: [
      table("fiction_orders", { comment: "订单表" }),
      table("fiction_stores", { kind: "view" }),
      table("fiction_customers"),
    ],
  });
  const onSave = renderPicker({ tableScope: "all" });

  await waitFor(() => expect(screen.getByRole("button", { name: "关联到会话" })).toBeEnabled());
  expect(await screen.findByText(/匹配 3 张 · 已选 3 \/ 共 3 张/)).toBeInTheDocument();

  // Header checkbox is checked
  const headerCheckbox = screen.getByRole("checkbox", { name: "全选" });
  expect(headerCheckbox).toBeChecked();

  // Row checkboxes are checked
  expect(screen.getByRole("checkbox", { name: "dw.fiction_orders" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "dw.fiction_stores" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "dw.fiction_customers" })).toBeChecked();

  // Saving without changes saves table_scope all
  fireEvent.click(screen.getByRole("button", { name: "关联到会话" }));
  await waitFor(() => {
    expect(onSave).toHaveBeenCalledWith({ table_scope: "all", linked_tables: [] });
  });
  expect(datasetApi.registeredTables).toHaveBeenCalledWith("w1", "s1");
});

it("filter then header-select selects only matching rows across pages", async () => {
  // Create 25 tables to test across pagination (page size is 20):
  // 22 fiction_order_* tables and 3 fiction_store_* tables.
  const orderTables = Array.from({ length: 22 }, (_, i) =>
    table(`fiction_order_${i + 1}`, { comment: `Order table ${i + 1}` }),
  );
  const storeTables = Array.from({ length: 3 }, (_, i) =>
    table(`fiction_store_${i + 1}`, { comment: `Store table ${i + 1}` }),
  );
  const allTables = [...orderTables, ...storeTables];

  vi.mocked(datasetApi.registeredTables).mockResolvedValue({ items: allTables });
  const onSave = renderPicker({ tableScope: "selected", linked: [] });

  await waitFor(() => expect(screen.getByRole("button", { name: "关联到会话" })).toBeEnabled());
  expect(await screen.findByText(/匹配 25 张 · 已选 0 \/ 共 25 张/)).toBeInTheDocument();

  // Filter by query "fiction_order"
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索数据表" }), {
    target: { value: "fiction_order" },
  });
  expect(await screen.findByText(/匹配 22 张 · 已选 0 \/ 共 25 张/)).toBeInTheDocument();

  // Header select selects all 22 matching rows across pages
  const headerCheckbox = screen.getByRole("checkbox", { name: "全选" });
  expect(headerCheckbox).not.toBeChecked();
  fireEvent.click(headerCheckbox);

  expect(await screen.findByText(/匹配 22 张 · 已选 22 \/ 共 25 张/)).toBeInTheDocument();
  expect(headerCheckbox).toBeChecked();

  // Save verifies only the 22 matching rows across pages are saved
  fireEvent.click(screen.getByRole("button", { name: "关联到会话" }));
  await waitFor(() => {
    expect(onSave).toHaveBeenCalledWith({
      table_scope: "selected",
      linked_tables: orderTables.map((t) => ({
        connection_id: t.connection_id,
        schema_name: t.schema_name,
        table_name: t.table_name,
      })),
    });
  });
});

it("saves table_scope all when 全选全部 is clicked", async () => {
  vi.mocked(datasetApi.registeredTables).mockResolvedValue({
    items: [table("fiction_orders"), table("fiction_stores"), table("fiction_customers")],
  });
  const onSave = renderPicker({
    tableScope: "selected",
    linked: [{ connection_id: "c1", schema_name: "dw", table_name: "fiction_orders" }],
  });

  await waitFor(() => expect(screen.getByRole("button", { name: "关联到会话" })).toBeEnabled());
  expect(await screen.findByText(/匹配 3 张 · 已选 1 \/ 共 3 张/)).toBeInTheDocument();

  // Click "全选全部"
  fireEvent.click(screen.getByRole("button", { name: "全选全部" }));
  expect(await screen.findByText(/匹配 3 张 · 已选 3 \/ 共 3 张/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "关联到会话" }));
  await waitFor(() => {
    expect(onSave).toHaveBeenCalledWith({ table_scope: "all", linked_tables: [] });
  });
});

it("saves table_scope selected with N-1 tables when deselecting one table", async () => {
  vi.mocked(datasetApi.registeredTables).mockResolvedValue({
    items: [table("fiction_orders"), table("fiction_stores"), table("fiction_customers")],
  });
  const onSave = renderPicker({ tableScope: "all" });

  await waitFor(() => expect(screen.getByRole("button", { name: "关联到会话" })).toBeEnabled());
  expect(await screen.findByText(/匹配 3 张 · 已选 3 \/ 共 3 张/)).toBeInTheDocument();

  // Deselect fiction_orders
  const ordersBox = screen.getByRole("checkbox", { name: "dw.fiction_orders" });
  expect(ordersBox).toBeChecked();
  fireEvent.click(ordersBox);

  expect(await screen.findByText(/匹配 3 张 · 已选 2 \/ 共 3 张/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "关联到会话" }));
  await waitFor(() => {
    expect(onSave).toHaveBeenCalledWith({
      table_scope: "selected",
      linked_tables: [
        { connection_id: "c1", schema_name: "dw", table_name: "fiction_stores" },
        { connection_id: "c1", schema_name: "dw", table_name: "fiction_customers" },
      ],
    });
  });
});

it("saves table_scope selected with empty array when 清空 is clicked", async () => {
  vi.mocked(datasetApi.registeredTables).mockResolvedValue({
    items: [table("fiction_orders"), table("fiction_stores"), table("fiction_customers")],
  });
  const onSave = renderPicker({ tableScope: "all" });

  await waitFor(() => expect(screen.getByRole("button", { name: "关联到会话" })).toBeEnabled());
  expect(await screen.findByText(/匹配 3 张 · 已选 3 \/ 共 3 张/)).toBeInTheDocument();

  // Click "清空"
  fireEvent.click(screen.getByRole("button", { name: "清空" }));
  expect(await screen.findByText(/匹配 3 张 · 已选 0 \/ 共 3 张/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "关联到会话" }));
  await waitFor(() => {
    expect(onSave).toHaveBeenCalledWith({ table_scope: "selected", linked_tables: [] });
  });
});

it("points to data management when nothing is synced yet", async () => {
  vi.mocked(datasetApi.registeredTables).mockResolvedValue({ items: [] });
  renderPicker();
  expect(await screen.findByText(/还没有已同步的数据表/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "数据管理" })).toHaveAttribute("href", "/workspaces/w1/mappings");
});

it("keeps the dialog open and shows why linking failed", async () => {
  vi.mocked(datasetApi.registeredTables).mockResolvedValue({ items: [table("fiction_orders")] });
  const onSave = renderPicker({
    tableScope: "selected",
    linked: [{ connection_id: "c1", schema_name: "dw", table_name: "fiction_orders" }],
    onSave: vi.fn().mockRejectedValue(new Error("关联的数据表尚未同步或已不存在")),
  });
  await waitFor(() => expect(screen.getByRole("button", { name: "关联到会话" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "关联到会话" }));
  expect(await screen.findByText("关联的数据表尚未同步或已不存在")).toBeInTheDocument();
  expect(onSave).toHaveBeenCalled();
});
