// The semantic view's resource explorer: objects, relations, metrics and
// datasets (§8A). Rules open inside their owner's popup, so they are not a
// resource kind. The relation graph only draws objects and links.
import type { Draft, GraphEdge, GraphNode, TypeGraph } from "../api/types";
import type { SelectedGraphItem } from "../components/OntologyGraph";
import { AGGREGATIONS, byId, effectiveProperties, isExpression, isRatio, metricDatasetId } from "./coreModel";
import type { ElementRequest } from "./elementInspector";
import { shortObjectName } from "./objectMapping";

export type ResourceKind = "object" | "relation" | "metric" | "dataset";

export const RESOURCE_KIND_LABELS: Record<ResourceKind, string> = {
  object: "对象",
  relation: "关系",
  metric: "指标",
  dataset: "数据集",
};

export type SemanticResource = {
  id: string;
  kind: ResourceKind;
  name: string;
  technical: string;
  subtitle?: string;
  /** Graph selection for objects and relations; metrics and datasets have none. */
  selection: SelectedGraphItem;
  detail: ElementRequest;
};

export function semanticResources(graph: TypeGraph, model?: Draft | null): SemanticResource[] {
  const objectName = (id: string) => graph.nodes.find((n) => n.id === id)?.label ?? "";
  const resources: SemanticResource[] = graph.nodes.map((item: GraphNode) => ({
    id: item.id,
    kind: "object",
    name: shortObjectName({ name: item.label }),
    technical: item.name,
    selection: { category: "node", item },
    detail: { kind: "object_type", id: item.id, tab: "basic", sessionId: null },
  }));
  for (const item of graph.edges.filter((e: GraphEdge) => e.kind === "link_type")) {
    const id = item.link_type_id ?? item.id;
    resources.push({
      id,
      kind: "relation",
      name: shortObjectName({ name: item.label }),
      technical: item.name,
      subtitle: `${objectName(item.source)} → ${objectName(item.target)}`,
      selection: { category: "edge", item },
      detail: { kind: "link_type", id, tab: "basic", sessionId: null },
    });
  }
  if (!model) return resources;
  for (const metric of model.metrics) {
    const dataset = byId(model.datasets, metricDatasetId(model, metric));
    const how = isRatio(metric) ? "比率" : isExpression(metric) ? "表达式" : AGGREGATIONS[metric.aggregation];
    resources.push({
      id: metric.id,
      kind: "metric",
      name: (metric.display_name || metric.name),
      technical: metric.name,
      subtitle: [dataset?.name, how].filter(Boolean).join(" · "),
      selection: null,
      detail: { kind: "metric", id: metric.id, tab: "definition", sessionId: null },
    });
  }
  for (const dataset of model.datasets) {
    resources.push({
      id: dataset.id,
      kind: "dataset",
      name: dataset.name,
      technical: [dataset.schema_name, dataset.table_name].filter(Boolean).join("."),
      subtitle: dataset.snapshot_date_column ? `每日快照 · ${dataset.snapshot_date_column}` : undefined,
      selection: null,
      detail: { kind: "dataset", id: dataset.id, tab: "basic", sessionId: null },
    });
  }
  return resources;
}

/** Objects, links and inheritance only; metrics and datasets are never drawn. */
export function semanticCanvas(graph: TypeGraph, resources: SemanticResource[]): TypeGraph {
  return {
    ...graph,
    nodes: graph.nodes.map((n) => ({ ...n, label: resources.find((r) => r.id === n.id)?.name ?? n.label })),
    edges: graph.edges.filter((e) => e.kind === "extends" || e.kind === "link_type"),
  };
}

/** The session draft as a graph when the server sent none. */
export function draftGraph(draft: Draft): TypeGraph {
  return {
    workspace_id: draft.workspace_id,
    version_id: "draft",
    version_sha256: "",
    version_content_sha256: "",
    normalized_snapshot_sha256: "",
    nodes: draft.object_types.map((t) => ({
      id: t.id,
      kind: "object_type",
      label: (t.display_name || t.name),
      name: t.name,
      description: t.description,
      tags: t.tags,
      attribute_count: effectiveProperties(draft, t.id).length,
    })),
    edges: [
      ...draft.link_types.map((r) => ({
        id: r.id,
        kind: "link_type" as const,
        label: (r.display_name || r.name),
        name: r.name,
        source: r.source_type_id,
        target: r.target_type_id,
        link_type_id: r.id,
        description: r.description,
        multiplicity: r.multiplicity,
      })),
      ...draft.object_types
        .filter((t) => t.extends)
        .map((t) => ({
          id: `extends:${t.id}`,
          kind: "extends" as const,
          label: "继承",
          name: "extends",
          source: t.id,
          target: t.extends!,
        })),
    ],
  };
}
