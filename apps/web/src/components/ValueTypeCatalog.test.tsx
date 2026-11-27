import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { ApiError, modelingApi } from "../api/client";
import type { Draft, SessionElementSaveImpact, Workspace } from "../api/types";
import { emptyDraft } from "../lib/coreModel";
import { modelingSession } from "../test/apiRecords";
import { renderWithProviders } from "../test/renderWithProviders";
import { ValueTypeCatalog } from "./ValueTypeCatalog";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return {
    ...original,
    modelingApi: { get: vi.fn(), personal: vi.fn(), previewElementSave: vi.fn(), saveElement: vi.fn() },
  };
});
vi.mock("../hooks/useElementDetail", () => ({ useElementDetail: () => ({ href: () => "/detail", open: vi.fn() }) }));

beforeEach(() => vi.resetAllMocks());
afterEach(cleanup);

const workspace = { id: "w", role: "admin", version_id: "v1" } as Workspace;

function draftWithLevel(): Draft {
  return {
    ...emptyDraft("w"),
    object_types: [{ id: "o1", name: "member", display_name: "会员", description: "", synonyms: [], tags: [], extends: null, title_property_id: null, derived_by: [], evidence: [] }],
    value_types: [{ id: "vt1", name: "member_level", display_name: "会员等级", value_kind: "string", description: "会员等级取值", evidence: [] }],
    properties: [{ id: "p1", owner_type_id: "o1", name: "level", display_name: "等级", description: "", value_kind: "string", value_type_id: "vt1", required: false, identifier: false, unique: false, synonyms: [], evidence: [] }],
    rules: [{ id: "r1", name: "level_values", display_name: null, description: "", owner_kind: "value_type", owner_id: "vt1", rule_kind: "constraint", expression: "member_level IN ('普通', '金卡')", evidence: [] }],
  };
}

function renderCatalog(draft: Draft, createRequest = 0, onSaved = vi.fn()) {
  const view = renderWithProviders(
    <MemoryRouter>
      <ValueTypeCatalog workspace={workspace} draft={draft} sessionId={null} query="" createRequest={createRequest} onSaved={onSaved} />
    </MemoryRouter>,
  );
  return { ...view, onSaved };
}

it("lists each value type with base kind, constraints and derived usage", async () => {
  renderCatalog(draftWithLevel());
  const row = screen.getByRole("button", { name: "会员等级" }).closest("tr")!;
  expect(within(row).getByText("member_level")).toBeInTheDocument();
  expect(within(row).getByText("文本")).toBeInTheDocument();
  expect(within(row).getByText("member_level IN ('普通', '金卡')")).toBeInTheDocument();
  fireEvent.click(within(row).getByRole("button", { name: "查看使用 member_level 的属性" }));
  expect(await screen.findByRole("link", { name: "会员 · 等级" })).toBeInTheDocument();
});

it("creates a value type with its constraint into the personal session through preview and save", async () => {
  const personal = modelingSession({ id: "personal-1", workspace_id: "w", revision: 4 }, emptyDraft("w"));
  vi.mocked(modelingApi.personal).mockResolvedValue(personal);
  vi.mocked(modelingApi.previewElementSave).mockResolvedValue({ session_revision: 4, affected_items: [] });
  vi.mocked(modelingApi.saveElement).mockImplementation(async (_w, sid, payload) =>
    modelingSession({ id: sid, workspace_id: "w", revision: 5, unpublished_change_count: 1 }, payload.draft),
  );
  const { rerender, onSaved } = renderCatalog(emptyDraft("w"));
  rerender(
    <MemoryRouter>
      <ValueTypeCatalog workspace={workspace} draft={emptyDraft("w")} sessionId={null} query="" createRequest={1} onSaved={onSaved} />
    </MemoryRouter>,
  );
  const dialog = await screen.findByRole("dialog");
  fireEvent.change(within(dialog).getByRole("textbox", { name: "值类型名称" }), { target: { value: "金额" } });
  fireEvent.change(within(dialog).getByRole("textbox", { name: "值类型英文标识" }), { target: { value: "money" } });
  fireEvent.change(within(dialog).getByRole("textbox", { name: "约束 1" }), { target: { value: "money >= 0" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
  await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalled());
  expect(modelingApi.personal).toHaveBeenCalledWith("w");
  expect(modelingApi.previewElementSave).toHaveBeenCalledWith("w", "personal-1", expect.objectContaining({ expected_session_revision: 4 }));
  const [, sid, payload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
  expect(sid).toBe("personal-1");
  expect(payload.expected_session_revision).toBe(4);
  expect(payload.idempotency_key).toEqual(expect.any(String));
  expect(payload.idempotency_key!.length).toBeGreaterThanOrEqual(8);
  expect(payload.target_kind).toBe("value_type");
  expect(payload.draft.value_types).toEqual([expect.objectContaining({ name: "money", display_name: "金额", value_kind: "string" })]);
  expect(payload.draft.rules).toEqual([expect.objectContaining({ owner_kind: "value_type", rule_kind: "constraint", expression: "money >= 0" })]);
  expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ id: "personal-1", revision: 5, unpublished_change_count: 1 }));
});

