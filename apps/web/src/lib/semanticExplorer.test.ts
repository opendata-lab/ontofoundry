import { describe, expect, it } from "vitest";
import { example } from "../test/drafts";
import { draftGraph, semanticCanvas, semanticResources } from "./semanticExplorer";

describe("semantic resources", () => {
  it("lists objects, relations, metrics and datasets; only objects and links are drawn", () => {
    const draft = example("01-basic-sales");
    const graph = draftGraph(draft);
    const resources = semanticResources(graph, draft);
    const count = (kind: string) => resources.filter((r) => r.kind === kind).length;
    expect([count("object"), count("relation"), count("metric"), count("dataset")]).toEqual([2, 1, 10, 2]);
    const metric = resources.find((r) => r.technical === "order_amount")!;
    expect(metric.subtitle).toBe("orders · 求和");
    expect(metric.selection).toBeNull();
    expect(metric.detail).toMatchObject({ kind: "metric", id: metric.id });
    expect(resources.find((r) => r.kind === "dataset" && r.name === "orders")?.detail.kind).toBe("dataset");
    const canvas = semanticCanvas(graph, resources);
    expect(canvas.nodes).toHaveLength(2);
    expect(canvas.edges.every((e) => e.kind === "link_type" || e.kind === "extends")).toBe(true);
  });
  it("draws inheritance as extends edges from the child", () => {
    const draft = example("06-inheritance");
    const graph = draftGraph(draft);
    const person = draft.object_types.find((o) => o.name === "person")!;
    expect(graph.edges.find((e) => e.kind === "extends" && e.source === person.id)?.target).toBe(person.extends);
  });
});
