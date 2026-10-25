import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, instancesApi, modelingApi } from "../../api/client";
import type { Draft, ElementSaveResult, InstanceList, Workspace } from "../../api/types";
import { PageTabContext } from "../../hooks/usePageTab";
import { WorkspaceContextProvider } from "../../hooks/useWorkspaceContext";
import { example } from "../../test/drafts";
import { renderWithProviders } from "../../test/renderWithProviders";
import { legacyInspectRequest, notifyOntologySaved, type ElementRequest } from "../../lib/elementInspector";
import { ElementModal } from "./ElementInspector";

vi.mock("../../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api/client")>();
  return {
    ...original,
    api: { ...original.api, workspace: vi.fn(), presentation: vi.fn(), elementPresentation: vi.fn(), elementDocuments: vi.fn() },
    modelingApi: {
      ...original.modelingApi,
      snapshot: vi.fn(),
      get: vi.fn(),
      previewElementSave: vi.fn(),
      saveElement: vi.fn(),
    },
    catalogApi: { ...original.catalogApi, mappingPreview: vi.fn() },
    metricsApi: { preview: vi.fn() },
    instancesApi: { ...original.instancesApi, list: vi.fn() },
  };
});

const workspace = { id: "w", name: "测试空间", role: "admin", version_id: "v1", current_version: 1 } as Workspace;
const refresh = vi.fn();

/** Holds the popup request the way a page does; queries use the former `inspect` keys. */
function Popup({ initial, nextId }: { initial: ElementRequest; nextId?: string }) {
  const [request, setRequest] = useState<ElementRequest | null>(initial);
  const [active, setActive] = useState(true);
  return <>
    <button onClick={() => setRequest(initial)}>重新打开</button>
    <button onClick={() => setRequest({ ...initial, id: nextId ?? initial.id })}>切换元素</button>
    <button onClick={() => setActive(!active)}>切换页面激活</button>
    <PageTabContext.Provider value={{ active, update: refresh }}>
      {request && <ElementModal request={request} onChange={setRequest} onClose={() => setRequest(null)} />}
    </PageTabContext.Provider>
  </>;
}

