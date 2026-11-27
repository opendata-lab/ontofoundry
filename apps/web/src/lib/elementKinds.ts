/**
 * Shared element-kind and draft-collection registries for the web client.
 *
 * Core collections are keyed against the generated `CoreDraft` interface so
 * TypeScript and vitest both fail if a new core-1 collection is added without
 * updating each UI surface's coverage decision.
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
export type InstanceCollectionKey = "material_objects" | "material_links";
export type CoreTargetKind = Exclude<TargetKind, "material_object" | "material_link">;
export type InstanceTargetKind = "material_object" | "material_link";

export const CORE_KIND_BY_COLLECTION = {
  object_types: "object_type",
  properties: "property",
  link_types: "link_type",
  rules: "rule",
  metrics: "metric",
  datasets: "dataset",
  mappings: "mapping",
  value_types: "value_type",
} as const satisfies Record<CoreCollectionKey, CoreTargetKind>;

export const INSTANCE_KIND_BY_COLLECTION = {
  material_objects: "material_object",
  material_links: "material_link",
} as const satisfies Record<InstanceCollectionKey, InstanceTargetKind>;

export const CORE_COLLECTION_KEYS = Object.keys(CORE_KIND_BY_COLLECTION) as CoreCollectionKey[];
export const CORE_TARGET_KINDS = Object.values(CORE_KIND_BY_COLLECTION) as CoreTargetKind[];
export const INSTANCE_TARGET_KINDS = Object.values(INSTANCE_KIND_BY_COLLECTION) as InstanceTargetKind[];
export const ALL_TARGET_KINDS = Object.keys(COLLECTION_BY_KIND) as TargetKind[];

// Compile-time check: every generated core collection is present in CollectionKey.
export const _ALL_COLLECTIONS_BY_KIND: Record<TargetKind, CollectionKey> = COLLECTION_BY_KIND;

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

// Tab mappings for PublishedTypeCatalogPage.
export const PUBLISHED_CATALOG_KINDS: Record<"entities" | "relations" | "metrics" | "datasets", CatalogResourceKind> = {
  entities: "object_type",
  relations: "link_type",
  metrics: "metric",
  datasets: "dataset",
};
export const PUBLISHED_CATALOG_COUNT_COLLECTIONS = {
  entities: "object_types",
  values: "value_types",
  relations: "link_types",
  metrics: "metrics",
  datasets: "datasets",
} as const;
