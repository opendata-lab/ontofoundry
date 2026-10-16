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
  | "columns";
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
const INSPECT_KEYS = [
  "inspect",
  "inspectTab",
  "inspectMode",
  "inspectSession",
  "inspectSource",
  "inspectPreviewHash",
  "inspectOwner",
  "mapping_source",
  "mapping_table",
  "mapping_schema",
];
export function withoutInspector(href: string) {
  const url = new URL(href, "http://local");
  INSPECT_KEYS.forEach((key) => url.searchParams.delete(key));
  return url.pathname + url.search + url.hash;
}
export function inspectorHref(href: string, request: ElementRequest) {
  const url = new URL(withoutInspector(href), "http://local");
  url.searchParams.set("inspect", `${request.kind}:${request.id}`);
  if (request.tab) url.searchParams.set("inspectTab", request.tab);
  if (request.mode === "edit") url.searchParams.set("inspectMode", "edit");
  if (request.owner) url.searchParams.set("inspectOwner", request.owner);
  const session =
    request.sessionId === undefined
      ? url.searchParams.get("session")
      : request.sessionId;
  url.searchParams.set("inspectSource", session ? "session" : "published");
  if (session) url.searchParams.set("inspectSession", session);
  if (request.previewHash) {
    url.searchParams.set("inspectSource", "preview");
    url.searchParams.set("inspectPreviewHash", request.previewHash);
  }
  return url.pathname + url.search + url.hash;
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
