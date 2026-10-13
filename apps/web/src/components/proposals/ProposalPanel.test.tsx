import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { StrictMode } from "react";
import type { ModelingSession, ProposalBatchDetail, ProposalItem } from "../../api/types";
import type { ProposalsState } from "../../hooks/useProposals";
import { emptyDraft } from "../../lib/draftView";
import { ModelResults } from "../ModelResults";
import { ProposalPanel } from "./ProposalPanel";

vi.mock("../OntologyGraph", () => ({ OntologyGraph: () => <div /> }));
afterEach(cleanup);

function item(overrides: Partial<ProposalItem> = {}): ProposalItem {
  const id = overrides.id ?? "i";
  return {
    id, batch_id: "b", ordinal: 0, client_ref: null, operation: "create", target_kind: "object_type",
    target_id: `target-${id}`, display_name: "对象", before: null,
    after: { name: "对象", technical_name: id }, field_changes: [], evidence: [], reason: "",
    depends_on: [], dependency_group: [id], status: "pending", stored_status: "pending", ...overrides,
  };
}

const evidence = {
  kind: "material" as const, id: "e", material_id: "m", material_sha256: "a".repeat(64),
  material_name: "制度.md", material_archived: false,
  locator: { line_start: 42, line_end: 47 }, quote: "供应商名称以材料为准",
};
const items = [
  item({ id: "po", display_name: "采购订单", after: { name: "采购订单", technical_name: "purchase_order" } }),
  item({ id: "no", target_kind: "property", display_name: "订单号", owner_label: "采购订单",
    after: { name: "订单号", technical_name: "order_no", owner_type_id: "target-po" },
    depends_on: ["po"], dependency_group: ["no", "po"] }),
  item({ id: "upd", operation: "update", display_name: "供应商", before: { name: "旧供应商名称", technical_name: "supplier" },
    after: { name: "供应商", technical_name: "supplier" },
    field_changes: [{ path: "name", before: "旧供应商名称", after: "供应商" },
      { path: "evidence", before: [], after: [evidence] }], evidence: [evidence] }),
  item({ id: "old", operation: "update", display_name: "物料", status: "stale", status_reason: "目标在提案生成后已被修改" }),
  item({ id: "act", target_kind: "action", display_name: "审批供应商" }),
  item({ id: "gone", display_name: "旧提案", status: "rejected", stored_status: "rejected" }),
];

function batch(extra: Partial<ProposalBatchDetail> = {}): ProposalBatchDetail {
  return { id: "b", status: "available", created_at: "2026-09-30T10:00:00Z", source_session_revision: 7,
    base_version_id: "v", counts: { pending: 4, accepted: 0, rejected: 1, stale: 1, conflict: 0, superseded: 0 }, items, ...extra };
}
function state(extra: Partial<ProposalsState> = {}): ProposalsState {
  return { batches: [batch()], selected: "b", select: vi.fn(), detail: batch(), error: "", itemErrors: {},
    busy: false, reload: vi.fn(), decide: vi.fn().mockResolvedValue(true), ...extra };
}
function session(extra: Partial<ModelingSession> = {}): ModelingSession {
  return { id: "s", title: "t", workspace_id: "w", base_version_id: "v", revision: 7, draft: emptyDraft("w"),
    graph: { workspace_id: "w", version_id: "v", version_sha256: "", nodes: [], edges: [] }, candidates: [],
    material_ids: [], task_status: "idle", task_detail: "", updated_at: "", pending_proposal_count: 4,
    latest_batch_id: "b", base_diff: [], ...extra };
}
const panel = (proposals = state(), s = session(), onRemodel = vi.fn()) =>
  render(<MemoryRouter><ProposalPanel session={s} proposals={proposals} running={false} onRemodel={onRemodel} /></MemoryRouter>);
const row = (name: string) => screen.getByRole("article", { name: new RegExp(name) });
const tab = (name: string) => screen.getByRole("tab", { name: new RegExp(`^${name} `) });
const accepted = (id: string, extra: Partial<ProposalItem> = {}) =>
  item({ id, status: "accepted", stored_status: "accepted", accepted_revision: 8, ...extra });

