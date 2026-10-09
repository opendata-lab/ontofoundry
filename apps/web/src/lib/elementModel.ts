import type {
  LegacyDraft,
  LinkTypeElement,
  ObjectTypeElement,
  PropertyElement,
} from "../api/types";
import type { ElementRequest } from "./elementInspector";

export type ElementType = ObjectTypeElement | LinkTypeElement;
export type PanelProps = {
  draft: LegacyDraft;
  type: ElementType;
  editing: boolean;
  change: (next: LegacyDraft) => void;
  open: (request: ElementRequest) => void;
};
export const VALUE_KINDS: Record<string, string> = {
  string: "文本",
  integer: "整数",
  decimal: "小数",
  float: "浮点数",
  boolean: "布尔值",
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
  const key = isObject(type) ? type.concept_kind === "value_type" ? "value_types" : "object_types" : "link_types";
  change({
    ...draft,
    [key]: (draft[key] ?? []).map((item) =>
      item.id === type.id ? { ...item, ...patch } : item,
    ),
  });
}
export function inheritedProperties(draft: LegacyDraft, type: ObjectTypeElement) {
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
export function rulesFor(draft: LegacyDraft, type: ElementType) {
  const props = new Set(
    draft.properties
      .filter((p) => p.owner_type_id === type.id)
      .map((p) => p.id),
  );
  const actions = new Set(
    draft.actions.filter((a) => a.input_type_id === type.id).map((a) => a.id),
  );
  return draft.rules.filter(
    (r) =>
      (r.owner_kind === (isObject(type) ? "object_type" : "link_type") &&
        r.owner_id === type.id) ||
      (r.owner_kind === "property" && props.has(r.owner_id)) ||
      (r.owner_kind === "action" && actions.has(r.owner_id)),
  );
}
