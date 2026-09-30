import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import type { ModelingSession, ProposalBatchDetail, ProposalItem } from "../../api/types";
import type { ProposalsState } from "../../hooks/useProposals";
import { emptyDraft } from "../../lib/draftView";
import { ModelResults } from "../ModelResults";
import { ProposalPanel } from "./ProposalPanel";

vi.mock("../OntologyGraph", () => ({ OntologyGraph: () => <div /> }));
afterEach(cleanup);

function item(overrides: Partial<ProposalItem>): ProposalItem {
  return {
    id: "i",
    batch_id: "b",
    ordinal: 0,
    client_ref: null,
    operation: "create",
    target_kind: "object_type",
    target_id: "t",
    display_name: "对象",
    before: null,
    after: {},
    field_changes: [],
    evidence: [],
    reason: "",
    depends_on: [],
    dependency_group: [overrides.id ?? "i"],
    status: "pending",
    stored_status: "pending",
    ...overrides,
  };
}

const items: ProposalItem[] = [
  item({ id: "po", display_name: "采购订单" }),
  item({
    id: "no",
    target_kind: "property",
    display_name: "订单号",
    owner_label: "采购订单",
    depends_on: ["po"],
    dependency_group: ["no", "po"],
  }),
  item({
    id: "upd",
    operation: "update",
    display_name: "供应商",
    field_changes: [{ path: "description", before: "旧", after: "新" }],
    evidence: [
      {
        kind: "material",
        id: "e",
        material_id: "m",
        material_sha256: "a".repeat(64),
        material_name: "制度.md",
        material_archived: false,
        locator: { line_start: 42, line_end: 47 },
        quote: "原文",
      },
    ],
  }),
  item({
    id: "old",
    operation: "update",
    display_name: "物料",
    status: "stale",
    status_reason: "目标在提案生成后已被修改",
  }),
  item({ id: "act", target_kind: "action", display_name: "审批供应商" }),
  item({ id: "gone", display_name: "旧提案", status: "rejected", stored_status: "rejected" }),
];

function batch(extra: Partial<ProposalBatchDetail> = {}): ProposalBatchDetail {
  return {
    id: "b",
    status: "available",
    created_at: "2026-09-30T10:00:00Z",
    source_session_revision: 7,
    base_version_id: "v",
    counts: { pending: 4, accepted: 0, rejected: 1, stale: 1, conflict: 0, superseded: 0 },
    items,
    ...extra,
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
    ...extra,
  };
}

function session(extra: Partial<ModelingSession> = {}): ModelingSession {
  return {
    id: "s",
    title: "t",
    workspace_id: "w",
    base_version_id: "v",
    revision: 7,
    draft: emptyDraft("w"),
    graph: { workspace_id: "w", version_id: "v", version_sha256: "", nodes: [], edges: [] },
    candidates: [],
    material_ids: [],
    task_status: "idle",
    task_detail: "",
    updated_at: "",
    pending_proposal_count: 4,
    latest_batch_id: "b",
    base_diff: [],
    ...extra,
  };
}

const panel = (proposals: ProposalsState, s = session(), onRemodel = vi.fn()) =>
  render(
    <MemoryRouter>
      <ProposalPanel session={s} proposals={proposals} running={false} onRemodel={onRemodel} />
    </MemoryRouter>,
  );

