import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, modelingApi } from "../api/client";
import type { Draft, ModelingSession, User, Workspace } from "../api/types";
import { emptyDraft } from "../lib/coreModel";
import { usePageActive } from "./usePageTab";
import { getWorkspacePermissions } from "./useWorkspacePermissions";
import { ONTOLOGY_SAVED, type OntologySaved } from "../lib/elementInspector";

/**
 * The core-1 draft a page reads: the session draft when ?session= is set, the
 * published snapshot for readers, or the authorised presentation of the
 * current version for visitors. All three are the same Draft shape.
 */
export function useSnapshot(workspace: Workspace, user?: User | null) {
  const { canRead } = getWorkspacePermissions(workspace, user);
  const active = usePageActive();
  const [params] = useSearchParams();
  const sid = params.get("session");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [session, setSession] = useState<ModelingSession | null>(null);
  const [error, setError] = useState("");
  const request = useRef(0);
  const invalidate = useCallback(() => {
    request.current++;
  }, []);
  const load = useCallback(() => {
    const revision = ++request.current;
    setError("");
    setDraft(null);
    if (!sid) setSession(null);
    const accept = (next: Draft, nextSession: ModelingSession | null = null) => {
      if (revision === request.current) {
        setDraft(next);
        setSession(nextSession);
      }
    };
    const fail = (error: Error) => {
      if (revision === request.current) setError(error.message);
    };
    if (sid && canRead)
      modelingApi
        .get(workspace.id, sid)
        .then((s) => accept(s.draft, s))
        .catch(fail);
    else if (canRead) modelingApi.snapshot(workspace.id, workspace.version_id).then((d) => accept(d)).catch(fail);
    else if (!workspace.version_id) accept(emptyDraft(workspace.id));
    else
      api
        .presentation(workspace.id, workspace.version_id)
        .then((r) => accept(r.model))
        .catch(fail);
  }, [workspace.id, canRead, workspace.version_id, sid]);
  useEffect(() => {
    if (active) load();
    return invalidate;
  }, [load, active, invalidate]);
  useEffect(() => {
    const saved = (event: Event) => {
      const detail = (event as CustomEvent<OntologySaved>).detail;
      if (detail.workspaceId !== workspace.id) return;
      if (sid && detail.session?.id === sid) {
        request.current++;
        setDraft(detail.session.draft);
        setSession(detail.session);
      } else if (active && !sid && !detail.session) load();
    };
    window.addEventListener(ONTOLOGY_SAVED, saved);
    return () => window.removeEventListener(ONTOLOGY_SAVED, saved);
  }, [workspace.id, sid, active, load]);
  return {
    draft,
    setDraft,
    session,
    setSession,
    error,
    load,
    sessionId: sid,
    suffix: sid ? "?session=" + sid : "",
  };
}
