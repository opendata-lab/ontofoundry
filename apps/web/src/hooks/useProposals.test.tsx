import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, proposalsApi } from "../api/client";
import type { ModelingSession } from "../api/types";
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
});
