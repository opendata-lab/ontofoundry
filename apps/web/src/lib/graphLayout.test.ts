import { describe, expect, it } from "vitest";
import {
  NODE_HEIGHT,
  NODE_WIDTH,
  borderPoint,
  edgeGeometry,
  layoutGraph,
  parallelOffsets,
  selfLoopGeometry,
  type LayoutEdge,
  type LayoutNode,
} from "./graphLayout";

function model(objectCount: number, attributes: Record<string, number> = {}) {
  const nodes: LayoutNode[] = [];
  const edges: LayoutEdge[] = [];
  for (let i = 0; i < objectCount; i++) {
    const id = "o" + i;
    nodes.push({ id, kind: "object_type" });
    if (i)
      edges.push({
        id: "rel" + i,
        kind: "link_type",
        source: "o" + (i - 1),
        target: id,
      });
    for (let a = 0; a < (attributes[id] ?? 0); a++) {
      const value = id + "-v" + a;
      nodes.push({ id: value, kind: "value_type" });
      edges.push({ id: value, kind: "attribute", source: id, target: value });
    }
  }
  return { nodes, edges };
}

function distance(a: { x: number; y: number }, b: { x: number; y: number }) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

describe("图谱布局", () => {
  it("places every node once, deterministically, inside a positive canvas", () => {
    const { nodes, edges } = model(9, { o0: 3, o4: 7 });
    const first = layoutGraph(nodes, edges);
    const second = layoutGraph(nodes, edges);
    expect(first.size).toBe(nodes.length);
    for (const node of nodes) {
      const point = first.get(node.id)!;
      expect(point).toEqual(second.get(node.id));
      expect(point.x).toBeGreaterThan(0);
      expect(point.y).toBeGreaterThan(0);
    }
  });

  it("keeps object cards from overlapping instead of stacking them in one column", () => {
    const { nodes, edges } = model(12);
    const points = layoutGraph(nodes, edges);
    const objects = nodes.filter((n) => n.kind === "object_type");
    const columns = new Set<number>();
    for (const node of objects) columns.add(Math.round(points.get(node.id)!.x));
    expect(columns.size).toBeGreaterThan(1);
    for (const a of objects)
      for (const b of objects) {
        if (a.id >= b.id) continue;
        const one = points.get(a.id)!;
        const two = points.get(b.id)!;
        const clearX = Math.abs(one.x - two.x) >= NODE_WIDTH;
        const clearY = Math.abs(one.y - two.y) >= NODE_HEIGHT;
        expect(clearX || clearY).toBe(true);
      }
  });

  it("orbits attributes around the object that declares them", () => {
    const { nodes, edges } = model(4, { o1: 6 });
    const points = layoutGraph(nodes, edges);
    const owner = points.get("o1")!;
    const values = [...Array(6)].map((_, a) => points.get("o1-v" + a)!);
    for (const value of values) {
      expect(distance(value, owner)).toBeGreaterThan(120);
      expect(distance(value, owner)).toBeLessThan(420);
    }
    for (const a of values)
      for (const b of values)
        if (a !== b) expect(distance(a, b)).toBeGreaterThan(40);
  });

  it("lays out a graph that has no edges at all", () => {
    const nodes: LayoutNode[] = [
      { id: "a", kind: "object_type" },
      { id: "b", kind: "object_type" },
    ];
    const points = layoutGraph(nodes, []);
    expect(points.size).toBe(2);
    expect(distance(points.get("a")!, points.get("b")!)).toBeGreaterThan(
      NODE_WIDTH,
    );
  });
});

describe("平行关系", () => {
  it("fans relations that share a pair and leaves a lone relation straight", () => {
    const edges: LayoutEdge[] = [
      { id: "r1", kind: "link_type", source: "a", target: "b" },
      { id: "r2", kind: "link_type", source: "a", target: "b" },
      { id: "r3", kind: "link_type", source: "b", target: "a" },
      { id: "solo", kind: "link_type", source: "b", target: "c" },
    ];
    const offsets = parallelOffsets(edges);
    expect(offsets.get("solo")).toBe(0);
    // Each offset is read in its own edge's direction, so compare them on the
    // shared a→b axis: the three bends must land on three different sides.
    const shared = [
      offsets.get("r1")!,
      offsets.get("r2")!,
      -offsets.get("r3")!,
    ];
    expect(new Set(shared).size).toBe(3);
    expect(shared.reduce((sum, value) => sum + value, 0)).toBeCloseTo(0);
    expect(Math.max(...shared.map(Math.abs))).toBeGreaterThan(20);
  });
});

describe("边几何", () => {
  const source = { x: 0, y: 0, width: 160, height: 40 };
  const target = { x: 400, y: 300, width: 160, height: 40 };

  it("anchors on the card border and bends by the given offset", () => {
    const straight = edgeGeometry(source, target, 0);
    const bent = edgeGeometry(source, target, 60);
    expect(straight.path.startsWith("M ")).toBe(true);
    expect(straight.path).toContain("Q");
    expect(
      Math.hypot(bent.labelX - straight.labelX, bent.labelY - straight.labelY),
    ).toBeGreaterThan(20);
    const anchor = borderPoint(source, { x: 400, y: 320 });
    const onVertical = Math.abs(Math.abs(anchor.x - 80) - 85) < 0.001;
    const onHorizontal = Math.abs(Math.abs(anchor.y - 20) - 25) < 0.001;
    expect(onVertical || onHorizontal).toBe(true);
  });

  it("keeps the label between the two cards", () => {
    const { labelX, labelY } = edgeGeometry(source, target, 0);
    expect(labelX).toBeGreaterThan(80);
    expect(labelX).toBeLessThan(480);
    expect(labelY).toBeGreaterThan(20);
    expect(labelY).toBeLessThan(320);
  });

  it("draws self relations as a loop that grows with each repetition", () => {
    const inner = selfLoopGeometry(source, 0);
    const outer = selfLoopGeometry(source, 2);
    expect(inner.path.startsWith("M ")).toBe(true);
    expect(outer.labelX).toBeGreaterThan(inner.labelX);
    expect(outer.labelY).toBeLessThan(inner.labelY);
  });

  it("does not divide by zero when two cards sit on the same spot", () => {
    const geometry = edgeGeometry(source, { ...source }, 0);
    expect(geometry.path).not.toContain("NaN");
    expect(Number.isFinite(geometry.labelX)).toBe(true);
  });
});
