import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, modelingApi, proposalsApi } from "../api/client";
import type {
  Dataset,
  FactProposalRevision,
  ModelingSession,
  ProposalBatch,
  ProposalBatchDetail,
} from "../api/types";
import { newId } from "../lib/id";

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
  // Preserve a just-returned session while its parent prop catches up.
  if (sessionRef.current?.id !== session?.id || !sessionRef.current ||
    (session && session.revision >= sessionRef.current.revision)) sessionRef.current = session;
  const sessionId = session?.id;
  const workspaceId = session?.workspace_id;
  const latest = session?.latest_batch_id;
  const revision = session?.revision;

  const reload = useCallback(() => setRefresh((n) => n + 1), []);
  useEffect(() => {
    const synced = () => reload();
    window.addEventListener("ontofoundry:metadata-synced", synced);
    window.addEventListener("ontofoundry:proposal-source-changed", synced);
    return () => { window.removeEventListener("ontofoundry:metadata-synced", synced); window.removeEventListener("ontofoundry:proposal-source-changed", synced); };
  }, [reload]);

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
        // Keep the user's choice; otherwise the newest batch that can be
        // acted on, not a newer failed one.
        setSelected((current) =>
          current && r.items.some((b) => b.id === current)
            ? current
            : (r.items.find((b) => b.status === "available")?.id ??
              r.items[0]?.id ??
              null),
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
      pendingKey.current = { body, key: newId() };
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
      // A server-backed undo can issue another decision before React renders
      // the returned session. Its expected revision must already be current.
      sessionRef.current = result.session;
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

  /**
   * Turns a pending duplicate-fact create into an update of an existing fact.
   * The server builds a new pending item; the session and batch are reread.
   */
  const revise = async (itemId: string, payload: Omit<FactProposalRevision, "expected_session_revision">) => {
    const current = sessionRef.current;
    if (!current) return false;
    setBusy(true);
    setError("");
    setItemErrors({});
    try {
      await proposalsApi.reviseFact(current, itemId, {
        ...payload,
        expected_session_revision: current.revision,
      });
      onStale();
      reload();
      return true;
    } catch (e) {
      const message = e instanceof Error ? e.message : "修订失败";
      setItemErrors({ [itemId]: message });
      if (e instanceof ApiError && (e.status === 409 || e.status === 422)) {
        onStale();
        reload();
      }
      return false;
    } finally {
      setBusy(false);
    }
  };

  /** Replace a pending proposal's content before it is decided; the server re-validates it. */
  const reviseContent = async (proposalId: string, fields: Record<string, unknown>) => {
    const current = sessionRef.current;
    if (!current) return false;
    setBusy(true);
    setError("");
    setItemErrors((errors) => Object.fromEntries(Object.entries(errors).filter(([id]) => id !== proposalId)));
    try {
      // Only the edited field is sent; the server merges it into the stored content.
      await proposalsApi.reviseContent(current.workspace_id, current.id, proposalId, fields, current.revision);
      const fresh = await modelingApi.get(current.workspace_id, current.id);
      sessionRef.current = fresh;
      onSession(fresh);
      reload();
      return true;
    } catch (e) {
      const reasons = e instanceof ApiError ? e.errors.map((issue) => `${issue.path ?? ""}：${issue.message}`).filter(Boolean) : [];
      setItemErrors({ [proposalId]: [e instanceof Error ? e.message : "修改提案失败", ...reasons].join("；") });
      if (e instanceof ApiError && e.status === 409) onStale();
      return false;
    } finally {
      setBusy(false);
    }
  };

  /** Change a pending dataset proposal's connection or table, then re-check dependents. */
  const reviseDataset = async (proposalId: string, dataset: Dataset) => {
    const current = sessionRef.current;
    if (!current) return false;
    setBusy(true);
    setError("");
    try {
      await proposalsApi.reviseDataset(current.workspace_id, current.id, proposalId, dataset, current.revision);
      const fresh = await modelingApi.get(current.workspace_id, current.id);
      sessionRef.current = fresh;
      onSession(fresh);
      reload();
      return true;
    } catch (e) {
      setItemErrors({ [proposalId]: e instanceof Error ? e.message : "修改数据集来源失败" });
      if (e instanceof ApiError && e.status === 409) onStale();
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
    revise,
    reviseContent,
    reviseDataset,
  };
}

export type ProposalsState = ReturnType<typeof useProposals>;
