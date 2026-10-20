import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CoreElement, ModelingSession, ProposalBatchDetail, ProposalItem } from "../../api/types";
import type { ProposalsState } from "../../hooks/useProposals";
import { emptyDraft } from "../../lib/coreModel";
import { example } from "../../test/drafts";
import { renderWithProviders } from "../../test/renderWithProviders";
import { ProposalPanel } from "./ProposalPanel";

afterEach(cleanup);

const element = (value: Record<string, unknown>) => value as unknown as CoreElement;
function item(overrides: Partial<ProposalItem> = {}): ProposalItem {
  const id = overrides.id ?? "i";
  return {
    id,
    batch_id: "b",
    ordinal: 0,
    client_ref: null,
    operation: "create",
    target_kind: "object_type",
    target_id: `target-${id}`,
    display_name: "对象",
    owner_label: null,
    before: null,
    after: element({ name: "对象", technical_name: id }),
    field_changes: [],
    evidence: [],
    reason: "",
    depends_on: [],
    dependency_group: [id],
    atomic_group_id: null,
    duplicate_candidates: [],
    status: "pending",
    stored_status: "pending",
    status_reason: "",
    accepted_revision: null,
    decided_at: null,
    ...overrides,
  };
}
const evidence = {
  kind: "material" as const,
  id: "e",
  material_id: "m",
  material_sha256: "a".repeat(64),
  material_name: "制度.md",
  material_archived: false,
  locator: { line_start: 42, line_end: 47 },
  quote: "供应商名称以材料为准",
};
const items = [
  item({ id: "po", display_name: "采购订单", after: element({ name: "采购订单", technical_name: "purchase_order" }) }),
  item({
    id: "no",
    target_kind: "property",
    display_name: "订单号",
    owner_label: "采购订单",
    after: element({ name: "订单号", technical_name: "order_no", owner_type_id: "target-po" }),
    depends_on: ["po"],
    dependency_group: ["no", "po"],
  }),
  item({
    id: "upd",
    operation: "update",
    display_name: "供应商",
    before: element({ name: "旧供应商名称", technical_name: "supplier" }),
    after: element({ name: "供应商", technical_name: "supplier" }),
    field_changes: [{ path: "name", before: "旧供应商名称", after: "供应商" }],
    evidence: [evidence],
  }),
  item({ id: "metric", target_kind: "metric", display_name: "订单数", after: element({ name: "订单数", technical_name: "order_count", kind: "simple" }) }),
  item({ id: "old", operation: "update", display_name: "物料", status: "stale", status_reason: "目标在提案生成后已被修改" }),
  item({ id: "gone", display_name: "旧提案", status: "rejected", stored_status: "rejected" }),
];
function batch(list = items): ProposalBatchDetail {
  return {
    id: "b",
    status: "available",
    created_at: "2026-09-30T10:00:00Z",
    source_session_revision: 7,
    base_version_id: "v",
    counts: { pending: 4, accepted: 0, rejected: 1, stale: 1, conflict: 0, superseded: 0 },
    error: null,
    items: list,
  };
}
function state(extra: Partial<ProposalsState> = {}): ProposalsState {
  return {
    batches: [batch()],
    selected: "b",
    select: vi.fn(),
    detail: batch(),
    error: "",
    itemErrors: {},
    busy: false,
    reload: vi.fn(),
    decide: vi.fn().mockResolvedValue(true),
    revise: vi.fn().mockResolvedValue(true),
    ...extra,
  };
}
function session(extra: Partial<ModelingSession> = {}): ModelingSession {
  return {
    id: "s",
    workspace_id: "w",
    revision: 7,
    draft: emptyDraft("w"),
    latest_batch_id: "b",
    pending_proposal_count: 4,
    base_diff: [],
    ...extra,
  } as ModelingSession;
}
const panel = (proposals = state(), s = session()) =>
  renderWithProviders(
    <MemoryRouter>
      <ProposalPanel session={s} proposals={proposals} running={false} onRemodel={vi.fn()} />
    </MemoryRouter>,
  );
const row = (name: string) => screen.getByRole("article", { name: new RegExp(name) });

