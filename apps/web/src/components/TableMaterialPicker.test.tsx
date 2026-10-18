import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { catalogApi } from "../api/client";
import type { DataConnection, DataTable, Material } from "../api/types";
import { example } from "../test/drafts";
import { renderWithProviders } from "../test/renderWithProviders";
import { TableMaterialPicker } from "./TableMaterialPicker";

vi.mock("../api/client", () => ({
  catalogApi: {
    connections: vi.fn(),
    tables: vi.fn(),
    tableMaterial: vi.fn(),
  },
}));

beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

const connection = (id: string, name: string): DataConnection => ({
  id,
  name,
  kind: "mysql",
  host: "db.example.test",
  port: 3306,
  database: "dw",
  username: "reader",
});

// The catalog tables behind the fictional order example's datasets; the first
// column stands in as the primary key.
const catalogTables = (name: string): DataTable[] =>
  example(name).datasets.map((d) => ({
    name: d.table_name,
    schema: d.schema_name,
    columns: (d.columns ?? []).map((c, i) => ({ name: c.name, type: c.physical_type ?? "varchar", primary_key: i === 0 })),
  }));

function renderPicker(onMaterial = vi.fn().mockResolvedValue(undefined)) {
  renderWithProviders(
    <MemoryRouter>
      <TableMaterialPicker workspaceId="w1" disabled={false} onMaterial={onMaterial} />
    </MemoryRouter>,
  );
  return onMaterial;
}

const openPicker = async () => {
  fireEvent.click(await screen.findByRole("button", { name: "选择数据表…" }));
  return screen.findByRole("group", { name: "选择数据表" });
};

it("turns the chosen tables into one material for the session", async () => {
  vi.mocked(catalogApi.connections).mockResolvedValue({ items: [connection("c1", "销售业务库")] });
  vi.mocked(catalogApi.tables).mockResolvedValue({ items: catalogTables("01-basic-sales") });
  const material: Material = {
    id: "m1",
    name: "数据表结构-销售业务库-orders-customers.md",
    byte_size: 2048,
    chunk_count: 1,
    sha256: "e".repeat(64),
  };
  vi.mocked(catalogApi.tableMaterial).mockResolvedValue(material);
  const onMaterial = renderPicker();

  const list = await openPicker();
  // A single connection is chosen for the user.
  await waitFor(() => expect(catalogApi.tables).toHaveBeenCalledWith("w1", "c1"));
  fireEvent.click(await within(list).findByRole("checkbox", { name: "orders" }));
  fireEvent.click(within(list).getByRole("checkbox", { name: "customers" }));
  fireEvent.click(screen.getByRole("button", { name: "加入建模材料（2 张表）" }));

  await waitFor(() => expect(onMaterial).toHaveBeenCalledWith(material));
  expect(catalogApi.tableMaterial).toHaveBeenCalledWith("w1", "c1", ["orders", "customers"]);
  await waitFor(() => expect(screen.queryByRole("group", { name: "选择数据表" })).toBeNull());
});

it("keeps the choice and shows why reading the tables failed", async () => {
  vi.mocked(catalogApi.connections).mockResolvedValue({ items: [connection("c1", "销售业务库")] });
  vi.mocked(catalogApi.tables).mockResolvedValue({ items: catalogTables("01-basic-sales") });
  vi.mocked(catalogApi.tableMaterial).mockRejectedValue(new Error("连接超时"));
  const onMaterial = renderPicker();

  const list = await openPicker();
  fireEvent.click(await within(list).findByRole("checkbox", { name: "orders" }));
  fireEvent.click(screen.getByRole("button", { name: "加入建模材料（1 张表）" }));

  expect(await screen.findByText("连接超时")).toBeInTheDocument();
  expect(onMaterial).not.toHaveBeenCalled();
  expect(within(list).getByRole("checkbox", { name: "orders" })).toBeChecked();
});

it("filters by name and selects only the visible tables", async () => {
  vi.mocked(catalogApi.connections).mockResolvedValue({ items: [connection("c1", "销售业务库")] });
  vi.mocked(catalogApi.tables).mockResolvedValue({ items: catalogTables("04-composite-key") });
  renderPicker();

  const list = await openPicker();
  await within(list).findByRole("checkbox", { name: "orders" });
  expect(within(list).getByText("dw · 2 列 · 主键 order_id")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索数据表" }), { target: { value: "order" } });
  expect(within(list).queryByRole("checkbox", { name: "products" })).not.toBeInTheDocument();
  expect(within(list).getAllByRole("checkbox")).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "全选筛选结果" }));
  expect(screen.getByRole("button", { name: "加入建模材料（2 张表）" })).toBeEnabled();
  expect(screen.getByText("已选 2 / 共 4 张表")).toBeInTheDocument();

  fireEvent.change(screen.getByRole("searchbox", { name: "搜索数据表" }), { target: { value: "missing" } });
  expect(within(list).getByText("没有匹配的数据表")).toBeInTheDocument();
});

it("asks for a connection first when the workspace has several", async () => {
  vi.mocked(catalogApi.connections).mockResolvedValue({
    items: [connection("c1", "销售业务库"), connection("c2", "仓储业务库")],
  });
  vi.mocked(catalogApi.tables).mockResolvedValue({ items: catalogTables("04-composite-key") });
  renderPicker();

  const list = await openPicker();
  expect(within(list).getByText("先选择数据连接")).toBeInTheDocument();
  expect(catalogApi.tables).not.toHaveBeenCalled();
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "数据连接" }));
  fireEvent.click(await screen.findByTitle("仓储业务库"));
  await waitFor(() => expect(catalogApi.tables).toHaveBeenCalledWith("w1", "c2"));
  expect(await within(list).findByRole("checkbox", { name: "shipments" })).toBeInTheDocument();
});

it("points to connections when the workspace has none", async () => {
  vi.mocked(catalogApi.connections).mockResolvedValue({ items: [] });
  renderPicker();
  expect(await screen.findByRole("link", { name: "新增数据连接" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "选择数据表…" })).toBeNull();
});
