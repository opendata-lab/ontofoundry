import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  api,
  ApiError,
  modelingApi,
  publishApi,
  workspaceRequest,
} from "../../api/client";
import type {
  Draft,
  LegacyDraft,
  ModelingSession,
  MappingNode,
  NativeDraft,
  Workspace,
} from "../../api/types";
import { emptyDraft } from "../../lib/draftView";
import { nativeMappingFixture } from "../../lib/objectMapping.fixture";
import { WorkspaceContextProvider } from "../../hooks/useWorkspaceContext";
import { ElementInspector } from "./ElementInspector";

vi.mock("../../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api/client")>();
  return {
    ...original,
    api: { ...original.api, workspace: vi.fn() },
    modelingApi: {
      ...original.modelingApi,
      snapshot: vi.fn(),
      get: vi.fn(),
      saveElement: vi.fn(),
      connections: vi.fn(),
      tables: vi.fn(),
    },
    publishApi: { ...original.publishApi, preview: vi.fn() },
    workspaceRequest: vi.fn(),
  };
});
const workspace = {
  id: "w",
  name: "测试空间",
  role: "admin",
  version_id: "v1",
  current_version: 1,
} as Workspace;
const refresh = vi.fn();
function legacy(): LegacyDraft {
  return {
    ...emptyDraft("w"),
    object_types: [
      {
        id: "supplier",
        name: "供应商",
        technical_name: "supplier",
        description: "供应商说明 别名：供方",
        tags: [],
        extends: [],
        evidence: [],
      },
      {
        id: "product",
        name: "产品",
        technical_name: "product",
        description: "",
        tags: [],
        extends: [],
        evidence: [],
      },
    ],
    properties: [
      {
        id: "code",
        owner_type_id: "supplier",
        name: "编码",
        technical_name: "code",
        description: "",
        value_kind: "string",
        identifier: true,
        required: true,
        evidence: [],
        verbalizes: [],
      },
      {
        id: "name",
        owner_type_id: "supplier",
        name: "名称",
        technical_name: "name",
        description: "",
        value_kind: "string",
        identifier: false,
        required: false,
        evidence: [],
        verbalizes: [],
      },
    ],
    mappings: [
      {
        id: "mapping",
        type_id: "supplier",
        connection_alias: "warehouse",
        table_name: "dim_supplier",
        schema_name: "public",
        key_column: "supplier_code",
        fields: { code: "supplier_code" },
      },
    ],
  };
}
function show(
  draft: Draft = legacy(),
  tab = "properties",
  role: Workspace["role"] = "admin",
  session = false,
  initialHref?: string,
) {
  vi.mocked(workspaceRequest).mockResolvedValue({ model: draft });
  vi.mocked(modelingApi.snapshot).mockResolvedValue(draft);
  vi.mocked(modelingApi.get).mockResolvedValue({
    id: "s",
    revision: 7,
    draft,
    workspace_id: "w",
  } as ModelingSession);
  const href = `/workspaces/w/objects?inspect=object_type:${draft.object_types[0].id}&inspectTab=${tab}${session ? "&session=s" : ""}`;
  const router = createMemoryRouter(
    [
      {
        path: "/workspaces/:workspaceId/*",
        element: (
          <WorkspaceContextProvider.Provider
            value={{
              workspace: { ...workspace, role },
              refresh,
              user: { id: "u" } as never,
            }}
          >
            <ElementInspector />
          </WorkspaceContextProvider.Provider>
        ),
      },
    ],
    { initialEntries: [initialHref ?? href] },
  );
  render(<RouterProvider router={router} />);
  return router;
}
const dialog = () => screen.findByRole("dialog", { name: "供应商" });
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.workspace).mockResolvedValue(workspace);
  vi.mocked(modelingApi.connections).mockResolvedValue({ items: [] });
  vi.mocked(modelingApi.tables).mockResolvedValue({ items: [] });
});
afterEach(cleanup);

