import type { ModelingSession, TargetKind } from "../api/types";

export type ElementTab =
  | "basic"
  | "properties"
  | "endpoints"
  | "mapping"
  | "relations"
  | "rules"
  | "members"
  | "instances"
  | "definition"
  | "preview"
  | "fields"
  | "columns"
  | "source"
  | "references";
export type ElementRequest = {
  kind: TargetKind;
  id: string;
  tab?: ElementTab;
  mode?: "view" | "edit";
  sessionId?: string | null;
  previewHash?: string;
  /** For a new link or metric: the object or dataset it starts from. */
  owner?: string;
};
/** The address of an element's own detail page. */
export function elementHref(workspaceId: string, request: ElementRequest) {
  const params = new URLSearchParams();
  if (request.tab) params.set("tab", request.tab);
  if (request.mode === "edit") params.set("mode", "edit");
  if (request.owner) params.set("owner", request.owner);
  if (request.sessionId) params.set("session", request.sessionId);
  if (request.previewHash) params.set("preview", request.previewHash);
  const query = params.toString();
  return `/workspaces/${workspaceId}/elements/${request.kind}/${encodeURIComponent(request.id)}${query ? `?${query}` : ""}`;
}

/** Links copied before detail pages existed carried the element in `?inspect=`. */
export function legacyInspectRequest(params: URLSearchParams): ElementRequest | null {
  const target = params.get("inspect");
  const split = target?.indexOf(":") ?? -1;
  if (!target || split < 1) return null;
  const source = params.get("inspectSource");
  return {
    kind: target.slice(0, split) as TargetKind,
    id: target.slice(split + 1),
    tab: (params.get("inspectTab") ?? undefined) as ElementTab | undefined,
    mode: params.get("inspectMode") === "edit" ? "edit" : undefined,
    owner: params.get("inspectOwner") ?? undefined,
    sessionId: source === "published" ? null : (params.get("inspectSession") ?? params.get("session")),
    previewHash: params.get("inspectPreviewHash") ?? undefined,
  };
}

export const ONTOLOGY_SAVED = "ontofoundry:element-saved";
export type OntologySaved = {
  workspaceId: string;
  session: ModelingSession | null;
};
export function notifyOntologySaved(detail: OntologySaved) {
  window.dispatchEvent(
    new CustomEvent<OntologySaved>(ONTOLOGY_SAVED, { detail }),
  );
}