describe("proposal panel", () => {
  it("groups items, badges dependency groups and marks actions as definitions", () => {
    panel(state());
    expect(screen.getByText("冲突 / 已过期")).toBeInTheDocument();
    expect(screen.getByText(/依赖组 2 项/)).toBeInTheDocument();
    expect(screen.getByText("仅定义 · 不可执行")).toBeInTheDocument();
    expect(screen.getByText(/制度\.md 第 42–47 行/)).toBeInTheDocument();
    // History is collapsed but present.
    expect(screen.getByText("历史")).toBeInTheDocument();
  });

  it("accepts a whole dependency group", () => {
    const proposals = state();
    panel(proposals);
    const card = screen.getByRole("article", { name: /新增 属性 · 采购订单\.订单号/ });
    fireEvent.click(within(card).getByRole("button", { name: "接受整组" }));
    expect(proposals.decide).toHaveBeenCalledWith([
      { proposal_id: "no", decision: "accept" },
      { proposal_id: "po", decision: "accept" },
    ]);
  });

  it("never offers accept on a stale item, only reject and re-modelling", () => {
    const onRemodel = vi.fn();
    panel(state(), session(), onRemodel);
    const card = screen.getByRole("article", { name: /修改 实体 · 物料/ });
    expect(within(card).queryByRole("button", { name: "接受" })).not.toBeInTheDocument();
    fireEvent.click(within(card).getByRole("button", { name: "基于当前草稿重新建模" }));
    expect(onRemodel).toHaveBeenCalledWith(expect.stringContaining("物料"));
    expect(within(card).getByRole("button", { name: "拒绝" })).toBeInTheDocument();
  });

  it("accept-all takes only items whose group is clear", () => {
    const proposals = state();
    panel(proposals);
    fireEvent.click(screen.getByRole("button", { name: "接受全部无冲突项" }));
    const ids = (proposals.decide as ReturnType<typeof vi.fn>).mock.calls[0][0].map(
      (d: { proposal_id: string }) => d.proposal_id,
    );
    expect(ids.sort()).toEqual(["act", "no", "po", "upd"]);
  });

  it("restores a rejected item and shows per-item refusals in place", () => {
    const proposals = state({ itemErrors: { upd: "目标在提案生成后已被修改" } });
    panel(proposals);
    expect(screen.getByRole("alert")).toHaveTextContent("目标在提案生成后已被修改");
    fireEvent.click(screen.getByText("历史"));
    fireEvent.click(screen.getByRole("button", { name: "恢复" }));
    expect(proposals.decide).toHaveBeenCalledWith([{ proposal_id: "gone", decision: "restore" }]);
  });

  it("explains a draft that moved during generation, and failed batches", () => {
    panel(state(), session({ revision: 9 }));
    expect(screen.getByText(/生成期间草稿已变化（r7 → r9）/)).toBeInTheDocument();
    cleanup();
    const failed = batch({ status: "failed", items: [], error: { code: "X", message: "格式不对" } });
    panel(state({ detail: failed, batches: [failed] }));
    expect(screen.getByRole("alert")).toHaveTextContent("格式不对");
  });

  it("filters by kind of change", () => {
    panel(state());
    fireEvent.click(screen.getByRole("radio", { name: /新增/ }));
    expect(screen.queryByText("冲突 / 已过期")).not.toBeInTheDocument();
    expect(screen.getByRole("article", { name: /新增 实体 · 采购订单/ })).toBeInTheDocument();
  });

  it("opens the detail drawer with field changes and evidence", () => {
    panel(state());
    fireEvent.click(screen.getByRole("button", { name: /修改 实体 · 供应商/ }));
    const drawer = screen.getByRole("dialog", { hidden: true });
    expect(within(drawer).getByText("字段差异")).toBeInTheDocument();
    expect(within(drawer).getByText("原文")).toBeInTheDocument();
  });

  it("has an honest empty state", () => {
    panel(state({ batches: [], detail: null }));
    expect(screen.getByText(/提案会出现在这里/)).toBeInTheDocument();
  });
});

describe("result tabs", () => {
  it("opens on proposals when some are pending, and marks draft changes", () => {
    const s = session({
      base_diff: [
        {
          element_kind: "object_type",
          element_id: "gone-type",
          label: "旧对象",
          change: "deleted",
          field_changes: [],
          before: { technical_name: "old_type" },
          after: null,
        },
      ],
    });
    render(
      <MemoryRouter>
        <ModelResults session={s} proposals={state()} />
      </MemoryRouter>,
    );
    expect(screen.getAllByRole("tab")).toHaveLength(3);
    expect(screen.getByRole("tab", { name: /提案/ })).toHaveAttribute("aria-selected", "true");
    fireEvent.click(screen.getByRole("tab", { name: /本体草稿/ }));
    expect(screen.getByText("旧对象")).toBeInTheDocument();
    expect(screen.getByText("待删除")).toBeInTheDocument();
  });

  it("opens on the draft when nothing is pending", () => {
    render(
      <MemoryRouter>
        <ModelResults session={session({ pending_proposal_count: 0 })} proposals={state()} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("tab", { name: /本体草稿/ })).toHaveAttribute("aria-selected", "true");
  });
});
