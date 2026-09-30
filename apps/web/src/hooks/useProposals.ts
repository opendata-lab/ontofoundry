import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, proposalsApi } from "../api/client";
import type {
  ModelingSession,
  ProposalBatch,
  ProposalBatchDetail,
} from "../api/types";

type Decision = {
  proposal_id: string;
  decision: "accept" | "reject" | "restore";
};

/**
 * Proposal batches of one session, the selected batch's items, and decisions.
 *
 * A decision keeps its idempotency key until it succeeds or is refused, so a
 * retry after a lost response replays safely; the next user action gets a new
 * key. Refusals (409/422) never become a generic toast: their per-item
 * reasons land in `itemErrors` and the batch is reloaded.
 */
export function useProposals(
  session: ModelingSession | null,
  onSession: (value: ModelingSession) => void,
  onStale: () => void,
) {
  const [batches, setBatches] = useState<ProposalBatch[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<ProposalBatchDetail | null>(null);
  const [error, setError] = useState("");
  const [itemErrors, setItemErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const pendingKey = useRef<{ body: string; key: string } | null>(null);
  const sessionRef = useRef(session);
  sessionRef.current = session;
  const sessionId = session?.id;
  const workspaceId = session?.workspace_id;
  const latest = session?.latest_batch_id;
  const revision = session?.revision;

  const reload = useCallback(() => setRefresh((n) => n + 1), []);

  useEffect(() => {
    if (!sessionId || !workspaceId) {
      setBatches([]);
      setDetail(null);
      return;
    }
    let active = true;
    proposalsApi
      .batches({ id: sessionId, workspace_id: workspaceId })
      .then((r) => {
        if (!active) return;
        setBatches(r.items);
        setSelected((current) =>
          current && r.items.some((b) => b.id === current)
            ? current
            : (r.items[0]?.id ?? null),
        );
      })
      .catch((e: Error) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [sessionId, workspaceId, latest, revision, refresh]);

  useEffect(() => {
    if (!sessionId || !workspaceId || !selected) {
      setDetail(null);
      return;
    }
    let active = true;
    proposalsApi
      .batch({ id: sessionId, workspace_id: workspaceId }, selected)
      .then((value) => active && setDetail(value))
      .catch((e: Error) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [sessionId, workspaceId, selected, revision, refresh]);

  // A new batch from a finished run becomes the selected one.
  useEffect(() => {
    if (latest) setSelected(latest);
  }, [latest]);

  const decide = async (decisions: Decision[]) => {
    const current = sessionRef.current;
    if (!current) return false;
    const body = JSON.stringify(decisions);
    if (pendingKey.current?.body !== body)
      pendingKey.current = { body, key: crypto.randomUUID() };
    setBusy(true);
    setError("");
    setItemErrors({});
    try {
      const result = await proposalsApi.decide(
        current,
        decisions,
        pendingKey.current.key,
      );
      pendingKey.current = null;
      onSession(result.session);
      reload();
      return true;
    } catch (e) {
      if (e instanceof ApiError && (e.status === 409 || e.status === 422)) {
        pendingKey.current = null;
        setItemErrors(
          Object.fromEntries(e.items.map((i) => [i.proposal_id, i.reason])),
        );
        setError(
          e.code === "SESSION_REVISION_CHANGED"
            ? "草稿已更新，请重新确认"
            : e.message,
        );
        onStale();
        reload();
      } else {
        // Transport failure: keep the key, so trying again is a replay.
        setError(e instanceof Error ? e.message : "提交失败");
      }
      return false;
    } finally {
      setBusy(false);
    }
  };

  return {
    batches,
    selected,
    select: setSelected,
    detail,
    error,
    itemErrors,
    busy,
    reload,
    decide,
  };
}

export type ProposalsState = ReturnType<typeof useProposals>;