describe("proposal review", () => {
  it("shows pending rows with technical identity, change summary and kind", () => {
    panel();
    expect(screen.getAllByRole("article")).toHaveLength(4);
    expect(within(row("supplier")).getByText("旧供应商名称")).toBeInTheDocument();
    expect(within(row("supplier")).getByText("供应商").tagName).toBe("STRONG");
    expect(screen.getByText("purchase_order.order_no")).toBeInTheDocument();
    expect(within(row("order_count")).getByText("指标")).toBeInTheDocument();
  });

  it("accepts a property together with the object it depends on", async () => {
    const proposals = state();
    panel(proposals);
    fireEvent.click(within(row("order_no")).getByRole("button", { name: "接受 订单号" }));
    await waitFor(() =>
      expect(proposals.decide).toHaveBeenCalledWith([
        { proposal_id: "no", decision: "accept" },
        { proposal_id: "po", decision: "accept" },
      ]),
    );
    expect(await screen.findByText("已接受 2 条（含 1 条依赖项）")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "撤销" }));
    await waitFor(() => expect(proposals.decide).toHaveBeenCalledTimes(3));
  });

  it("filters by status, kind and search text", async () => {
    panel();
    fireEvent.click(screen.getByRole("tab", { name: /冲突\s*1/ }));
    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(within(row("old")).getByText("目标在提案生成后已被修改")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /待审\s*4/ }));
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索提案名称" }), { target: { value: "purchase" } });
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });

  it("accepts everything acceptable regardless of filters and asks before rejecting all", async () => {
    const proposals = state();
    panel(proposals);
    fireEvent.click(screen.getByRole("button", { name: "全部接受（4）" }));
    await waitFor(() => expect(proposals.decide).toHaveBeenCalledTimes(1));
    expect(vi.mocked(proposals.decide).mock.calls[0][0].map((d) => d.proposal_id).sort()).toEqual(["metric", "no", "po", "upd"]);
  });

  it("opens the detail with names instead of ids (including document facts), evidence and linked dependency count", () => {
    const draft = example("07-instances-and-evidence");
    const customer = draft.object_types.find((o) => o.technical_name === "customer")!;
    const fact0 = draft.material_objects[0];
    const fact1 = draft.material_objects[1];
    const link = draft.link_types[0];
    const factLink = item({
      id: "fl",
      target_kind: "material_link",
      display_name: "文档关系",
      after: element({ id: "fl", type_id: link.id, source_id: fact0.id, target_id: fact1.id, evidence: [] }),
      depends_on: ["po"],
      dependency_group: ["fl", "po"],
    });
    panel(state({ detail: batch([items[0], factLink]) }), session({ draft }));
    expect(within(row("文档关系")).getByText("联动 1 项")).toBeInTheDocument();
    fireEvent.click(row("文档关系"));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(link.name)).toBeInTheDocument();
    expect(within(dialog).getByText("C001")).toBeInTheDocument();
    expect(within(dialog).getByText("1 项")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "采购订单" })).toBeInTheDocument();
    expect(customer).toBeDefined();
  });

  it("opens evidence without opening the row and keeps source identifiers and manual confirmation available in detail", async () => {
    const manual = {
      kind: "manual" as const,
      id: "manual-confirmation",
      created_by: "林晓",
      created_at: "2026-10-17T02:00:00Z",
      note: "已核对供应商名称",
    };
    const supplier = { ...items[2], evidence: [evidence, manual] };
    panel(state({ detail: batch([supplier]) }));
    fireEvent.click(within(row("supplier")).getByRole("button", { name: "查看 供应商 的证据（2 条）" }));
    const popover = (await screen.findByText("制度.md")).closest(".ant-popover") as HTMLElement;
    expect(within(popover).getByText("供应商名称以材料为准")).toBeInTheDocument();
    expect(within(popover).getByText("已核对供应商名称")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(within(popover).getByText("来源标识"));
    expect(await within(popover).findByText("a".repeat(64))).toBeInTheDocument();
    fireEvent.click(within(row("supplier")).getByRole("button", { name: "查看 供应商 的证据（2 条）" }));
    fireEvent.keyDown(row("supplier"), { key: "Enter" });
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("旧供应商名称")).toBeInTheDocument();
    expect(within(dialog).getByText("供应商名称以材料为准")).toBeInTheDocument();
    expect(within(dialog).getByText("已核对供应商名称")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "接受 供应商" })).toBeEnabled();
  });

  it("turns a duplicate fact create into an update of the chosen existing fact", async () => {
    const draft = example("07-instances-and-evidence");
    const customer = draft.material_objects.find((o) => o.values.customer_no === "C001")!;
    const proposed = { id: "new-fact", type_id: customer.type_id, values: { customer_no: "C001", name: "星海贸易有限公司" }, evidence: [evidence] };
    const duplicate = item({
      id: "dup",
      target_kind: "material_object",
      display_name: "C001",
      after: proposed as unknown as CoreElement,
      evidence: [evidence],
      duplicate_candidates: [{ id: customer.id, type_id: customer.type_id, display_text: "C001", expected_target_hash: "hash" }],
    });
    const proposals = state({ detail: batch([duplicate]) });
    panel(proposals, session({ draft }));
    expect(within(row("C001")).getByText("可能重复")).toBeInTheDocument();
    fireEvent.click(row("C001"));
    fireEvent.click(screen.getByRole("button", { name: "改为更新" }));
    // antd labels every dialog with the same id under test, so pick it by content.
    await waitFor(() => expect(screen.getAllByRole("dialog")).toHaveLength(2));
    const confirm = screen.getAllByRole("dialog").find((d) => d.textContent?.includes("提案不再新建事实"))!;
    expect(within(confirm).getByText("星海贸易有限公司")).toBeInTheDocument();
    fireEvent.click(within(confirm).getByRole("button", { name: "改为更新" }));
    await waitFor(() => expect(proposals.revise).toHaveBeenCalled());
    const [id, payload] = vi.mocked(proposals.revise).mock.calls[0];
    expect(id).toBe("dup");
    expect(payload).toMatchObject({ target_id: customer.id, expected_target_hash: "hash" });
    expect(payload.after.id).toBe(customer.id);
    expect(payload.after.values).toMatchObject({ customer_no: "C001", name: "星海贸易有限公司", is_vip: true });
    expect(payload.after.evidence.map((e) => e.id)).toEqual([...customer.evidence.map((e) => e.id), "e"]);
  });
});
