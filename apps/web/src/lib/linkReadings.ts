import type { Draft, LinkType } from "../api/types";
import { byId } from "./coreModel";

/** Readings retain complete sentences; direction follows the first endpoint. */
export function isForwardReading(reading: string): boolean {
  const source = reading.indexOf("{source}");
  const target = reading.indexOf("{target}");
  return target < 0 || (source >= 0 && source < target);
}

export function renderLinkReading(draft: Draft, link: LinkType, reading: string): string {
  const source = link.source_role_name || byId(draft.object_types, link.source_type_id)?.name || "来源对象";
  const target = link.target_role_name || byId(draft.object_types, link.target_type_id)?.name || "目标对象";
  return reading.replace(/\{(source|target)\}/g, (_, endpoint: string) => endpoint === "source" ? source : target);
}

export const readingEditorText = (reading: string) => reading.replaceAll("{source}", "{来源}").replaceAll("{target}", "{目标}");
export const storedReading = (reading: string) => reading.replaceAll("{来源}", "{source}").replaceAll("{目标}", "{target}");
