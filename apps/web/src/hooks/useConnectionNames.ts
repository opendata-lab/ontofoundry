import { useLayoutEffect, useState } from "react";
import { catalogApi } from "../api/client";
import { METADATA_SYNCED } from "../lib/metadataSync";

/** Connection names by id, so a stored connection_id reads as the name the user picked. */
export function useConnectionNames(workspaceId: string, active = true) {
  const [names, setNames] = useState<Map<string, string>>(() => new Map());
  useLayoutEffect(() => {
    if (!active) return;
    let live = true;
    const load = () => Promise.resolve()
      .then(() => live ? catalogApi.connections(workspaceId) : null)
      .then((result) => { if (live && result) setNames(new Map(result.items.map((c) => [c.id, c.name]))); })
      // Names are a display aid; an unreadable list keeps the raw value.
      .catch(() => undefined);
    void load();
    window.addEventListener(METADATA_SYNCED, load);
    return () => { live = false; window.removeEventListener(METADATA_SYNCED, load); };
  }, [workspaceId, active]);
  return names;
}
