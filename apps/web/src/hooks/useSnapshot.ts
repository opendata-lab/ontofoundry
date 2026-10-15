import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, modelingApi } from "../api/client";
import type { Draft, DraftView, Workspace } from "../api/types";
import { emptyDraft, toView, viewFromTypes } from "../lib/draftView";
import { usePageActive } from "./usePageTab";
import { ONTOLOGY_SAVED, type OntologySaved } from "../lib/elementInspector";

export function useSnapshot(workspace: Workspace) {
  const active = usePageActive();
  const [params] = useSearchParams();
  const sid = params.get("session");
  const [sourceDraft, setSourceDraft] = useState<Draft | null>(null);
  const [draft, setDraft] = useState<DraftView | null>(null);
  const [error, setError] = useState("");
  const request = useRef(0);
  const invalidate = useCallback(() => { request.current++; }, []);
  const load = useCallback(() => {
    const revision = ++request.current;
    setError("");
    setSourceDraft(null);
    setDraft(null);
    const accept = (source: Draft | null, view: DraftView) => {
      if (revision !== request.current) return;
      setSourceDraft(source);
      setDraft(view);
    };
    const fail = (error: Error) => {
      if (revision === request.current) setError(error.message);
    };
    const empty = toView(emptyDraft(workspace.id));
    if (sid && workspace.role)
      modelingApi
        .get(workspace.id, sid)
        .then((s) => {
          accept(s.draft, toView(s.draft));
        })
        .catch(fail);
    else if (workspace.role)
      modelingApi
        .snapshot(workspace.id)
        .then((d) => {
          accept(d, toView(d));
        })
        .catch(fail);
    else if (!workspace.current_version) accept(null, empty);
    else
      api
        .types(workspace.id)
        .then((r) => accept(null, viewFromTypes(workspace.id, r.items)))
        .catch(fail);
  }, [workspace.id, workspace.role, workspace.current_version, sid]);
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
        setSourceDraft(detail.session.draft);
        setDraft(toView(detail.session.draft));
      } else if (active && !sid) load();
    };
    window.addEventListener(ONTOLOGY_SAVED, saved);
    return () => window.removeEventListener(ONTOLOGY_SAVED, saved);
  }, [workspace.id, sid, active, load]);
  return {
    draft,
    sourceDraft,
    setDraft,
    error,
    load,
    sessionId: sid,
    suffix: sid ? "?session=" + sid : "",
  };
}
