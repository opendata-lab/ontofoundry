// Read-only selectors over a core-1 draft. They mirror the backend's
// domain/graph.py so pages derive inheritance, links and bindings the same way
// the server validates them. Nothing here writes back into the draft.
import type {
  Aggregation,
  DataJoin,
  DataMapping,
  Dataset,
  Draft,
  ExpressionMetric,
  LinkType,
  MappingSource,
  Metric,
  ObjectType,
  Property,
  RatioMetric,
  Rule,
  SimpleMetric,
  UUID,
  ValueKind,
} from "../api/types";

export const VALUE_KINDS: Record<ValueKind, string> = {
  string: "文本",
  integer: "整数",
  decimal: "小数",
  float: "浮点数",
  boolean: "布尔",
  date: "日期",
  datetime: "日期时间",
};

export const MULTIPLICITY: Record<LinkType["multiplicity"], string> = {
  one_to_one: "一对一",
  many_to_one: "多对一",
  many_to_many: "多对多",
};

/** A traversal is named for the role played by the object it returns. */
export function linkDisplayName(link: LinkType, forward: boolean): string {
  return (forward ? link.target_role_name : link.source_role_name)
    || (forward ? (link.display_name || link.name) : `${(link.display_name || link.name)}（反向）`);
}

export const AGGREGATIONS: Record<Aggregation, string> = {
  count: "计数",
  sum: "求和",
  avg: "平均",
  max: "最大",
  min: "最小",
  count_distinct: "去重计数",
  median: "中位数",
};

export const NUMERIC_KINDS: ReadonlySet<ValueKind> = new Set(["integer", "decimal", "float"]);
export const DATE_KINDS: ReadonlySet<ValueKind> = new Set(["date", "datetime"]);

export function emptyDraft(workspaceId: UUID): Draft {
  return {
    schema_version: "core-1",
    workspace_id: workspaceId,
    object_types: [],
    properties: [],
    link_types: [],
    rules: [],
    metrics: [],
    datasets: [],
    mappings: [],
    material_objects: [],
    material_links: [],
    value_types: [],
  };
}

export const byId = <T extends { id: UUID }>(items: T[], id: UUID | null | undefined) =>
  id ? items.find((item) => item.id === id) : undefined;

// --- inheritance ------------------------------------------------------------

/** Parent first, root last; stops at a missing parent or a cycle. */
export function ancestors(draft: Draft, typeId: UUID): ObjectType[] {
  const chain: ObjectType[] = [];
  const seen = new Set([typeId]);
  let current = byId(draft.object_types, typeId);
  while (current?.extends && !seen.has(current.extends)) {
    seen.add(current.extends);
    const parent = byId(draft.object_types, current.extends);
    if (!parent) break;
    chain.push(parent);
    current = parent;
  }
  return chain;
}

/** The object itself, then its ancestors. */
export function lineage(draft: Draft, typeId: UUID): UUID[] {
  return [typeId, ...ancestors(draft, typeId).map((o) => o.id)];
}

export function children(draft: Draft, typeId: UUID): ObjectType[] {
  return draft.object_types.filter((o) => o.extends === typeId);
}

export function isA(draft: Draft, typeId: UUID, ancestorId: UUID) {
  return lineage(draft, typeId).includes(ancestorId);
}

export type Inherited<T> = { definition: T; inheritedFrom: UUID | null };

/** Own properties first, then inherited ones, nearest ancestor first. */
export function effectiveProperties(draft: Draft, typeId: UUID): Inherited<Property>[] {
  const owners = lineage(draft, typeId);
  return owners.flatMap((owner) =>
    draft.properties
      .filter((p) => p.owner_type_id === owner)
      .map((definition) => ({ definition, inheritedFrom: owner === typeId ? null : owner })),
  );
}

export function propertyByName(draft: Draft, typeId: UUID, technicalName: string) {
  const wanted = technicalName.toLowerCase();
  return effectiveProperties(draft, typeId).find(
    (p) => p.definition.name.toLowerCase() === wanted,
  )?.definition;
}

export type EffectiveLink = Inherited<LinkType> & {
  /** forward: this object (or an ancestor) is the source; reverse: the target. */
  direction: "forward" | "reverse";
};

