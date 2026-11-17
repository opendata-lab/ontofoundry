import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { proposalsApi } from "../../api/client";
import type { ChangeEvent, CoreElement, ModelingSession, ProposalItem } from "../../api/types";
import { emptyDraft } from "../../lib/coreModel";
import { renderWithProviders } from "../../test/renderWithProviders";
import { ElementChangeHistory } from "./ElementChangeHistory";
import { ProposalDetail } from "./ProposalDetail";

vi.mock("../../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api/client")>();
  return {
    ...original,
    catalogApi: { ...original.catalogApi, connections: vi.fn() },
    proposalsApi: { ...original.proposalsApi, changeEvents: vi.fn() },
  };
});

beforeEach(async () => {
  vi.clearAllMocks();
  const { catalogApi } = await import("../../api/client");
  vi.mocked(catalogApi.connections).mockResolvedValue({ items: [] });
});

afterEach(cleanup);

function makeEvent(overrides: Partial<ChangeEvent> = {}): ChangeEvent {
  return {
    id: "ev-1",
    workspace_id: "w1",
    session_id: "s1",
    at: "2026-11-16T08:00:00Z",
    actor_id: "u1",
    actor_display_name: "林晓",
    actor_kind: "human",
    run_token: null,
    subject: "draft",
    action: "updated",
    target_kind: "object_type",
    target_id: "obj-1",
    proposal_id: "p1",
    batch_id: "b1",
    version_id: null,
    before: { id: "obj-1", name: "order", display_name: "订单", description: "旧描述" },
    after: { id: "obj-1", name: "order", display_name: "订单", description: "新描述" },
    cause_id: "ev-0",
    ...overrides,
  };
}