describe("approved object popup", () => {
  it("shows exact populated tabs and counts, hides empty tabs, and supports keyboard switching", async () => {
    show();
    const element = await dialog();
    expect(
      within(element)
        .getAllByRole("tab")
        .map((t) => t.textContent),
    ).toEqual(["概览", "属性与映射2", "实例"]);
    expect(element.querySelector("header")).toHaveTextContent(
      "部分映射 · public.dim_supplier",
    );
    expect(
      within(element).queryByRole("button", { name: "高级" }),
    ).not.toBeInTheDocument();
    fireEvent.keyDown(
      within(element).getByRole("tab", { name: "属性与映射 2" }),
      { key: "Home" },
    );
    await waitFor(() =>
      expect(within(element).getByRole("tab", { name: "概览" })).toHaveFocus(),
    );
  });
  it("hides a zero-property tab and includes inherited relations and rules exactly once", async () => {
    const draft = legacy();
    draft.properties = [];
    draft.object_types[0].extends = ["product", "product"];
    draft.link_types = [
      {
        id: "parent-link",
        name: "依赖",
        technical_name: "depends_on",
        description: "",
        tags: [],
        evidence: [],
        source_type_id: "product",
        target_type_id: "product",
        multiplicity: "many_to_many",
        verbalizes: [],
      },
    ];
    draft.rules = [
      {
        id: "parent-rule",
        owner_kind: "object_type",
        owner_id: "product",
        name: "product·constraint1",
        technical_name: "generated",
        expression: "EXISTS(code)",
        description: "父类约束",
        rule_kind: "constraint",
        verbalizes: [],
        evidence: [],
      },
    ];
    show(draft, "relations");
    const element = await dialog();
    expect(
      within(element)
        .getAllByRole("tab")
        .map((t) => t.textContent),
    ).toEqual(["概览", "关系1", "规则1", "实例"]);
    expect(within(element).getByText("继承")).toBeInTheDocument();
    fireEvent.click(within(element).getByRole("row", { name: "查看依赖" }));
    const relation = await screen.findByRole("dialog", { name: "依赖" });
    expect(
      within(relation).queryByRole("button", { name: "保存" }),
    ).not.toBeInTheDocument();
    fireEvent.click(within(relation).getByRole("button", { name: "编辑" }));
    expect(
      within(relation).getByRole("button", { name: "保存" }),
    ).toBeDisabled();
    expect(
      within(relation).getByRole("button", { name: "编辑父对象" }),
    ).toBeInTheDocument();
    fireEvent.click(
      within(relation).getByRole("button", { name: "编辑父对象" }),
    );
    const parent = await screen.findByRole("dialog", { name: "产品" });
    expect(within(parent).getByRole("tab", { name: "关系 1" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
  it("shows synonyms and context inline and puts only evidence behind the basic-info icon", async () => {
    const draft = legacy();
    draft.object_types[0].concept_context = {
      synonyms: ["供货主体"],
      instructions: "与供货组织一致",
    };
    draft.object_types[0].evidence = [
      {
        kind: "manual",
        id: "e1",
        note: "访谈记录",
        created_by: "u",
        created_at: "2026-10-01",
      },
    ];
    show(draft, "basic");
    const element = await dialog();
    expect(within(element).getByText("供方、供货主体")).toBeInTheDocument();
    expect(within(element).getByText("与供货组织一致")).toBeInTheDocument();
    fireEvent.click(within(element).getByRole("button", { name: "来源证据" }));
    const evidence = await screen.findByRole("dialog", { name: "来源证据" });
    expect(within(evidence).getByText("访谈记录")).toBeInTheDocument();
    expect(
      within(evidence).queryByText("供方、供货主体"),
    ).not.toBeInTheDocument();
    expect(
      within(evidence).queryByText("与供货组织一致"),
    ).not.toBeInTheDocument();
  });
  it("omits empty metadata and the evidence icon when there is no evidence", async () => {
    const draft = legacy();
    draft.object_types[0].description = "";
    show(draft, "basic");
    const element = await dialog();
    for (const label of ["同义词", "上下文说明", "描述", "继承自"])
      expect(within(element).queryByText(label)).not.toBeInTheDocument();
    expect(
      within(element).queryByRole("button", { name: "来源证据" }),
    ).not.toBeInTheDocument();
  });
  it("shows all source fields one per line, with short names and full hover names", async () => {
    const native = nativeMappingFixture();
    native.mapping_nodes.push(
      {
        id: "other-code-link",
        parent_id: "properties",
        kind: "link",
        slot: "children",
        relationship: "code",
        concept_mapping_id: "cm-s",
      },
      {
        id: "other-code-value",
        parent_id: "other-code-link",
        kind: "object",
        slot: "object_mapping",
        expression: "events.owner",
        concept_mapping_id: "cm-s",
      },
    );
    show(native);
    const element = await dialog();
    expect(
      within(element)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["属性", "类型", "来源字段"]);
    const row = within(element).getByText("编码").closest("tr")!;
    expect(row.querySelectorAll(".om-entry")).toHaveLength(2);
    expect(
      within(row).getByTitle("public.dim_supplier.supplier_code"),
    ).toHaveTextContent("dim_supplier.supplier_code");
    expect(
      within(row).getByTitle("public.fact_calls.supplier_code"),
    ).toHaveTextContent("fact_calls.supplier_code");
    expect(
      within(element).getByRole("textbox", { name: "搜索属性" }),
    ).toBeInTheDocument();
    fireEvent.change(
      within(element).getByRole("combobox", { name: "来源表" }),
      { target: { value: "unbound" } },
    );
    expect(within(element).queryByText("编码")).not.toBeInTheDocument();
    expect(within(element).getByText("名称")).toBeInTheDocument();
  });
  it("shows the derived tag and full wrapped expression inline without a content icon", async () => {
    const native = nativeMappingFixture();
    const expression = "CASE WHEN LOWER(name) = 'core' THEN 'Y' ELSE 'N' END";
    native.dataset_fields.push({
      id: "derived",
      dataset_id: "s",
      name: "normalized",
      expression: { dialects: [{ dialect: "ANSI_SQL", expression }] },
    });
    (native.mapping_nodes as MappingNode[]).find(
      (n) => n.id === "code-value",
    )!.expression = "suppliers.normalized";
    show(native);
    const element = await dialog();
    const row = within(element).getByText("编码").closest("tr")!;
    expect(within(row).getByText("派生")).toBeInTheDocument();
    expect(within(row).getByText(`code = ${expression}`)).toHaveClass(
      "om-binding-expression",
    );
    expect(within(row).queryByRole("button")).not.toBeInTheDocument();
  });
  it("shows a parent's declared property type with an inheritance tag", async () => {
    const draft = legacy();
    draft.object_types[0].extends = ["product"];
    draft.properties.push({
      ...draft.properties[1],
      id: "parent-count",
      owner_type_id: "product",
      name: "数量",
      technical_name: "quantity",
      value_kind: "integer",
    });
    show(draft);
    const element = await dialog();
    const row = within(element).getByText("数量").closest("tr")!;
    expect(within(row).getByText("整数")).toBeInTheDocument();
    expect(within(row).getByText("继承")).toBeInTheDocument();
    expect(
      within(element).getByRole("tab", { name: "属性与映射 3" }),
    ).toBeInTheDocument();
  });
  it("renders all neighbours radially, groups parallel relations, and opens objects from the graph", async () => {
    const native = nativeMappingFixture();
    native.mapping_nodes.push(
      {
        id: "overview-secondary-link",
        parent_id: "properties",
        kind: "link",
        slot: "children",
        relationship: "name",
        concept_mapping_id: "cm-s",
      },
      {
        id: "overview-secondary-value",
        parent_id: "overview-secondary-link",
        kind: "object",
        slot: "object_mapping",
        expression: "events.name",
        concept_mapping_id: "cm-s",
      },
    );
    show(native, "basic");
    const element = await dialog();
    expect(within(element).getByText("附表")).toBeInTheDocument();
    const graph = within(element).getByLabelText("供应商的关系图");
    expect(graph.querySelectorAll(".om-graph-connection")).toHaveLength(1);
    expect(graph.querySelector(".om-edge-count")).toHaveTextContent("2");
    expect(graph.querySelector(".om-edge")).toHaveAttribute("marker-end");
    expect(graph.querySelector("title")).toHaveTextContent("供应产品");
    fireEvent.click(
      within(element).getByRole("button", { name: "全部关系 ↗" }),
    );
    expect(
      within(element).getByRole("tab", { name: "关系 2" }),
    ).toHaveAttribute("aria-selected", "true");
    fireEvent.click(within(element).getByRole("tab", { name: "概览" }));
    fireEvent.click(within(element).getByRole("button", { name: "打开产品" }));
    expect(
      await screen.findByRole("dialog", { name: "产品" }),
    ).toBeInTheDocument();
  });
  it("saves native fields through semantic_changes and preserves sibling mappings", async () => {
    const native = nativeMappingFixture();
    show(native);
    const element = await dialog();
    fireEvent.click(within(element).getByRole("button", { name: "编辑" }));
    expect(
      within(element)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["属性", "来源字段 ▾", "类型 ▾", "删除"]);
    fireEvent.change(
      within(element).getByRole("combobox", { name: "编码 字段" }),
      { target: { value: "s|name" } },
    );
    vi.mocked(modelingApi.saveElement).mockResolvedValue({
      draft: native,
      version: { version_id: "v2" } as never,
      session: null,
    });
    fireEvent.click(within(element).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledOnce());
    const payload = vi.mocked(modelingApi.saveElement).mock.calls[0][1];
    expect((payload.draft as NativeDraft)._legacy_form).toBeUndefined();
    expect(
      payload.semantic_changes![0].nodes!.find((n) => n.id === "code-value")
        ?.expression,
    ).toBe("suppliers.name");
    expect(
      payload.semantic_changes![0].nodes!.find((n) => n.id === "simple-value")
        ?.expression,
    ).toBe("events.ref");
  });
  it("keeps conflicts editable and includes session revision in the existing save contract", async () => {
    show(legacy(), "basic", "admin", true);
    const element = await dialog();
    fireEvent.click(within(element).getByRole("button", { name: "编辑" }));
    fireEvent.change(within(element).getByLabelText("名称"), {
      target: { value: "修改名称" },
    });
    vi.mocked(modelingApi.saveElement).mockRejectedValue(
      new ApiError("内容已变化", 409, "VERSION_CHANGED"),
    );
    fireEvent.click(within(element).getByRole("button", { name: "保存" }));
    expect(await within(element).findByRole("alert")).toHaveTextContent(
      "你的修改仍保留",
    );
    expect(vi.mocked(modelingApi.saveElement).mock.calls[0][1]).toMatchObject({
      session_id: "s",
      expected_session_revision: 7,
    });
    expect(within(element).getByLabelText("名称")).toHaveValue("修改名称");
  });
  it("retains native field edits across tabs and discards them on cancel", async () => {
    show(nativeMappingFixture());
    const element = await dialog();
    fireEvent.click(within(element).getByRole("button", { name: "编辑" }));
    fireEvent.change(
      within(element).getByRole("combobox", { name: "名称 字段" }),
      { target: { value: "s|name" } },
    );
    fireEvent.click(within(element).getByRole("tab", { name: "概览" }));
    fireEvent.click(within(element).getByRole("tab", { name: "属性与映射 2" }));
    expect(
      within(element).getByRole("combobox", { name: "名称 字段" }),
    ).toHaveValue("s|name");
    fireEvent.click(within(element).getByRole("button", { name: "取消" }));
    await waitFor(() =>
      expect(
        within(element).getByRole("button", { name: "编辑" }),
      ).toBeEnabled(),
    );
    expect(
      within(within(element).getByRole("table")).getByText("未绑定"),
    ).toBeInTheDocument();
    expect(modelingApi.saveElement).not.toHaveBeenCalled();
  });
  it("keeps visitors and publish previews read-only, including nested relationship dialogs", async () => {
    const native = nativeMappingFixture();
    show(native, "relations", null);
    const element = await dialog();
    expect(
      within(element).queryByRole("button", { name: "编辑" }),
    ).not.toBeInTheDocument();
    expect(
      within(element).queryByRole("tab", { name: "实例" }),
    ).not.toBeInTheDocument();
    fireEvent.click(within(element).getByRole("row", { name: "查看供应产品" }));
    expect(
      within(
        await screen.findByRole("dialog", { name: "供应产品" }),
      ).queryByRole("button", { name: "编辑" }),
    ).not.toBeInTheDocument();
  });
  it("reads merged preview content without offering editing", async () => {
    const merged = legacy();
    merged.object_types[0].description = "合并后的描述";
    vi.mocked(publishApi.preview).mockResolvedValue({
      merged_model: merged,
      merged_snapshot_sha256: "hash",
      current_version_id: "v1",
    } as never);
    show(
      legacy(),
      "basic",
      "admin",
      true,
      "/workspaces/w/objects?session=s&inspect=object_type:supplier&inspectSource=preview&inspectSession=s&inspectPreviewHash=hash",
    );
    const element = await dialog();
    expect(within(element).getByText("合并后的描述")).toBeInTheDocument();
    expect(
      within(element).queryByRole("button", { name: "编辑" }),
    ).not.toBeInTheDocument();
  });
  it("saves existing inline synonyms/context to the native context extension", async () => {
    const native = nativeMappingFixture();
    native.extension_v4.concept_context = {
      ...native.extension_v4.concept_context,
      [native.object_types[0].id]: {
        synonyms: ["供方"],
        instructions: "原说明",
      },
    };
    show(native, "basic");
    const element = await dialog();
    fireEvent.click(within(element).getByRole("button", { name: "编辑" }));
    fireEvent.change(within(element).getByRole("textbox", { name: "同义词" }), {
      target: { value: "供方\n供货方" },
    });
    fireEvent.change(
      within(element).getByRole("textbox", { name: "上下文说明" }),
      { target: { value: "供货主体" } },
    );
    vi.mocked(modelingApi.saveElement).mockResolvedValue({
      draft: native,
      version: { version_id: "v2" } as never,
      session: null,
    });
    fireEvent.click(within(element).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledOnce());
    const saved = vi.mocked(modelingApi.saveElement).mock.calls[0][1]
      .draft as NativeDraft;
    expect(
      saved.extension_v4.concept_context?.[native.object_types[0].id],
    ).toMatchObject({ synonyms: ["供方", "供货方"], instructions: "供货主体" });
    expect(saved.mapping_nodes).toEqual(native.mapping_nodes);
  });
});

describe("compact actions", () => {
  it("counts actions and renders the approved name/parameters/impact columns", async () => {
    const draft = legacy();
    draft.actions = [
      {
        id: "disable",
        input_type_id: "supplier",
        name: "停用供应商",
        technical_name: "disable_supplier",
        description: "",
        parameters: [],
        precondition_rule_ids: [],
        effects: [],
        evidence: [],
      },
    ];
    show(draft, "actions");
    const element = await dialog();
    expect(
      within(element).getByRole("tab", { name: "动作 1" }),
    ).toHaveAttribute("aria-selected", "true");
    expect(
      within(element)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["名称", "参数", "影响"]);
    expect(within(element).getByText("停用供应商")).toBeInTheDocument();
  });
});

describe("relationship and rules prototypes", () => {
  it("renders the four relation columns with directions and record roles, without a status column", async () => {
    show(nativeMappingFixture(), "relations");
    const element = await dialog();
    expect(
      within(element)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["关系", "方向", "关联对象", "关联方式"]);
    expect(within(element).getAllByText("→ 出")).toHaveLength(2);
    expect(within(element).getByText("记录型")).toBeInTheDocument();
    expect(within(element).queryByText("状态")).not.toBeInTheDocument();
    expect(
      within(element).getByRole("button", { name: "＋ 添加关系" }),
    ).toBeDisabled();
  });
  it("opens read-only, switches to editable, and saves an existing native record branch", async () => {
    const native = nativeMappingFixture();
    show(native, "relations");
    const element = await dialog();
    fireEvent.click(within(element).getByRole("row", { name: "查看调用记录" }));
    const detail = await screen.findByRole("dialog", { name: "调用记录" });
    expect(within(detail).getByText("供应商 → 产品")).toBeInTheDocument();
    expect(
      within(detail)
        .getAllByRole("heading")
        .map((h) => h.textContent),
    ).toEqual(["调用记录", "来源对象", "关系", "附加属性", "目标对象"]);
    expect(within(detail).getByText("常量")).toBeInTheDocument();
    expect(
      within(detail).queryByRole("button", { name: "保存" }),
    ).not.toBeInTheDocument();
    expect(within(detail).queryByRole("textbox")).not.toBeInTheDocument();
    fireEvent.click(within(detail).getByRole("button", { name: "编辑" }));
    expect(
      within(detail).getByRole("switch", { name: "使用映射表" }),
    ).toBeDisabled();
    expect(within(detail).getByRole("button", { name: "删除" })).toBeDisabled();
    fireEvent.change(
      within(detail).getByRole("textbox", { name: "次数来源字段 常量" }),
      { target: { value: "20" } },
    );
    vi.mocked(modelingApi.saveElement).mockResolvedValue({
      draft: native,
      version: { version_id: "v2" } as never,
      session: null,
    });
    fireEvent.click(within(detail).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledOnce());
    const nodes = vi.mocked(modelingApi.saveElement).mock.calls[0][1]
      .semantic_changes![0].nodes!;
    expect(nodes.find((n) => n.id === "record-count-value-0")?.expression).toBe(
      "20",
    );
    expect(nodes.find((n) => n.id === "record-count-value-1")?.expression).toBe(
      "10",
    );
  });
  it("labels the two sides explicitly for a self relationship", async () => {
    const draft = legacy();
    draft.link_types = [
      {
        id: "self",
        name: "依赖",
        technical_name: "depends",
        description: "",
        tags: [],
        evidence: [],
        source_type_id: "supplier",
        target_type_id: "supplier",
        multiplicity: "many_to_many",
        verbalizes: [],
        data_join: {
          source_column: "parent_code",
          target_column: "supplier_code",
        },
      },
    ];
    show(draft, "relations");
    const element = await dialog();
    fireEvent.click(within(element).getByRole("row", { name: "查看依赖" }));
    const detail = await screen.findByRole("dialog", { name: "依赖" });
    expect(within(detail).getByText("来源 · 供应商.code")).toBeInTheDocument();
    expect(within(detail).getByText("目标 · 供应商.code")).toBeInTheDocument();
    expect(within(detail).getByText("供应商 → 供应商")).toBeInTheDocument();
  });
  it("saves standalone join columns through the existing relation form", async () => {
    const draft = legacy();
    draft.mappings.push({
      ...draft.mappings[0],
      id: "mp",
      type_id: "product",
      table_name: "dim_product",
      key_column: "product_id",
      fields: {},
    });
    draft.link_types = [
      {
        id: "join",
        name: "供应产品",
        technical_name: "supplies",
        description: "",
        tags: [],
        evidence: [],
        source_type_id: "supplier",
        target_type_id: "product",
        multiplicity: "many_to_one",
        verbalizes: [],
        data_join: {
          source_column: "supplier_code",
          target_column: "product_id",
        },
      },
    ];
    show(
      draft,
      "basic",
      "admin",
      false,
      "/workspaces/w/relations?inspect=link_type:join&inspectMode=edit",
    );
    const element = await screen.findByRole("dialog", { name: "供应产品" });
    fireEvent.change(
      within(element).getByRole("combobox", { name: "来源 · 供应商.code" }),
      { target: { value: "supplier_code" } },
    );
    fireEvent.change(
      within(element).getByRole("textbox", { name: "关系名称" }),
      { target: { value: "供货产品" } },
    );
    vi.mocked(modelingApi.saveElement).mockResolvedValue({
      draft,
      version: { version_id: "v2" } as never,
      session: null,
    });
    fireEvent.click(within(element).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledOnce());
    expect(vi.mocked(modelingApi.saveElement).mock.calls[0][1]).toMatchObject({
      target_kind: "link_type",
      target_id: "join",
      semantic_changes: [],
    });
  });
  it("orders object, property, relation rules and shows content/description/inheritance instead of auto names", async () => {
    const draft = legacy();
    draft.object_types[0].extends = ["product"];
    draft.link_types = [
      {
        id: "parent-link",
        name: "依赖",
        technical_name: "depends_on",
        description: "",
        tags: [],
        evidence: [],
        source_type_id: "product",
        target_type_id: "product",
        multiplicity: "many_to_many",
        verbalizes: [],
      },
    ];
    const rule = {
      name: "host_type·constraint1",
      technical_name: "generated",
      description: "",
      rule_kind: "constraint" as const,
      verbalizes: [],
      evidence: [],
    };
    draft.rules = [
      {
        ...rule,
        id: "link-rule",
        owner_kind: "link_type",
        owner_id: "parent-link",
        expression: "count > 0",
      },
      {
        ...rule,
        id: "prop-rule",
        owner_kind: "property",
        owner_id: "code",
        expression: "code IS NOT NULL",
        description: "编码不能为空",
      },
      {
        ...rule,
        id: "object-rule",
        owner_kind: "object_type",
        owner_id: "product",
        expression: "EXISTS(code)",
      },
    ];
    show(draft, "rules");
    const element = await dialog();
    expect(
      within(element).getByRole("tab", { name: "规则 3" }),
    ).toBeInTheDocument();
    expect(
      within(element)
        .getAllByRole("columnheader")
        .map((h) => h.textContent),
    ).toEqual(["作用于", "类型", "规则"]);
    const rows = within(element).getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("对象继承");
    expect(rows[1]).toHaveTextContent("编码不能为空");
    expect(rows[2]).toHaveTextContent("依赖继承");
    expect(
      within(element).queryByText("host_type·constraint1"),
    ).not.toBeInTheDocument();
    expect(
      within(element).queryByRole("button", { name: "规则来源" }),
    ).not.toBeInTheDocument();
  });
});
