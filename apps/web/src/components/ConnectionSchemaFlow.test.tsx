import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { DataConnection, Dataset, Draft } from "../api/types";
import { ConnectionsPage } from "../pages/ConnectionsPage";
import { MappingsPage } from "../pages/MappingsPage";
import { example } from "../test/drafts";
import { renderWithProviders } from "../test/renderWithProviders";
import { DatasetPanel } from "./elements/DatasetPanel";
import { TableMaterialPicker } from "./TableMaterialPicker";

vi.mock("../hooks/useWorkspaceContext", () => ({ useWorkspaceContext: () => ({ workspace: { id: "fiction", role: "admin" } }) }));
vi.mock("../hooks/usePageTab", () => ({ usePageTab: vi.fn(), usePageActive: () => true }));
vi.mock("./DocumentMaterials", () => ({ DocumentMaterials: () => null }));

const schemas = ["fiction_alpha", "fiction_beta"];
let connections: DataConnection[];
let calls: { path: string; method: string; schema: string | null; body: Record<string, unknown> }[];
let latest: Draft;
const table = (schema: string) => ({ name: "fiction_orders", schema, missing: false, datasets: [], columns: [{ name: "id", type: "INTEGER", primary_key: true }] });

beforeEach(() => {
  calls = [];
  connections = [{ id: "c", name: "虚构服务", kind: "mysql", database: "", host: "fiction.invalid", port: 3306, username: "reader" }];
  vi.stubGlobal("fetch", vi.fn(async (path: string, init?: RequestInit) => {
    const url = new URL(path, "http://fiction.invalid");
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : {};
    let schema = url.searchParams.get("schema_name");
    calls.push({ path: url.pathname, method, schema, body });
    const reply = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
    if (url.pathname.endsWith("/connections")) {
      if (method === "POST") { connections = [{ ...connections[0], ...body, id: "c" }]; return reply(connections[0], 201); }
      return reply({ items: connections });
    }
    if (url.pathname.endsWith("/schemas")) return reply({ items: schemas });
    // Synced tables come from the platform in one call, with no schema parameter.
    if (url.pathname.endsWith("/assets/synced")) return reply({ items: schemas.map((s) => ({ schema: s, assets: { connection_id: "c", items: [table(s)], changes: [], status: "ready" } })) });
    if (/\/(assets|tables|assets\/rows|assets\/sync-jobs)$/.test(url.pathname)) {
      const connectionId = url.pathname.split("/connections/")[1]?.split("/")[0];
      if (!schema && connections.find((c) => c.id === connectionId)?.kind === "postgresql") schema = "public";
      if (!schema) return reply({ error: { code: "SCHEMA_REQUIRED", message: "请选择库" } }, 422);
      if (url.pathname.endsWith("/assets/sync-jobs")) return reply(method === "GET" ? { items: [] } : { id: schema, connection_id: "c", schema_name: schema, state: "succeeded", total: 1, processed: 1, available: 1, failed: 0, duration_ms: 1, batches: [] }, method === "GET" ? 200 : 202);
      if (url.pathname.endsWith("/assets/rows")) return reply({ columns: ["id"], items: [{ id: 42 }], limit: 100 });
      return reply({ connection_id: "c", items: [table(schema)], changes: [], status: "ready" });
    }
    if (url.pathname.endsWith("/registered-tables")) return reply({ items: schemas.map((s) => ({ connection_id: "c", connection_name: "虚构服务", schema_name: s, table_name: "fiction_orders", column_count: 1, datasets: [] })) });
    if (url.pathname.endsWith("/datasets/validate")) return reply({ valid: true, columns: [{ name: "id", physical_type: "integer" }], diagnostics: [], referenced_tables: [] });
    if (url.pathname.endsWith("/datasets/preview")) return reply({ columns: [{ name: "id", physical_type: "integer" }], items: [{ id: 42 }], limit: 20 });
    throw new Error(`Unexpected request: ${method} ${path}`);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

// Full flows render several antd dialogs; vitest's 5 s per-test default is tight on CI.
vi.setConfig({ testTimeout: 20_000 });

async function choose(label: string, option: string) {
  fireEvent.mouseDown(screen.getByRole("combobox", { name: label }));
  // Options load asynchronously after the select is enabled; slow CI runners need more than 1 s.
  fireEvent.click(await screen.findByText(option, { selector: ".ant-select-item-option-content" }, { timeout: 5000 }));
}
const renderPage = (node: React.ReactNode) => renderWithProviders(<MemoryRouter>{node}</MemoryRouter>);

it.each(["mysql", "doris"] as const)("creates a %s server connection, browses all databases, syncs and previews with explicit URL schemas", async (kind) => {
  connections = [];
  renderPage(<ConnectionsPage />);
  fireEvent.click(screen.getByRole("button", { name: "添加连接" }));
  await choose("数据库类型", kind === "mysql" ? "MySQL" : "Apache Doris");
  expect(screen.queryByRole("textbox", { name: "数据库名称" })).not.toBeInTheDocument();
  for (const [name, value] of [["连接名称", "虚构服务"], ["主机", "fiction.invalid"], ["查询用户名", "reader"], ["密码", "fiction-secret"]]) {
    fireEvent.change(screen.getByLabelText(name, { exact: true }), { target: { value } });
  }
  fireEvent.click(screen.getByRole("button", { name: "测试并保存" }));
  await screen.findByRole("cell", { name: "虚构服务" });
  expect(calls.find((c) => c.method === "POST")?.body.kind).toBe(kind);
  expect(calls.find((c) => c.method === "POST")?.body.database ?? "").toBe("");
  cleanup();
  renderPage(<MappingsPage />);
  await waitFor(() => expect(screen.getAllByRole("button", { name: "fiction_orders" })).toHaveLength(2));
  expect(calls).toContainEqual(expect.objectContaining({ path: "/api/v1/workspaces/fiction/connections/c/assets/synced" }));
  expect(calls.filter((c) => c.path.endsWith("/assets"))).toEqual([]);
  fireEvent.click(screen.getAllByRole("button", { name: "fiction_orders" })[1]);
  const detail = await screen.findByRole("dialog");
  expect(within(detail).getByText("fiction_beta")).toBeInTheDocument();
  expect(within(detail).getByText("引用的数据集")).toBeInTheDocument();
  fireEvent.click(within(detail).getByRole("tab", { name: "字段（1）" }));
  expect(within(detail).getByRole("cell", { name: "INTEGER" })).toBeInTheDocument();
  fireEvent.click(within(detail).getByRole("tab", { name: "数据" }));
  await within(detail).findByRole("cell", { name: "42" });
  expect(calls).toContainEqual(expect.objectContaining({ path: "/api/v1/workspaces/fiction/connections/c/assets/rows", schema: "fiction_beta" }));
  fireEvent.click(within(detail).getByRole("button", { name: "Close" }));
  fireEvent.click(screen.getByRole("button", { name: "同步数据表" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "下一步" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "下一步" }));
  for (const schema of schemas) fireEvent.click(await screen.findByRole("checkbox", { name: schema }));
  fireEvent.click(screen.getByRole("button", { name: "下一步" }));
  await screen.findByRole("checkbox", { name: "fiction_alpha.fiction_orders" });
  fireEvent.click(screen.getByRole("button", { name: "全选全部" }));
  fireEvent.click(screen.getByRole("button", { name: "开始同步" }));
  await waitFor(() => expect(calls.filter((c) => c.path.endsWith("/assets/sync-jobs") && c.method === "POST")).toHaveLength(2));
  expect(calls.filter((c) => /\/(assets|tables|assets\/rows|assets\/sync-jobs)$/.test(c.path)).every((c) => schemas.includes(c.schema ?? ""))).toBe(true);
  expect(screen.queryByText("请选择库")).not.toBeInTheDocument();
});

function DatasetFields({ dataset }: { dataset: Partial<Dataset> }) {
  const initial = example("12-snapshot-and-trends");
  initial.workspace_id = "fiction";
  initial.datasets[0] = { ...initial.datasets[0], source_kind: "table", connection_id: null, schema_name: null, table_name: "", ...dataset };
  const [draft, setDraft] = useState(initial);
  latest = draft;
  return <DatasetPanel draft={draft} dataset={draft.datasets[0]} editing change={setDraft} open={vi.fn()} tab="fields" canPreview />;
}

it.each(["mysql", "doris"] as const)("waits for a database before selecting, validating and previewing a %s dataset", async (kind) => {
  connections[0].kind = kind;
  renderPage(<DatasetFields dataset={{}} />);
  await choose("数据库连接", "虚构服务");
  await waitFor(() => expect(calls.some((c) => c.path.endsWith("/schemas"))).toBe(true));
  expect(calls.filter((c) => c.path.endsWith("/assets"))).toEqual([]);
  expect(screen.getByRole("combobox", { name: "表或视图" })).toBeDisabled();
  await choose("库或 schema", "fiction_beta");
  await waitFor(() => expect(screen.getByRole("combobox", { name: "表或视图" })).toBeEnabled());
  await choose("表或视图", "fiction_orders");
  fireEvent.click(screen.getByRole("button", { name: "校验并探测列" }));
  await screen.findByText("来源校验通过");
  fireEvent.click(screen.getByRole("button", { name: "预览前 20 行" }));
  await screen.findByRole("cell", { name: "42" });
  for (const call of calls.filter((c) => /\/datasets\/(validate|preview)$/.test(c.path))) {
    expect(call.body.dataset).toMatchObject({ connection_id: "c", schema_name: "fiction_beta", table_name: "fiction_orders" });
  }
  expect(calls.filter((c) => c.path.endsWith("/assets")).every((c) => c.schema === "fiction_beta")).toBe(true);
});

it("edits a legacy dataset with a table but no database without requesting empty-schema assets on connection change", async () => {
  connections.push({ ...connections[0], id: "c2", name: "虚构备用服务" });
  renderPage(<DatasetFields dataset={{ connection_id: "c", schema_name: null, table_name: "fiction_orders" }} />);
  await choose("数据库连接", "虚构备用服务");
  await waitFor(() => expect(latest.datasets[0]).toMatchObject({ connection_id: "c2", schema_name: null, table_name: "", columns: null }));
  expect(calls.filter((c) => c.path.endsWith("/assets"))).toEqual([]);
  await choose("库或 schema", "fiction_alpha");
  await waitFor(() => expect(screen.getByRole("combobox", { name: "表或视图" })).toBeEnabled());
  await choose("表或视图", "fiction_orders");
  expect(latest.datasets[0]).toMatchObject({ schema_name: "fiction_alpha", table_name: "fiction_orders" });
});

it("preserves PostgreSQL's default schema when editing a dataset without an explicit schema", async () => {
  connections[0].kind = "postgresql";
  connections[0].database = "fiction_database";
  renderPage(<DatasetFields dataset={{ connection_id: "c", schema_name: null }} />);
  await waitFor(() => expect(screen.getByRole("combobox", { name: "表或视图" })).toBeEnabled());
  await choose("表或视图", "fiction_orders");
  expect(latest.datasets[0]).toMatchObject({ connection_id: "c", schema_name: null, table_name: "fiction_orders" });
  expect(calls.filter((c) => c.path.endsWith("/assets"))).toEqual([expect.objectContaining({ schema: null })]);
  expect(screen.queryByText("请选择库")).not.toBeInTheDocument();
});

it("links same-named tables from two databases through the builder's registered-table catalog", async () => {
  const onLink = vi.fn().mockResolvedValue(undefined);
  renderPage(<TableMaterialPicker workspaceId="fiction" linked={[]} disabled={false} onLink={onLink} />);
  fireEvent.click(screen.getByRole("button", { name: "选择数据表…" }));
  await waitFor(() => expect(screen.getAllByRole("checkbox")).toHaveLength(2));
  await act(async () => { await Promise.resolve(); });
  for (const schema of schemas) {
    const checkbox = screen.getByRole("checkbox", { name: new RegExp(`${schema}.fiction_orders`) });
    fireEvent.click(checkbox);
    await waitFor(() => expect(checkbox).toBeChecked());
  }
  fireEvent.click(screen.getByRole("button", { name: "关联到会话" }));
  await waitFor(() => expect(onLink).toHaveBeenCalledWith(schemas.map((schema) => ({ connection_id: "c", schema_name: schema, table_name: "fiction_orders" }))));
  expect(calls.some((c) => c.path.endsWith("/registered-tables"))).toBe(true);
  expect(calls.some((c) => c.path.endsWith("/assets") || c.path.endsWith("/table-material"))).toBe(false);
});
