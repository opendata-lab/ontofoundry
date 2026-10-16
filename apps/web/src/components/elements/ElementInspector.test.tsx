import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, modelingApi } from "../../api/client";
import type { Draft, ElementSaveResult, Workspace } from "../../api/types";
import { WorkspaceContextProvider } from "../../hooks/useWorkspaceContext";
import { example } from "../../test/drafts";
import { renderWithProviders } from "../../test/renderWithProviders";
import { ElementInspector } from "./ElementInspector";

vi.mock("../../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api/client")>();
  return {
    ...original,
    api: { ...original.api, workspace: vi.fn(), presentation: vi.fn() },
    modelingApi: { ...original.modelingApi, snapshot: vi.fn(), get: vi.fn(), saveElement: vi.fn() },
    catalogApi: { ...original.catalogApi, mappingPreview: vi.fn() },
    metricsApi: { preview: vi.fn() },
  };
});

const workspace = { id: "w", name: "测试空间", role: "admin", version_id: "v1", current_version: 1 } as Workspace;
const refresh = vi.fn();

function show(draft: Draft, query: string, role: Workspace["role"] = "admin") {
  vi.mocked(modelingApi.snapshot).mockResolvedValue(draft);
  vi.mocked(api.presentation).mockResolvedValue({ model: draft, version: {} as never });
  const router = createMemoryRouter(
    [
      {
        path: "/workspaces/:workspaceId/*",
        element: (
          <WorkspaceContextProvider.Provider value={{ workspace: { ...workspace, role }, refresh, user: { id: "u" } as never }}>
            <ElementInspector />
          </WorkspaceContextProvider.Provider>
        ),
      },
    ],
    { initialEntries: [`/workspaces/w/objects?${query}`] },
  );
  renderWithProviders(<RouterProvider router={router} />);
  return router;
}

const saved = (draft: Draft): ElementSaveResult => ({
  version: { version_id: "v2" } as never,
  draft,
  session: null,
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.workspace).mockResolvedValue(workspace);
});
afterEach(cleanup);

describe("object popup", () => {
  it("shows the populated tabs, mapping status and column bindings", async () => {
    const draft = example("01-basic-sales");
    const customer = draft.object_types.find((o) => o.technical_name === "customer")!;
    show(draft, `inspect=object_type:${customer.id}&inspectTab=properties`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(dialog).getAllByRole("tab").map((t) => t.textContent)).toEqual(["概览", "属性与映射4", "关系1", "实例"]),
    );
    expect(within(dialog).getByText("已映射")).toBeInTheDocument();
    expect(within(dialog).getByText("main.customer_id")).toBeInTheDocument();
    expect(within(dialog).getByText(/^customers/)).toBeInTheDocument();
  });

  it("edits the object and saves only its aggregate against the current version", async () => {
    const draft = example("01-basic-sales");
    const customer = draft.object_types.find((o) => o.technical_name === "customer")!;
    vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => saved(payload.draft));
    show(draft, `inspect=object_type:${customer.id}&inspectTab=basic`);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: "编辑" }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: "名称" }), { target: { value: "重要客户" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledTimes(1));
    const [, payload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
    expect(payload).toMatchObject({
      target_kind: "object_type",
      target_id: customer.id,
      expected_current_version_id: "v1",
      session_id: null,
      expected_session_revision: null,
    });
    expect(payload.draft.object_types.find((o) => o.id === customer.id)?.name).toBe("重要客户");
    expect(await screen.findByRole("status")).toHaveTextContent("已保存");
    expect(refresh).toHaveBeenCalled();
  });

  it("keeps edits and explains a version conflict", async () => {
    const draft = example("01-basic-sales");
    const customer = draft.object_types[0];
    vi.mocked(modelingApi.saveElement).mockRejectedValue(new ApiError("当前版本已变化", 409, "VERSION_CHANGED"));
    show(draft, `inspect=object_type:${customer.id}&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(await within(dialog).findByRole("textbox", { name: "名称" }), { target: { value: "改名" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    expect(await within(dialog).findByText(/当前版本已变化。你的修改仍保留/)).toBeInTheDocument();
    expect(within(dialog).getByRole("textbox", { name: "名称" })).toHaveValue("改名");
  });

  it("edits a child's member conditions on the direct parent's properties", async () => {
    const draft = example("06-inheritance");
    const vip = draft.object_types.find((o) => o.technical_name === "vip_party")!;
    vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => saved(payload.draft));
    show(draft, `inspect=object_type:${vip.id}&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("哪些当事人属于VIP当事人")).toBeInTheDocument();
    expect(within(dialog).getByRole("textbox", { name: "条件 1 的值" })).toHaveValue("VIP");
    fireEvent.change(within(dialog).getByRole("textbox", { name: "条件 1 的值" }), { target: { value: "SVIP" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalled());
    const [, payload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
    expect(payload.draft.object_types.find((o) => o.id === vip.id)?.derived_by).toEqual([
      { kind: "simple", conditions: [{ path: { links: [], property_id: expect.any(String) }, operator: "eq", values: ["SVIP"] }] },
    ]);
  });

  it("lets visitors read the published presentation without editing", async () => {
    const draft = example("01-basic-sales");
    show(draft, `inspect=object_type:${draft.object_types[0].id}`, null);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getAllByRole("tab").map((t) => t.textContent)).toEqual(["概览", "属性与映射4", "关系1"]));
    expect(api.presentation).toHaveBeenCalledWith("w", "v1");
    expect(within(dialog).queryByRole("button", { name: "编辑" })).not.toBeInTheDocument();
  });

  it("shows virtual parent alert instead of main table picker when editing a virtual parent object", async () => {
    const draft = example("06-inheritance");
    const asset = draft.object_types.find((o) => o.technical_name === "asset")!;
    show(draft, `inspect=object_type:${asset.id}&inspectTab=properties&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByText("子对象已各自绑定数据集，本对象作为虚拟父对象不绑定主表"),
    ).toBeInTheDocument();
    expect(within(dialog).queryByRole("combobox", { name: "主表数据集" })).not.toBeInTheDocument();
  });

  it("clears derived_by and removes orphaned shared_parent mapping when parent object changes", async () => {
    const draft = example("06-inheritance");
    const vip = draft.object_types.find((o) => o.technical_name === "vip_party")!;
    expect(draft.mappings.find((m) => m.type_id === vip.id)?.binding_mode).toBe("shared_parent");
    vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => saved(payload.draft));
    show(draft, `inspect=object_type:${vip.id}&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByText("哪些当事人属于VIP当事人");
    const parentField = within(dialog).getByRole("combobox", { name: "父对象" }).closest(".ant-select")!;
    fireEvent.mouseDown(parentField.querySelector(".ant-select-clear")!);
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalled());
    const [, payload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
    const updatedVip = payload.draft.object_types.find((o) => o.id === vip.id)!;
    expect(updatedVip.extends).toBeNull();
    expect(updatedVip.derived_by).toEqual([]);
    expect(payload.draft.mappings.find((m) => m.type_id === vip.id)).toBeUndefined();
  });
});

