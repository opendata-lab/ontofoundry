import type { MaterialObject, MaterialLink, GraphNode, GraphEdge, LinkDefinition } from "../api/types";

/** A read-only binary view. Persisted role IDs, never value-array order, select ends. */
export function materialLinkEndpoints(link: MaterialLink, relation?: Pick<LinkDefinition, "roles" | "owner_ref" | "endpoint_direction" | "owner_role_id">) {
  const definition = relation ?? link;
  const roles = definition.roles;
  if (!roles) return { source_id: link.source_id, target_id: link.target_id };
  if (roles.length !== 1 || definition.owner_ref?.kind !== "object_type" || roles[0].concept.kind !== "object_type")
    return { source_id: null, target_id: null };
  const values = link.role_values ?? [];
  const extra = values.find(v => v.role_id === roles[0].id)?.object_id;
  const owner = definition.owner_role_id
    ? values.find(v => v.role_id === definition.owner_role_id)?.object_id
    : values.length === 2 ? values.find(v => v.role_id !== roles[0].id)?.object_id : undefined;
  const reverse = definition.endpoint_direction === "reverse";
  return { source_id: link.source_id ?? (reverse ? extra : owner) ?? null,
    target_id: link.target_id ?? (reverse ? owner : extra) ?? null };
}

export function instanceNeighborhood(
  objects: MaterialObject[],
  links: MaterialLink[],
  centerId: string,
  depth: number,
) {
  const ends = (link: MaterialLink) => link.role_values?.flatMap(r => r.object_id ? [r.object_id] : []) ?? [link.source_id, link.target_id].filter((id): id is string => !!id);
  const ids = new Set([centerId]);
  for (let i = 0; i < Math.min(depth, 3); i++) {
    const frontier = new Set(ids);
    for (const link of links) {
      if (ends(link).some(id => frontier.has(id)))
        for (const id of ends(link)) if (ids.size < 100) ids.add(id);
    }
  }
  return {
    objects: objects.filter((o) => ids.has(o.id)),
    links: links
      .filter((l) => ends(l).length > 0 && ends(l).every(id => ids.has(id)))
      .slice(0, 300),
  };
}


export function instanceCanvas(objects: MaterialObject[], links: MaterialLink[], types: { id: string; name: string }[], relations: LinkDefinition[]): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = objects.map(o => ({ id: o.id, kind: "object_type", label: o.name, technical_name: types.find(t => t.id === o.type_id)?.name ?? "", description: "实例", tags: [] }));
  const edges: GraphEdge[] = [];
  for (const link of links) {
    const relation = relations.find(r => r.id === link.type_id);
    const label = relation?.name ?? "关系";
    const ends = materialLinkEndpoints(link, relation);
    if (ends.source_id && ends.target_id) {
      edges.push({ id: link.id, kind: "link_type", label, technical_name: "document", source: ends.source_id, target: ends.target_id });
      continue;
    }
    nodes.push({ id: link.id, kind: "link_type", label, technical_name: "document", description: "实例关系", tags: [] });
    for (const value of link.role_values ?? []) {
      const target = value.object_id ?? `value:${link.id}:${value.role_id}`;
      if (!value.object_id) nodes.push({ id: target, kind: "value_type", label: JSON.stringify(value.value), technical_name: "role_value", description: "角色值", tags: [] });
      edges.push({ id: `${link.id}:${value.role_id}`, kind: "role", label: link.all_roles?.find(r => r.id === value.role_id)?.name ?? "角色", technical_name: "role", source: link.id, target });
    }
  }
  return { nodes, edges };
}
