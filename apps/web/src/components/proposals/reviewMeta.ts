import type { CoreElement, Draft, FieldChange, MaterialObject, ProposalItem, TargetKind } from "../../api/types";
import { byId } from "../../lib/coreModel";
import { documentDisplayText } from "../../lib/instanceDisplay";
import { FIELD_LABELS, KIND, STATUS } from "./elementMeta";

export const reviewKindName = (kind: TargetKind) => KIND[kind].label;
export const REVIEW_FIELD_LABELS = FIELD_LABELS;

export function valueText(value: unknown): string {
  if (value == null || value === "" || (Array.isArray(value) && !value.length)) return "（空）";
  if (typeof value === "boolean") return value ? "是" : "否";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

const field = (element: CoreElement | null, key: string): unknown =>
  element ? (element as unknown as Record<string, unknown>)[key] : undefined;

export function reviewChanges(item: ProposalItem): FieldChange[] {
  const changes =
    item.operation === "update"
      ? item.field_changes
      : Object.entries((item.after ?? item.before ?? {}) as Record<string, unknown>)
          .filter(([path]) => path !== "id")
          .map(([path, value]) => ({
            path,
            before: item.operation === "create" ? null : (value as FieldChange["before"]),
            after: item.operation === "delete" ? null : (value as FieldChange["after"]),
          }));
  return changes.filter((change) => change.path !== "evidence");
}

/** Technical name of a property's owner object, from the batch or the draft. */
export function ownerName(item: ProposalItem, items: ProposalItem[], draft: Draft): string {
  if (item.target_kind !== "property") return item.owner_label ?? "";
  const element = item.after ?? item.before;
  const ownerId = field(element, "owner_type_id") as string | undefined;
  const proposal = items.find((c) => c.target_kind === "object_type" && c.target_id === ownerId);
  const owner = proposal?.after ?? proposal?.before;
  if (owner) return String(field(owner, "name") ?? item.owner_label ?? "");
  return byId(draft.object_types, ownerId)?.name ?? item.owner_label ?? "";
}

export function technicalName(item: ProposalItem, items: ProposalItem[], draft: Draft): string {
  const value = field(item.after, "name") ?? field(item.before, "name") ?? item.display_name;
  const name = typeof value === "string" && value ? value : item.display_name;
  const owner = item.target_kind === "property" ? ownerName(item, items, draft) : "";
  return owner ? `${owner}.${name}` : name;
}

/** Text a search box matches. */
export function searchText(item: ProposalItem, items: ProposalItem[], draft: Draft) {
  return [
    item.display_name,
    field(item.before, "display_name"),
    field(item.after, "display_name"),
    field(item.before, "name"),
    field(item.after, "name"),
    technicalName(item, items, draft),
    item.owner_label,
  ]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase();
}

export function requiredIds(item: ProposalItem): string[] {
  return [...new Set([...item.depends_on, ...item.dependency_group])].filter((id) => id !== item.id);
}

/** Block missing, rejected or stale dependencies, including transitive groups. */
export function acceptanceBlock(item: ProposalItem, byIdMap: Map<string, ProposalItem>, visited = new Set<string>()): string {
  if (item.status === "accepted") return "";
  if (item.status !== "pending") return item.status_reason || `提案${STATUS[item.status]}`;
  if (visited.has(item.id)) return "";
  visited.add(item.id);
  const source = item.source_diagnostics?.find((d) => d.severity === "error");
  if (source) return `数据来源未就绪：${source.message}`;
  for (const id of requiredIds(item)) {
    const dependency = byIdMap.get(id);
    if (!dependency) return "依赖提案缺失";
    const blocked = acceptanceBlock(dependency, byIdMap, visited);
    if (blocked) return `依赖项「${dependency.display_name}」${blocked}`;
  }
  return "";
}

export type ReviewDecision = "accept" | "reject" | "restore";

/** Share the same dependency expansion for row, modal and bulk decisions. */
export function decisionIds(items: ProposalItem[], requested: string[], decision: ReviewDecision): string[] {
  const byIdMap = new Map(items.map((item) => [item.id, item]));
  const ids = new Set<string>();
  const accept = (item: ProposalItem) => {
    if (item.status !== "pending" || ids.has(item.id)) return;
    ids.add(item.id);
    for (const id of requiredIds(item)) {
      const dependency = byIdMap.get(id);
      if (dependency) accept(dependency);
    }
  };
  for (const id of requested) {
    const item = byIdMap.get(id);
    if (!item) continue;
    if (decision === "accept") {
      if (item.status === "pending" && !acceptanceBlock(item, byIdMap)) accept(item);
    } else if (
      decision === "restore" ? item.status === "rejected" : ["pending", "stale", "conflict", "accepted"].includes(item.status)
    )
      ids.add(id);
  }
  if (decision === "reject") {
    let changed = true;
    while (changed) {
      changed = false;
      for (const item of items) {
        if (item.status === "accepted" && !ids.has(item.id) && item.depends_on.some((id) => ids.has(id))) {
          ids.add(item.id);
          changed = true;
        }
      }
    }
  }
  return [...ids];
}

/** The existing fact with the proposal's non-empty values and new evidence added. */
export function mergedFact(existing: MaterialObject, proposed: MaterialObject): MaterialObject {
  const values = { ...existing.values };
  for (const [key, value] of Object.entries(proposed.values)) {
    if (value !== null && value !== "") values[key] = value;
  }
  const known = new Set(existing.evidence.map((e) => e.id));
  return {
    ...existing,
    values,
    evidence: [...existing.evidence, ...proposed.evidence.filter((e) => !known.has(e.id))],
  };
}

/** Names of draft elements and of elements created in the batch, by id. */
export function elementNames(draft: Draft, items: ProposalItem[]) {
  const names = new Map<string, string>();
  for (const key of ["object_types", "properties", "link_types", "rules", "metrics", "datasets"] as const)
    for (const element of draft[key] as { id: string; name: string; display_name?: string | null }[]) names.set(element.id, element.display_name || element.name);
  for (const fact of draft.material_objects) names.set(fact.id, documentDisplayText(draft, fact));
  for (const item of items) names.set(item.target_id, item.display_name);
  return names;
}
