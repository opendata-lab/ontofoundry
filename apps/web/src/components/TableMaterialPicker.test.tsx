import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { datasetApi } from "../api/client";
import type { LinkedTable, RegisteredTable } from "../api/types";
import { renderWithProviders } from "../test/renderWithProviders";
import { TableMaterialPicker } from "./TableMaterialPicker";

vi.mock("../api/client", () => ({ datasetApi: { registeredTables: vi.fn() } }));

// The first antd modal render is slow on CI runners; the waits below need more
// than vitest's 5 s per-test default.
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
  ...patch,
});

function renderPicker(linked: LinkedTable[] = [], onLink = vi.fn().mockResolvedValue(undefined)) {
  renderWithProviders(
    <MemoryRouter>
      <TableMaterialPicker workspaceId="w1" sessionId="s1" linked={linked} disabled={false} onLink={onLink} />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "选择数据表…" }));
  return onLink;
}

it("links the chosen registered tables to the session", async () => {
  vi.mocked(datasetApi.registeredTables).mockResolvedValue({
    items: [table("orders", { comment: "订单" }), table("stores", { kind: "view" })],
  });
  const onLink = renderPicker();
  // Wait until the loaded list has settled before choosing.
  await waitFor(() => expect(screen.getByRole("button", { name: "关联到会话" })).toBeEnabled(), { timeout: 5000 });
  // On slow CI runners the list can re-render after it is found, so a click may land
  // on a detached node; re-query each attempt and click until the box is checked.
  await waitFor(() => {
    const box = screen.getByRole("checkbox", { name: /dw\.orders/ });
    if (!(box as HTMLInputElement).checked) fireEvent.click(box);
    expect(box).toBeChecked();
  }, { timeout: 10_000 });
  fireEvent.click(screen.getByRole("button", { name: "关联到会话" }));
  await waitFor(() =>
    expect(onLink).toHaveBeenCalledWith([{ connection_id: "c1", schema_name: "dw", table_name: "orders" }]),
  );
  expect(datasetApi.registeredTables).toHaveBeenCalledWith("w1", "s1");
});

it("starts from the tables already linked and shows existing datasets", async () => {
  vi.mocked(datasetApi.registeredTables).mockResolvedValue({
    items: [table("orders", { datasets: [{ id: "d1", name: "orders", display_name: "订单" }] }), table("stores")],
  });
  const onLink = renderPicker([{ connection_id: "c1", schema_name: "dw", table_name: "orders" }]);
  expect(await screen.findByRole("checkbox", { name: /已有数据集 订单/ })).toBeChecked();
  fireEvent.click(await screen.findByRole("checkbox", { name: /dw\.orders/ }));
  fireEvent.click(screen.getByRole("button", { name: "关联到会话" }));
  await waitFor(() => expect(onLink).toHaveBeenCalledWith([]));
});

it("filters by table, connection or comment", async () => {
  vi.mocked(datasetApi.registeredTables).mockResolvedValue({
    items: [table("orders", { comment: "订单" }), table("stores", { comment: "门店" })],
  });
  renderPicker();
  await screen.findByRole("checkbox", { name: /dw\.orders/ });
  fireEvent.change(screen.getByRole("searchbox", { name: "搜索数据表" }), { target: { value: "门店" } });
  expect(screen.queryByRole("checkbox", { name: /dw\.orders/ })).toBeNull();
  expect(screen.getByRole("checkbox", { name: /dw\.stores/ })).toBeInTheDocument();
});

it("points to data management when nothing is synced yet", async () => {
  vi.mocked(datasetApi.registeredTables).mockResolvedValue({ items: [] });
  renderPicker();
  expect(await screen.findByText(/还没有已同步的数据表/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "数据管理" })).toHaveAttribute("href", "/workspaces/w1/mappings");
});

it("keeps the dialog open and shows why linking failed", async () => {
  vi.mocked(datasetApi.registeredTables).mockResolvedValue({ items: [table("orders")] });
  const onLink = renderPicker([], vi.fn().mockRejectedValue(new Error("关联的数据表尚未同步或已不存在")));
  fireEvent.click(await screen.findByRole("checkbox", { name: /dw\.orders/ }));
  fireEvent.click(screen.getByRole("button", { name: "关联到会话" }));
  expect(await screen.findByText("关联的数据表尚未同步或已不存在")).toBeInTheDocument();
  expect(onLink).toHaveBeenCalled();
});
