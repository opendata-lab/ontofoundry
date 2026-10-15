import type {
  GraphEdge,
  GraphNode,
  LegacyDraft,
  TypeGraph,
} from "../api/types";
import type { SelectedGraphItem } from "../components/OntologyGraph";
import { shortObjectName } from "./objectMapping";
import type { ElementRequest } from "./elementInspector";

export type SemanticResource = {
  id: string;
  kind: "object" | "relation" | "value" | "rule";
  name: string;
  technical: string;
  subtitle?: string;
  selection: SelectedGraphItem;
  detail?: ElementRequest;
};
const builtinLabels: Record<string, string> = {
  String: "文本",
  Integer: "整数",
  Decimal: "小数",
  Float: "小数",
  Boolean: "布尔值",
  Date: "日期",
  DateTime: "日期时间",
};
export function semanticResources(
  graph: TypeGraph,
  model?: LegacyDraft | null,
): SemanticResource[] {
  const objects = graph.nodes.filter((n) => n.kind === "object_type");
  const objectName = (id: string) =>
    graph.nodes.find((n) => n.id === id)?.label ?? "";
  const binary = graph.edges.filter((e) => e.kind === "link_type");
  const resources: SemanticResource[] = graph.nodes
    .filter((n) => n.kind !== "value_type" || !n.id.startsWith("value:"))
    .map((item) => ({
      id: item.id,
      kind:
        item.kind === "object_type"
          ? "object"
          : item.kind === "link_type"
            ? "relation"
            : "value",
      name: item.id.startsWith("builtin:")
        ? (builtinLabels[item.technical_name] ?? item.label)
        : shortObjectName({ name: item.label }),
      technical: item.technical_name,
      selection: { category: "node", item },
      subtitle:
        item.kind === "link_type"
          ? [
              objectName(item.owner_ref?.ref ?? ""),
              ...(item.roles
                ?.filter((r) => r.concept.kind === "object_type")
                .map((r) => objectName(r.concept.ref)) ?? []),
            ]
              .filter(Boolean)
              .join(" → ")
          : undefined,
      detail: { kind: item.kind, id: item.id, tab: "basic", sessionId: null },
    }));
  resources.push(
    ...binary.map((item): SemanticResource => ({
      id: item.id,
      kind: "relation",
      name: item.id.startsWith("builtin:")
        ? (builtinLabels[item.technical_name] ?? item.label)
        : shortObjectName({ name: item.label }),
      technical: item.technical_name,
      subtitle: `${objectName(item.source)} → ${objectName(item.target)}`,
      selection: { category: "edge", item },
      detail: { kind: "link_type", id: item.id, tab: "basic", sessionId: null },
    })),
  );
  // V2 attribute-value nodes are projections of properties, not declared value types.
  for (const value of model?.value_types ?? [])
    if (!resources.some((r) => r.id === value.id)) {
      const item: GraphNode = {
        id: value.id,
        kind: "value_type",
        label: value.name,
        technical_name: value.technical_name,
        description: value.description,
        tags: value.tags,
      };
      resources.push({
        id: value.id,
        kind: "value",
        name: value.name,
        technical: value.technical_name,
        selection: { category: "node", item },
        detail: {
          kind: "value_type",
          id: value.id,
          tab: "basic",
          sessionId: null,
        },
      });
    }
  for (const rule of model?.rules ?? []) {
    const property = model?.properties.find((p) => p.id === rule.owner_id);
    const ownerId = property?.owner_type_id ?? rule.owner_id;
    const item = objects.find((n) => n.id === ownerId);
    const relation = resources.find(
      (r) => r.kind === "relation" && r.id === ownerId,
    );
    resources.push({
      id: rule.id,
      kind: "rule",
      name: rule.expression,
      technical: "",
      subtitle: property?.name ?? item?.label ?? relation?.name,
      selection: item
        ? { category: "node", item }
        : (relation?.selection ?? null),
      detail: { kind: "rule", id: rule.id, tab: "rules", sessionId: null },
    });
  }
  return resources;
}
/** Record relations are edges with optional role branches, as in the approved canvas. */
export function semanticCanvas(
  graph: TypeGraph,
  resources: SemanticResource[],
): TypeGraph {
  const nodes = [
    ...graph.nodes
      .filter((n) => n.kind !== "link_type" && !n.id.startsWith("value:"))
      .map((n) => ({
        ...n,
        label: resources.find((r) => r.id === n.id)?.name ?? n.label,
      })),
  ];
  for (const resource of resources)
    if (
      resource.kind === "value" &&
      resource.selection?.category === "node" &&
      !nodes.some((n) => n.id === resource.id)
    )
      nodes.push(resource.selection.item);
  const edges = graph.edges.filter(
    (e) => e.kind === "extends" || e.kind === "link_type",
  );
  for (const relation of graph.nodes.filter((n) => n.kind === "link_type")) {
    const source =
      relation.owner_ref?.ref ??
      graph.edges.find((e) => e.source === relation.id && e.kind === "role")
        ?.target;
    if (!source) continue;
    const incidences = graph.edges.filter(
      (e) => e.source === relation.id && e.kind === "role",
    );
    const declaredRoles = new Set(relation.roles?.map((role) => role.id) ?? []);
    const ownerEdge = incidences.find(
      (e) =>
        e.target === source && (!e.role_id || !declaredRoles.has(e.role_id)),
    );
    const roles = incidences.filter((e) => e.id !== ownerEdge?.id);
    const first = roles.find((e) =>
      nodes.some((n) => n.id === e.target && n.kind === "object_type"),
    );
    const main: GraphEdge = {
      id: relation.id,
      kind: "link_type",
      source,
      target: first?.target ?? source,
      label: relation.label,
      technical_name: relation.technical_name,
      link_type_id: relation.id,
    };
    edges.push(
      main,
      ...roles
        .filter((r) => r.id !== first?.id)
        .map((role) => ({ ...role, source, link_type_id: relation.id })),
    );
  }
  return { ...graph, nodes, edges };
}
