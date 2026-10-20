import { Navigate, useParams, useSearchParams } from "react-router-dom";
import { usePageActive } from "../../hooks/usePageTab";
import { useWorkspaceContext } from "../../hooks/useWorkspaceContext";
import { elementHref, legacyInspectRequest, type ElementTab } from "../../lib/elementInspector";

/** Keep old bookmarks, including dataset suggestions and numbered editor steps. */
export function LegacyElementRoute({
  relation = false,
  editing = false,
}: {
  relation?: boolean;
  editing?: boolean;
}) {
  const { typeId = "" } = useParams();
  const [params] = useSearchParams();
  const { workspace } = useWorkspaceContext();
  const active = usePageActive();
  if (!active) return null;
  const steps: ElementTab[] = relation
    ? ["basic", "endpoints", "mapping"]
    : ["basic", "mapping", "properties", "mapping", "relations"];
  const to = elementHref(workspace.id, {
    kind: relation ? "link_type" : "object_type",
    id: typeId,
    sessionId: params.get("session"),
    ...(editing ? { mode: "edit" as const, tab: steps[Number(params.get("step") ?? 0)] ?? "basic" } : {}),
  });
  return <Navigate replace to={to} />;
}

/** Links copied from the former URL-backed popup open the element's page instead. */
export function LegacyInspectRedirect() {
  const [params] = useSearchParams();
  const { workspace } = useWorkspaceContext();
  const active = usePageActive();
  const request = legacyInspectRequest(params);
  if (!active || !request) return null;
  return <Navigate replace to={elementHref(workspace.id, request)} />;
}
