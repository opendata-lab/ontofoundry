import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { modelingApi } from "../api/client";
import type { ModelingSession } from "../api/types";
import { usePageActive } from "./usePageTab";

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
  const [sessions, setSessions] = useState<
    Pick<ModelingSession, "id" | "title" | "task_status">[]
  >([]);
  const [error, setError] = useState("");
  const pending = useRef<Promise<ModelingSession> | null>(null);
  const [refresh, setRefresh] = useState(0);
  const taskStatus = session?.task_status;
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
    if (pageActive && !wasActive.current && refreshOnActivate) reload();
    wasActive.current = pageActive;
  }, [pageActive, refreshOnActivate, reload]);
  useEffect(() => {
    setSession(null);
    setError("");
    setSessions([]);
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
        if (active) setSessions(r.items);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [workspaceId, sessionId, enabled, refresh]);
  useEffect(() => {
    if (
      !pageActive ||
      !sessionId ||
      !taskStatus ||
      !["queued", "running"].includes(taskStatus)
    )
      return;
    let active = true;
    const timer = window.setInterval(() => {
      modelingApi
        .get(workspaceId, sessionId)
        .then((value) => {
          if (active) setSession(value);
        })
        .catch((e: Error) => {
          if (active) setError(e.message);
        });
    }, 1500);
    return () => {
      active = false;
      clearInterval(timer);
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
