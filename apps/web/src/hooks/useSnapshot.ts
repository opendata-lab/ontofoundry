import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, modelingApi } from "../api/client";
import type { Draft, Workspace } from "../api/types";
import { usePageActive } from "./usePageTab";

export function useSnapshot(workspace: Workspace) {
  const active = usePageActive();
  const [params] = useSearchParams();
  const sid = params.get("session");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(() => {
    setError("");
    const empty: Draft = {
      schema_version: "1",
      workspace_id: workspace.id,
      object_types: [],
      link_types: [],
      objects: [],
      links: [],
      mappings: [],
    };
    if (sid && workspace.role)
      modelingApi
        .get(workspace.id, sid)
        .then((s) => setDraft(s.draft))
        .catch((e: Error) => setError(e.message));
    else if (workspace.role)
      modelingApi
        .snapshot(workspace.id)
        .then(setDraft)
        .catch((e: Error) => setError(e.message));
    else if (!workspace.current_version) setDraft(empty);
    else
      api
        .types(workspace.id)
        .then((r) =>
          setDraft({
            ...empty,
            object_types: r.items.filter((t) => t.kind === "object_type"),
            link_types: r.items.filter((t) => t.kind === "link_type"),
          }),
        )
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
