import type {
  LegacyDraft,
  NativeDraft,
  LinkTypeElement,
  ObjectTypeElement,
  PropertyElement,
} from "../api/types";
import type { ElementRequest } from "./elementInspector";

export type ElementType = ObjectTypeElement | LinkTypeElement;
export type PanelProps = {
  draft: LegacyDraft;
  nativeDraft?: NativeDraft;
  type: ElementType;
  editing: boolean;
  canEdit?: boolean;
  saveError?: string;
  requestEdit?: () => void;
  saveDraft?: (draft: LegacyDraft) => Promise<boolean>;
  change: (next: LegacyDraft) => void;
  open: (request: ElementRequest) => void;
};
export const VALUE_KINDS: Record<string, string> = {
  string: "文本",
  integer: "整数",
  decimal: "小数",
  float: "浮点数",
  boolean: "布尔",
  date: "日期",
  datetime: "日期时间",
};
export const MULTIPLICITY: Record<string, string> = {
  many_to_many: "多对多",
  many_to_one: "多对一",
  one_to_many: "一对多",
  one_to_one: "一对一",
};
export function isObject(type: ElementType): type is ObjectTypeElement {
  return "extends" in type;
}
export function changeType(
  { draft, type, change }: PanelProps,
  patch: Partial<ElementType>,
) {
  const key = isObject(type)
    ? type.concept_kind === "value_type"
      ? "value_types"
      : "object_types"
    : "link_types";
  change({
    ...draft,
    [key]: (draft[key] ?? []).map((item) =>
      item.id === type.id ? { ...item, ...patch } : item,
    ),
  });
}
export function inheritedProperties(
  draft: LegacyDraft,
  type: ObjectTypeElement,
) {
  const seenTypes = new Set([type.id]);
  const seenProps = new Set(
    draft.properties
      .filter((p) => p.owner_type_id === type.id)
      .map((p) => p.technical_name),
  );
  const queue = [...type.extends];
  const rows: { property: PropertyElement; owner: ObjectTypeElement }[] = [];
  while (queue.length) {
    const id = queue.shift()!;
    if (seenTypes.has(id)) continue;
    seenTypes.add(id);
    const owner = draft.object_types.find((t) => t.id === id);
    if (!owner) continue;
    for (const property of draft.properties.filter(
      (p) => p.owner_type_id === id,
    )) {
      if (seenProps.has(property.technical_name)) continue;
      seenProps.add(property.technical_name);
      rows.push({ property, owner });
    }
    queue.push(...owner.extends);
  }
  return rows;
}
/** Breadth-first lineage, stable and cycle-safe for multiple inheritance. */
export function objectLineage(draft: LegacyDraft, type: ObjectTypeElement) {
  const ids = new Set<string>();
  const queue = [type.id];
  while (queue.length) {
    const id = queue.shift()!;
    if (ids.has(id)) continue;
    ids.add(id);
    queue.push(...(draft.object_types.find((o) => o.id === id)?.extends ?? []));
  }
  return ids;
}
export const relationSource = (relation: LinkTypeElement) =>
  relation.source_type_id || relation.owner_ref?.ref || "";
export const relationTarget = (relation: LinkTypeElement) =>
  relation.target_type_id ||
  relation.roles?.find((r) => r.concept.kind === "object_type")?.concept.ref ||
  "";
export function relationObjects(relation: LinkTypeElement) {
  return [
    ...new Set(
      [
        relation.owner_ref?.ref ?? relation.source_type_id,
        ...(relation.roles
          ? relation.roles
              .filter((r) => r.concept.kind === "object_type")
              .map((r) => r.concept.ref)
          : [relation.target_type_id]),
      ].filter(Boolean),
    ),
  ];
}
export function relationsFor(draft: LegacyDraft, type: ObjectTypeElement) {
  const lineage = objectLineage(draft, type);
  return draft.link_types.flatMap((definition) => {
    const ends = relationObjects(definition);
    const direct = ends.includes(type.id);
    const inheritedFrom = direct
      ? undefined
      : [...lineage].slice(1).find((id) => ends.includes(id));
    if (!direct && !inheritedFrom) return [];
    return [
      {
        definition,
        inherited: !!inheritedFrom,
        inheritedFrom,
        incoming: relationSource(definition) !== (inheritedFrom ?? type.id),
      },
    ];
  });
}
export function rulesFor(draft: LegacyDraft, type: ElementType) {
  const lineage = isObject(type)
    ? objectLineage(draft, type)
    : new Set([type.id]);
  const properties = draft.properties.filter((p) =>
    lineage.has(p.owner_type_id),
  );
  const links = isObject(type)
    ? relationsFor(draft, type)
    : [{ definition: type, inherited: false }];
  const actions = draft.actions.filter((a) => a.input_type_id === type.id);
  const rank = (kind: string) =>
    kind === "object_type" || kind === "value_type"
      ? 0
      : kind === "property"
        ? 1
        : kind === "link_type"
          ? 2
          : 3;
  return draft.rules
    .filter(
      (r) =>
        ((r.owner_kind === "object_type" || r.owner_kind === "value_type") &&
          lineage.has(r.owner_id)) ||
        (r.owner_kind === "property" &&
          properties.some((p) => p.id === r.owner_id)) ||
        (r.owner_kind === "link_type" &&
          links.some((l) => l.definition.id === r.owner_id)) ||
        (r.owner_kind === "action" && actions.some((a) => a.id === r.owner_id)),
    )
    .sort((a, b) => rank(a.owner_kind) - rank(b.owner_kind));
}
