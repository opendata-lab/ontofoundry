import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { catalogApi, workspaceRequest } from "../api/client";
import { workspace } from "../test/apiRecords";
import { renderWithProviders } from "../test/renderWithProviders";
import { ConnectionsPage } from "./ConnectionsPage";

const context = vi.hoisted(() => ({ workspace: { id: "w1", role: "admin" as string | null } }));
vi.mock("../hooks/useWorkspaceContext", () => ({ useWorkspaceContext: () => context }));
vi.mock("../hooks/usePageTab", () => ({ usePageTab: vi.fn() }));
vi.mock("../api/client", () => ({ catalogApi: { connections: vi.fn() }, workspaceRequest: vi.fn() }));

const connection = {
  id: "conn-demo",
  name: "星河只读库",
  kind: "postgresql",
  host: "db.example.invalid",
  port: 5432,
  database: "xinghe_demo",
  username: "demo_reader",
} as const;

beforeEach(() => {
  vi.clearAllMocks();
  context.workspace = workspace();
  vi.mocked(catalogApi.connections).mockResolvedValue({ items: [connection] });
  vi.mocked(workspaceRequest).mockResolvedValue({});
});
afterEach(cleanup);

it("tests the selected connection and announces its result", async () => {
  renderWithProviders(<ConnectionsPage />);
  expect(await screen.findByRole("cell", { name: "星河只读库" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "测试" }));
  expect(await screen.findByRole("status")).toHaveTextContent("星河只读库：连接正常");
  expect(workspaceRequest).toHaveBeenCalledWith("w1", "/connections/conn-demo/test", {});
});

it("opens the admin form, updates the default port and saves the connection", async () => {
  vi.mocked(workspaceRequest).mockResolvedValue({
    ...connection,
    id: "conn-new",
    name: "云杉分析库",
    kind: "mysql",
    port: 3306,
  });
  renderWithProviders(<ConnectionsPage />);
  fireEvent.click(screen.getByRole("button", { name: "添加连接" }));
  expect(screen.getByRole("spinbutton", { name: "端口" })).toHaveValue("5432");
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "数据库类型" }));
  fireEvent.click(await screen.findByText("MySQL", { selector: ".ant-select-item-option-content" }));
  expect(screen.getByRole("spinbutton", { name: "端口" })).toHaveValue("3306");
  // A MySQL connection reaches the whole server; libraries are chosen when syncing.
  expect(screen.queryByRole("textbox", { name: "数据库名称" })).toBeNull();
  for (const [name, value] of [
    ["连接名称", "云杉分析库"],
    ["主机", "db.example.invalid"],
    ["查询用户名", "demo_reader"],
  ])
    fireEvent.change(screen.getByRole("textbox", { name }), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "测试并保存" }));
  expect(await screen.findByRole("cell", { name: "云杉分析库" })).toBeInTheDocument();
  expect(workspaceRequest).toHaveBeenCalledWith(
    "w1",
    "/connections",
    expect.objectContaining({ name: "云杉分析库", kind: "mysql", port: 3306 }),
  );
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

it("keeps connections readable for members and hides the admin add action", async () => {
  context.workspace = workspace({ role: "member" });
  renderWithProviders(<ConnectionsPage />);
  expect(await screen.findByRole("cell", { name: "星河只读库" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "添加连接" })).not.toBeInTheDocument();
});

it("edits a connection without resending an unchanged password", async () => {
  renderWithProviders(<ConnectionsPage />);
  fireEvent.click(await screen.findByRole("button", { name: `编辑 ${connection.name}` }));
  const dialog = await screen.findByRole("dialog", { name: "编辑数据连接" });
  expect(screen.getByRole("combobox", { name: "数据库类型" })).toBeDisabled();
  vi.mocked(workspaceRequest).mockResolvedValue({ ...connection, host: "db2.example.invalid" });
  fireEvent.change(screen.getByRole("textbox", { name: "主机" }), { target: { value: "db2.example.invalid" } });
  fireEvent.click(screen.getByRole("button", { name: "测试并保存" }));
  await waitFor(() => expect(workspaceRequest).toHaveBeenCalledWith("w1", `/connections/${connection.id}`, expect.not.objectContaining({ password: expect.anything() }), "PATCH"));
  expect(vi.mocked(workspaceRequest).mock.calls.at(-1)?.[2]).toMatchObject({ host: "db2.example.invalid" });
  await waitFor(() => expect(dialog).not.toBeVisible());
});

it("removes the database column and appends only PostgreSQL's database to its address", async () => {
  vi.mocked(catalogApi.connections).mockResolvedValue({ items: [connection, { ...connection, id: "mysql", name: "虚构服务", kind: "mysql", port: 3306, database: "" }] });
  renderWithProviders(<ConnectionsPage />);
  expect(await screen.findByRole("cell", { name: "db.example.invalid:5432/xinghe_demo" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "db.example.invalid:3306" })).toBeInTheDocument();
  expect(screen.queryByRole("columnheader", { name: "数据库" })).not.toBeInTheDocument();
  expect(screen.queryByText("整个服务")).not.toBeInTheDocument();
});

it.each(["MySQL", "Apache Doris"])("drops a hidden PostgreSQL database when switching to %s", async (engine) => {
  vi.mocked(workspaceRequest).mockResolvedValue({ ...connection, id: "fiction-new" });
  renderWithProviders(<ConnectionsPage />);
  fireEvent.click(screen.getByRole("button", { name: "添加连接" }));
  fireEvent.change(screen.getByRole("textbox", { name: "数据库名称" }), { target: { value: "fiction_old" } });
  fireEvent.mouseDown(screen.getByRole("combobox", { name: "数据库类型" }));
  fireEvent.click(await screen.findByText(engine, { selector: ".ant-select-item-option-content" }));
  expect(screen.queryByRole("textbox", { name: "数据库名称" })).not.toBeInTheDocument();
  for (const [name, value] of [["连接名称", "虚构新服务"], ["主机", "fiction.invalid"], ["查询用户名", "reader"]]) {
    fireEvent.change(screen.getByRole("textbox", { name }), { target: { value } });
  }
  fireEvent.click(screen.getByRole("button", { name: "测试并保存" }));
  await waitFor(() => expect(workspaceRequest).toHaveBeenCalledWith("w1", "/connections", expect.objectContaining({ database: "" })));
});

it("requires a PostgreSQL database before submitting", async () => {
  renderWithProviders(<ConnectionsPage />);
  fireEvent.click(screen.getByRole("button", { name: "添加连接" }));
  fireEvent.click(screen.getByRole("button", { name: "测试并保存" }));
  expect(await screen.findByText("PostgreSQL 连接需要填写数据库名称")).toBeInTheDocument();
  expect(workspaceRequest).not.toHaveBeenCalled();
});
