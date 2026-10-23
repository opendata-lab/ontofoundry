import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, modelingApi } from "../api/client";
import type { Draft, Workspace } from "../api/types";
import { emptyDraft } from "../lib/coreModel";
import { usePageActive } from "./usePageTab";
import { ONTOLOGY_SAVED, type OntologySaved } from "../lib/elementInspector";

/**
 * The core-1 draft a page reads: the session draft when ?session= is set, the
 * published snapshot for members, or the authorised presentation of the
 * current version for visitors. All three are the same Draft shape.
 */
export function useSnapshot(workspace: Workspace) {
  const active = usePageActive();
  const [params] = useSearchParams();
  const sid = params.get("session");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState("");
  const request = useRef(0);
  const invalidate = useCallback(() => {
    request.current++;
  }, []);
  const load = useCallback(() => {
    const revision = ++request.current;
    setError("");
    setDraft(null);
    const accept = (next: Draft) => {
      if (revision === request.current) setDraft(next);
    };
    const fail = (error: Error) => {
      if (revision === request.current) setError(error.message);
    };
    if (sid && workspace.role)
      modelingApi
        .get(workspace.id, sid)
        .then((s) => accept(s.draft))
        .catch(fail);
    else if (workspace.role) modelingApi.snapshot(workspace.id, workspace.version_id).then(accept).catch(fail);
    else if (!workspace.version_id) accept(emptyDraft(workspace.id));
    else
      api
        .presentation(workspace.id, workspace.version_id)
        .then((r) => accept(r.model))
        .catch(fail);
  }, [workspace.id, workspace.role, workspace.version_id, sid]);
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
      } else if (active && !sid) load();
    };
    window.addEventListener(ONTOLOGY_SAVED, saved);
    return () => window.removeEventListener(ONTOLOGY_SAVED, saved);
  }, [workspace.id, sid, active, load]);
  return {
    draft,
    setDraft,
    error,
    load,
    sessionId: sid,
    suffix: sid ? "?session=" + sid : "",
  };
}
