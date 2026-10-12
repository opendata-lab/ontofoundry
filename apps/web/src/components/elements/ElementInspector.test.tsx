import nativeJson from "../../lib/nativeDraft.fixture.json";
import type { NativeDraft } from "../../api/types";
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
import type { Draft, ModelingSession, Workspace } from "../../api/types";
import { emptyDraft } from "../../lib/draftView";
import { WorkspaceContextProvider } from "../../hooks/useWorkspaceContext";
import { WorkspaceTabs } from "../WorkspaceTabs";

vi.mock("../../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api/client")>();
  return {
    ...original,
    api: { ...original.api, workspace: vi.fn(), types: vi.fn() },
    modelingApi: {
      ...original.modelingApi,
      snapshot: vi.fn(),
      get: vi.fn(),
      saveElement: vi.fn(),
    },
    publishApi: { ...original.publishApi, preview: vi.fn() },
    workspaceRequest: vi.fn(),
  };
});
const refresh = vi.fn();
const workspace = {
  id: "w",
  name: "测试空间",
  role: "admin",
  version_id: "v1",
  current_version: 1,
} as Workspace;
function model(): Draft {
  return {
    ...emptyDraft("w"),
    object_types: [
      {
        id: "supplier",
        name: "供应商",
        technical_name: "supplier",
        description: "原描述",
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
    ],
    link_types: [
      {
        id: "supplies",
        name: "供应商供货",
        technical_name: "supplies",
        description: "供货描述",
        tags: [],
        source_type_id: "supplier",
        target_type_id: "product",
        multiplicity: "many_to_many",
        evidence: [],
        verbalizes: ["supplier supplies product"],
      },
    ],
    actions: [
      {
        id: "approve",
        name: "批准",
        technical_name: "approve",
        description: "审批操作",
        input_type_id: "supplier",
        parameters: [],
        precondition_rule_ids: ["action-rule"],
        effects: [],
        evidence: [],
      },
    ],
    rules: [
      {
        id: "action-rule",
        owner_kind: "action",
        owner_id: "approve",
        name: "前置规则",
        technical_name: "precondition",
        description: "",
        rule_kind: "constraint",
        expression: "TRUE",
        evidence: [],
        verbalizes: [],
      },
    ],
  };
}
function show(
  href = "/workspaces/w/objects?inspect=object_type:supplier&inspectTab=properties",
  role: Workspace["role"] = "admin",
) {
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
            <WorkspaceTabs workspaceId="w" userId="u" />
          </WorkspaceContextProvider.Provider>
        ),
      },
    ],
    { initialEntries: [href] },
  );
  render(<RouterProvider router={router} />);
  return router;
}
beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  vi.mocked(api.workspace).mockResolvedValue(workspace);
  vi.mocked(modelingApi.snapshot).mockResolvedValue(model());
  vi.mocked(workspaceRequest).mockResolvedValue({ model: model() });
  vi.mocked(api.types).mockResolvedValue({ items: [] });
  vi.mocked(modelingApi.get).mockResolvedValue({
    id: "s",
    revision: 7,
    draft: model(),
    workspace_id: "w",
    base_diff: [],
    task_status: "idle",
  } as unknown as ModelingSession);
});
afterEach(cleanup);
const dialog = () => screen.findByRole("dialog", { name: "供应商" });

