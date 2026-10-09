import { describe, expect, it } from "vitest";
import { instanceCanvas, instanceNeighborhood, materialLinkEndpoints } from "./instanceGraph";
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

it("expands a n-ary fact through all entity role values", () => {
  const objects = ["a", "b", "c"].map(id => ({ id, type_id: "type", name: id, values: {}, evidence: [] }));
  const links = [{ id: "fact", type_id: "link", source_id: null, target_id: null, evidence: [], role_values: [
    { role_id: "owner", object_id: "a" }, { role_id: "other", object_id: "b" }, { role_id: "third", object_id: "c" }, { role_id: "value", value: 42 },
  ] }];
  const result = instanceNeighborhood(objects, links, "a", 1);
  expect(result.objects.map(o => o.id)).toEqual(["a", "b", "c"]);
  expect(result.links).toEqual(links);
});


it.each([false, true])("derives binary graph endpoints by role ID (reverse=%s)", reverse => {
  const relation = { id: "r", name: "针对订单", technical_name: "targets", description: "", tags: [],
    source_type_id: "return", target_type_id: "order", multiplicity: "many_to_one",
    owner_ref: { kind: "object_type" as const, ref: "return" }, endpoint_direction: reverse ? "reverse" as const : "forward" as const,
    roles: [{ id: "other", concept: { kind: "object_type" as const, ref: "order" } }] };
  const fact = { id: "fact", type_id: "r", source_id: null, target_id: null, evidence: [],
    role_values: [{ role_id: "other", object_id: "b" }, { role_id: "owner", object_id: "a" }] };
  expect(materialLinkEndpoints(fact, relation)).toEqual({ source_id: reverse ? "b" : "a", target_id: reverse ? "a" : "b" });
  const graph = instanceCanvas(objects, [fact], [], [relation]);
  expect(graph.edges).toHaveLength(1);
  expect(graph.edges[0]).toMatchObject({ source: reverse ? "b" : "a", target: reverse ? "a" : "b", kind: "link_type" });
  expect(graph.nodes.some(n => n.id === "fact")).toBe(false);
  expect(fact.source_id).toBeNull();
});
