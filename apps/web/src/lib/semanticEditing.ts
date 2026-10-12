import type {
  MappingNode,
  SemanticDataset,
  SemanticField,
  SemanticInfo,
  SemanticMetric,
  SemanticModel,
  SemanticRelationship,
  NativeDraft,
  SemanticConcept,
  ConceptRef,
} from "../api/types";

export function cleanNodes(nodes: MappingNode[]): MappingNode[] {
  return nodes.map(
    ({ id, parent_id, slot, kind, relationship, concept, expression }) => ({
      id,
      parent_id,
      slot,
      kind,
      relationship,
      concept,
      expression,
    }),
  );
}
export function contextSynonyms(context: unknown): string[] {
  return context &&
    typeof context === "object" &&
    "synonyms" in context &&
    Array.isArray(context.synonyms)
    ? context.synonyms.filter((s): s is string => typeof s === "string")
    : [];
}
export function semanticLabel(item: { name: string; display_name?: string }) {
  return item.display_name || item.name;
}
type Parent = { semantic_model_id: string };
export function nativeSemanticModels(draft: NativeDraft): SemanticModel[] {
  const display = <T extends SemanticInfo>(node: T) => ({
    ...node,
    display_name:
      (
        draft.extension_v4.display_names as Record<string, string> | undefined
      )?.[node.id] ?? node.name,
  });
  const concepts: SemanticConcept[] = [
    ...draft.object_types.map((c) => ({
      id: c.id,
      name: c.name,
      technical_name: c.concept,
      kind: "object_type" as const,
    })),
    ...draft.value_types.map((c) => ({
      id: c.id,
      name: c.name,
      technical_name: c.concept,
      kind: "value_type" as const,
    })),
  ];
  return (
    draft.semantic_models as (SemanticInfo & { map_name?: string })[]
  ).map((model) => ({
    ...display(model),
    connection_alias: null,
    datasets: (draft.datasets as (Omit<SemanticDataset, "fields"> & Parent)[])
      .filter((d) => d.semantic_model_id === model.id)
      .map((d) => ({
        ...display(d),
        fields: (
          draft.dataset_fields as (SemanticField & { dataset_id: string })[]
        )
          .filter((f) => f.dataset_id === d.id)
          .map(display),
      })),
    relationships: (
      draft.dataset_relationships as (SemanticRelationship &
        Parent & { from_?: string })[]
    )
      .filter((r) => r.semantic_model_id === model.id)
      .map((r) => ({ ...r, from: r.from ?? r.from_ ?? "" })),
    metrics: (draft.metrics as (SemanticMetric & Parent)[]).filter(
      (m) => m.semantic_model_id === model.id,
    ),
    concept_mappings: (
      draft.concept_mappings as ({
        id: string;
        concept_id: ConceptRef;
      } & Parent)[]
    )
      .filter((c) => c.semantic_model_id === model.id)
      .map((c) => ({
        ...c,
        concept: concepts.find((concept) => concept.id === c.concept_id.ref),
        nodes: cleanNodes(
          (draft.mapping_nodes as (MappingNode & { position?: number })[])
            .filter((n) => n.concept_mapping_id === c.id)
            .sort((a, b) => (a.position ?? 0) - (b.position ?? 0)),
        ),
      })),
  }));
}
