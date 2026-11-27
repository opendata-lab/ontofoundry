/**
 * Shared element-kind and draft-collection registries for the web client.
 *
 * Core collections are verified against the generated `CoreDraft` interface so
 * TypeScript (`tsc -b`) and vitest (against `ontofoundry.core-1.schema.json`)
 * both fail if a new core-1 collection is added without updating each UI surface.
 */
import type { CoreDraft } from "../api/core.generated";
import {
  COLLECTION_BY_KIND,
  type CollectionKey,
  type OntologySearchKind,
  type ResourceKind as CatalogResourceKind,
  type TargetKind,
} from "../api/types";

export type CoreCollectionKey = Exclude<keyof CoreDraft, "schema_version" | "workspace_id">;
export type InstanceTargetKind = "material_object" | "material_link";
export type CoreTargetKind = Exclude<TargetKind, InstanceTargetKind>;
export type InstanceCollectionKey = (typeof COLLECTION_BY_KIND)[InstanceTargetKind];

type Exact<A, B> = [A] extends [B] ? ([B] extends [A] ? true : never) : never;

// Compile-time guard: `COLLECTION_BY_KIND` core values must match `keyof CoreDraft`.
export const CORE_COLLECTIONS_IN_SYNC: Exact<
  CoreCollectionKey,
  (typeof COLLECTION_BY_KIND)[CoreTargetKind]
> = true;

export const INSTANCE_TARGET_KINDS = ["material_object", "material_link"] as const satisfies readonly InstanceTargetKind[];
const INSTANCE_KIND_SET = new Set<TargetKind>(INSTANCE_TARGET_KINDS);

// Reverse map derived from the single `COLLECTION_BY_KIND` registry.
export const KIND_BY_COLLECTION = Object.fromEntries(
  Object.entries(COLLECTION_BY_KIND).map(([kind, collection]) => [collection, kind]),
) as Record<CollectionKey, TargetKind>;

export const ALL_TARGET_KINDS = Object.keys(COLLECTION_BY_KIND) as TargetKind[];
export const CORE_TARGET_KINDS = ALL_TARGET_KINDS.filter(
  (kind): kind is CoreTargetKind => !INSTANCE_KIND_SET.has(kind),
);
export const CORE_COLLECTION_KEYS = CORE_TARGET_KINDS.map(
  (kind) => COLLECTION_BY_KIND[kind],
) as CoreCollectionKey[];
export const INSTANCE_COLLECTION_KEYS = INSTANCE_TARGET_KINDS.map(
  (kind) => COLLECTION_BY_KIND[kind],
) as InstanceCollectionKey[];

// Draft collections whose elements have `name` / `display_name` and are indexed
// for review and publish name lookup (shared by reviewMeta and PublishPanel).
export const NAMED_DRAFT_COLLECTIONS = [
  "object_types",
  "properties",
  "link_types",
  "rules",
  "metrics",
  "datasets",
] as const satisfies readonly CoreCollectionKey[];

// Top-level element kinds that open directly as inspector roots / can be created in the inspector.
export const INSPECTABLE_KINDS = ["object_type", "link_type", "metric", "dataset"] as const;
export type InspectableKind = (typeof INSPECTABLE_KINDS)[number];
export const INSPECTABLE_NOUN: Record<InspectableKind, string> = {
  object_type: "对象",
  link_type: "关系",
  metric: "指标",
  dataset: "数据集",
};
// Target kinds accepted by ElementInspector (value_type is managed in ValueTypeCatalog).
export const ELEMENT_INSPECTOR_KINDS = new Set<TargetKind>([
  "object_type",
  "property",
  "link_type",
  "rule",
  "metric",
  "dataset",
  "mapping",
  "material_object",
  "material_link",
]);

// Ordering of element changes in PublishPanel (value_type currently omitted for zero behavior change).
export const PUBLISH_KIND_ORDER: TargetKind[] = [
  "object_type",
  "property",
  "link_type",
  "rule",
  "metric",
  "dataset",
  "mapping",
  "material_object",
  "material_link",
];

// Fields locked against inline edits during proposal review (mirrors backend proposal_revision.LOCKED_FIELDS).
export const LOCKED_PROPOSAL_FIELDS = new Set(["id", "evidence", "extends", "type_id"]);

// Resource kinds displayed in the semantic explorer sidebar and filter bar.
export const SEMANTIC_RESOURCE_KINDS = ["object", "relation", "metric", "dataset"] as const;
export type SemanticResourceKind = (typeof SEMANTIC_RESOURCE_KINDS)[number];

// Labels and navigable subset for OntologySearchDialog (value_type has no standalone detail route yet).
export const SEARCH_KIND_LABELS: Record<OntologySearchKind, string> = {
  object_type: "实体",
  property: "属性",
  link_type: "关系",
  rule: "规则",
  metric: "指标",
  dataset: "数据集",
  value_type: "值类型",
};
export const NAVIGABLE_SEARCH_KINDS = new Set<OntologySearchKind>([
  "object_type",
  "property",
  "link_type",
  "rule",
  "metric",
  "dataset",
]);

// Shared catalog tab mappings for both TypeCatalogPage (draft) and PublishedTypeCatalogPage.
export type CatalogTab = "entities" | "values" | "relations" | "metrics" | "datasets";
export type ResourceCatalogTab = Exclude<CatalogTab, "values">;
export const CATALOG_TAB_LABELS: Record<CatalogTab, string> = {
  entities: "实体类型",
  values: "值类型",
  relations: "关系",
  metrics: "指标",
  datasets: "数据集",
};
export const CATALOG_RESOURCE_KINDS: Record<ResourceCatalogTab, CatalogResourceKind> = {
  entities: "object_type",
  relations: "link_type",
  metrics: "metric",
  datasets: "dataset",
};
export const CATALOG_TAB_COLLECTIONS = {
  entities: COLLECTION_BY_KIND.object_type,
  values: COLLECTION_BY_KIND.value_type,
  relations: COLLECTION_BY_KIND.link_type,
  metrics: COLLECTION_BY_KIND.metric,
  datasets: COLLECTION_BY_KIND.dataset,
} as const satisfies Record<CatalogTab, CoreCollectionKey>;
