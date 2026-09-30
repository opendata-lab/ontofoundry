import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, modelingApi } from "../api/client";
import type { DraftView, Workspace } from "../api/types";
import { emptyDraft, toView, viewFromTypes } from "../lib/draftView";
import { usePageActive } from "./usePageTab";

export function useSnapshot(workspace: Workspace) {
  const active = usePageActive();
  const [params] = useSearchParams();
  const sid = params.get("session");
  const [draft, setDraft] = useState<DraftView | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    setError("");
    const empty = toView(emptyDraft(workspace.id));
    if (sid && workspace.role)
      modelingApi
        .get(workspace.id, sid)
        .then((s) => setDraft(toView(s.draft)))
        .catch((e: Error) => setError(e.message));
    else if (workspace.role)
      modelingApi
        .snapshot(workspace.id)
        .then((d) => setDraft(toView(d)))
        .catch((e: Error) => setError(e.message));
    else if (!workspace.current_version) setDraft(empty);
    else
      api
        .types(workspace.id)
        .then((r) => setDraft(viewFromTypes(workspace.id, r.items)))
        .catch((e: Error) => setError(e.message));
  }, [workspace.id, workspace.role, workspace.current_version, sid]);
  useEffect(() => {
    if (active) load();
  }, [load, active]);
  return {
    draft,
    setDraft,
    error,
    load,
    sessionId: sid,
    suffix: sid ? "?session=" + sid : "",
  };
}