async function decided(proposals: ProposalsState, expected: { proposal_id: string; decision: string }[]) {
  expect(proposals.decide).toHaveBeenCalledWith(expected);
  await waitFor(() => expect(screen.getAllByRole("status").some((element) => /已接受|已拒绝|已恢复/.test(element.textContent ?? ""))).toBe(true));
}

describe("compact proposal review", () => {
  it("renders two-line old → new rows with technical identity and no revision jargon", () => {
    panel();
    const supplier = row("supplier");
    expect(within(supplier).getByText("旧供应商名称")).toHaveClass("old-value");
    expect(within(supplier).getByText("→")).toBeInTheDocument();
    expect(within(supplier).getByText("供应商")).toHaveClass("new-value");
    expect(within(supplier).getByText("供应商").tagName).toBe("STRONG");
    expect(screen.getByText("purchase_order.order_no")).toBeInTheDocument();
    // Counts live on the status tabs only; no duplicate summary line.
    expect(screen.queryByText(/条待审 ·/)).not.toBeInTheDocument();
    expect(screen.queryByText(/基于草稿|批次 #|→ r\d/)).not.toBeInTheDocument();
    expect(within(supplier).queryByText("供应商名称以材料为准")).not.toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(4);
  });

  it("shows create/delete values and hides evidence-only changes in the compact summary", () => {
    panel(state({ detail: batch({ items: [
      item({ id: "new", after: { name: "新增对象", technical_name: "new" } }),
      item({ id: "delete", operation: "delete", before: { name: "被删除对象", technical_name: "delete" }, after: null }),
      item({ id: "evidence", operation: "update", field_changes: [{ path: "evidence", before: [], after: [evidence] }] }),
    ] }) }));
    expect(within(row("new")).getByText("（空）")).toHaveClass("old-value");
    expect(within(row("delete")).getByText("（空）")).toHaveClass("new-value");
    expect(within(row("evidence")).getByText("无内容改动")).toBeInTheDocument();
    expect(within(row("evidence")).getByText("补充证据")).toBeInTheDocument();
  });

  it("resolves an owner technical name from the draft when there is no owner proposal", () => {
    const draft = emptyDraft("w");
    draft.object_types.push({ id: "target-po", name: "采购订单", technical_name: "purchase_order", description: "", tags: [], extends: [], evidence: [] });
    panel(state({ detail: batch({ items: [items[1]] }) }), session({ draft }));
    expect(screen.getByText("purchase_order.order_no")).toBeInTheDocument();
  });

  it("opens evidence in a popover without opening detail and restores icon focus on close/Escape", () => {
    panel();
    const button = within(row("supplier")).getByRole("button", { name: /查看.*证据/ });
    fireEvent.click(button);
    const popover = screen.getByRole("dialog", { name: "材料证据" });
    expect(within(popover).getByText("制度.md")).toBeInTheDocument();
    expect(within(popover).getByText("· 第 42–47 行")).toBeInTheDocument();
    expect(within(popover).getByText(evidence.quote)).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "提案详情" })).not.toBeInTheDocument();
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(within(popover).getByRole("button", { name: "关闭证据" })).toHaveFocus();
    fireEvent.keyDown(popover, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
    fireEvent.click(button);
    fireEvent.click(screen.getByRole("button", { name: "关闭证据" }));
    expect(button).toHaveFocus();
  });

  it("dismisses evidence on outside click, list scroll and resize", () => {
    panel();
    const button = within(row("supplier")).getByRole("button", { name: /查看.*证据/ });
    fireEvent.click(button); fireEvent.click(document.body);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(button); fireEvent.scroll(screen.getByRole("tabpanel"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(button); fireEvent(window, new Event("resize"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("handles empty evidence and manual confirmations", () => {
    const manual = item({ evidence: [{ kind: "manual", id: "manual", note: "已核对", created_by: "admin", created_at: "" }] });
    panel(state({ detail: batch({ items: [manual] }) }));
    fireEvent.click(screen.getByRole("button", { name: /查看.*证据/ }));
    expect(screen.getByText("人工确认")).toBeInTheDocument();
    expect(screen.getByText("已核对")).toBeInTheDocument();
    cleanup(); panel(state({ detail: batch({ items: [item()] }) }));
    fireEvent.click(screen.getByRole("button", { name: /查看.*证据/ }));
    expect(screen.getByText("未附证据")).toBeInTheDocument();
  });

  it("opens a centered detail modal on row click or Enter and returns focus to the row", () => {
    panel();
    const supplier = row("supplier");
    supplier.focus(); fireEvent.keyDown(supplier, { key: "Enter" });
    const modal = screen.getByRole("dialog", { name: "提案详情" });
    expect(modal).toHaveClass("detail-dialog");
    expect(within(modal).getByRole("columnheader", { name: "修改前" })).toBeInTheDocument();
    expect(within(modal).getByText(evidence.quote)).toBeInTheDocument();
    expect(within(modal).queryByRole("rowheader", { name: "证据" })).not.toBeInTheDocument();
    expect(within(modal).queryByText("提案理由")).not.toBeInTheDocument();
    expect(within(modal).getByText("本提案无依赖，可独立审核。")).toBeInTheDocument();
    fireEvent.click(within(modal).getByRole("button", { name: "关闭提案详情" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(supplier).toHaveFocus();
    fireEvent.click(supplier);
    fireEvent(screen.getByRole("dialog"), new Event("cancel", { cancelable: true }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(supplier).toHaveFocus();
  });

  it("only shows a nonblank reason and lets dependency links navigate within the modal", () => {
    panel(state({ detail: batch({ items: [items[0], { ...items[1], reason: "需要订单标识" }] }) }));
    const property = row("purchase_order.order_no");
    fireEvent.click(property);
    const modal = screen.getByRole("dialog", { name: "提案详情" });
    expect(within(modal).getByText("需要订单标识")).toBeInTheDocument();
    fireEvent.click(within(modal).getByRole("button", { name: "实体 · 采购订单" }));
    expect(within(modal).getByRole("heading", { name: "新增实体 · 采购订单" })).toBeInTheDocument();
    fireEvent.click(within(modal).getByRole("button", { name: "关闭提案详情" }));
    expect(property).toHaveFocus();
  });

  it("keeps the detail dialog open through StrictMode effect replay", () => {
    render(<StrictMode><ProposalPanel session={session()} proposals={state()} running={false} onRemodel={vi.fn()} /></StrictMode>);
    fireEvent.click(row("supplier"));
    expect(screen.getByRole("dialog", { name: "提案详情" })).toHaveAttribute("open");
  });

  it("uses one bulk toolbar and switches its controls with selection", () => {
    panel();
    const toolbar = screen.getByRole("group", { name: "批量审核操作" });
    expect(screen.getAllByRole("group", { name: "批量审核操作" })).toHaveLength(1);
    expect(within(toolbar).getByRole("button", { name: "全部接受（4）" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "接受选中" })).not.toBeInTheDocument();
    fireEvent.click(within(row("supplier")).getByRole("checkbox"));
    expect(screen.getByText("已选 1 项")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "选择当前筛选的全部提案" })).toBePartiallyChecked();
    expect(screen.queryByRole("button", { name: /全部接受/ })).not.toBeInTheDocument();
    expect(within(toolbar).getByRole("button", { name: "接受选中" })).toBeEnabled();
    expect(within(toolbar).getByRole("button", { name: "拒绝选中" })).toBeEnabled();
    fireEvent.click(within(toolbar).getByRole("button", { name: "取消选择" }));
    expect(screen.getByRole("checkbox", { name: "选择当前筛选的全部提案" })).toHaveFocus();
    expect(within(toolbar).getByRole("button", { name: "全部接受（4）" })).toBeInTheDocument();
  });

  it("selects only current results and preserves selections across filters", () => {
    panel();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "supplier" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "选择当前筛选的全部提案" }));
    expect(screen.getByText("已选 1 项")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "清空搜索" }));
    expect(within(row("supplier")).getByRole("checkbox")).toBeChecked();
    expect(within(row("purchase_order，")).getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "选择当前筛选的全部提案" })).toBePartiallyChecked();
  });

  it("accepts selected dependency groups and clears selection only after success", async () => {
    const proposals = state(); panel(proposals);
    fireEvent.click(within(row("purchase_order.order_no")).getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "接受选中" }));
    await decided(proposals, [{ proposal_id: "no", decision: "accept" }, { proposal_id: "po", decision: "accept" }]);
    await waitFor(() => expect(screen.queryByText("已选 1 项")).not.toBeInTheDocument());
  });

  it("preserves selection and displays backend errors when a decision fails", async () => {
    const proposals = state({ decide: vi.fn().mockResolvedValue(false), error: "提交失败", itemErrors: { upd: "目标已修改" } });
    panel(proposals);
    fireEvent.click(within(row("supplier")).getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "接受选中" }));
    await waitFor(() => expect(proposals.decide).toHaveBeenCalledTimes(1));
    expect(screen.getByText("已选 1 项")).toBeInTheDocument();
    expect(within(row("supplier")).getByRole("alert")).toHaveTextContent("目标已修改");
    expect(screen.getByText("提交失败")).toBeInTheDocument();
  });

  it("reject-all exists only in More and requires explicit confirmation", async () => {
    const proposals = state(); panel(proposals);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "supplier" } });
    expect(screen.queryByRole("button", { name: "全部拒绝" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /更多/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "全部拒绝" }));
    const confirmation = screen.getByRole("dialog", { name: "拒绝全部 5 条待审提案？" });
    expect(proposals.decide).not.toHaveBeenCalled();
    expect(within(confirmation).getByRole("button", { name: "取消" })).toHaveFocus();
    fireEvent.click(within(confirmation).getByRole("button", { name: "取消" }));
    expect(proposals.decide).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /更多/ })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: /更多/ }));
    fireEvent.click(screen.getByRole("menuitem", { name: "全部拒绝" }));
    fireEvent.click(screen.getByRole("button", { name: "确认拒绝" }));
    await decided(proposals, ["po", "no", "upd", "old", "act"].map((proposal_id) => ({ proposal_id, decision: "reject" })));
  });

  it("accept-all ignores search and excludes blocked, rejected and missing dependencies", async () => {
    const proposals = state({ detail: batch({ items: [...items,
      item({ id: "blocked-dep", depends_on: ["old"] }), item({ id: "missing", dependency_group: ["missing", "absent"] }),
    ] }) }); panel(proposals);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "supplier" } });
    fireEvent.click(screen.getByRole("button", { name: "全部接受（4）" }));
    await decided(proposals, ["po", "no", "upd", "act"].map((proposal_id) => ({ proposal_id, decision: "accept" })));
  });

  it("accepts a row's whole dependency group", async () => {
    const proposals = state(); panel(proposals);
    fireEvent.click(within(row("purchase_order.order_no")).getByRole("button", { name: "接受 订单号" }));
    await decided(proposals, [{ proposal_id: "no", decision: "accept" }, { proposal_id: "po", decision: "accept" }]);
  });

  it("undoes an accept toast through reject and restore API decisions", async () => {
    const proposals = state(); panel(proposals);
    fireEvent.click(within(row("purchase_order.order_no")).getByRole("button", { name: "接受 订单号" }));
    await decided(proposals, [{ proposal_id: "no", decision: "accept" }, { proposal_id: "po", decision: "accept" }]);
    fireEvent.click(screen.getByRole("button", { name: "撤销" }));
    await waitFor(() => expect(proposals.decide).toHaveBeenCalledTimes(3));
    expect(proposals.decide).toHaveBeenNthCalledWith(2, ["no", "po"].map((proposal_id) => ({ proposal_id, decision: "reject" })));
    expect(proposals.decide).toHaveBeenNthCalledWith(3, ["no", "po"].map((proposal_id) => ({ proposal_id, decision: "restore" })));
    await waitFor(() => expect(screen.getByText("已撤销上次操作")).toBeInTheDocument());
  });

  it("undoes rejection of accepted dependents through restore and accept, retaining the group", async () => {
    const proposals = state({ detail: batch({ items: [accepted("root"), accepted("child", { depends_on: ["root"] })] }) });
    panel(proposals); fireEvent.click(tab("已接受"));
    fireEvent.click(within(row("root")).getByRole("button", { name: /拒绝并撤销/ }));
    await decided(proposals, ["root", "child"].map((proposal_id) => ({ proposal_id, decision: "reject" })));
    fireEvent.click(screen.getByRole("button", { name: "撤销" }));
    await waitFor(() => expect(proposals.decide).toHaveBeenCalledTimes(3));
    expect(proposals.decide).toHaveBeenNthCalledWith(2, ["root", "child"].map((proposal_id) => ({ proposal_id, decision: "restore" })));
    expect(proposals.decide).toHaveBeenNthCalledWith(3, ["root", "child"].map((proposal_id) => ({ proposal_id, decision: "accept" })));
  });

  it("retries only the remaining phase of a partially refused undo", async () => {
    const decide = vi.fn().mockResolvedValueOnce(true).mockResolvedValueOnce(true).mockResolvedValueOnce(false).mockResolvedValue(true);
    const proposals = state({ decide }); panel(proposals);
    fireEvent.click(within(row("supplier")).getByRole("button", { name: "接受 供应商" }));
    await decided(proposals, [{ proposal_id: "upd", decision: "accept" }]);
    fireEvent.click(screen.getByRole("button", { name: "撤销" }));
    await waitFor(() => expect(screen.getByText("撤销未完成，请重试")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "撤销" }));
    await waitFor(() => expect(decide).toHaveBeenCalledTimes(4));
    expect(decide).toHaveBeenNthCalledWith(4, [{ proposal_id: "upd", decision: "restore" }]);
  });

  it("offers undo on accepted rows and modal footers without revision labels", async () => {
    const proposals = state({ detail: batch({ items: [accepted("reviewed", { display_name: "已审实体" })] }) }); panel(proposals);
    fireEvent.click(tab("已接受"));
    const reviewed = row("reviewed");
    expect(within(reviewed).getByText("✓ 已接受")).toBeInTheDocument();
    expect(within(reviewed).queryByRole("button", { name: /^接受/ })).not.toBeInTheDocument();
    fireEvent.click(within(reviewed).getByRole("button", { name: "拒绝并撤销 已审实体" }));
    await decided(proposals, [{ proposal_id: "reviewed", decision: "reject" }]);
    fireEvent.click(reviewed);
    fireEvent.click(within(screen.getByRole("dialog", { name: "提案详情" })).getByRole("button", { name: "拒绝并撤销 已审实体" }));
    await waitFor(() => expect(proposals.decide).toHaveBeenCalledTimes(2));
    expect(screen.queryByText(/基于草稿|→ r8/)).not.toBeInTheDocument();
  });

  it("rejects accepted dependents transitively but keeps unrelated and pending proposals", async () => {
    const proposals = state({ detail: batch({ items: [
      accepted("grandchild", { depends_on: ["child"] }), accepted("child", { depends_on: ["root"] }),
      accepted("root"), accepted("other"), item({ id: "pending", depends_on: ["root"] }),
    ] }) }); panel(proposals); fireEvent.click(tab("已接受"));
    fireEvent.click(within(row("root")).getByRole("button", { name: /拒绝并撤销/ }));
    await decided(proposals, ["root", "child", "grandchild"].map((proposal_id) => ({ proposal_id, decision: "reject" })));
  });

  it("applies the same accepted dependent grouping to reject-selected", async () => {
    const proposals = state({ detail: batch({ items: [accepted("root"), accepted("child", { depends_on: ["root"] }), accepted("other")] }) });
    panel(proposals); fireEvent.click(tab("已接受"));
    fireEvent.click(within(row("root")).getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "拒绝选中" }));
    await decided(proposals, ["root", "child"].map((proposal_id) => ({ proposal_id, decision: "reject" })));
  });

  it("keeps backend undo refusals visible on accepted rows and in their detail modal", () => {
    const proposals = state({ detail: batch({ items: [accepted("reviewed")] }),
      itemErrors: { reviewed: "该元素在接受后又被修改，不能直接撤销" } });
    panel(proposals); fireEvent.click(tab("已接受"));
    const reviewed = row("reviewed");
    expect(within(reviewed).getByRole("alert")).toHaveTextContent("不能直接撤销");
    fireEvent.click(reviewed);
    expect(within(screen.getByRole("dialog", { name: "提案详情" })).getByRole("alert")).toHaveTextContent("不能直接撤销");
  });

  it("moves a newly accepted row to its status tab after backend refresh", async () => {
    const pending = item({ id: "changing" });
    const proposals = state({ detail: batch({ items: [pending] }) });
    const view = panel(proposals);
    fireEvent.click(within(row("changing")).getByRole("button", { name: /^接受/ }));
    await decided(proposals, [{ proposal_id: "changing", decision: "accept" }]);
    view.rerender(<MemoryRouter><ProposalPanel session={session({ revision: 8 })}
      proposals={state({ detail: batch({ items: [{ ...pending, status: "accepted", stored_status: "accepted" }] }) })}
      running={false} onRemodel={vi.fn()} /></MemoryRouter>);
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
    fireEvent.click(tab("已接受"));
    expect(within(row("changing")).getByRole("button", { name: /拒绝并撤销/ })).toBeEnabled();
  });

  it("restores rejected rows and disables decisions while submitting", async () => {
    const proposals = state(); panel(proposals); fireEvent.click(tab("已拒绝"));
    const rejected = row("gone");
    expect(within(rejected).queryByRole("button", { name: /拒绝/ })).not.toBeInTheDocument();
    fireEvent.click(within(rejected).getByRole("button", { name: "恢复 旧提案" }));
    await decided(proposals, [{ proposal_id: "gone", decision: "restore" }]);
    cleanup(); panel(state({ busy: true, detail: batch({ items: [accepted("reviewed")] }) }));
    fireEvent.click(tab("已接受"));
    expect(within(row("reviewed")).getByRole("button", { name: /拒绝并撤销/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /全部接受/ })).toBeDisabled();
  });

  it("filters by status, technical/owner/name search and multi-select kinds with facet counts", () => {
    panel();
    expect(tab("待审")).toHaveTextContent("4");
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "purchase_order order_no" } });
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.getByText("显示 1 / 6 条")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "清空搜索" }));
    fireEvent.click(screen.getByRole("button", { name: "类型： 全部" }));
    const types = screen.getByRole("dialog", { name: "元素类型" });
    fireEvent.click(within(types).getByRole("checkbox", { name: /^全部/ }));
    fireEvent.click(within(types).getByRole("checkbox", { name: /^属性/ }));
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(tab("待审")).toHaveTextContent("1");
    expect(screen.getByRole("button", { name: "类型： 属性" })).toBeInTheDocument();
    fireEvent.keyDown(types, { key: "Escape" });
    fireEvent.click(screen.getByRole("button", { name: "清除筛选" }));
    expect(screen.getAllByRole("article")).toHaveLength(4);
    expect(screen.getByRole("searchbox")).toHaveFocus();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "旧供应商名称" } });
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });

  it("shows an empty result with clear filters and resets to pending", () => {
    panel(); fireEvent.change(screen.getByRole("searchbox"), { target: { value: "不存在" } });
    expect(screen.getByText("没有符合条件的提案")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "清除筛选" })[0]);
    expect(tab("待审")).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("searchbox")).toHaveValue("");
  });

  it("uses arrow/Home/End navigation for status tabs, kinds and More", () => {
    panel(); const pending = tab("待审"); pending.focus();
    fireEvent.keyDown(pending, { key: "ArrowRight" });
    expect(tab("已接受")).toHaveFocus();
    expect(tab("已接受")).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tab("已接受"), { key: "End" });
    expect(tab("冲突")).toHaveFocus();
    fireEvent.keyDown(tab("冲突"), { key: "Home" });
    expect(pending).toHaveFocus();
    const types = screen.getByRole("button", { name: "类型： 全部" });
    fireEvent.keyDown(types, { key: "ArrowDown" });
    const options = within(screen.getByRole("dialog", { name: "元素类型" })).getAllByRole("checkbox");
    expect(options[0]).toHaveFocus();
    fireEvent.keyDown(options[0], { key: "ArrowDown" }); expect(options[1]).toHaveFocus();
    fireEvent.keyDown(options[1], { key: "End" }); expect(options.at(-1)).toHaveFocus();
    fireEvent.keyDown(options.at(-1)!, { key: "Escape" }); expect(types).toHaveFocus();
    const more = screen.getByRole("button", { name: /更多/ });
    fireEvent.keyDown(more, { key: "ArrowDown" });
    const rejectAll = screen.getByRole("menuitem", { name: "全部拒绝" });
    expect(rejectAll).toHaveFocus();
    fireEvent.keyDown(rejectAll, { key: "Escape" }); expect(more).toHaveFocus();
  });

  it("warns only when a moved draft left proposals stale or conflicting", () => {
    const clean = state({ detail: batch({ items: [items[0]] }) });
    panel(clean); expect(screen.queryByText("草稿已更新，部分提案需要重新确认")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /^冲突/ })).not.toBeInTheDocument();
    // Every decision bumps the revision; that alone is not a reason to warn.
    cleanup(); panel(clean, session({ revision: 9 }));
    expect(screen.queryByText("草稿已更新，部分提案需要重新确认")).not.toBeInTheDocument();
    cleanup(); panel(undefined, session({ revision: 9 }));
    expect(screen.getByText("草稿已更新，部分提案需要重新确认")).toBeInTheDocument();
    cleanup(); panel();
    fireEvent.click(tab("冲突"));
    const stale = row("old");
    expect(stale).toHaveClass("is-blocked");
    expect(within(stale).getByRole("button", { name: "接受 物料" })).toBeDisabled();
    expect(within(stale).getByRole("button", { name: "拒绝 物料" })).toBeEnabled();
  });

  it("retains failed-batch error and re-modelling, and an honest initial empty state", () => {
    const failed = batch({ status: "failed", items: [], error: { code: "X", message: "格式不对" } });
    const onRemodel = vi.fn(); panel(state({ detail: failed, batches: [failed] }), session(), onRemodel);
    expect(screen.getByRole("alert")).toHaveTextContent("格式不对");
    fireEvent.click(screen.getByRole("button", { name: "重新建模" }));
    expect(onRemodel).toHaveBeenCalled();
    cleanup(); panel(state({ batches: [], detail: null }));
    expect(screen.getByText(/提案会出现在这里/)).toBeInTheDocument();
  });
});

