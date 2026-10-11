/** P1 editor adapter. Native drafts remain the saved truth; simple mapping forms
 * travel separately from draft JSON. Native roles and absent fields survive edits. */
import { materialLinkEndpoints } from "./instanceGraph";
import type {
  ConceptRef, Draft, DraftView, LegacyDraft, NativeConcept,
  NativeDraft, NativeLink, NativeProperty, NativeRole, RuleElement, JoinView, RoleJoin,
} from "../api/types";

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const bases: Record<string, string> = { string: "String", integer: "Integer", decimal: "Decimal", float: "Float", boolean: "Boolean", date: "Date", datetime: "DateTime" };

export function relationReadOnly(link: { owner_ref?: ConceptRef; roles?: NativeRole[]; readonly?: boolean }) {
  return link.readonly || (!!link.owner_ref && (link.owner_ref.kind !== "object_type" || link.roles?.length !== 1 || link.roles[0].concept.kind !== "object_type"));
}

function endpointJoin(join: RoleJoin | JoinView | null | undefined, reverse: boolean): JoinView | null {
  if (!join) return null;
  if (!("owner_columns" in join)) return join;
  const [source, target] = reverse ? [join.role_columns, join.owner_columns] : [join.owner_columns, join.role_columns];
  return { source_column: source[0], target_column: target[0], ...(source.length > 1 ? { source_columns: source, target_columns: target } : {}) };
}

export function editorDraft(source: Draft): LegacyDraft {
  if (source.schema_version === "2") return structuredClone(source);
  const draft = source;
  const concepts = new Map([...draft.object_types, ...draft.value_types].map(c => [c.id, c]));
  const links = draft.link_types.map(link => {
    const binary = !relationReadOnly(link);
    const forward = link.endpoint_direction !== "reverse";
    const owner = link.owner_ref.ref;
    const extra = link.roles[0]?.concept.ref ?? "";
    return {
      ...link, description: link.description ?? "", readonly: !binary,
      source_type_id: binary ? (forward ? owner : extra) : "",
      target_type_id: binary ? (forward ? extra : owner) : "",
      multiplicity: link.legacy_multiplicity ?? (link.multiplicity === "OneToOne" ? "one_to_one" : link.multiplicity === "ManyToOne" ? "many_to_one" : ""),
      source_role_name: forward ? link.owner_role_name : link.roles[0]?.name,
      target_role_name: forward ? link.roles[0]?.name : link.owner_role_name,
      data_join: endpointJoin(draft._legacy_form?.joins[link.id], !forward),
      role_concepts: [{ id: link.owner_role_id ?? `owner:${link.id}`, name: link.owner_role_name, concept: concepts.get(owner)?.concept ?? owner, kind: link.owner_ref.kind },
        ...link.roles.map(r => ({ id: r.id, name: r.name, concept: concepts.get(r.concept.ref)?.concept ?? r.concept.ref, kind: r.concept.kind }))],
    };
  });
  return {
    schema_version: "2", workspace_id: draft.workspace_id, ontology_requires: [...draft.ontology_requires],
    value_types: draft.value_types.map(c => ({ ...c, concept_kind: "value_type", concept_context: structuredClone(draft.extension_v4.concept_context?.[c.id]), description: c.description ?? "", extends: [] })),
    object_types: draft.object_types.map(c => ({ ...c, concept_context: structuredClone(draft.extension_v4.concept_context?.[c.id]), description: c.description ?? "", extends: c.extends.filter(r => r.kind === "object_type").map(r => r.ref) })),
    properties: draft.properties.map(p => ({ ...p, owner_type_id: p.owner_ref.ref, description: p.description ?? "", value_concept: concepts.get(p.roles[0].concept.ref)?.concept ?? p.roles[0].concept.ref, target_role_name: p.roles[0].name, multiplicity: p.multiplicity === "OneToOne" ? "one_to_one" : p.multiplicity === "ManyToOne" ? "many_to_one" : null })),
    link_types: links, rules: structuredClone(draft.rules), actions: structuredClone(draft.actions),
    material_objects: structuredClone(draft.material_objects), material_links: draft.material_links.map(fact => ({ ...structuredClone(fact), ...materialLinkEndpoints(fact, draft.link_types.find(r => r.id === fact.type_id)) })),
    mappings: structuredClone(draft._legacy_form?.mappings ?? []),
    mapping_status: structuredClone(draft._legacy_form?.mapping_status),
  };
}