/** Self-links remain single definitions unless a direction-specific list requests both. */
export function effectiveLinks(draft: Draft, typeId: UUID, bothSelfDirections = false): EffectiveLink[] {
  const owners = lineage(draft, typeId);
  const rank = new Map(owners.map((id, i) => [id, i]));
  const result: EffectiveLink[] = [];
  const seen = new Set<UUID>();
  for (const link of draft.link_types) {
    const source = rank.get(link.source_type_id);
    const target = rank.get(link.target_type_id);
    if (source === undefined && target === undefined) continue;
    if (seen.has(link.id)) continue;
    seen.add(link.id);
    const forward = source !== undefined;
    const owner = owners[(forward ? source : target)!];
    result.push({
      definition: link,
      direction: forward ? "forward" : "reverse",
      inheritedFrom: owner === typeId ? null : owner,
    });
    if (bothSelfDirections && link.source_type_id === link.target_type_id) {
      result.push({
        definition: link,
        direction: "reverse",
        inheritedFrom: owner === typeId ? null : owner,
      });
    }
  }
  return result;
}

/** Rules on the object, its effective properties and outgoing links. */
export function effectiveRules(draft: Draft, typeId: UUID): Inherited<Rule>[] {
  const owners = new Map<UUID, UUID | null>();
  for (const id of lineage(draft, typeId)) owners.set(id, id === typeId ? null : id);
  for (const p of effectiveProperties(draft, typeId)) {
    owners.set(p.definition.id, p.inheritedFrom);
    // A property's value type contributes its constraints, read-only here (VT-10).
    if (p.definition.value_type_id) owners.set(p.definition.value_type_id, null);
  }
  for (const l of effectiveLinks(draft, typeId)) {
    if (l.direction === "forward") owners.set(l.definition.id, l.inheritedFrom);
  }
  return draft.rules
    .filter((rule) => owners.has(rule.owner_id))
    .map((definition) => ({ definition, inheritedFrom: owners.get(definition.owner_id) ?? null }));
}

export function rulesOfLink(draft: Draft, linkId: UUID): Rule[] {
  return draft.rules.filter((r) => r.owner_kind === "link_type" && r.owner_id === linkId);
}

/** Effective identifier properties, ordered by UUID bytes like the server. */
export function identifier(draft: Draft, typeId: UUID): Property[] {
  return effectiveProperties(draft, typeId)
    .map((p) => p.definition)
    .filter((p) => p.identifier)
    .sort((a, b) => compareUuidBytes(a.id, b.id));
}

/** The nearest declared title property along the lineage. */
export function titleProperty(draft: Draft, typeId: UUID): Property | undefined {
  for (const id of lineage(draft, typeId)) {
    const titleId = byId(draft.object_types, id)?.title_property_id;
    if (titleId) return byId(draft.properties, titleId);
  }
  return undefined;
}

export function compareUuidBytes(a: string, b: string) {
  const x = a.replace(/-/g, "").toLowerCase();
  const y = b.replace(/-/g, "").toLowerCase();
  return x < y ? -1 : x > y ? 1 : 0;
}

// --- datasets and bindings --------------------------------------------------

export function mappingFor(draft: Draft, typeId: UUID): DataMapping | undefined {
  return draft.mappings.find((m) => m.type_id === typeId);
}

export type ResolvedSource = MappingSource & {
  dataset: Dataset | undefined;
  /** Object whose mapping declares this source (an ancestor for shared_parent). */
  ownerTypeId: UUID;
};

/**
 * Effective sources: an independent mapping's own sources, or for a
 * shared_parent child the nearest bound ancestor's sources plus its own
 * extension sources. `main` is always the instance-defining source.
 */
export function effectiveSources(draft: Draft, typeId: UUID): ResolvedSource[] {
  const result: ResolvedSource[] = [];
  for (const id of lineage(draft, typeId)) {
    const mapping = mappingFor(draft, id);
    if (!mapping) continue;
    for (const source of mapping.sources) {
      if (result.some((s) => s.id === source.id)) continue;
      result.push({
        ...source,
        key_columns: source.key_columns ?? [],
        dataset: byId(draft.datasets, source.dataset_id),
        ownerTypeId: id,
      });
    }
    if (mapping.binding_mode === "independent") break;
  }
  return result;
}

export type BindingMode = "independent" | "shared_parent" | "virtual" | "unbound";

/** How the object gets its instances (§3.2 of the design). */
export function bindingMode(draft: Draft, typeId: UUID): BindingMode {
  const mapping = mappingFor(draft, typeId);
  if (mapping) return mapping.binding_mode;
  if (lineage(draft, typeId).slice(1).some((id) => mappingFor(draft, id))) return "shared_parent";
  const hasMappedDescendant = draft.object_types.some(
    (o) => o.id !== typeId && isA(draft, o.id, typeId) && Boolean(mappingFor(draft, o.id)),
  );
  return hasMappedDescendant ? "virtual" : "unbound";
}

