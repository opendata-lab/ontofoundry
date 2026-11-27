/// <reference types="vite/client" />
/**
 * Guard every frontend element-kind and collection list against the generated
 * core-1 schema types (`api/core.generated.ts`).
 *
 * When a new core collection is added to `CoreDraft`, both `tsc -b` (via
 * `CoreCollectionKey` in `elementKinds.ts`) and these runtime coverage tests
 * fail and point at every UI list that must decide whether to include or
 * exclude the new kind.
 */
import { describe, expect, it } from "vitest";
import coreGeneratedSource from "../api/core.generated.ts?raw";
import { COLLECTION_BY_KIND, type TargetKind } from "../api/types";
import { KIND as PROPOSAL_KIND_META } from "../components/proposals/elementMeta";
import { ELEMENT_CATEGORIES } from "./elementCategories";
import {
  ALL_TARGET_KINDS,
  CORE_COLLECTION_KEYS,
  CORE_KIND_BY_COLLECTION,
  CORE_TARGET_KINDS,
  ELEMENT_INSPECTOR_KINDS,
  INSPECTABLE_KINDS,
  INSPECTABLE_NOUN,
  INSTANCE_KIND_BY_COLLECTION,
  INSTANCE_TARGET_KINDS,
  LOCKED_PROPOSAL_FIELDS,
  NAMED_DRAFT_COLLECTIONS,
  NAVIGABLE_SEARCH_KINDS,
  PUBLISHED_CATALOG_COUNT_COLLECTIONS,
  PUBLISHED_CATALOG_KINDS,
  PUBLISH_KIND_ORDER,
  SEARCH_KIND_LABELS,
  SEMANTIC_RESOURCE_KINDS,
} from "./elementKinds";
import { RESOURCE_KIND_LABELS, RESOURCE_KINDS, type ResourceKind } from "./semanticExplorer";

function generatedCoreDraftCollections(): string[] {
  const match = coreGeneratedSource.match(/export interface CoreDraft\s*\{([\s\S]*?)\n\}/);
  expect(match, "CoreDraft interface should exist in core.generated.ts").not.toBeNull();
  const keys = [...match![1].matchAll(/^\s*([a-z_]+)\??:/gm)].map((m) => m[1]);
  return keys.filter((key) => key !== "schema_version" && key !== "workspace_id").sort();
}

function assertCoverage(actual: Iterable<string>, registered: Iterable<string>, excluded: Iterable<string>) {
  const actualSet = new Set(actual);
  const registeredSet = new Set(registered);
  const excludedSet = new Set(excluded);
  expect([...excludedSet].filter((item) => !registeredSet.has(item))).toEqual([]);
  expect([...actualSet].filter((item) => excludedSet.has(item))).toEqual([]);
  const expected = [...registeredSet].filter((item) => !excludedSet.has(item)).sort();
  expect([...actualSet].sort()).toEqual(expected);
}

describe("frontend element-kind and collection coverage", () => {
  const generatedCollections = generatedCoreDraftCollections();

  it("matches generated CoreDraft collections in elementKinds and COLLECTION_BY_KIND", () => {
    expect([...CORE_COLLECTION_KEYS].sort()).toEqual(generatedCollections);
    const coreKinds = generatedCollections.map((collection) => CORE_KIND_BY_COLLECTION[collection as keyof typeof CORE_KIND_BY_COLLECTION]);
    expect(coreKinds.every(Boolean)).toBe(true);
    expect([...CORE_TARGET_KINDS].sort()).toEqual([...coreKinds].sort());

    const instanceCollections = Object.keys(INSTANCE_KIND_BY_COLLECTION);
    expect(Object.values(COLLECTION_BY_KIND).sort()).toEqual([...generatedCollections, ...instanceCollections].sort());
    expect([...ALL_TARGET_KINDS].sort()).toEqual([...CORE_TARGET_KINDS, ...INSTANCE_TARGET_KINDS].sort());
  });

  it("covers all target kinds in proposal elementMeta and documented subsets in elementCategories and PublishPanel", () => {
    assertCoverage(Object.keys(PROPOSAL_KIND_META), ALL_TARGET_KINDS, []);

    // Proposal/category tiles currently omit value_type (managed in ValueTypeCatalog).
    assertCoverage(
      ELEMENT_CATEGORIES.map((category) => category.key),
      ALL_TARGET_KINDS,
      ["value_type"],
    );

    // Publish change ordering currently omits value_type (preserved for zero behavior change).
    assertCoverage(PUBLISH_KIND_ORDER, ALL_TARGET_KINDS, ["value_type"]);
  });

  it("covers named draft collections shared by reviewMeta and PublishPanel", () => {
    // Mappings have no `name` field; value_types are currently excluded from
    // proposal/publish name-map preloading.
    assertCoverage(NAMED_DRAFT_COLLECTIONS, generatedCollections, ["mappings", "value_types"]);
  });

  it("covers ElementInspector kinds and inspectable roots", () => {
    // Value types open in ValueTypeCatalog rather than ElementInspector.
    assertCoverage(ELEMENT_INSPECTOR_KINDS, ALL_TARGET_KINDS, ["value_type"]);

    // Top-level inspector tabs/creators cover objects, links, metrics and datasets;
    // nested elements resolve to their owner, value_types use ValueTypeCatalog,
    // and instances resolve to their object/link type.
    assertCoverage(
      INSPECTABLE_KINDS,
      ALL_TARGET_KINDS,
      ["property", "rule", "mapping", "value_type", ...INSTANCE_TARGET_KINDS],
    );
    expect(Object.keys(INSPECTABLE_NOUN).sort()).toEqual([...INSPECTABLE_KINDS].sort());
  });

  it("covers semantic explorer resource kinds", () => {
    const resourceToCoreKind: Record<ResourceKind, TargetKind> = {
      object: "object_type",
      relation: "link_type",
      metric: "metric",
      dataset: "dataset",
    };
    expect([...RESOURCE_KINDS]).toEqual([...SEMANTIC_RESOURCE_KINDS]);
    expect(Object.keys(RESOURCE_KIND_LABELS).sort()).toEqual([...SEMANTIC_RESOURCE_KINDS].sort());
    // SemanticView explores top-level resource kinds; properties, rules and
    // mappings open inside their owning inspector, and value_types live in the catalog.
    assertCoverage(
      SEMANTIC_RESOURCE_KINDS.map((kind) => resourceToCoreKind[kind]),
      CORE_TARGET_KINDS,
      ["property", "rule", "mapping", "value_type"],
    );
  });

  it("covers OntologySearchDialog labels and navigable kinds", () => {
    // Search covers all core kinds except internal physical mappings.
    assertCoverage(Object.keys(SEARCH_KIND_LABELS), CORE_TARGET_KINDS, ["mapping"]);
    // Value types are searchable but currently have no standalone detail route.
    assertCoverage(NAVIGABLE_SEARCH_KINDS, CORE_TARGET_KINDS, ["mapping", "value_type"]);
  });

  it("covers PublishedTypeCatalogPage resource tabs and counts", () => {
    assertCoverage(
      Object.values(PUBLISHED_CATALOG_KINDS),
      CORE_TARGET_KINDS,
      ["property", "rule", "mapping", "value_type"],
    );
    assertCoverage(
      Object.values(PUBLISHED_CATALOG_COUNT_COLLECTIONS),
      generatedCollections,
      ["properties", "rules", "mappings"],
    );
  });

  it("keeps locked proposal review fields explicit", () => {
    expect([...LOCKED_PROPOSAL_FIELDS].sort()).toEqual(["evidence", "extends", "id", "type_id"]);
  });
});
