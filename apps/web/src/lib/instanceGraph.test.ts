import { describe, expect, it } from "vitest";
import { instanceNeighborhood } from "./instanceGraph";
const objects = ["a", "b", "c", "d", "isolated"].map((id) => ({
  id,
  type_id: "t",
  name: id,
  values: {},
  evidence: [],
}));
const links = [
  ["a", "b"],
  ["b", "c"],
  ["c", "d"],
  ["c", "a"],
].map(([source_id, target_id], i) => ({
  id: String(i),
  source_id,
  target_id,
  type_id: "r",
  evidence: [],
}));
describe("文档实例邻域", () => {
  it("expands existing links in both directions without duplicates or invented facts", () => {
    expect(
      instanceNeighborhood(objects, links, "a", 1).objects.map((o) => o.id),
    ).toEqual(["a", "b", "c"]);
    expect(
      instanceNeighborhood(objects, links, "a", 2).objects.map((o) => o.id),
    ).toEqual(["a", "b", "c", "d"]);
    expect(
      instanceNeighborhood(objects, links, "isolated", 3).links,
    ).toHaveLength(0);
  });
  it("bounds the number of expanded nodes", () => {
    const nodes = Array.from({ length: 110 }, (_, i) => ({
      ...objects[0],
      id: String(i),
    }));
    const edges = nodes
      .slice(1)
      .map((o) => ({ ...links[0], id: o.id, source_id: "0", target_id: o.id }));
    const result = instanceNeighborhood(nodes, edges, "0", 1);
    expect(result.objects).toHaveLength(100);
    expect(result.links).toHaveLength(99);
  });
});
