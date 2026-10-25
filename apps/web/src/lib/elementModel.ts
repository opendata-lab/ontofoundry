import type { Draft, LinkType, ObjectType, Property, Rule, UUID } from "../api/types";
import {
  effectiveLinks,
  effectiveProperties,
  byId,
  effectiveRules,
  isA,
  lineage,
  rulesOfLink,
  type EffectiveLink,
} from "./coreModel";
import type { ElementRequest } from "./elementInspector";

export { MULTIPLICITY, VALUE_KINDS } from "./coreModel";

/** The two definitions that open in the element inspector with tabs. */
export type ElementType = ObjectType | LinkType;

/** What every inspector panel receives; `type` is the inspected element. */
export type PanelProps<T = ElementType> = {
  draft: Draft;
  type: T;
  editing: boolean;
  canEdit: boolean;
  sessionId: string | null;
  versionId?: string;
  partialRead?: boolean;
  change: (next: Draft) => void;
  open: (request: ElementRequest) => void;
};

export function isObject(type: ElementType): type is ObjectType {
  return "derived_by" in type;
}

/** Replaces the inspected object or link with a patched copy. */
export function changeType<T extends ElementType>({ draft, type, change }: PanelProps<T>, patch: Partial<T>) {
  if (isObject(type)) {
    change({
      ...draft,
      object_types: draft.object_types.map((item) =>
        item.id === type.id ? ({ ...item, ...patch } as ObjectType) : item,
      ),
    });
  } else {
    change({
      ...draft,
      link_types: draft.link_types.map((item) =>
        item.id === type.id ? ({ ...item, ...patch } as LinkType) : item,
      ),
    });
  }
}

/** Inherited (not local) properties with the ancestor that defines them. */
export function inheritedProperties(draft: Draft, type: ObjectType) {
  return effectiveProperties(draft, type.id)
    .filter((p) => p.inheritedFrom)
    .map((p) => ({
      property: p.definition,
      owner: draft.object_types.find((o) => o.id === p.inheritedFrom)!,
    }))
    .filter((row) => row.owner);
}

export function ownProperties(draft: Draft, type: ObjectType): Property[] {
  return draft.properties.filter((p) => p.owner_type_id === type.id);
}

export function objectLineage(draft: Draft, type: ObjectType): Set<UUID> {
  return new Set(lineage(draft, type.id));
}

export type RelationRow = {
  definition: LinkType;
  inherited: boolean;
  inheritedFrom: UUID | undefined;
  /** The inspected object is the link's target. */
  incoming: boolean;
};

export function relationsFor(draft: Draft, type: ObjectType): RelationRow[] {
  return effectiveLinks(draft, type.id, true).map((link: EffectiveLink) => ({
    definition: link.definition,
    inherited: link.inheritedFrom !== null,
    inheritedFrom: link.inheritedFrom ?? undefined,
    incoming: link.direction === "reverse",
  }));
}

const RULE_RANK: Record<Rule["owner_kind"], number> = { object_type: 0, property: 1, link_type: 2, value_type: 3 };

export function rulesFor(draft: Draft, type: ElementType): Rule[] {
  const rules = isObject(type)
    ? effectiveRules(draft, type.id).map((r) => r.definition)
    : rulesOfLink(draft, type.id);
  return [...rules].sort((a, b) => RULE_RANK[a.owner_kind] - RULE_RANK[b.owner_kind]);
}

type TreeNode = { value: string; title: string; children: TreeNode[]; disabled?: boolean };


/** Objects as an inheritance tree; `exclude` and its descendants cannot be picked. */
export function objectTree(draft: Draft, exclude?: UUID): TreeNode[] {
  const build = (parent: string | null): TreeNode[] =>
    draft.object_types
      .filter((o) => (o.extends ?? null) === parent || (parent === null && o.extends && !byId(draft.object_types, o.extends)))
      .map((o) => ({
        value: o.id,
        title: (o.display_name || o.name) || o.name || "未命名对象",
        disabled: !!exclude && isA(draft, o.id, exclude),
        children: build(o.id),
      }));
  return build(null);
}
