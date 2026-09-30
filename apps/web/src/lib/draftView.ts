import type {
  AttributeDefinition,
  Draft,
  DraftView,
  LinkDefinition,
  ObjectDefinition,
  OntologyType,
  RuleElement,
} from "../api/types";

/**
 * The one place that knows how a stored v2 Draft maps onto the view the UI
 * edits. Components read DraftView; anything that saves converts back with
 * fromView, which keeps every existing rule id whose owner, kind and
 * expression are unchanged, and leaves actions, action-owned rules and
 * evidence untouched.
 */

export function emptyDraft(workspaceId: string): Draft {
  return {
    schema_version: "2",
    workspace_id: workspaceId,
    ontology_requires: [],
    object_types: [],
    properties: [],
    link_types: [],
    rules: [],
    actions: [],
    material_objects: [],
    material_links: [],
    mappings: [],
  };
}

type RuleKind = RuleElement["rule_kind"];
const FIELD: Record<RuleKind, "requires" | "derived_by"> = {
  constraint: "requires",
  derivation: "derived_by",
};

export function expressionsOf(
  draft: Draft,
  ownerId: string,
  kind: RuleKind,
): string[] {
  return draft.rules
    .filter((r) => r.owner_id === ownerId && r.rule_kind === kind)
    .map((r) => r.expression);
}

export function propertiesOf(draft: Draft, typeId: string) {
  return draft.properties.filter((p) => p.owner_type_id === typeId);
}

export function toView(draft: Draft): DraftView {
  const rules = (id: string) => ({
    requires: expressionsOf(draft, id, "constraint"),
    derived_by: expressionsOf(draft, id, "derivation"),
  });
  return {
    workspace_id: draft.workspace_id,
    requires: draft.ontology_requires ?? [],
    object_types: draft.object_types.map((type) => {
      const { evidence: _evidence, ...rest } = type;
      void _evidence;
      return {
        ...rest,
        ...rules(type.id),
        attributes: propertiesOf(draft, type.id).map((p) => {
          const { owner_type_id: _owner, evidence: _ev, ...attribute } = p;
          void _owner;
          void _ev;
          return { ...attribute, ...rules(p.id) } as AttributeDefinition;
        }),
      };
    }),
    link_types: draft.link_types.map((link) => {
      const { evidence: _evidence, ...rest } = link;
      void _evidence;
      return { ...rest, ...rules(link.id) };
    }),
    objects: draft.material_objects,
    links: draft.material_links,
    mappings: draft.mappings,
  };
}

function ruleTechnicalName(kind: RuleKind, id: string) {
  return `${kind}_${id.replace(/-/g, "").slice(0, 8)}`;
}

export function fromView(original: Draft, view: DraftView): Draft {
  const byId = <T extends { id: string }>(items: T[]) =>
    new Map(items.map((item) => [item.id, item]));
  const oldTypes = byId(original.object_types);
  const oldProps = byId(original.properties);
  const oldLinks = byId(original.link_types);
  const clean = (lines: string[] | undefined) =>
    (lines ?? []).map((line) => line.trim()).filter(Boolean);

  const rules: RuleElement[] = [];
  const restate = (
    ownerKind: RuleElement["owner_kind"],
    ownerId: string,
    label: string,
    source: { requires?: string[]; derived_by?: string[] },
  ) => {
    for (const kind of ["constraint", "derivation"] as RuleKind[]) {
      const previous = original.rules.filter(
        (r) => r.owner_id === ownerId && r.rule_kind === kind,
      );
      const seen = new Set<string>();
      clean(source[FIELD[kind]]).forEach((expression, index) => {
        if (seen.has(expression)) return;
        seen.add(expression);
        const kept = previous.find((r) => r.expression === expression);
        if (kept) {
          rules.push(kept);
          return;
        }
        const id = crypto.randomUUID();
        rules.push({
          id,
          name: `${label}·${kind === "constraint" ? "约束" : "派生"}${index + 1}`,
          technical_name: ruleTechnicalName(kind, id),
          description: "",
          owner_kind: ownerKind,
          owner_id: ownerId,
          rule_kind: kind,
          expression,
          verbalizes: [],
          evidence: [],
        });
      });
    }
  };

  const properties: Draft["properties"] = [];
  const objectTypes = view.object_types.map((type) => {
    const {
      attributes,
      requires,
      derived_by,
      supertypes: _s,
      inherited_attributes: _i,
      ...rest
    } = type;
    void _s;
    void _i;
    restate("object_type", type.id, type.name, { requires, derived_by });
    for (const attribute of attributes ?? []) {
      const {
        requires: r,
        derived_by: d,
        declared_by: _declared,
        ...prop
      } = attribute;
      void _declared;
      properties.push({
        ...prop,
        verbalizes: prop.verbalizes ?? [],
        owner_type_id: type.id,
        evidence: oldProps.get(attribute.id)?.evidence ?? [],
      });
      restate("property", attribute.id, `${type.name}.${attribute.name}`, {
        requires: r,
        derived_by: d,
      });
    }
    return {
      ...rest,
      extends: rest.extends ?? [],
      evidence: oldTypes.get(type.id)?.evidence ?? [],
    };
  });
  const linkTypes = view.link_types.map((link) => {
    const { requires, derived_by, ...rest } = link;
    restate("link_type", link.id, link.name, { requires, derived_by });
    return {
      ...rest,
      evidence: oldLinks.get(link.id)?.evidence ?? [],
    };
  });
  // Action-owned rules are not part of the view; keep them as they were.
  const actionRules = original.rules.filter((r) => r.owner_kind === "action");
  return {
    ...original,
    ontology_requires: clean(view.requires),
    object_types: objectTypes,
    properties,
    link_types: linkTypes,
    rules: [...rules, ...actionRules],
    material_objects: view.objects,
    material_links: view.links,
    mappings: view.mappings,
  };
}

/** A read-only view for visitors, built from the public type catalog. */
export function viewFromTypes(
  workspaceId: string,
  items: OntologyType[],
): DraftView {
  return {
    workspace_id: workspaceId,
    requires: [],
    object_types: items.filter(
      (t): t is Extract<OntologyType, { kind: "object_type" }> =>
        t.kind === "object_type",
    ) as ObjectDefinition[],
    link_types: items.filter(
      (t): t is Extract<OntologyType, { kind: "link_type" }> =>
        t.kind === "link_type",
    ) as LinkDefinition[],
    objects: [],
    links: [],
    mappings: [],
  };
}