describe("relation, metric and dataset popups", () => {
  it("shows a relation's ends and its own data binding tab, and alerts when an endpoint is a virtual parent", async () => {
    const draft = example("06-inheritance");
    const link = draft.link_types.find((l) => l.technical_name === "responsible_party")!;
    show(draft, `inspect=link_type:${link.id}&inspectTab=mapping`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getAllByRole("tab").map((t) => t.textContent)).toEqual(["概览", "数据绑定", "实例"]));
    expect(
      within(dialog).getByText("端点包含虚拟父对象：这条关系的数据绑定在各具体子对象的「关系」页分别配置，关系本身可不绑定。"),
    ).toBeInTheDocument();
  });

  it("creates a metric from the form, supports equal bounds in between filter, and shows expression result type wording", async () => {
    const draft = example("01-basic-sales");
    vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => saved(payload.draft));
    show(draft, "inspect=metric:new&inspectMode=edit");
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(await within(dialog).findByRole("textbox", { name: "指标名称" }), { target: { value: "客户数" } });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "指标技术名" }), { target: { value: "customer_count" } });

    fireEvent.click(within(dialog).getByText("表达式"));
    expect(await within(dialog).findByText("可选；未指定时留空待补全")).toBeInTheDocument();
    expect(within(dialog).getByText("未指定")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByText("聚合"));

    fireEvent.click(within(dialog).getByRole("button", { name: /添加条件/ }));
    fireEvent.mouseDown(within(dialog).getByRole("combobox", { name: "条件 1 的列" }));
    fireEvent.click((await screen.findAllByText(/region/))[0]);
    fireEvent.mouseDown(within(dialog).getByRole("combobox", { name: "条件 1 的运算" }));
    fireEvent.click(await screen.findByText("介于"));
    fireEvent.change(within(dialog).getByRole("textbox", { name: "条件 1 的值起" }), { target: { value: "100" } });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "条件 1 的值止" }), { target: { value: "100" } });

    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalled());
    const [, payload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
    expect(payload.target_kind).toBe("metric");
    const metric = payload.draft.metrics.find((m) => m.id === payload.target_id)!;
    expect(metric).toMatchObject({
      kind: "simple",
      name: "客户数",
      technical_name: "customer_count",
      aggregation: "count",
      measure: null,
      filters: [{ operator: "between", values: [100, 100] }],
    });
    expect(metric).not.toHaveProperty("value_kind");
  });

  it("blocks saving an incomplete metric and points at the field", async () => {
    show(example("01-basic-sales"), "inspect=metric:new&inspectMode=edit");
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("textbox", { name: "指标名称" });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    expect(await within(dialog).findAllByText("请填写名称")).not.toHaveLength(0);
    expect(modelingApi.saveElement).not.toHaveBeenCalled();
  });

  it("shows a dataset's location, snapshot column and registered columns", async () => {
    const draft = example("12-snapshot-and-trends");
    const dataset = draft.datasets.find((d) => d.snapshot_date_column)!;
    show(draft, `inspect=dataset:${dataset.id}`);
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText(`每日快照（${dataset.snapshot_date_column}）`)).toBeInTheDocument();
    const columns = within(dialog).getByRole("columnheader", { name: "物理类型" }).closest("table")!;
    expect(within(columns).getAllByRole("row")).toHaveLength((dataset.columns?.length ?? 0) + 1);
  });

  it("opens a property's owner object on the properties tab", async () => {
    const draft = example("01-basic-sales");
    const property = draft.properties.find((p) => p.technical_name === "region")!;
    show(draft, `inspect=property:${property.id}`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("tab", { selected: true })).toHaveTextContent("属性与映射"));
  });
});
