import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { modelingApi } from "../api/client";
import type { Draft, Workspace } from "../api/types";
import { emptyDraft } from "../lib/coreModel";
import { renderWithProviders } from "../test/renderWithProviders";
import { ValueTypeCatalog } from "./ValueTypeCatalog";

vi.mock("../api/client", () => ({ modelingApi: { get: vi.fn(), previewElementSave: vi.fn(), saveElement: vi.fn() } }));
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

it("creates a value type with its constraint through preview and save", async () => {
  vi.mocked(modelingApi.previewElementSave).mockResolvedValue({ current_version_id: "v1", session_revision: null, affected_items: [] });
  vi.mocked(modelingApi.saveElement).mockImplementation(async (_id, payload) => ({ version: {} as never, draft: payload.draft, session: null }));
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
  const [, payload] = vi.mocked(modelingApi.saveElement).mock.calls[0];
  expect(payload.target_kind).toBe("value_type");
  expect(payload.draft.value_types).toEqual([expect.objectContaining({ name: "money", display_name: "金额", value_kind: "string" })]);
  expect(payload.draft.rules).toEqual([expect.objectContaining({ owner_kind: "value_type", rule_kind: "constraint", expression: "money >= 0" })]);
  expect(onSaved).toHaveBeenCalled();
});

it("rejects a non-ASCII identifier before saving", async () => {
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