function field<T extends object>(result: T, previous: object | undefined, edited: object, key: string, native = false) {
  const next = (edited as Record<string, unknown>)[key];
  if (!previous || !same((previous as Record<string, unknown>)[key], next)) {
    (result as Record<string, unknown>)[key] = next;
    if (native && (previous || (next !== "" && next !== null && !same(next, [])))) {
      const node = result as { native_presence?: string[] };
      node.native_presence = [...new Set([...(node.native_presence ?? []), key])];
    }
  }
}

export function nativeFromEditor(original: Draft, edited: LegacyDraft): Draft {
  if (original.schema_version === "2") return edited;
  const result = structuredClone(original);
  const before = editorDraft(original);
  const oldConcepts = new Map(original.object_types.map(c => [c.id, c]));
  const oldProps = new Map(original.properties.map(p => [p.id, p]));
  const oldLinks = new Map(original.link_types.map(l => [l.id, l]));
  result.object_types = edited.object_types.map(c => {
    const old = oldConcepts.get(c.id);
    const { concept_context: _context, concept_kind: _kind, ...native } = c;
    void _context; void _kind;
    const node: NativeConcept = old ? structuredClone(old) : { ...native, concept: c.technical_name, extends: [], identify_by: [], requires: [], derived_by: [], native_presence: [], position: null, origin: "platform" };
    const prev = before.object_types.find(p => p.id === c.id);
    for (const key of ["name", "technical_name", "tags"]) field(node, prev, c, key);
    field(node, prev, c, "description", true);
    if (!prev || !same(prev.extends, c.extends)) { node.extends = c.extends.map(ref => ({ kind: "object_type", ref })); node.native_presence = [...new Set([...(node.native_presence ?? []), "extends"])]; }
    return node;
  });
  // Context is a platform extension keyed by stable concept ID, never a native node field.
  const contexts = structuredClone(original.extension_v4.concept_context ?? {});
  for (const concept of [...edited.object_types, ...(edited.value_types ?? [])]) {
    const previous = [...before.object_types, ...(before.value_types ?? [])].find(c => c.id === concept.id);
    if (!same(previous?.concept_context, concept.concept_context)) {
      if (concept.concept_context) contexts[concept.id] = structuredClone(concept.concept_context);
      else delete contexts[concept.id];
    }
  }
  const keptIds = new Set([...edited.object_types, ...(edited.value_types ?? [])].map(c => c.id));
  for (const key of Object.keys(contexts)) if (!keptIds.has(key)) delete contexts[key];
  if (!same(contexts, original.extension_v4.concept_context ?? {})) result.extension_v4.concept_context = contexts;
  result.properties = edited.properties.map(p => {
    const old = oldProps.get(p.id);
    const prev = before.properties.find(prop => prop.id === p.id);
    const node: NativeProperty = old ? structuredClone(old) : {
      id: p.id, name: p.name, technical_name: p.technical_name, description: p.description, tags: [], evidence: p.evidence,
      owner_ref: { kind: "object_type", ref: p.owner_type_id }, roles: [{ id: crypto.randomUUID(), concept: { kind: "builtin", ref: bases[p.value_kind] ?? "String" }, origin: "platform", position: 0, native_presence: [] }],
      value_kind: p.value_kind, required: p.required, identifier: p.identifier, requires: [], derived_by: [], verbalizes: [], multiplicity: null, origin: "platform", position: null, native_presence: [],
    };
    for (const key of ["name", "technical_name", "required", "identifier", "value_kind"]) field(node, prev, p, key);
    for (const key of ["description", "verbalizes"]) field(node, prev, p, key, true);
    if (!prev || prev.owner_type_id !== p.owner_type_id) node.owner_ref = { kind: "object_type", ref: p.owner_type_id };
    if (prev && prev.value_kind !== p.value_kind) node.roles[0].concept = { kind: "builtin", ref: bases[p.value_kind] ?? "String" };
    if (p.value_concept && (!prev || prev.value_concept !== p.value_concept)) {
      let concept = result.value_types.find(v => v.concept === p.value_concept);
      if (!concept && !Object.values(bases).includes(p.value_concept)) {
        concept = { id: crypto.randomUUID(), name: p.value_concept, technical_name: p.value_concept, concept: p.value_concept, description: null, tags: [], evidence: [], extends: [{ kind: "builtin", ref: bases[p.value_kind] ?? "String" }], identify_by: [], requires: [], derived_by: [], origin: "platform", position: null, native_presence: [] };
        result.value_types.push(concept);
      }
      node.roles[0].concept = concept ? { kind: "value_type", ref: concept.id } : { kind: "builtin", ref: p.value_concept };
    }
    if ((!prev && p.target_role_name != null) || (prev && prev.target_role_name !== p.target_role_name)) { node.roles[0].name = p.target_role_name ?? null; node.roles[0].native_presence = [...new Set([...(node.roles[0].native_presence ?? []), "name"])].filter(key => key !== "name" || p.target_role_name != null); }
    if (prev && prev.multiplicity !== p.multiplicity) node.multiplicity = p.multiplicity === "one_to_one" ? "OneToOne" : p.multiplicity ? "ManyToOne" : null;
    return node;
  });
  result.link_types = edited.link_types.map(l => {
    const old = oldLinks.get(l.id);
    if (old && relationReadOnly(old)) return structuredClone(old);
    const prev = before.link_types.find(link => link.id === l.id);
    const reverse = l.multiplicity === "one_to_many";
    const node: NativeLink = old ? structuredClone(old) : {
      id: l.id, name: l.name, technical_name: l.technical_name, description: l.description, tags: l.tags, evidence: l.evidence,
      owner_ref: { kind: "object_type", ref: reverse ? l.target_type_id : l.source_type_id },
      roles: [{ id: crypto.randomUUID(), concept: { kind: "object_type", ref: reverse ? l.source_type_id : l.target_type_id }, position: 0, native_presence: [], origin: "platform" }],
      requires: [], derived_by: [], verbalizes: [], multiplicity: null, origin: "platform", position: null, native_presence: [],
    };
    for (const key of ["name", "technical_name", "tags", "identifier"]) field(node, prev, l, key);
    for (const key of ["description", "verbalizes"]) field(node, prev, l, key, true);
    if (!prev || prev.source_type_id !== l.source_type_id || prev.target_type_id !== l.target_type_id || prev.multiplicity !== l.multiplicity) {
      node.endpoint_direction = reverse ? "reverse" : "forward";
      node.owner_ref = { kind: "object_type", ref: reverse ? l.target_type_id : l.source_type_id };
      node.roles[0].concept = { kind: "object_type", ref: reverse ? l.source_type_id : l.target_type_id };
      node.legacy_multiplicity = l.multiplicity;
      node.multiplicity = l.multiplicity === "one_to_one" ? "OneToOne" : ["one_to_many", "many_to_one"].includes(l.multiplicity) ? "ManyToOne" : null;
      if (node.multiplicity !== null) node.native_presence = [...new Set([...(node.native_presence ?? []), "multiplicity"])];
      else node.native_presence = node.native_presence?.filter(f => f !== "multiplicity");
    }
    const roleName = node.endpoint_direction === "reverse" ? l.source_role_name : l.target_role_name;
    const ownerName = node.endpoint_direction === "reverse" ? l.target_role_name : l.source_role_name;
    const previousRoleName = old?.roles[0].name;
    if (roleName !== previousRoleName && (prev || roleName != null)) {
      node.roles[0].name = roleName ?? null;
      node.roles[0].native_presence = [...new Set([...(node.roles[0].native_presence ?? []), "name"])].filter(key => key !== "name" || roleName != null);
    }
    if (ownerName !== old?.owner_role_name && (prev || ownerName != null)) node.owner_role_name = ownerName ?? null;
    return node;
  });
  // Identifier edits change the owning concept's ordered native name references.
  const oldRelations = [...original.properties, ...original.link_types];
  for (const relation of [...result.properties, ...result.link_types]) {
    const old = oldRelations.find(r => r.id === relation.id);
    const beforeOwner = old?.owner_ref.ref;
    const afterOwner = relation.owner_ref.ref;
    const touched = !old || old.identifier !== relation.identifier || old.technical_name !== relation.technical_name || beforeOwner !== afterOwner;
    if (!touched || (!old?.identifier && !relation.identifier)) continue;
    for (const concept of [...result.object_types, ...result.value_types]) {
      const previousNames = [...concept.identify_by];
      if (concept.id === beforeOwner && old?.identifier) {
        concept.identify_by = beforeOwner === afterOwner && relation.identifier
          ? concept.identify_by.map(name => name === old.technical_name ? relation.technical_name : name)
          : concept.identify_by.filter(name => name !== old.technical_name);
      }
      if (concept.id === afterOwner && relation.identifier && !concept.identify_by.includes(relation.technical_name)) concept.identify_by.push(relation.technical_name);
      if (!same(previousNames, concept.identify_by)) concept.native_presence = [...new Set([...(concept.native_presence ?? []), "identify_by"])];
    }
  }
  result.rules = structuredClone(edited.rules);
  for (const node of [...result.object_types, ...result.properties, ...result.link_types]) {
    if ("roles" in node && relationReadOnly(node) && !oldConcepts.has(node.id)) continue;
    for (const [key, kind] of [["requires", "constraint"], ["derived_by", "derivation"]] as const) {
      const old = [...original.object_types, ...original.properties, ...original.link_types].find(n => n.id === node.id);
      const previous = old?.[key] ?? [];
      const remaining = result.rules.filter(r => r.owner_id === node.id && r.rule_kind === kind);
      const ordered = [...previous.filter(id => remaining.some(r => r.id === id)), ...remaining.filter(r => !previous.includes(r.id)).map(r => r.id)];
      node[key] = ordered;
      if (old && !same(previous, ordered)) node.native_presence = [...new Set([...(node.native_presence ?? []), key])];
    }
  }
  result.actions = structuredClone(edited.actions);
  result.material_objects = structuredClone(edited.material_objects);
  result.material_links = structuredClone(edited.material_links);
  result.ontology_requires = [...edited.ontology_requires];
  result._legacy_form = { mapping_status: original._legacy_form?.mapping_status, mappings: structuredClone(edited.mappings), joins: Object.fromEntries(edited.link_types.filter(l => !relationReadOnly(l)).map(l => {
    if (!l.data_join) return [l.id, null];
    const source = l.data_join.source_columns ?? [l.data_join.source_column];
    const target = l.data_join.target_columns ?? [l.data_join.target_column];
    const reverse = result.link_types.find(r => r.id === l.id)?.endpoint_direction === "reverse";
    return [l.id, { owner_columns: reverse ? target : source, role_columns: reverse ? source : target }];
  })) };
  return result;
}

