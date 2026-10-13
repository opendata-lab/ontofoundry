import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { modelingApi } from "../api/client";

/** Mirrors the backend's ACTIVE_RUN_STATUSES; a parked run is still a run. */
const ACTIVE_TASK_STATUSES = [
  "submitting",
  "queued",
  "running",
  "waiting_input",
  "waiting_permission",
];
import type { ModelingSession, ModelingSessionSummary } from "../api/types";
import { usePageActive } from "./usePageTab";
import { ONTOLOGY_SAVED, type OntologySaved } from "../lib/elementInspector";

export function useModeling(
  workspaceId: string,
  enabled = true,
  refreshOnActivate = false,
) {
  const pageActive = usePageActive();
  const wasActive = useRef(pageActive);
  const [params, setParams] = useSearchParams();
  const sessionId = params.get("session");
  const [session, setSession] = useState<ModelingSession | null>(null);
  const [sessions, setSessions] = useState<ModelingSessionSummary[]>([]);
  const [error, setError] = useState("");
  const pending = useRef<Promise<ModelingSession> | null>(null);
  const [refresh, setRefresh] = useState(0);
  const taskStatus = session?.task_status;
  const sessionRef = useRef(session);
  useEffect(() => {
    sessionRef.current = session;
  }, [session]);
  const select = useCallback(
    (id: string, created = false) =>
      setParams(
        (p) => {
          const next = new URLSearchParams(p);
          next.set("session", id);
          return next;
        },
        {
          replace: true,
          state: created ? { tabOperation: "session-created" } : null,
        },
      ),
    [setParams],
  );
  const reload = useCallback(() => setRefresh((value) => value + 1), []);
  useEffect(() => {
    const saved = (event: Event) => {
      const detail = (event as CustomEvent<OntologySaved>).detail;
      if (detail.workspaceId === workspaceId && detail.session?.id === sessionId) setSession(detail.session);
    };
    window.addEventListener(ONTOLOGY_SAVED, saved);
    return () => window.removeEventListener(ONTOLOGY_SAVED, saved);
  }, [workspaceId, sessionId]);
  useEffect(() => {
    if (pageActive && !wasActive.current && refreshOnActivate) reload();
    wasActive.current = pageActive;
  }, [pageActive, refreshOnActivate, reload]);
  const loadedKey = useRef("");
  useEffect(() => {
    // Only a different workspace or session starts from blank. A reload of
    // the same session keeps showing it while the new copy loads; blanking it
    // made the page flip to "正在加载会话…/尚未开始" on every run event.
    const key = `${workspaceId}:${sessionId ?? ""}:${enabled}`;
    if (loadedKey.current !== key) {
      loadedKey.current = key;
      setSession(null);
      setSessions([]);
    }
    setError("");
    if (!enabled) return;
    let active = true;
    if (sessionId)
      modelingApi
        .get(workspaceId, sessionId)
        .then((value) => {
          if (active) setSession(value);
        })
        .catch((e: Error) => {
          if (active) setError(e.message);
        });
    modelingApi
      .sessions(workspaceId)
      .then((r) => {
        if (!active) return;
        setSessions(r.items);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [workspaceId, sessionId, enabled, refresh]);
  useEffect(() => {
    if (!enabled || sessionId) return;
    const activeSession = sessions.find((item) =>
      ACTIVE_TASK_STATUSES.includes(item.task_status),
    );
    if (activeSession) select(activeSession.id);
  }, [enabled, sessionId, sessions, select]);
  useEffect(() => {
    if (
      !pageActive ||
      !sessionId ||
      !taskStatus ||
      // Every active state, matching the backend. A run waiting on input is
      // not finished, and stopping the poll there leaves the page showing a
      // stale revision that later saves and publishes will 409 against.
      !ACTIVE_TASK_STATUSES.includes(taskStatus)
    )
      return;
    // The full session (draft, graph, diff) takes seconds to build on a large
    // ontology, and a fixed interval stacked those requests until none came
    // back. Poll the cheap summary list one request at a time and fetch the
    // full session only when its status or timestamp moved, plus every 10th
    // tick for detail text that changes without either.
    let active = true;
    let timer = 0;
    let ticks = 0;
    const tick = async () => {
      try {
        const { items } = await modelingApi.sessions(workspaceId);
        if (!active) return;
        setSessions(items);
        const summary = items.find((item) => item.id === sessionId);
        const current = sessionRef.current;
        ticks += 1;
        if (
          !summary ||
          !current ||
          summary.task_status !== current.task_status ||
          summary.updated_at !== current.updated_at ||
          ticks % 10 === 0
        ) {
          const value = await modelingApi.get(workspaceId, sessionId);
          if (active) setSession(value);
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
      if (active) timer = window.setTimeout(tick, 1500);
    };
    timer = window.setTimeout(tick, 1500);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [workspaceId, sessionId, taskStatus, pageActive]);
  const create = async (title = "新的建模会话") => {
    const created = await modelingApi.create(workspaceId, title);
    if (!sessionId) setSession(created);
    setSessions((list) => [created, ...list]);
    select(created.id, true);
    return created;
  };
  const ensure = async () => {
    if (session) return session;
    if (sessionId) return modelingApi.get(workspaceId, sessionId);
    if (!pending.current)
      pending.current = create().finally(() => {
        pending.current = null;
      });
    return pending.current;
  };
  return {
    session,
    // The id from the URL, which changes the moment the user switches — unlike
    // `session`, which is null until its request comes back. Anything deriving
    // a conversation address must use this: an address that briefly goes empty
    // reads as a switch and resets the embedded conversation.
    sessionId,
    setSession,
    sessions,
    error,
    setError,
    select,
    create,
    ensure,
    reload,
  };
}
