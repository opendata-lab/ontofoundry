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
  it("lists actions in semantic resources without drawing them on the canvas", () => {
    const draft = example("01-basic-sales");
    const order = draft.object_types[0];
    draft.actions = [
      {
        id: "act-bound",
        name: "cancel_order",
        display_name: "取消订单",
        description: "",
        synonyms: [],
        tags: [],
        target_type_id: order.id,
        parameters: [],
        effects: [],
        evidence: [],
      },
      {
        id: "act-global",
        name: "daily_settlement",
        display_name: "每日结算",
        description: "",
        synonyms: [],
        tags: [],
        target_type_id: null,
        parameters: [],
        effects: [],
        evidence: [],
      },
    ];
    const graph = draftGraph(draft);
    const resources = semanticResources(graph, draft);
    const actions = resources.filter((r) => r.kind === "action");
    expect(actions).toHaveLength(2);
    expect(actions.find((a) => a.id === "act-bound")?.subtitle).toBe(order.display_name || order.name);
    expect(actions.find((a) => a.id === "act-global")?.subtitle).toBe("全局动作");
    expect(actions.every((a) => a.selection === null && a.detail.kind === "action")).toBe(true);
    const canvas = semanticCanvas(graph, resources);
    expect(canvas.nodes).toHaveLength(2);
  });
});