describe("result tabs", () => {
  it("opens on proposals when some are pending and keeps the outer tabs intact", () => {
    render(<MemoryRouter><ModelResults session={session()} proposals={state()} /></MemoryRouter>);
    const outer = screen.getByRole("tablist", { name: "构建结果" });
    expect(within(outer).getAllByRole("tab")).toHaveLength(3);
    expect(within(outer).getByRole("tab", { name: /提案/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tablist", { name: "审核状态" })).toBeInTheDocument();
  });

  it("keeps accepted proposals accessible and undoable after returning from the draft", async () => {
    const proposals = state({ detail: batch({ items: [accepted("reviewed")] }) });
    render(<MemoryRouter><ModelResults session={session({ pending_proposal_count: 0 })} proposals={proposals} /></MemoryRouter>);
    const outer = screen.getByRole("tablist", { name: "构建结果" });
    expect(within(outer).getByRole("tab", { name: /本体草稿/ })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(within(outer).getByRole("tab", { name: /提案/ })); fireEvent.click(tab("已接受"));
    expect(row("reviewed")).toBeVisible();
    fireEvent.click(within(outer).getByRole("tab", { name: /本体草稿/ }));
    fireEvent.click(within(outer).getByRole("tab", { name: /提案/ })); fireEvent.click(tab("已接受"));
    fireEvent.click(within(row("reviewed")).getByRole("button", { name: /拒绝并撤销/ }));
    await decided(proposals, [{ proposal_id: "reviewed", decision: "reject" }]);
  });
});
