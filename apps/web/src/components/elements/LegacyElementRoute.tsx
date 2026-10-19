import { Navigate, useParams, useSearchParams } from "react-router-dom";
import { usePageActive } from "../../hooks/usePageTab";
import type { ElementTab } from "../../lib/elementInspector";

/** Keep old bookmarks, including dataset suggestions and numbered editor steps. */
export function LegacyElementRoute({
  relation = false,
  editing = false,
}: {
  relation?: boolean;
  editing?: boolean;
}) {
  const { workspaceId, typeId = "" } = useParams();
  const [params] = useSearchParams();
  const active = usePageActive();
  if (!active) return null;
  const next = new URLSearchParams(params);
  const steps: ElementTab[] = relation
    ? ["basic", "endpoints", "mapping"]
    : ["basic", "mapping", "properties", "mapping", "relations"];
  next.set("inspect", `${relation ? "link_type" : "object_type"}:${typeId}`);
  next.set("inspectSource", params.get("session") ? "session" : "published");
  if (params.get("session")) next.set("inspectSession", params.get("session")!);
  if (editing) {
    next.set("inspectMode", "edit");
    next.set("inspectTab", steps[Number(params.get("step") ?? 0)] ?? "basic");
  }
  next.delete("step");
  if (relation) next.set("catalogTab", "relations");
  return (
    <Navigate
      replace
      to={`/workspaces/${workspaceId}/objects?${next}`}
    />
  );
}