describe("ElementChangeHistory", () => {
  it("renders events newest-first with time, who, action, field diffs, and pagination", async () => {
    vi.mocked(proposalsApi.changeEvents)
      .mockResolvedValueOnce({
        items: [
          makeEvent({
            id: "ev-3",
            actor_kind: "human",
            actor_display_name: "林晓",
            subject: "draft",
            action: "updated",
            before: { id: "obj-1", description: "智能体描述" },
            after: { id: "obj-1", description: "人工修订描述" },
          }),
          makeEvent({
            id: "ev-2",
            actor_kind: "agent",
            actor_display_name: "林晓",
            subject: "proposal",
            action: "created",
            before: null,
            after: {
              status: "pending",
              operation: "update",
              before: { id: "obj-1", description: "初始描述" },
              after: { id: "obj-1", description: "智能体描述" },
            },
          }),
        ],
        next_cursor: "ev-2",
      })
      .mockResolvedValueOnce({
        items: [
          makeEvent({
            id: "ev-1",
            actor_kind: "import",
            actor_display_name: null,
            subject: "proposal",
            action: "created",
            before: null,
            after: {
              status: "pending",
              operation: "create",
              before: null,
              after: { id: "obj-1", name: "order", display_name: "订单" },
            },
          }),
        ],
        next_cursor: null,
      });

    renderWithProviders(
      <ElementChangeHistory workspaceId="w1" sessionId="s1" targetId="obj-1" />,
    );

    const list = await screen.findByRole("list", { name: "元素修改记录" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("人工 · 林晓")).toBeInTheDocument();
    expect(within(rows[0]).getByText("草稿修改")).toBeInTheDocument();
    expect(within(rows[0]).getByText("智能体描述")).toBeInTheDocument();
    expect(within(rows[0]).getByText("人工修订描述")).toBeInTheDocument();

    expect(within(rows[1]).getByText("智能体 · 林晓")).toBeInTheDocument();
    expect(within(rows[1]).getByText("生成提案")).toBeInTheDocument();
    expect(within(rows[1]).getByText("初始描述")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "加载更多" }));
    await waitFor(() => expect(within(list).getAllByRole("listitem")).toHaveLength(3));
    const thirdRow = within(list).getAllByRole("listitem")[2];
    expect(within(thirdRow).getByText("导入")).toBeInTheDocument();
    expect(proposalsApi.changeEvents).toHaveBeenNthCalledWith(2, "w1", "s1", {
      target_id: "obj-1",
      limit: 20,
      cursor: "ev-2",
    });
  });

  it("renders 修改记录 inside ProposalDetail for the proposal target", async () => {
    vi.mocked(proposalsApi.changeEvents).mockResolvedValue({
      items: [makeEvent()],
      next_cursor: null,
    });
    const draft = emptyDraft("w1");
    const session = { id: "s1", workspace_id: "w1", revision: 2, draft } as ModelingSession;
    const item: ProposalItem = {
      id: "p1",
      batch_id: "b1",
      ordinal: 0,
      client_ref: null,
      operation: "update",
      target_kind: "object_type",
      target_id: "obj-1",
      display_name: "订单",
      owner_label: null,
      before: { id: "obj-1", name: "order", display_name: "订单", description: "旧描述" } as unknown as CoreElement,
      after: { id: "obj-1", name: "order", display_name: "订单", description: "新描述" } as unknown as CoreElement,
      field_changes: [{ path: "description", before: "旧描述", after: "新描述" }],
      evidence: [],
      reason: "",
      depends_on: [],
      dependency_group: ["p1"],
      atomic_group_id: null,
      duplicate_candidates: [],
      status: "pending",
      stored_status: "pending",
      status_reason: "",
      accepted_revision: null,
      decided_at: null,
    };

    renderWithProviders(
      <ProposalDetail
        item={item}
        items={[item]}
        draft={session.draft}
        technical="order"
        busy={false}
        actions={{
          open: vi.fn(),
          accept: vi.fn(),
          reject: vi.fn(),
          restore: vi.fn(),
          backToPending: vi.fn(),
        }}
        onRevise={vi.fn()}
        onReviseDataset={vi.fn()}
        onReviseContent={vi.fn()}
        workspaceId="w1"
        sessionId="s1"
        sessionRevision={2}
        onClose={vi.fn()}
      />,
    );

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "修改记录" })).toBeInTheDocument();
    expect(await within(dialog).findByText("草稿修改")).toBeInTheDocument();
    expect(proposalsApi.changeEvents).toHaveBeenCalledWith("w1", "s1", {
      target_id: "obj-1",
      limit: 20,
    });
  });

  it("drops stale load-more responses after a refresh", async () => {
    let resolveLoadMore!: (page: { items: ChangeEvent[]; next_cursor: string | null }) => void;
    const staleLoadMorePromise = new Promise<{ items: ChangeEvent[]; next_cursor: string | null }>(
      (resolve) => {
        resolveLoadMore = resolve;
      },
    );

    vi.mocked(proposalsApi.changeEvents)
      .mockResolvedValueOnce({
        items: [
          makeEvent({
            id: "ev-initial",
            before: { id: "obj-1", description: "初始前" },
            after: { id: "obj-1", description: "初始后" },
          }),
        ],
        next_cursor: "cursor-1",
      })
      .mockReturnValueOnce(staleLoadMorePromise)
      .mockResolvedValueOnce({
        items: [
          makeEvent({
            id: "ev-fresh",
            before: { id: "obj-1", description: "刷新前" },
            after: { id: "obj-1", description: "刷新后" },
          }),
        ],
        next_cursor: "cursor-fresh",
      });

    const view = renderWithProviders(
      <ElementChangeHistory workspaceId="w1" sessionId="s1" targetId="obj-1" refreshKey={1} />,
    );

    await screen.findByText("初始后");
    fireEvent.click(screen.getByRole("button", { name: "加载更多" }));

    view.rerender(
      <ElementChangeHistory workspaceId="w1" sessionId="s1" targetId="obj-1" refreshKey={2} />,
    );
    await screen.findByText("刷新后");

    resolveLoadMore({
      items: [
        makeEvent({
          id: "ev-stale",
          before: { id: "obj-1", description: "过期前" },
          after: { id: "obj-1", description: "过期后" },
        }),
      ],
      next_cursor: null,
    });

    await waitFor(() => {
      expect(screen.getByText("刷新后")).toBeInTheDocument();
      expect(screen.queryByText("过期后")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: "加载更多" })).toBeInTheDocument();
    });
  });
});