export function datasetColumns(dataset: Dataset | undefined) {
  return dataset?.columns ?? null;
}

export function joinSummary(draft: Draft, join: DataJoin | null): string {
  if (!join) return "未绑定";
  if (join.kind === "direct") {
    const names = (ids: UUID[]) => ids.map((id) => (byId(draft.properties, id)?.display_name || byId(draft.properties, id)?.name) ?? "?").join(" + ");
    return `${names(join.source_property_ids)} = ${names(join.target_property_ids)}`;
  }
  return `映射表 ${byId(draft.datasets, join.dataset_id)?.name ?? "?"}`;
}

// --- metrics ----------------------------------------------------------------

export const isSimple = (m: Metric): m is SimpleMetric => m.kind === "simple";
export const isRatio = (m: Metric): m is RatioMetric => m.kind === "ratio";
export const isExpression = (m: Metric): m is ExpressionMetric => m.kind === "expression";

/** The dataset a metric reads; a ratio inherits it from its numerator. */
export function metricDatasetId(draft: Draft, metric: Metric): UUID | null {
  if (!isRatio(metric)) return metric.dataset_id;
  const numerator = byId(draft.metrics, metric.numerator_id);
  return numerator && !isRatio(numerator) ? numerator.dataset_id : null;
}

/** Derived result type: count/count_distinct integer, avg/median/ratio decimal. */
export function metricValueKind(draft: Draft, metric: Metric): ValueKind | null {
  if (isRatio(metric)) return "decimal";
  if (isExpression(metric)) return metric.value_kind ?? null;
  switch (metric.aggregation) {
    case "count":
    case "count_distinct":
      return "integer";
    case "avg":
    case "median":
      return "decimal";
    default: {
      const dataset = byId(draft.datasets, metric.dataset_id);
      const column = dataset?.columns?.find((c) => c.name === metric.measure?.column);
      return physicalValueKind(column?.physical_type ?? null);
    }
  }
}

/** Best-effort semantic kind of a physical column type; null when unknown. */
export function physicalValueKind(physical: string | null): ValueKind | null {
  if (!physical) return null;
  const t = physical.toLowerCase();
  if (/^(tinyint\(1\)|bool)/.test(t)) return "boolean";
  if (/int|serial/.test(t)) return "integer";
  if (/decimal|numeric|money/.test(t)) return "decimal";
  if (/float|double|real/.test(t)) return "float";
  if (/^date$/.test(t)) return "date";
  if (/time|date/.test(t)) return "datetime";
  if (/char|text|string|uuid|json/.test(t)) return "string";
  return null;
}

/** Simple metrics on the same dataset that a ratio may use as components. */
export function ratioComponents(draft: Draft, datasetId: UUID | null): SimpleMetric[] {
  return draft.metrics.filter(
    (m): m is SimpleMetric => isSimple(m) && (!datasetId || m.dataset_id === datasetId),
  );
}

/** Metrics that read a dataset directly or through ratio components. */
export function metricsOnDataset(draft: Draft, datasetId: UUID): Metric[] {
  return draft.metrics.filter((m) => metricDatasetId(draft, m) === datasetId);
}

// --- replacing elements -----------------------------------------------------

/** Returns a draft with one element replaced (or appended when new). */
export function upsert<K extends keyof Draft & string>(
  draft: Draft,
  collection: K,
  element: Draft[K] extends (infer T)[] ? T & { id: UUID } : never,
): Draft {
  const items = draft[collection] as unknown as { id: UUID }[];
  const exists = items.some((item) => item.id === element.id);
  return {
    ...draft,
    [collection]: exists ? items.map((item) => (item.id === element.id ? element : item)) : [...items, element],
  };
}

export function remove<K extends keyof Draft & string>(draft: Draft, collection: K, id: UUID): Draft {
  const items = draft[collection] as unknown as { id: UUID }[];
  return { ...draft, [collection]: items.filter((item) => item.id !== id) };
}

/** Presentation fallback also accepts datasets, which keep their original name. */
export function displayName(element: { name: string } | null | undefined): string {
  return element && "display_name" in element && typeof element.display_name === "string" && element.display_name
    ? element.display_name : element?.name ?? "";
}
