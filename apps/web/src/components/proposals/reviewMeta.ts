import type { Draft, FieldChange, ProposalItem, TargetKind } from "../../api/types";
import { FIELD_LABELS, KIND, STATUS } from "./elementMeta";

export const reviewKindName = (kind: TargetKind) => kind === "action" ? "动作" : KIND[kind].label;
export const REVIEW_FIELD_LABELS: Record<string, string> = {
  ...FIELD_LABELS,
  owner_type_id: "所属实体",
  source_type_id: "源实体",
  target_type_id: "目标实体",
  owner_ref: "所属实体",
  concept: "概念",
  roles: "角色",
};

export function valueText(value: unknown): string {
  if (value == null || value === "" || (Array.isArray(value) && !value.length)) return "（空）";
  if (typeof value === "boolean") return value ? "是" : "否";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

export function reviewChanges(item: ProposalItem): FieldChange[] {
  const changes = item.operation === "update"
    ? item.field_changes
    : Object.entries(item.after ?? item.before ?? {})
        .filter(([path]) => path !== "id")
        .map(([path, value]) => ({
          path,
          before: item.operation === "create" ? null : value,
          after: item.operation === "delete" ? null : value,
        }));
  return changes.filter((change) => change.path !== "evidence");
}

export function ownerName(item: ProposalItem, items: ProposalItem[], draft: Draft): string {
  const element = item.before ?? item.after ?? {};
  const ref = element.owner_ref as { ref?: string; concept?: string } | undefined;
  const ownerId = ref?.ref ?? element.owner_type_id;
  const ownerProposal = items.find((candidate) =>
    ["object_type", "value_type", "link_type"].includes(candidate.target_kind) &&
    (ownerId ? candidate.target_id === ownerId : candidate.before?.name === item.owner_label),
  );
  const owner = ownerProposal?.before ?? ownerProposal?.after;
  if (owner) return String(owner.technical_name || owner.concept || item.owner_label || "");
  const draftOwner = [...draft.object_types, ...(draft.value_types ?? []), ...draft.link_types]
    .find((candidate) => ownerId ? candidate.id === ownerId : candidate.name === item.owner_label);
  return draftOwner?.technical_name || ref?.concept || item.owner_label || "";
}

export function technicalName(item: ProposalItem, items: ProposalItem[], draft: Draft): string {
  const value = item.before?.technical_name || item.before?.concept ||
    item.after?.technical_name || item.after?.concept || item.display_name;
  const name = typeof value === "string" ? value : item.display_name;
  const owner = item.target_kind === "property" ? ownerName(item, items, draft) : "";
  return owner ? `${owner}.${name}` : name;
}

export function requiredIds(item: ProposalItem): string[] {
  return [...new Set([...item.depends_on, ...item.dependency_group])].filter((id) => id !== item.id);
}

/** Block missing, rejected or stale dependencies, including transitive groups. */
export function acceptanceBlock(
  item: ProposalItem,
  byId: Map<string, ProposalItem>,
  visited = new Set<string>(),
): string {
  if (item.status === "accepted") return "";
  if (item.status !== "pending") return item.status_reason || `提案${STATUS[item.status]}`;
  if (visited.has(item.id)) return "";
  visited.add(item.id);
  for (const id of requiredIds(item)) {
    const dependency = byId.get(id);
    if (!dependency) return "依赖提案缺失";
    const blocked = acceptanceBlock(dependency, byId, visited);
    if (blocked) return `依赖项「${dependency.display_name}」${blocked}`;
  }
  return "";
}

export type ReviewDecision = "accept" | "reject" | "restore";

/** Share the same dependency expansion for row, modal and bulk decisions. */
export function decisionIds(items: ProposalItem[], requested: string[], decision: ReviewDecision): string[] {
  const byId = new Map(items.map((item) => [item.id, item]));
  const ids = new Set<string>();
  const accept = (item: ProposalItem) => {
    if (item.status !== "pending" || ids.has(item.id)) return;
    ids.add(item.id);
    for (const id of requiredIds(item)) {
      const dependency = byId.get(id);
      if (dependency) accept(dependency);
    }
  };
  for (const id of requested) {
    const item = byId.get(id);
    if (!item) continue;
    if (decision === "accept") {
      if (item.status === "pending" && !acceptanceBlock(item, byId)) accept(item);
    } else if (decision === "restore" ? item.status === "rejected" :
      ["pending", "stale", "conflict", "accepted"].includes(item.status)) ids.add(id);
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
