import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { modelingApi } from "../api/client";
import { TableMaterialPicker } from "./TableMaterialPicker";

vi.mock("../api/client", () => ({
  modelingApi: {
    connections: vi.fn(),
    tables: vi.fn(),
    tableMaterial: vi.fn(),
  },
}));

afterEach(cleanup);

function renderPicker(onMaterial = vi.fn().mockResolvedValue(undefined)) {
  render(
    <MemoryRouter>
      <TableMaterialPicker workspaceId="w1" disabled={false} onMaterial={onMaterial} />
    </MemoryRouter>,
  );
  return onMaterial;
}

it("turns the chosen tables into one material for the session", async () => {
  vi.mocked(modelingApi.connections).mockResolvedValue({
    items: [{ id: "c1", name: "销售业务库", kind: "mysql", host: "h", port: 3306,
      database: "d", username: "u" }],
  });
  vi.mocked(modelingApi.tables).mockResolvedValue({
    items: [{ name: "customers", schema: null, columns: [] },
      { name: "orders", schema: null, columns: [] }],
  });
  const material = { id: "m1", name: "数据表结构-销售业务库-orders-customers.md" };
  vi.mocked(modelingApi.tableMaterial).mockResolvedValue(material as never);
  const onMaterial = renderPicker();

  fireEvent.click(await screen.findByRole("checkbox", { name: "orders" }));
  fireEvent.click(screen.getByRole("checkbox", { name: "customers" }));
  fireEvent.click(screen.getByRole("button", { name: "加入建模材料（2 张表）" }));

  await waitFor(() => expect(onMaterial).toHaveBeenCalledWith(material));
  expect(modelingApi.tableMaterial).toHaveBeenCalledWith("w1", "c1", ["orders", "customers"]);
});

it("points to connections when the workspace has none", async () => {
  vi.mocked(modelingApi.connections).mockResolvedValue({ items: [] });
  renderPicker();
  expect(await screen.findByRole("link", { name: "新增数据连接" })).toBeInTheDocument();
});
