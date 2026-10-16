import type { GraphEdge, GraphNode, LinkType } from "../api/types";

/** What the instance graph needs from a fact or a database row. */
export type InstanceNode = { id: string; type_id: string; display_text: string };
/** A binary instance link; links are always source → target in core-1. */
export type InstanceEdge = { id: string; type_id: string; source_id: string; target_id: string };

/** Facts within `depth` hops of the center, capped like the server (100 / 300). */
export function instanceNeighborhood<N extends InstanceNode, E extends InstanceEdge>(
  objects: N[],
  links: E[],
  centerId: string,
  depth: number,
) {
  const ids = new Set([centerId]);
  for (let i = 0; i < Math.min(depth, 3); i++) {
    const frontier = new Set(ids);
    for (const link of links) {
      if (frontier.has(link.source_id) || frontier.has(link.target_id)) {
        for (const id of [link.source_id, link.target_id]) if (ids.size < 100) ids.add(id);
      }
    }
  }
  return {
    objects: objects.filter((o) => ids.has(o.id)),
    links: links.filter((l) => ids.has(l.source_id) && ids.has(l.target_id)).slice(0, 300),
  };
}

export function instanceCanvas(
  objects: InstanceNode[],
  links: InstanceEdge[],
  types: { id: string; name: string }[],
  relations: Pick<LinkType, "id" | "name">[],
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = objects.map((o) => ({
    id: o.id,
    kind: "object_type",
    label: o.display_text,
    technical_name: types.find((t) => t.id === o.type_id)?.name ?? "",
    description: "实例",
    tags: [],
  }));
  const edges: GraphEdge[] = links.map((link) => ({
    id: link.id,
    kind: "link_type",
    label: relations.find((r) => r.id === link.type_id)?.name ?? "关系",
    technical_name: "instance",
    source: link.source_id,
    target: link.target_id,
    link_type_id: link.type_id,
  }));
  return { nodes, edges };
}