function show(draft: Draft, query: string, role: Workspace["role"] = "admin", versionId?: string) {
  const request = legacyInspectRequest(new URLSearchParams(query))!;
  if (versionId) request.versionId = versionId;
  vi.mocked(modelingApi.snapshot).mockResolvedValue(draft);
  vi.mocked(api.elementPresentation).mockResolvedValue({ model: draft, version_id: "v1", workspace_id: "w", complete: false, representation: "element-1" } as never);
  vi.mocked(api.elementDocuments).mockResolvedValue({ material_objects: draft.material_objects, material_links: draft.material_links, version_id: "v1", workspace_id: "w" } as never);
  vi.mocked(api.presentation).mockResolvedValue({ model: draft, version: {} as never });
  const router = createMemoryRouter(
    [
      {
        path: "/workspaces/:workspaceId/*",
        element: (
          <WorkspaceContextProvider.Provider value={{ workspace: { ...workspace, role }, refresh, user: { id: "u" } as never }}>
            <Popup initial={request} nextId={draft.object_types.find((o) => o.id !== request.id)?.id} />
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
  vi.mocked(instancesApi.list).mockResolvedValue({ items: [], snapshot_dates: [], next_cursor: null, truncated: false } as unknown as InstanceList);
  vi.mocked(modelingApi.previewElementSave).mockResolvedValue({
    current_version_id: "v1",
    session_revision: null,
    affected_items: [],
  });
});
afterEach(cleanup);

describe("object popup", () => {
  it("keeps the overview graph and field positions when entering edit mode", async () => {
    const draft = example("01-basic-sales");
    const customer = draft.object_types.find((object) => object.name === "customer")!;
    show(draft, `inspect=object_type:${customer.id}`);
    const dialog = await screen.findByRole("dialog");
    const graph = await within(dialog).findByLabelText(`${customer.display_name || customer.name}的关系图`);
    const layout = dialog.querySelector(".object-overview-columns");
    fireEvent.click(within(dialog).getByRole("button", { name: "编辑" }));
    expect(within(dialog).getByLabelText(`${customer.display_name || customer.name}的关系图`)).toBe(graph);
    expect(dialog.querySelector(".object-overview-columns")).toBe(layout);
    expect(await within(dialog).findByRole("textbox", { name: "名称" })).toBeEnabled();
  });
  it("shows the populated tabs, mapping status and column bindings", async () => {
    const draft = example("01-basic-sales");
    const customer = draft.object_types.find((o) => o.name === "customer")!;
    show(draft, `inspect=object_type:${customer.id}&inspectTab=properties`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(within(dialog).getAllByRole("tab").map((t) => t.textContent)).toEqual([
        "概览",
        "字段4",
        "关系1",
        "规则0",
      ]),
    );
    expect(within(dialog).getByText("已映射")).toBeInTheDocument();
    expect(within(dialog).getByText("main.customer_id")).toBeInTheDocument();
    expect(within(dialog).queryByText(/主数据集 customers/)).not.toBeInTheDocument();
  });

  it("keeps a visited tab mounted, so returning to it does not rebuild its tables", async () => {
    const draft = example("01-basic-sales");
    const customer = draft.object_types.find((o) => o.name === "customer")!;
    show(draft, `inspect=object_type:${customer.id}&inspectTab=properties`);
    const dialog = await screen.findByRole("dialog");
    const binding = await within(dialog).findByText("main.customer_id");
    fireEvent.click(within(dialog).getByRole("tab", { name: /^关系/ }));
    await waitFor(() => expect(binding).not.toBeVisible());
    fireEvent.click(within(dialog).getByRole("tab", { name: /^字段/ }));
    // The very same node: hidden and shown again, never remounted.
    await waitFor(() => expect(within(dialog).getByText("main.customer_id")).toBe(binding));
  });

  it("edits the object and saves only its aggregate against the current version", async () => {
    const draft = example("01-basic-sales");
    const customer = draft.object_types.find((o) => o.name === "customer")!;
    vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => saved(payload.draft));
    show(draft, `inspect=object_type:${customer.id}&inspectTab=basic`);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(await within(dialog).findByRole("button", { name: "编辑" }));
    fireEvent.change(await within(dialog).findByRole("textbox", { name: "名称" }), { target: { value: "重要客户" } });
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
    expect((payload.draft.object_types.find((o) => o.id === customer.id)?.display_name || payload.draft.object_types.find((o) => o.id === customer.id)?.name)).toBe("重要客户");
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
    const vip = draft.object_types.find((o) => o.name === "vip_party")!;
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
    await waitFor(() => expect(within(dialog).getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "概览",
      "字段4",
      "关系1",
      "规则0",
    ]));
    expect(api.elementPresentation).toHaveBeenCalledWith("w", "object_type", draft.object_types[0].id, "v1");
    expect(within(dialog).queryByRole("button", { name: "编辑" })).not.toBeInTheDocument();
  });

  it("shows virtual parent alert instead of main table picker when editing a virtual parent object", async () => {
    const draft = example("06-inheritance");
    const asset = draft.object_types.find((o) => o.name === "asset")!;
    show(draft, `inspect=object_type:${asset.id}&inspectTab=properties&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByText("子对象已各自绑定数据集，本对象作为虚拟父对象不绑定主表"),
    ).toBeInTheDocument();
    expect(within(dialog).queryByRole("combobox", { name: "主表数据集" })).not.toBeInTheDocument();
  });

  it("clears derived_by and removes orphaned shared_parent mapping when parent object changes", async () => {
    const draft = example("06-inheritance");
    const vip = draft.object_types.find((o) => o.name === "vip_party")!;
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
  it("shows a relation's ends and its own data binding tab, with mapping-table binding off by default", async () => {
    const draft = example("06-inheritance");
    const link = draft.link_types.find((l) => (l.display_name || l.name) === "responsible_party")!;
    show(draft, `inspect=link_type:${link.id}&inspectTab=mapping`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getAllByRole("tab").map((t) => t.textContent)).toEqual(["概览", "映射", "规则0"]));
    const mappingSwitch = within(dialog).getByRole("switch", { name: "使用映射表" });
    expect(mappingSwitch).not.toBeChecked();
    expect(within(dialog).getByText("未启用")).toBeInTheDocument();
  });

  it("creates a metric from the form, supports equal bounds in between filter, and shows expression result type wording", async () => {
    const draft = example("01-basic-sales");
    vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => saved(payload.draft));
    show(draft, "inspect=metric:new&inspectMode=edit");
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(await within(dialog).findByRole("textbox", { name: "指标名称" }), { target: { value: "客户数" } });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "指标英文标识" }), { target: { value: "customer_count" } });

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
      display_name: "客户数",
      name: "customer_count",
      aggregation: "count",
      measure: null,
      filters: [{ operator: "between", values: ["100", "100"] }],
    });
    expect(metric).not.toHaveProperty("value_kind");
  });

  it("blocks saving an incomplete metric and points at the field", async () => {
    show(example("01-basic-sales"), "inspect=metric:new&inspectMode=edit");
    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByRole("textbox", { name: "指标名称" });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    expect(await within(dialog).findAllByText("英文标识只能使用字母、数字和下划线，且不能以数字开头")).not.toHaveLength(0);
    expect(modelingApi.saveElement).not.toHaveBeenCalled();
  });

  it("shows a dataset's location, snapshot column and registered columns", async () => {
    const draft = example("12-snapshot-and-trends");
    const dataset = draft.datasets.find((d) => d.snapshot_date_column)!;
    show(draft, `inspect=dataset:${dataset.id}`);
    const dialog = await screen.findByRole("dialog");
    // Overview keeps metadata and references; fields combines source and columns.
    expect(await within(dialog).findByText(dataset.snapshot_date_column!)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("tab", { name: "字段" }));
    const columns = within(dialog).getByRole("columnheader", { name: "物理类型" }).closest("table")!;
    expect(within(columns).getAllByRole("row")).toHaveLength((dataset.columns?.length ?? 0) + 1);
  });

  it.each(["source", "columns", "preview"])("opens legacy dataset %s links on the combined fields tab", async (tab) => {
    const draft = example("12-snapshot-and-trends");
    const dataset = draft.datasets[0];
    show(draft, `inspect=dataset:${dataset.id}&inspectTab=${tab}`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("tab", { selected: true })).toHaveTextContent("字段"));
    expect(within(dialog).getAllByRole("tab").map((value) => value.textContent)).toEqual(["概览", "字段"]);
    expect(within(dialog).getByRole("heading", { name: "来源定义" })).toBeInTheDocument();
    expect(within(dialog).getByRole("heading", { name: "字段结构" })).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "预览前 20 行" })).toBeInTheDocument();
  });

  it("keeps dataset references in the overview for legacy reference links", async () => {
    const draft = example("12-snapshot-and-trends");
    show(draft, `inspect=dataset:${draft.datasets[0].id}&inspectTab=references`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("tab", { selected: true })).toHaveTextContent("概览"));
    for (const name of ["基本信息", "对象映射", "关系映射", "指标"])
      expect(within(dialog).getByRole("heading", { name })).toBeInTheDocument();
  });

  it("opens a property's owner object on the properties tab", async () => {
    const draft = example("01-basic-sales");
    const property = draft.properties.find((p) => p.name === "region")!;
    show(draft, `inspect=property:${property.id}`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("tab", { selected: true })).toHaveTextContent("字段"));
  });
});

describe("element save impact preview", () => {
  it.each([false, true])("clears a binding inline without changing sibling bindings (expression: %s)", async (expression) => {
    const draft = example("01-basic-sales");
    const customer = draft.object_types.find((object) => object.name === "customer")!;
    const property = draft.properties.find((value) => value.owner_type_id === customer.id && value.name === "customer_no")!;
    const mapping = draft.mappings.find((value) => value.type_id === customer.id)!;
    vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => saved(payload.draft));
    show(draft, `inspect=object_type:${customer.id}&inspectTab=properties&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(dialog.querySelector(`[data-element-id="${property.id}"]`)).not.toBeNull());
    const row = dialog.querySelector(`[data-element-id="${property.id}"]`)!.closest("tr")!;
    if (expression) {
      fireEvent.mouseDown(within(row).getByRole("combobox", { name: `${property.display_name || property.name}绑定方式` }));
      fireEvent.click(await screen.findByTitle("计算"));
      const input = within(row).getByRole("textbox", { name: `${property.display_name || property.name}计算表达式` });
      fireEvent.change(input, { target: { value: "main.customer_no" } });
      fireEvent.click(row.querySelector(".ant-input-clear-icon")!);
      expect(input).toHaveValue("");
      expect(within(row).getByText("计算", { exact: true })).toBeInTheDocument();
    } else {
      fireEvent.mouseDown(row.querySelector(".ant-select-clear")!);
      expect(within(row).getByRole("combobox", { name: `${property.display_name || property.name}列` })).toHaveValue("");
    }
    expect(within(dialog).queryByRole("button", { name: /解除.*绑定/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledTimes(1));
    const candidate = vi.mocked(modelingApi.saveElement).mock.calls[0][1].draft.mappings.find((value) => value.id === mapping.id)!;
    expect(candidate.fields).not.toHaveProperty(property.name);
    expect(candidate.fields.name).toEqual(mapping.fields.name);
  });
  it.each([false, true])("preserves the shared ancestor source when editing VIP note (column edit: %s)", async (editColumn) => {
    const draft = example("06-inheritance");
    const vip = draft.object_types.find((o) => o.name === "vip_party")!;
    const note = draft.properties.find((p) => p.owner_type_id === vip.id)!;
    const mapping = draft.mappings.find((m) => m.type_id === vip.id)!;
    expect(mapping.sources).toEqual([]);
    vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => saved(payload.draft));
    show(draft, `inspect=object_type:${vip.id}&inspectTab=properties&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(dialog.querySelector(`[data-element-id="${note.id}"]`)).not.toBeNull());
    const row = dialog.querySelector<HTMLElement>(`[data-element-id="${note.id}"]`)!;
    fireEvent.click(row);
    const technical = within(dialog.querySelector(`[data-element-id="${note.id}"]`)!.closest("tr")!).getByRole("textbox", { name: "属性英文标识" });
    fireEvent.change(technical, { target: { value: "note2" } });
    expect(within(dialog).getByRole("combobox", { name: "VIP说明列" })).toHaveValue("vip_note");
    if (editColumn)
      fireEvent.change(within(dialog).getByRole("combobox", { name: "VIP说明列" }), { target: { value: "party_name" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledTimes(1));
    expect(modelingApi.previewElementSave).toHaveBeenCalledTimes(1);
    for (const [, payload] of [...vi.mocked(modelingApi.previewElementSave).mock.calls, ...vi.mocked(modelingApi.saveElement).mock.calls]) {
      expect(payload.draft.mappings.find((m) => m.id === mapping.id)!.fields).toEqual({
        note2: { kind: "column", source_id: "main", column: editColumn ? "party_name" : "vip_note" },
      });
    }
  });

  it("keeps both UUID bindings when a typed rename passes through another property's name", async () => {
    const draft = example("01-basic-sales");
    const customer = draft.object_types.find((o) => o.name === "customer")!;
    const customerNo = draft.properties.find((p) => p.owner_type_id === customer.id && p.name === "customer_no")!;
    const mapping = draft.mappings.find((m) => m.type_id === customer.id)!;
    vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => saved(payload.draft));
    show(draft, `inspect=object_type:${customer.id}&inspectTab=properties&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(dialog.querySelector(`[data-element-id="${customerNo.id}"]`)).not.toBeNull());
    const row = dialog.querySelector<HTMLElement>(`[data-element-id="${customerNo.id}"]`)!;
    fireEvent.click(row);
    const technical = within(dialog.querySelector(`[data-element-id="${customerNo.id}"]`)!.closest("tr")!).getByRole("textbox", { name: "属性英文标识" });
    for (const value of ["n", "na", "nam", "name", "name2"])
      fireEvent.change(technical, { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledTimes(1));
    for (const [, payload] of [...vi.mocked(modelingApi.previewElementSave).mock.calls, ...vi.mocked(modelingApi.saveElement).mock.calls]) {
      const fields = payload.draft.mappings.find((m) => m.id === mapping.id)!.fields;
      expect(fields.name2).toEqual(mapping.fields.customer_no);
      expect(fields.name).toEqual(mapping.fields.name);
      expect(fields).not.toHaveProperty("customer_no");
    }
  });

  it("previews once and saves directly without a confirmation modal when affected_items is empty", async () => {
    const draft = example("07-instances-and-evidence");
    const customer = draft.object_types.find((o) => o.name === "customer")!;
    const customerNo = draft.properties.find((p) => p.name === "customer_no")!;
    vi.mocked(modelingApi.previewElementSave).mockResolvedValue({
      current_version_id: "v1",
      session_revision: null,
      affected_items: [],
    });
    vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => saved(payload.draft));

    show(draft, `inspect=object_type:${customer.id}&inspectTab=properties&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(dialog.querySelector(`[data-element-id="${customerNo.id}"]`)).not.toBeNull());
    const row = dialog.querySelector<HTMLElement>(`[data-element-id="${customerNo.id}"]`)!;
    fireEvent.click(row);
    fireEvent.change(within(dialog.querySelector(`[data-element-id="${customerNo.id}"]`)!.closest("tr")!).getByRole("textbox", { name: "属性英文标识" }), { target: { value: "customer_code" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledTimes(1));
    expect(modelingApi.previewElementSave).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("确认后这些元素会随本次保存一并改写")).not.toBeInTheDocument();
    const [, previewPayload] = vi.mocked(modelingApi.previewElementSave).mock.calls[0];
    const [, savePayload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
    expect(previewPayload).toEqual(savePayload);
    expect(savePayload).not.toHaveProperty("affected_items");
    expect(savePayload.draft.properties.find((p) => p.id === customerNo.id)?.name).toBe("customer_code");
  });

  it("shows affected items and reason in a confirmation modal, cancels without saving, and strips reason when confirmed", async () => {
    const draft = example("07-instances-and-evidence");
    const customer = draft.object_types.find((o) => o.name === "customer")!;
    const customerNo = draft.properties.find((p) => p.name === "customer_no")!;
    const customerFact = draft.material_objects.find((f) => f.type_id === customer.id)!;
    const h = "1".repeat(64);
    vi.mocked(modelingApi.previewElementSave).mockResolvedValue({
      current_version_id: "v1",
      session_revision: null,
      affected_items: [
        {
          target_kind: "material_object",
          target_id: customerFact.id,
          expected_target_hash: h,
          reason: "当前元素修改需要同步此依赖的定义或引用",
        },
      ],
    });
    vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => saved(payload.draft));

    show(draft, `inspect=object_type:${customer.id}&inspectTab=properties&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(dialog.querySelector(`[data-element-id="${customerNo.id}"]`)).not.toBeNull());
    const row = dialog.querySelector<HTMLElement>(`[data-element-id="${customerNo.id}"]`)!;
    fireEvent.click(row);
    fireEvent.change(within(dialog.querySelector(`[data-element-id="${customerNo.id}"]`)!.closest("tr")!).getByRole("textbox", { name: "属性英文标识" }), { target: { value: "customer_code" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    const noticeText = await screen.findByText("确认后这些元素会随本次保存一并改写");
    const confirmDialog = noticeText.closest<HTMLElement>('[role="dialog"]')!;
    expect(within(confirmDialog).getByText("确认保存影响")).toBeInTheDocument();
    expect(within(confirmDialog).getByText("文档实例")).toBeInTheDocument();
    expect(within(confirmDialog).getByText("C001")).toBeInTheDocument();
    expect(within(confirmDialog).getByText("当前元素修改需要同步此依赖的定义或引用")).toBeInTheDocument();
    expect(modelingApi.saveElement).not.toHaveBeenCalled();

    fireEvent.click(within(confirmDialog).getByRole("button", { name: "取消" }));
    await waitFor(() => expect(screen.queryByText("确认后这些元素会随本次保存一并改写")).not.toBeInTheDocument());
    expect(modelingApi.saveElement).not.toHaveBeenCalled();
    expect(within(dialog.querySelector(`[data-element-id="${customerNo.id}"]`)!.closest("tr")!).getByRole("textbox", { name: "属性英文标识" })).toHaveValue("customer_code");

    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    const confirmAgain = (await screen.findByText("确认后这些元素会随本次保存一并改写")).closest<HTMLElement>('[role="dialog"]')!;
    fireEvent.click(within(confirmAgain).getByRole("button", { name: "确认保存" }));

    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledTimes(1));
    expect(modelingApi.previewElementSave).toHaveBeenCalledTimes(2);
    const [, savePayload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
    expect(savePayload.affected_items).toEqual([
      {
        target_kind: "material_object",
        target_id: customerFact.id,
        expected_target_hash: h,
      },
    ]);
    expect(savePayload.affected_items?.[0]).not.toHaveProperty("reason");
  });

  it("invalidates the impact confirmation when a late draft change arrives and previews the new draft again", async () => {
    const draft = example("07-instances-and-evidence");
    const customer = draft.object_types.find((o) => o.name === "customer")!;
    vi.mocked(modelingApi.previewElementSave).mockResolvedValue({
      current_version_id: "v1",
      session_revision: null,
      affected_items: [{
        target_kind: "material_object",
        target_id: draft.material_objects.find((f) => f.type_id === customer.id)!.id,
        expected_target_hash: "1".repeat(64),
        reason: "当前元素修改需要同步此依赖的定义或引用",
      }],
    });
    show(draft, `inspect=object_type:${customer.id}&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    const name = await within(dialog).findByRole("textbox", { name: "名称" });
    fireEvent.change(name, { target: { value: "星河客户" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
    await screen.findByText("确认后这些元素会随本次保存一并改写");

    // A queued input event may arrive after the confirmation was opened.
    fireEvent.change(name, { target: { value: "星河重点客户" } });
    await waitFor(() => expect(screen.queryByText("确认后这些元素会随本次保存一并改写")).not.toBeInTheDocument());
    expect(modelingApi.saveElement).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
    await screen.findByText("确认后这些元素会随本次保存一并改写");
    expect(modelingApi.previewElementSave).toHaveBeenCalledTimes(2);
    const [, payload] = vi.mocked(modelingApi.previewElementSave).mock.calls[1];
    expect((payload.draft.object_types.find((o) => o.id === customer.id)?.display_name || payload.draft.object_types.find((o) => o.id === customer.id)?.name)).toBe("星河重点客户");
    expect(modelingApi.saveElement).not.toHaveBeenCalled();
  });

  it("displays a 409 error from preview without opening the confirmation modal or saving", async () => {
    const draft = example("07-instances-and-evidence");
    const customer = draft.object_types.find((o) => o.name === "customer")!;
    const customerNo = draft.properties.find((p) => p.name === "customer_no")!;
    vi.mocked(modelingApi.previewElementSave).mockRejectedValue(
      new ApiError("当前版本已变化", 409, "VERSION_CHANGED"),
    );

    show(draft, `inspect=object_type:${customer.id}&inspectTab=properties&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(dialog.querySelector(`[data-element-id="${customerNo.id}"]`)).not.toBeNull());
    const row = dialog.querySelector<HTMLElement>(`[data-element-id="${customerNo.id}"]`)!;
    fireEvent.click(row);
    fireEvent.change(within(dialog.querySelector(`[data-element-id="${customerNo.id}"]`)!.closest("tr")!).getByRole("textbox", { name: "属性英文标识" }), { target: { value: "customer_code" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    expect(await within(dialog).findByText(/当前版本已变化。你的修改仍保留/)).toBeInTheDocument();
    expect(screen.queryByText("确认后这些元素会随本次保存一并改写")).not.toBeInTheDocument();
    expect(modelingApi.saveElement).not.toHaveBeenCalled();
    expect(within(dialog.querySelector(`[data-element-id="${customerNo.id}"]`)!.closest("tr")!).getByRole("textbox", { name: "属性英文标识" })).toHaveValue("customer_code");
  });

  it("disables Ant Design controls while busy and re-runs preview instead of saving stale candidate when Select changes during delayed preview", async () => {
    const draft = example("07-instances-and-evidence");
    const customer = draft.object_types.find((o) => o.name === "customer")!;
    const customerNo = draft.properties.find((p) => p.name === "customer_no")!;
    let resolveFirstPreview!: (value: {
      current_version_id: string | null;
      session_revision: number | null;
      affected_items: [];
    }) => void;
    let resolveSecondPreview!: (value: {
      current_version_id: string | null;
      session_revision: number | null;
      affected_items: [];
    }) => void;
    vi.mocked(modelingApi.previewElementSave)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveFirstPreview = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            resolveSecondPreview = resolve;
          }),
      );
    vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => saved(payload.draft));

    show(draft, `inspect=object_type:${customer.id}&inspectTab=properties&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(dialog.querySelector(`[data-element-id="${customerNo.id}"]`)).not.toBeNull());
    fireEvent.click(dialog.querySelector<HTMLElement>(`[data-element-id="${customerNo.id}"]`)!);

    const techInput = within(dialog.querySelector(`[data-element-id="${customerNo.id}"]`)!.closest("tr")!).getByRole("textbox", { name: "属性英文标识" });
    const valueKindSelect = within(dialog).getByRole("combobox", { name: `${(customerNo.display_name || customerNo.name)}类型` });
    const requiredCheckbox = within(dialog).getByRole("checkbox", { name: `${(customerNo.display_name || customerNo.name)}必填` });

    // Open the Select dropdown before clicking Save so its portal option is mounted, then click Save
    fireEvent.mouseDown(valueKindSelect);
    const integerOption = await screen.findByTitle("整数");
    fireEvent.change(techInput, { target: { value: "customer_code" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() => expect(modelingApi.previewElementSave).toHaveBeenCalledTimes(1));

    // While preview is in flight (busy), Ant Design Select, Checkbox, and Input controls must be disabled
    expect(techInput).toBeDisabled();
    expect(valueKindSelect).toBeDisabled();
    expect(valueKindSelect.closest(".ant-select")).toHaveClass("ant-select-disabled");
    expect(requiredCheckbox).toBeDisabled();

    // Simulate a late Select change arriving from the pre-opened portal while the first preview is still pending
    fireEvent.click(integerOption);

    // Resolve the first preview with no affected items (the direct-save branch)
    resolveFirstPreview({
      current_version_id: "v1",
      session_revision: null,
      affected_items: [],
    });

    // Must NOT save the old candidate; instead must re-run preview with the updated Select value
    await waitFor(() => expect(modelingApi.previewElementSave).toHaveBeenCalledTimes(2));
    expect(modelingApi.saveElement).not.toHaveBeenCalled();

    const [, firstPreviewPayload] = vi.mocked(modelingApi.previewElementSave).mock.calls[0];
    const [, secondPreviewPayload] = vi.mocked(modelingApi.previewElementSave).mock.calls[1];
    expect(firstPreviewPayload.draft.properties.find((p) => p.id === customerNo.id)?.value_kind).toBe("string");
    expect(secondPreviewPayload.draft.properties.find((p) => p.id === customerNo.id)?.value_kind).toBe("integer");
    expect(secondPreviewPayload.draft.properties.find((p) => p.id === customerNo.id)?.name).toBe(
      "customer_code",
    );

    resolveSecondPreview({
      current_version_id: "v1",
      session_revision: null,
      affected_items: [],
    });

    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledTimes(1));
    const [, savePayload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
    const savedProp = savePayload.draft.properties.find((p) => p.id === customerNo.id);
    expect(savedProp?.name).toBe("customer_code");
    expect(savedProp?.value_kind).toBe("integer");
  });
});


describe("retained popup editing and request lifecycle", () => {
  it.each(["save", "cancel", "conflict"])("keeps a single cross-tab draft through %s", async (action) => {
    const draft = example("01-basic-sales");
    const customer = draft.object_types.find((o) => o.name === "customer")!;
    const property = draft.properties.find((p) => p.owner_type_id === customer.id)!;
    vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => {
      if (action === "conflict") throw new ApiError("当前版本已变化", 409, "VERSION_CHANGED");
      return saved(payload.draft);
    });
    show(draft, `inspect=object_type:${customer.id}&inspectMode=edit`);
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(await within(dialog).findByRole("textbox", { name: "名称" }), { target: { value: "星舟客户" } });
    fireEvent.click(within(dialog).getByRole("tab", { name: /^字段/ }));
    const field = dialog.querySelector(`[data-element-id="${property.id}"]`)!;
    fireEvent.change(within(field as HTMLElement).getByRole("textbox", { name: "属性名称" }), { target: { value: "星舟编号" } });
    fireEvent.click(within(dialog).getByRole("tab", { name: /^概览/ }));
    expect(within(dialog).getByRole("textbox", { name: "名称" })).toHaveValue("星舟客户");
    if (action === "cancel") {
      fireEvent.click(within(dialog).getByRole("button", { name: "取消" }));
      await waitFor(() => expect(modelingApi.snapshot).toHaveBeenCalledTimes(2));
      await within(dialog).findByRole("button", { name: "编辑" });
      fireEvent.click(within(dialog).getByRole("tab", { name: /^字段/ }));
      await within(dialog).findByText(property.display_name || property.name);
      expect(within(dialog).queryByText("星舟编号")).not.toBeInTheDocument();
      fireEvent.click(within(dialog).getByRole("tab", { name: /^概览/ }));
      expect(within(dialog).getByLabelText(customer.display_name || customer.name)).toBeInTheDocument();
      expect(modelingApi.saveElement).not.toHaveBeenCalled();
      return;
    }
    fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledTimes(1));
    for (const [, payload] of [...vi.mocked(modelingApi.previewElementSave).mock.calls, ...vi.mocked(modelingApi.saveElement).mock.calls]) {
      expect(payload.draft.object_types.find((o) => o.id === customer.id)?.display_name).toBe("星舟客户");
      expect(payload.draft.properties.find((p) => p.id === property.id)?.display_name).toBe("星舟编号");
    }
    if (action === "conflict") {
      await within(dialog).findByText(/你的修改仍保留/);
      expect(within(dialog).getByRole("textbox", { name: "名称" })).toHaveValue("星舟客户");
      fireEvent.click(within(dialog).getByRole("tab", { name: /^字段/ }));
      expect(within(dialog).getAllByRole("textbox", { name: "属性名称", hidden: false })[0]).toHaveValue("星舟编号");
    } else {
      await within(dialog).findByRole("button", { name: "编辑" });
      fireEvent.click(within(dialog).getByRole("tab", { name: /^字段/ }));
      expect(await within(dialog).findByText("星舟编号")).toBeVisible();
    }
  });

  it("retains searches across tabs and resets them on close/reopen or element change", async () => {
    const draft = example("01-basic-sales");
    const type = draft.object_types[0];
    show(draft, `inspect=object_type:${type.id}&inspectTab=properties`);
    let dialog = await screen.findByRole("dialog");
    const search = await within(dialog).findByRole("searchbox", { name: "搜索属性" });
    fireEvent.change(search, { target: { value: "星舟过滤" } });
    fireEvent.click(within(dialog).getByRole("tab", { name: /^规则/ }));
    fireEvent.change(within(dialog).getByRole("searchbox", { name: "搜索规则" }), { target: { value: "月港过滤" } });
    fireEvent.click(within(dialog).getByRole("tab", { name: /^字段/ }));
    expect(within(dialog).getByRole("searchbox", { name: "搜索属性" })).toBe(search);
    expect(search).toHaveValue("星舟过滤");
    fireEvent.click(within(dialog).getByRole("button", { name: "关闭对象弹窗" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "重新打开" }));
    dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByRole("searchbox", { name: "搜索属性" })).toHaveValue("");
    fireEvent.change(within(dialog).getByRole("searchbox", { name: "搜索属性" }), { target: { value: "再次过滤" } });
    fireEvent.click(screen.getByRole("button", { name: "切换元素" }));
    dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(within(dialog).getByRole("searchbox", { name: "搜索属性" })).toHaveValue(""));
    fireEvent.click(within(dialog).getByRole("tab", { name: /^规则/ }));
    expect(within(dialog).getByRole("searchbox", { name: "搜索规则" })).toHaveValue("");
  });

  it("passes tab visibility and page activation to retained instance reads", async () => {
    const draft = example("01-basic-sales");
    draft.material_objects = [];
    const type = draft.object_types[0];
    let resolve!: (value: InstanceList) => void;
    vi.mocked(instancesApi.list).mockReturnValueOnce(new Promise((done) => { resolve = done; }));
    show(draft, `inspect=object_type:${type.id}&inspectTab=properties`);
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(instancesApi.list).toHaveBeenCalledTimes(1));
    fireEvent.click(within(dialog).getByRole("tab", { name: /^关系/ }));
    await act(async () => resolve({ items: [{ id: "old", ref: "old", type_id: type.id, source: "database", display_text: "迟到实例", values: {}, key: [], evidence: [] }], snapshot_dates: [], next_cursor: null, truncated: false } as unknown as InstanceList));
    expect(within(dialog).queryByText("迟到实例")).not.toBeInTheDocument();
    await act(async () => { await new Promise((done) => setTimeout(done, 300)); });
    expect(instancesApi.list).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "切换页面激活" }));
    await act(async () => { await new Promise((done) => setTimeout(done, 300)); });
    expect(instancesApi.list).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "切换页面激活" }));
    fireEvent.click(within(dialog).getByRole("tab", { name: /^字段/ }));
    await waitFor(() => expect(instancesApi.list).toHaveBeenCalledTimes(2));
    expect(within(dialog).queryByText("迟到实例")).not.toBeInTheDocument();
  });
});


it("loads a complete independent baseline before editing an incomplete view", async () => {
  const draft = example("01-basic-sales");
  const object = draft.object_types[0];
  vi.mocked(modelingApi.saveElement).mockImplementation(async (_, payload) => saved(payload.draft));
  show(draft, `inspect=object_type:${object.id}`);
  vi.mocked(api.elementPresentation).mockResolvedValue({ model: { ...draft, object_types: [object] }, version_id: "v1", workspace_id: "w", complete: false, representation: "element-1" } as never);
  const dialog = await screen.findByRole("dialog");
  await within(dialog).findByRole("button", { name: "编辑" });
  expect(modelingApi.snapshot).not.toHaveBeenCalled();
  fireEvent.click(within(dialog).getByRole("button", { name: "编辑" }));
  await waitFor(() => expect(modelingApi.snapshot).toHaveBeenCalledWith("w", "v1"));
  fireEvent.change(await within(dialog).findByRole("textbox", { name: "名称" }), { target: { value: "星舟客户" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
  await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledTimes(1));
  const payload = vi.mocked(modelingApi.saveElement).mock.calls[0][1];
  expect(payload.draft.object_types).toHaveLength(draft.object_types.length);
  expect(draft.object_types[0].display_name).not.toBe("星舟客户");
});


it("keeps a pinned view until an explicit refresh moves every definition to the new version", async () => {
  const draft = example("01-basic-sales");
  const object = draft.object_types[0];
  show(draft, `inspect=object_type:${object.id}`, "admin", "v1");
  const dialog = await screen.findByRole("dialog");
  await within(dialog).findByRole("button", { name: "编辑" });
  const next = structuredClone(draft);
  next.object_types[0].display_name = "星舟新版客户";
  vi.mocked(api.workspace).mockResolvedValue({ ...workspace, version_id: "v2" });
  vi.mocked(api.elementPresentation).mockResolvedValue({ model: next, version_id: "v2", workspace_id: "w", complete: false, representation: "element-1" } as never);
  act(() => notifyOntologySaved({ workspaceId: "w", session: null }));
  expect(within(dialog).queryByText("星舟新版客户")).not.toBeInTheDocument();
  fireEvent.click(await within(dialog).findByRole("button", { name: "版本已更新，刷新" }));
  await waitFor(() => expect(api.elementPresentation).toHaveBeenLastCalledWith("w", "object_type", object.id, "v2"));
  expect((await within(dialog).findAllByText("星舟新版客户")).length).toBeGreaterThan(0);
});
