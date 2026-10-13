import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, proposalsApi } from "../api/client";
import type { ModelingSession, ProposalBatchDetail } from "../api/types";
import { emptyDraft } from "../lib/draftView";
import { useProposals } from "./useProposals";

afterEach(() => vi.restoreAllMocks());

const session = {
  id: "s",
  workspace_id: "w",
  revision: 3,
  draft: emptyDraft("w"),
  latest_batch_id: null,
} as unknown as ModelingSession;

function setup() {
  vi.spyOn(proposalsApi, "batches").mockResolvedValue({ items: [], next_cursor: null });
  vi.spyOn(proposalsApi, "batch");
  const onSession = vi.fn();
  const onStale = vi.fn();
  const hook = renderHook(() => useProposals(session, onSession, onStale));
  return { hook, onSession, onStale };
}

describe("useProposals", () => {
  it("uses the returned session revision for sequential undo decisions before parent props catch up", async () => {
    const { hook } = setup();
    const updated = { ...session, revision: 4 };
    const decide = vi.spyOn(proposalsApi, "decide")
      .mockResolvedValueOnce({ session: updated, results: [], validation: {} as never })
      .mockResolvedValue({ session: updated, results: [], validation: {} as never });
    await act(() => hook.result.current.decide([{ proposal_id: "p", decision: "reject" }]));
    await act(() => hook.result.current.decide([{ proposal_id: "p", decision: "restore" }]));
    expect(decide.mock.calls[1][0]).toEqual(updated);
    expect(decide.mock.calls[0][2]).not.toBe(decide.mock.calls[1][2]);
  });

  it("replays a failed transport with the same key, and uses a new key next time", async () => {
    const { hook, onSession } = setup();
    const decide = vi
      .spyOn(proposalsApi, "decide")
      .mockRejectedValueOnce(new TypeError("network"))
      .mockResolvedValue({ session, results: [], validation: {} as never });
    const decision = [{ proposal_id: "p", decision: "accept" as const }];
    await act(() => hook.result.current.decide(decision));
    await act(() => hook.result.current.decide(decision));
    expect(decide.mock.calls[0][2]).toBe(decide.mock.calls[1][2]);
    expect(onSession).toHaveBeenCalledWith(session);
    await act(() => hook.result.current.decide(decision));
    expect(decide.mock.calls[2][2]).not.toBe(decide.mock.calls[1][2]);
  });

  it("puts refusal reasons on the items and resyncs", async () => {
    const { hook, onStale } = setup();
    vi.spyOn(proposalsApi, "decide").mockRejectedValue(
      new ApiError("过期", 409, "PROPOSAL_STALE", undefined, {
        items: [{ proposal_id: "p", reason: "目标已修改" }],
      }),
    );
    await act(() => hook.result.current.decide([{ proposal_id: "p", decision: "accept" }]));
    await waitFor(() => expect(hook.result.current.itemErrors).toEqual({ p: "目标已修改" }));
    expect(onStale).toHaveBeenCalled();
  });

  it("refreshes the draft, proposal items and counts after undo", async () => {
    const { hook, onSession } = setup();
    await waitFor(() => expect(proposalsApi.batches).toHaveBeenCalled());
    const batches = vi.mocked(proposalsApi.batches);
    const detail: ProposalBatchDetail = {
      id: "b", status: "available", created_at: "", source_session_revision: 3, base_version_id: null,
      counts: { pending: 0, accepted: 1, rejected: 0, stale: 0, conflict: 0, superseded: 0 },
      items: [],
    };
    batches.mockResolvedValue({ items: [detail], next_cursor: null });
    const batch = vi.mocked(proposalsApi.batch).mockResolvedValue(detail);
    act(() => hook.result.current.reload());
    await waitFor(() => expect(hook.result.current.detail).toEqual(detail));
    batches.mockClear();
    batch.mockClear();
    const rejected = { ...detail, counts: { ...detail.counts, accepted: 0, rejected: 1 } };
    batches.mockResolvedValue({ items: [rejected], next_cursor: null });
    batch.mockResolvedValue(rejected);
    const updated = { ...session, revision: 4, pending_proposal_count: 0 };
    vi.spyOn(proposalsApi, "decide").mockResolvedValue({
      session: updated,
      results: [{ proposal_id: "p", status: "rejected", reason: "" }],
      validation: {} as never,
    });
    await act(() => hook.result.current.decide([{ proposal_id: "p", decision: "reject" }]));
    expect(onSession).toHaveBeenCalledWith(updated);
    await waitFor(() => expect(batches).toHaveBeenCalled());
    await waitFor(() => expect(hook.result.current.detail?.counts).toEqual(rejected.counts));
    expect(batch).toHaveBeenCalledWith(expect.objectContaining({ id: "s" }), "b");
  });
});