describe("统一本体元素", () => {
  it("opens over the catalog, displays all object tabs and edits without creating a session", async () => {
    show();
    const el = await dialog();
    expect(
      within(el)
        .getAllByRole("tab")
        .map((t) => t.textContent),
    ).toEqual([
      "基本信息",
      "属性1",
      "映射0",
      "关系1",
      "规则1",
      "动作1",
      "实例",
    ]);
    expect(el.querySelector("footer")).toBeNull();
    expect(within(el).queryByText("supplier")).not.toBeInTheDocument();
    fireEvent.click(within(el).getByRole("button", { name: "编辑" }));
    expect(
      within(el).getByRole("button", { name: "保存" }).closest("header"),
    ).toBeTruthy();
    expect(
      within(el).getByRole("button", { name: "取消" }).closest("header"),
    ).toBeTruthy();
    expect(modelingApi.get).not.toHaveBeenCalled();
    fireEvent.change(within(el).getByLabelText("属性名称 1"), {
      target: { value: "供应商编码" },
    });
    fireEvent.click(within(el).getByRole("tab", { name: "基本信息" }));
    fireEvent.click(within(el).getByRole("tab", { name: "属性 1" }));
    expect(within(el).getByLabelText("属性名称 1")).toHaveValue("供应商编码");
  });

  it("edits tag chips and parent types without losing unfinished tag input on save", async () => {
    const draft = model();
    draft.object_types[0].tags = ["采购"];
    vi.mocked(workspaceRequest).mockResolvedValue({ model: draft });
    show("/workspaces/w/objects?inspect=object_type:supplier&inspectTab=basic");
    const el = await dialog();
    fireEvent.click(within(el).getByRole("button", { name: "编辑" }));
    const input = within(el).getByRole("textbox", { name: "标签" });
    expect(input).toHaveValue("");
    fireEvent.blur(input);
    expect(within(el).getByRole("button", { name: "保存" })).toBeDisabled();
    fireEvent.change(input, { target: { value: "供应链" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(input).toHaveValue("");
    expect(within(el).getByRole("button", { name: "移除标签 供应链" })).toBeInTheDocument();
    fireEvent.click(within(el).getByRole("button", { name: "移除标签 采购" }));
    const parents = within(el).getByRole("combobox", { name: "继承自" });
    expect(parents).not.toHaveAttribute("multiple");
    expect(within(parents).queryByRole("option", { name: "供应商" })).not.toBeInTheDocument();
    fireEvent.change(parents, { target: { value: "product" } });
    expect(parents).toHaveValue("product");
    fireEvent.change(parents, { target: { value: "" } });
    expect(parents).toHaveValue("");
    fireEvent.change(parents, { target: { value: "product" } });
    // A header Save must include text that has not yet been committed with Enter or blur.
    fireEvent.change(input, { target: { value: "合作" } });
    const saved = model();
    saved.object_types[0].tags = ["供应链", "合作"];
    saved.object_types[0].extends = ["product"];
    vi.mocked(modelingApi.saveElement).mockResolvedValue({ draft: saved, version: { version_id: "v2" } as never, session: null });
    fireEvent.click(within(el).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledOnce());
    expect(vi.mocked(modelingApi.saveElement).mock.calls[0][1].draft.object_types[0]).toMatchObject({
      tags: ["供应链", "合作"], extends: ["product"],
    });
    await within(el).findByRole("button", { name: "编辑" });
  });

  it("moves data preview into Mapping and keeps old data-tab links usable", async () => {
    const draft = model();
    const mapping = {
      id: "mapping",
      type_id: "supplier",
      connection_alias: "demo",
      table_name: "suppliers",
      schema_name: null,
      key_column: "code",
      fields: { code: "code" },
    };
    draft.mappings.push(mapping);
    vi.mocked(workspaceRequest).mockResolvedValue({ model: draft });
    show("/workspaces/w/objects?inspect=object_type:supplier&inspectTab=data");
    const el = await dialog();
    expect(
      within(el).queryByRole("tab", { name: "数据" }),
    ).not.toBeInTheDocument();
    expect(within(el).getByRole("tab", { name: "映射 1" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(
      within(el).getByRole("heading", { name: "数据预览" }),
    ).toBeInTheDocument();
    expect(within(el).getAllByText("suppliers")).toHaveLength(1);
    vi.mocked(workspaceRequest).mockResolvedValueOnce({
      items: [{ __key: "S01", code: "S01" }],
    });
    fireEvent.click(within(el).getByRole("button", { name: "预览数据" }));
    expect(await within(el).findByText("S01")).toBeInTheDocument();
    expect(workspaceRequest).toHaveBeenLastCalledWith("w", "/mapping-preview", {
      mapping,
      limit: 10,
    });
  });

  it("cancel restores the original content and saving creates a version while preserving action rules", async () => {
    const router = show();
    const el = await dialog();
    fireEvent.click(within(el).getByRole("button", { name: "编辑" }));
    fireEvent.change(within(el).getByLabelText("属性名称 1"), {
      target: { value: "临时名称" },
    });
    fireEvent.click(within(el).getByRole("button", { name: "取消" }));
    expect(await within(el).findByText("编码")).toBeInTheDocument();
    await waitFor(() =>
      expect(within(el).getByRole("button", { name: "编辑" })).toBeEnabled(),
    );
    fireEvent.click(within(el).getByRole("button", { name: "编辑" }));
    fireEvent.change(within(el).getByLabelText("属性名称 1"), {
      target: { value: "供应商编码" },
    });
    const saved = model();
    saved.properties[0].name = "供应商编码";
    vi.mocked(modelingApi.saveElement).mockResolvedValue({
      draft: saved,
      version: { version_id: "v2" } as never,
      session: null,
    });
    fireEvent.click(within(el).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledOnce());
    const payload = vi.mocked(modelingApi.saveElement).mock.calls[0][1];
    expect(payload.session_id).toBeNull();
    expect(payload.expected_current_version_id).toBe("v1");
    expect(payload.draft.rules).toEqual(model().rules);
    expect(payload.draft.actions).toEqual(model().actions);
    await waitFor(() =>
      expect(
        within(el).getByRole("button", { name: "编辑" }),
      ).toBeInTheDocument(),
    );
    expect(router.state.location.pathname).toBe("/workspaces/w/objects");
  });
  it("protects closing from losing unfinished edits", async () => {
    const router = show();
    const el = await dialog();
    fireEvent.click(within(el).getByRole("button", { name: "编辑" }));
    fireEvent.change(within(el).getByLabelText("属性名称 1"), {
      target: { value: "未保存" },
    });
    fireEvent.click(within(el).getByRole("button", { name: "关闭本体元素" }));
    const confirm = await screen.findByRole("dialog", {
      name: "有尚未保存的内容",
    });
    fireEvent.click(within(confirm).getByRole("button", { name: "返回页面" }));
    expect(within(el).getByLabelText("属性名称 1")).toHaveValue("未保存");
    expect(router.state.location.search).toContain("inspect=");
    fireEvent.click(within(el).getByRole("button", { name: "关闭本体元素" }));
    fireEvent.click(
      within(
        await screen.findByRole("dialog", { name: "有尚未保存的内容" }),
      ).getByRole("button", { name: "放弃并离开" }),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "供应商" }),
      ).not.toBeInTheDocument(),
    );
  });
  it("keeps input after a conflict and does not pretend to save", async () => {
    show();
    const el = await dialog();
    fireEvent.click(within(el).getByRole("button", { name: "编辑" }));
    fireEvent.change(within(el).getByLabelText("属性名称 1"), {
      target: { value: "保留我的修改" },
    });
    vi.mocked(modelingApi.saveElement).mockRejectedValue(
      new ApiError("内容已变化", 409, "VERSION_CHANGED"),
    );
    fireEvent.click(within(el).getByRole("button", { name: "保存" }));
    expect(await within(el).findByRole("alert")).toHaveTextContent(
      "你的修改仍保留",
    );
    expect(within(el).getByLabelText("属性名称 1")).toHaveValue("保留我的修改");
    expect(refresh).not.toHaveBeenCalled();
  });
  it("maps an old step URL to Mapping and keeps dataset suggestions", async () => {
    const router = show(
      "/workspaces/w/objects/supplier/edit?session=s&step=1&mapping_source=test&mapping_table=suppliers",
    );
    await dialog();
    expect(router.state.location.search).toContain("inspectTab=mapping");
    expect(router.state.location.search).toContain("mapping_table=suppliers");
    expect(router.state.location.search).not.toContain("step=");
    expect(screen.queryByText("下一步")).not.toBeInTheDocument();
  });
  it("has one description, relation endpoints and no relation-owned properties", async () => {
    show("/workspaces/w/relations?inspect=link_type:supplies&inspectTab=basic");
    const el = await screen.findByRole("dialog", { name: "供应商供货" });
    expect(
      within(el).queryByRole("tab", { name: /属性/ }),
    ).not.toBeInTheDocument();
    expect(within(el).queryByText("语义描述")).not.toBeInTheDocument();
    expect(within(el).getAllByText("描述")).toHaveLength(1);
    fireEvent.click(within(el).getByRole("tab", { name: "角色与语义描述" }));
    expect(
      within(el).getByRole("button", { name: /供应商/ }),
    ).toBeInTheDocument();
  });

  it("edits action parameters and preserves its owned rules when saving", async () => {
    show(
      "/workspaces/w/objects?inspect=object_type:supplier&inspectTab=actions",
    );
    const el = await dialog();
    fireEvent.click(within(el).getByRole("button", { name: "编辑" }));
    fireEvent.click(within(el).getByRole("button", { name: "新增参数" }));
    fireEvent.change(within(el).getByLabelText("动作 批准参数名称 1"), {
      target: { value: "备注" },
    });
    fireEvent.change(within(el).getByLabelText("动作 批准参数英文名称 1"), {
      target: { value: "note" },
    });
    fireEvent.click(within(el).getByRole("button", { name: "管理规则" }));
    expect(within(el).getByRole("tab", { name: "规则 1" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(
      screen.queryByRole("dialog", { name: "有尚未保存的内容" }),
    ).not.toBeInTheDocument();
    vi.mocked(modelingApi.saveElement).mockResolvedValue({
      draft: model(),
      version: { version_id: "v2" } as never,
      session: null,
    });
    fireEvent.click(within(el).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledOnce());
    const draft = vi.mocked(modelingApi.saveElement).mock.calls[0][1].draft;
    expect(draft.actions[0].parameters[0]).toMatchObject({
      name: "备注",
      technical_name: "note",
    });
    expect(draft.actions[0].precondition_rule_ids).toEqual(["action-rule"]);
    expect(draft.rules).toEqual(model().rules);
  });
  it("hides private tabs and editing from visitors", async () => {
    show(undefined, null);
    const el = await dialog();
    expect(
      within(el).queryByRole("tab", { name: "数据" }),
    ).not.toBeInTheDocument();
    expect(
      within(el).queryByRole("tab", { name: "实例" }),
    ).not.toBeInTheDocument();
    expect(
      within(el).queryByRole("button", { name: "编辑" }),
    ).not.toBeInTheDocument();
  });
  it("reads actual merged publish content instead of a stale session view", async () => {
    const merged = model();
    merged.object_types[0].description = "其他会话合并后的描述";
    vi.mocked(publishApi.preview).mockResolvedValue({
      merged_model: merged,
      merged_snapshot_sha256: "hash",
      current_version_id: "v1",
    } as never);
    show(
      "/workspaces/w/objects?session=s&inspect=object_type:supplier&inspectSource=preview&inspectSession=s&inspectPreviewHash=hash",
    );
    const el = await dialog();
    expect(within(el).getByText("其他会话合并后的描述")).toBeInTheDocument();
    expect(
      within(el).queryByRole("button", { name: "编辑" }),
    ).not.toBeInTheDocument();
  });
});


describe("v3 native relations", () => {
  it("edits ordered native roles in a direct n-ary edit link", async () => {
    const native = structuredClone(nativeJson) as NativeDraft;
    const nary = native.link_types.find(l => l.technical_name === "sale")!;
    vi.mocked(workspaceRequest).mockResolvedValue({ model: native });
    vi.mocked(modelingApi.snapshot).mockResolvedValue(native);
    vi.mocked(modelingApi.saveElement).mockResolvedValue({ draft: native, version: { version_id: "v2" } as never, session: null });
    show(`/workspaces/w/relations?inspect=link_type:${nary.id}&inspectTab=endpoints&inspectMode=edit`);
    const el = await screen.findByRole("dialog", { name: "sale" });
    expect(within(el).getByLabelText("角色 1 名称")).toHaveValue("product");
    fireEvent.click(within(el).getByRole("button", { name: "下移角色 1" }));
    fireEvent.click(within(el).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalled());
    const payload = vi.mocked(modelingApi.saveElement).mock.calls[0][1].draft as NativeDraft;
    expect(payload.link_types.find(l => l.id === nary.id)!.roles.map(r => r.id)).toEqual([nary.roles[1].id, nary.roles[0].id, nary.roles[2].id]);
    expect(payload.link_types.find(l => l.id === nary.id)!.verbalizes).toEqual(nary.verbalizes);
    expect(payload.semantic_models).toEqual(native.semantic_models);
  });
  it("saves a binary native edit as v3 without endpoint compatibility fields", async () => {
    const native = structuredClone(nativeJson) as NativeDraft;
    const binary = native.link_types.find(l => l.technical_name === "supply")!;
    vi.mocked(workspaceRequest).mockResolvedValue({ model: native });
    vi.mocked(modelingApi.snapshot).mockResolvedValue(native);
    vi.mocked(modelingApi.saveElement).mockResolvedValue({ draft: native, version: { version_id: "v2" } as never, session: null });
    show(`/workspaces/w/relations?inspect=link_type:${binary.id}&inspectTab=basic`);
    const el = await screen.findByRole("dialog", { name: "supply" });
    fireEvent.click(within(el).getByRole("button", { name: "编辑" }));
    fireEvent.change(within(el).getByLabelText("描述"), { target: { value: "新描述" } });
    fireEvent.click(within(el).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalled());
    const payload = vi.mocked(modelingApi.saveElement).mock.calls[0][1].draft as NativeDraft;
    expect(payload.schema_version).toBe("3");
    expect(payload.link_types[0].description).toBe("新描述");
    expect(payload.link_types[0].roles).toEqual(binary.roles);
    expect(payload.link_types[0]).not.toHaveProperty("source_type_id");
    expect(payload.link_types[1]).toEqual(native.link_types[1]);
  });
});

describe("P2 platform concept context editor", () => {
  it.each(["object_type", "value_type"] as const)("edits %s synonyms with a non-standard notice and native fields unchanged", async kind => {
    const native = structuredClone(nativeJson) as NativeDraft;
    const concept = (kind === "object_type" ? native.object_types : native.value_types)[0];
    native.extension_v4.concept_context = { [concept.id]: { synonyms: ["原同义词"], instructions: "原上下文" } };
    vi.mocked(workspaceRequest).mockResolvedValue({ model: native });
    vi.mocked(modelingApi.snapshot).mockResolvedValue(native);
    vi.mocked(modelingApi.saveElement).mockResolvedValue({ draft: native, version: { version_id: "v2" } as never, session: null });
    show(`/workspaces/w/objects?inspect=${kind}:${concept.id}&inspectTab=basic`);
    const el = await screen.findByRole("dialog", { name: concept.name });
    expect(within(el).getByRole("img", { name: "平台扩展，导出到其他工具会被忽略" })).toBeInTheDocument();
    expect(within(el).getByText("原同义词")).toBeInTheDocument();
    fireEvent.click(within(el).getByRole("button", { name: "编辑" }));
    fireEvent.change(within(el).getByLabelText("同义词"), { target: { value: "别名甲\n别名乙" } });
    fireEvent.change(within(el).getByLabelText("上下文说明"), { target: { value: "业务口径" } });
    fireEvent.click(within(el).getByRole("button", { name: "保存" }));
    await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalled());
    const request = vi.mocked(modelingApi.saveElement).mock.calls[0][1];
    expect(request.target_kind).toBe(kind);
    const saved = request.draft as NativeDraft;
    expect(saved.extension_v4.concept_context?.[concept.id]).toEqual({ synonyms: ["别名甲", "别名乙"], instructions: "业务口径" });
    expect(saved.object_types).toEqual(native.object_types);
    expect(saved.value_types).toEqual(native.value_types);
    expect(saved.ai_context).toEqual(native.ai_context);
  });
});