export function nativeFromView(original: NativeDraft, view: DraftView): NativeDraft {
  const edited = editorDraft(original);
  edited.object_types = view.object_types.map(({ attributes: _a, requires: _r, derived_by: _d, supertypes: _s, inherited_attributes: _i, ...c }) => {
    void _a; void _r; void _d; void _s; void _i;
    return { ...c, extends: c.extends ?? [], evidence: original.object_types.find(o => o.id === c.id)?.evidence ?? [] };
  });
  edited.properties = [...original.properties.filter(p => p.owner_ref.kind === "value_type").map(p => editorDraft(original).properties.find(e => e.id === p.id)!),
    ...view.object_types.flatMap(c => c.attributes.map(({ requires: _r, derived_by: _d, declared_by: _by, ...p }) => {
      void _r; void _d; void _by;
      return { ...p, verbalizes: p.verbalizes ?? [], owner_type_id: c.id, evidence: original.properties.find(o => o.id === p.id)?.evidence ?? [] };
    }))];
  edited.link_types = view.link_types.map(({ requires: _r, derived_by: _d, ...l }) => {
    void _r; void _d;
    return { ...l, evidence: original.link_types.find(o => o.id === l.id)?.evidence ?? [] };
  });
  const entityIds = new Set(edited.object_types.map(c => c.id));
  const editedOwners = new Set([...edited.object_types, ...edited.properties.filter(p => entityIds.has(p.owner_type_id)), ...edited.link_types].map(c => c.id));
  edited.rules = edited.rules.filter(r => !editedOwners.has(r.owner_id));
  const restate = (owner: { id: string; name: string; requires?: string[]; derived_by?: string[] }, ownerKind: RuleElement["owner_kind"]) => {
    for (const [key, kind] of [["requires", "constraint"], ["derived_by", "derivation"]] as const) {
      const native = [...original.object_types, ...original.properties, ...original.link_types].find(c => c.id === owner.id);
      const old = (native?.[key] ?? []).map(id => original.rules.find(r => r.id === id)!).filter(Boolean);
      const unused = [...old];
      for (const expression of owner[key] ?? []) {
        const index = unused.findIndex(r => r.expression === expression);
        const kept = index >= 0 ? unused.splice(index, 1)[0] : undefined;
        edited.rules.push(kept ?? { id: crypto.randomUUID(), owner_id: owner.id, owner_kind: ownerKind, rule_kind: kind, expression, name: owner.name, technical_name: `rule_${crypto.randomUUID().replaceAll("-", "")}`, description: "", verbalizes: [], evidence: [] });
      }
    }
  };
  for (const c of view.object_types) { restate(c, "object_type"); for (const p of c.attributes) restate(p, "property"); }
  for (const l of view.link_types) restate(l, "link_type");
  edited.material_objects = view.objects; edited.material_links = view.links; edited.mappings = view.mappings; edited.ontology_requires = view.requires;
  const result = nativeFromEditor(original, edited) as NativeDraft;
  // The view's rule list defines its order; duplicate expressions remain distinct.
  for (const node of [...result.object_types, ...result.properties, ...result.link_types]) {
    for (const [key, kind] of [["requires", "constraint"], ["derived_by", "derivation"]] as const)
      node[key] = edited.rules.filter(r => r.owner_id === node.id && r.rule_kind === kind).map(r => r.id);
  }
  return result;
}
