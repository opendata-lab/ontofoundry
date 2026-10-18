// Pure edits of an object's DataMapping. Each returns a new draft; nothing is
// saved here. Saving goes through the mapping element save or the session.
import type {
  DataJoin,
  DataMapping,
  Draft,
  FieldBinding,
  MappingSource,
  Property,
  UUID,
} from "../api/types";
import { identifier, lineage, mappingFor, upsert } from "./coreModel";
import { newId } from "./id";

export const MAIN_SOURCE = "main";

/** The object's own mapping, created (independent or shared) when missing. */
export function ensureMapping(draft: Draft, typeId: UUID): DataMapping {
  const existing = mappingFor(draft, typeId);
  if (existing) return existing;
  const sharesParent = lineage(draft, typeId)
    .slice(1)
    .some((id) => mappingFor(draft, id));
  return {
    id: newId(),
    type_id: typeId,
    binding_mode: sharesParent ? "shared_parent" : "independent",
    sources: [],
    fields: {},
    membership_source_id: null,
    inherited_link_bindings: {},
  };
}

function save(draft: Draft, mapping: DataMapping): Draft {
  return upsert(draft, "mappings", mapping);
}

/** Uses a dataset as the main source of an independent mapping. */
export function setMainDataset(draft: Draft, typeId: UUID, datasetId: UUID, keyColumns: string[] = []): Draft {
  const mapping = ensureMapping(draft, typeId);
  const main: MappingSource = { id: MAIN_SOURCE, dataset_id: datasetId, key_columns: keyColumns };
  const others = mapping.sources.filter((s) => s.id !== MAIN_SOURCE);
  return save(draft, { ...mapping, binding_mode: "independent", sources: [main, ...others] });
}

/** Adds a side table (or a shared-parent extension) with a fresh local id. */
export function addSource(draft: Draft, typeId: UUID, datasetId: UUID, keyColumns: string[] = []): { draft: Draft; sourceId: string } {
  const mapping = ensureMapping(draft, typeId);
  const taken = new Set(mapping.sources.map((s) => s.id));
  let n = 1;
  while (taken.has(`side${n}`)) n++;
  const sourceId = `side${n}`;
  return {
    draft: save(draft, { ...mapping, sources: [...mapping.sources, { id: sourceId, dataset_id: datasetId, key_columns: keyColumns }] }),
    sourceId,
  };
}

/** Removes a source and every field binding that reads it. */
export function removeSource(draft: Draft, typeId: UUID, sourceId: string): Draft {
  const mapping = mappingFor(draft, typeId);
  if (!mapping) return draft;
  const fields = Object.fromEntries(
    Object.entries(mapping.fields).filter(([, binding]) => binding.kind !== "column" || binding.source_id !== sourceId),
  );
  return save(draft, {
    ...mapping,
    sources: mapping.sources.filter((s) => s.id !== sourceId),
    fields,
    membership_source_id: mapping.membership_source_id === sourceId ? null : mapping.membership_source_id,
  });
}

export function setKeyColumns(draft: Draft, typeId: UUID, sourceId: string, keyColumns: string[]): Draft {
  const mapping = ensureMapping(draft, typeId);
  return save(draft, {
    ...mapping,
    sources: mapping.sources.map((s) => (s.id === sourceId ? { ...s, key_columns: keyColumns } : s)),
  });
}

/** Binds (or with null unbinds) one property by technical name. */
export function setFieldBinding(draft: Draft, typeId: UUID, property: Property, binding: FieldBinding | null): Draft {
  const mapping = ensureMapping(draft, typeId);
  const fields = { ...mapping.fields };
  if (binding) fields[property.technical_name] = binding;
  else delete fields[property.technical_name];
  return save(draft, { ...mapping, fields });
}

/** A shared-parent child's extension table limits its members. */
export function setMembershipSource(draft: Draft, typeId: UUID, sourceId: string | null): Draft {
  const mapping = ensureMapping(draft, typeId);
  return save(draft, { ...mapping, binding_mode: "shared_parent", membership_source_id: sourceId });
}

/** Local binding of a link inherited from a virtual parent. */
export function setInheritedLinkBinding(draft: Draft, typeId: UUID, linkId: UUID, join: DataJoin | null): Draft {
  const mapping = ensureMapping(draft, typeId);
  const bindings = { ...mapping.inherited_link_bindings };
  if (join) bindings[linkId] = join;
  else delete bindings[linkId];
  return save(draft, { ...mapping, inherited_link_bindings: bindings });
}

/** Sets a link's own data binding. */
export function setLinkJoin(draft: Draft, linkId: UUID, join: DataJoin | null): Draft {
  return {
    ...draft,
    link_types: draft.link_types.map((l) => (l.id === linkId ? { ...l, data_join: join } : l)),
  };
}

/**
 * Makes one property the whole identifier of its object. A single-property
 * identifier must be unique; a composite one need not be.
 */
export function chooseIdentifier(draft: Draft, typeId: UUID, propertyId: UUID): Draft {
  return {
    ...draft,
    properties: draft.properties.map((p) => {
      if (p.owner_type_id !== typeId) return p;
      if (p.id === propertyId) return { ...p, identifier: true, unique: true };
      return p.identifier ? { ...p, identifier: false } : p;
    }),
  };
}

/** Why the object may not change its identifier here, or null. */
export function identifierLockedReason(draft: Draft, typeId: UUID): string | null {
  const inherited = identifier(draft, typeId).some((p) => p.owner_type_id !== typeId);
  return inherited ? "子对象沿用父对象的标识，不能在这里修改" : null;
}

/** First reason a join cannot be saved, or null. */
export function joinProblem(join: DataJoin | null): string | null {
  if (!join) return null;
  if (join.kind === "direct") {
    const pairs = join.source_property_ids.map((s, i) => [s, join.target_property_ids[i]]);
    return pairs.length && pairs.every(([s, t]) => s && t) ? null : "关系绑定的属性对应未填完整";
  }
  if (!join.dataset_id) return "请选择映射表";
  if (!join.source_columns.length || !join.target_columns.length) return "请选择映射表两端的列";
  for (const key of [join.source_key, join.target_key]) {
    if (key.kind === "properties" && !key.property_ids.length) return "请选择映射表对应的属性";
  }
  return null;
}
