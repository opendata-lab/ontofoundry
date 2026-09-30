import type { MaterialObject, MaterialLink } from "../api/types";

export function instanceNeighborhood(
  objects: MaterialObject[],
  links: MaterialLink[],
  centerId: string,
  depth: number,
) {
  const ids = new Set([centerId]);
  for (let i = 0; i < Math.min(depth, 3); i++) {
    const frontier = new Set(ids);
    for (const link of links) {
      if (frontier.has(link.source_id) || frontier.has(link.target_id)) {
        if (ids.size < 100) ids.add(link.source_id);
        if (ids.size < 100) ids.add(link.target_id);
      }
    }
  }
  return {
    objects: objects.filter((o) => ids.has(o.id)),
    links: links
      .filter((l) => ids.has(l.source_id) && ids.has(l.target_id))
      .slice(0, 300),
  };
}