it("rejects a non-ASCII identifier before saving", async () => {
  vi.mocked(modelingApi.personal).mockResolvedValue(
    modelingSession({ id: "personal-1", workspace_id: "w", revision: 4 }, emptyDraft("w")),
  );
  const { rerender, onSaved } = renderCatalog(emptyDraft("w"));
  rerender(
    <MemoryRouter>
      <ValueTypeCatalog workspace={workspace} draft={emptyDraft("w")} sessionId={null} query="" createRequest={1} onSaved={onSaved} />
    </MemoryRouter>,
  );
  const dialog = await screen.findByRole("dialog");
  fireEvent.change(within(dialog).getByRole("textbox", { name: "值类型英文标识" }), { target: { value: "金额" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
  expect(await within(dialog).findByText(/英文标识只能使用字母/)).toBeInTheDocument();
  expect(modelingApi.previewElementSave).not.toHaveBeenCalled();
});

it("loads the target session baseline when editing so newer draft constraints and revision are preserved", async () => {
  const publishedDraft = draftWithLevel();
  const personalDraft = draftWithLevel();
  personalDraft.rules.push({
    id: "r2",
    name: "level_extra",
    display_name: null,
    description: "",
    owner_kind: "value_type",
    owner_id: "vt1",
    rule_kind: "constraint",
    expression: "member_level != '黑名单'",
    evidence: [],
  });
  const personalAtOpen = modelingSession({ id: "personal-1", workspace_id: "w", revision: 7 }, personalDraft);
  const personalLater = modelingSession({ id: "personal-1", workspace_id: "w", revision: 8 }, personalDraft);
  vi.mocked(modelingApi.personal).mockResolvedValueOnce(personalAtOpen).mockResolvedValueOnce(personalLater);
  vi.mocked(modelingApi.previewElementSave).mockResolvedValue({ session_revision: 7, affected_items: [] });
  vi.mocked(modelingApi.saveElement).mockImplementation(async (_w, sid, payload) =>
    modelingSession({ id: sid, workspace_id: "w", revision: 8, unpublished_change_count: 2 }, payload.draft),
  );

  renderCatalog(publishedDraft);
  fireEvent.click(screen.getByRole("button", { name: "会员等级" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByRole("textbox", { name: "约束 2" })).toHaveValue("member_level != '黑名单'");

  fireEvent.change(within(dialog).getByRole("textbox", { name: "值类型描述" }), { target: { value: "更新描述" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));

  await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledTimes(1));
  expect(modelingApi.personal).toHaveBeenCalledTimes(1);
  const [, , savePayload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
  expect(savePayload.expected_session_revision).toBe(7);
  expect(savePayload.draft.rules.map((r) => r.expression)).toEqual([
    "member_level IN ('普通', '金卡')",
    "member_level != '黑名单'",
  ]);
  expect(savePayload.draft.value_types?.find((v) => v.id === "vt1")?.description).toBe("更新描述");
});

it("resends the exact pending save with affected_items and idempotency_key after a lost response without re-previewing", async () => {
  const personal = modelingSession({ id: "personal-1", workspace_id: "w", revision: 4 }, draftWithLevel());
  vi.mocked(modelingApi.personal).mockResolvedValue(personal);
  vi.mocked(modelingApi.previewElementSave)
    .mockResolvedValueOnce({
      session_revision: 4,
      affected_items: [{
        target_kind: "property",
        target_id: "p1",
        expected_target_hash: "h".repeat(64),
        reason: "属性将同步基础类型",
      }],
    })
    .mockRejectedValueOnce(new ApiError("草稿已更新", 409, "SESSION_REVISION_CHANGED"));
  vi.mocked(modelingApi.saveElement)
    .mockRejectedValueOnce(new Error("网络超时"))
    .mockImplementationOnce(async (_w, sid, payload) =>
      modelingSession({ id: sid, workspace_id: "w", revision: 5, unpublished_change_count: 1 }, payload.draft),
    );

  const { onSaved } = renderCatalog(draftWithLevel());
  fireEvent.click(screen.getByRole("button", { name: "会员等级" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.change(within(dialog).getByRole("textbox", { name: "值类型描述" }), { target: { value: "改写描述" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));

  await within(dialog).findByText("保存会同时影响 1 个元素");
  fireEvent.click(within(dialog).getByRole("button", { name: "确认并保存" }));
  expect(await within(dialog).findByText("网络超时")).toBeInTheDocument();

  fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
  await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledTimes(2));
  expect(modelingApi.personal).toHaveBeenCalledTimes(1);
  expect(modelingApi.previewElementSave).toHaveBeenCalledTimes(1);

  const [, , firstSave] = vi.mocked(modelingApi.saveElement).mock.calls[0];
  const [, , secondSave] = vi.mocked(modelingApi.saveElement).mock.calls[1];
  expect(secondSave).toEqual(firstSave);
  expect(secondSave.affected_items).toEqual([{
    target_kind: "property",
    target_id: "p1",
    expected_target_hash: "h".repeat(64),
  }]);
  expect(onSaved).toHaveBeenCalledTimes(1);
});

it("re-runs preview instead of storing or saving a stale payload when the form changes during a delayed preview", async () => {
  const personal = modelingSession({ id: "personal-1", workspace_id: "w", revision: 4 }, draftWithLevel());
  vi.mocked(modelingApi.personal).mockResolvedValue(personal);
  let resolveFirst!: (value: SessionElementSaveImpact) => void;
  let resolveSecond!: (value: SessionElementSaveImpact) => void;
  vi.mocked(modelingApi.previewElementSave)
    .mockImplementationOnce(() => new Promise((resolve) => { resolveFirst = resolve; }))
    .mockImplementationOnce(() => new Promise((resolve) => { resolveSecond = resolve; }));
  vi.mocked(modelingApi.saveElement).mockImplementation(async (_w, sid, payload) =>
    modelingSession({ id: sid, workspace_id: "w", revision: 5, unpublished_change_count: 1 }, payload.draft),
  );

  renderCatalog(draftWithLevel());
  fireEvent.click(screen.getByRole("button", { name: "会员等级" }));
  const dialog = await screen.findByRole("dialog");
  const description = within(dialog).getByRole("textbox", { name: "值类型描述" });
  fireEvent.change(description, { target: { value: "旧输入" } });
  fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));
  await waitFor(() => expect(modelingApi.previewElementSave).toHaveBeenCalledTimes(1));

  // Edit the form while the first preview is still in flight.
  fireEvent.change(description, { target: { value: "最新输入" } });

  await act(async () => {
    resolveFirst({
      session_revision: 4,
      affected_items: [{
        target_kind: "property",
        target_id: "p1",
        expected_target_hash: "a".repeat(64),
        reason: "旧预览结果",
      }],
    });
  });

  await waitFor(() => expect(modelingApi.previewElementSave).toHaveBeenCalledTimes(2));
  expect(within(dialog).queryByText("旧预览结果")).not.toBeInTheDocument();
  expect(modelingApi.saveElement).not.toHaveBeenCalled();

  await act(async () => {
    resolveSecond({
      session_revision: 4,
      affected_items: [{
        target_kind: "property",
        target_id: "p1",
        expected_target_hash: "b".repeat(64),
        reason: "最新预览结果",
      }],
    });
  });

  await within(dialog).findByText("最新预览结果");
  fireEvent.click(within(dialog).getByRole("button", { name: "确认并保存" }));
  await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledTimes(1));
  const [, , savedPayload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
  expect(savedPayload.draft.value_types?.find((v) => v.id === "vt1")?.description).toBe("最新输入");
  expect(savedPayload.affected_items).toEqual([{
    target_kind: "property",
    target_id: "p1",
    expected_target_hash: "b".repeat(64),
  }]);
});

it("lists action parameter usages and syncs action parameter value_kind when base kind changes", async () => {
  const draft: Draft = {
    ...draftWithLevel(),
    actions: [
      {
        id: "act1",
        name: "upgrade_member",
        display_name: "升级会员",
        description: "",
        synonyms: [],
        tags: [],
        target_type_id: "o1",
        parameters: [
          { name: "target_level", display_name: "目标等级", value_kind: "string", value_type_id: "vt1", required: true, description: "" },
        ],
        effects: [],
        evidence: [],
      },
    ],
  };
  const personal = modelingSession({ id: "personal-1", workspace_id: "w", revision: 4 }, draft);
  vi.mocked(modelingApi.personal).mockResolvedValue(personal);
  vi.mocked(modelingApi.previewElementSave).mockResolvedValue({ session_revision: 4, affected_items: [] });
  vi.mocked(modelingApi.saveElement).mockImplementation(async (_w, sid, payload) =>
    modelingSession({ id: sid, workspace_id: "w", revision: 5, unpublished_change_count: 1 }, payload.draft),
  );

  renderCatalog(draft);
  const row = screen.getByRole("button", { name: "会员等级" }).closest("tr")!;
  fireEvent.click(within(row).getByRole("button", { name: "查看使用 member_level 的属性和动作参数" }));
  expect(await screen.findByRole("link", { name: "动作 升级会员 · 参数 目标等级" })).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "会员等级" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getByText("修改基础类型会同步修改使用它的属性和动作参数")).toBeInTheDocument();

  // Change base kind from string to integer via Ant Design Select.
  fireEvent.mouseDown(within(dialog).getByRole("combobox", { name: "基础类型" }));
  fireEvent.click(await screen.findByTitle("整数"));
  fireEvent.click(within(dialog).getByRole("button", { name: "保存" }));

  await waitFor(() => expect(modelingApi.saveElement).toHaveBeenCalledTimes(1));
  const [, , payload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
  expect(payload.draft.properties.find((p) => p.id === "p1")?.value_kind).toBe("integer");
  expect(payload.draft.actions.find((a) => a.id === "act1")?.parameters[0]?.value_kind).toBe("integer");
});
