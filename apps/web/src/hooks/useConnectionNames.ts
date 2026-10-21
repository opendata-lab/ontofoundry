import { useEffect, useState } from "react";
import { catalogApi } from "../api/client";
import { METADATA_SYNCED } from "../lib/metadataSync";

/** Connection names by id, so a stored connection_id reads as the name the user picked. */
export function useConnectionNames(workspaceId: string) {
  const [names, setNames] = useState<Map<string, string>>(() => new Map());
  useEffect(() => {
    let live = true;
    const load = () => Promise.resolve()
      .then(() => catalogApi.connections(workspaceId))
      .then(({ items }) => { if (live) setNames(new Map(items.map((c) => [c.id, c.name]))); })
      // Names are a display aid; an unreadable list keeps the raw value.
      .catch(() => undefined);
    void load();
    window.addEventListener(METADATA_SYNCED, load);
    return () => { live = false; window.removeEventListener(METADATA_SYNCED, load); };
  }, [workspaceId]);
  return names;
}
