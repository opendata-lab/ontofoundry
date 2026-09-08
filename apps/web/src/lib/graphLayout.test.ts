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
  type Point,
} from "./graphLayout";

/** A chain of object types, each related to the one before it. */
function model(objectCount: number) {
  const nodes: LayoutNode[] = [];
  const edges: LayoutEdge[] = [];
  for (let i = 0; i < objectCount; i++) {
    const id = "o" + i;
    nodes.push({ id });
    if (i) edges.push({ id: "rel" + i, source: "o" + (i - 1), target: id });
  }
  return { nodes, edges };
}

/** Pairs of cards whose rectangles overlap on screen. */
function overlapping(nodes: LayoutNode[], points: Map<string, Point>) {
  const pairs: string[] = [];
  for (const a of nodes)
    for (const b of nodes) {
      if (a.id >= b.id) continue;
      const one = points.get(a.id)!;
      const two = points.get(b.id)!;
      if (
        Math.abs(one.x - two.x) < NODE_WIDTH &&
        Math.abs(one.y - two.y) < NODE_HEIGHT
      )
        pairs.push(a.id + "/" + b.id);
    }
  return pairs;
}

describe("图谱布局", () => {
  it("places every node once, deterministically, inside a positive canvas", () => {
    const { nodes, edges } = model(9);
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
    const columns = new Set<number>();
    for (const node of nodes) columns.add(Math.round(points.get(node.id)!.x));
    expect(columns.size).toBeGreaterThan(1);
    expect(overlapping(nodes, points)).toEqual([]);
  });

  it("leaves no card sitting on another, however big the model gets", () => {
    // The canvas used to crowd once a model outgrew a fixed pass budget, which
    // read on screen as broken rather than dense.
    for (const size of [30, 80, 160]) {
      const { nodes, edges } = model(size);
      // Cross relations: a real model is a web, not a chain.
      for (let i = 0; i < size; i += 3)
        edges.push({
          id: "cross" + i,
          source: "o" + i,
          target: "o" + ((i * 7 + 5) % size),
        });
      const points = layoutGraph(nodes, edges);
      expect(points.size).toBe(size);
      expect(overlapping(nodes, points)).toEqual([]);
    }
  });

  it("lays out a graph that has no edges at all", () => {
    const nodes: LayoutNode[] = [{ id: "a" }, { id: "b" }];
    const points = layoutGraph(nodes, []);
    const [one, two] = [points.get("a")!, points.get("b")!];
    expect(points.size).toBe(2);
    expect(
      Math.abs(one.x - two.x) >= NODE_WIDTH ||
        Math.abs(one.y - two.y) >= NODE_HEIGHT,
    ).toBe(true);
  });

  it("packs unconnected parts instead of letting them drift apart", () => {
    const first = model(6);
    const second = model(4);
    const nodes = [
      ...first.nodes,
      ...second.nodes.map((node) => ({ ...node, id: "b" + node.id })),
    ];
    const edges = [
      ...first.edges,
      ...second.edges.map((edge) => ({
        ...edge,
        id: "b" + edge.id,
        source: "b" + edge.source,
        target: "b" + edge.target,
      })),
    ];
    const points = layoutGraph(nodes, edges);
    const xs = [...points.values()].map((p) => p.x);
    const ys = [...points.values()].map((p) => p.y);
    const width = Math.max(...xs) - Math.min(...xs);
    const height = Math.max(...ys) - Math.min(...ys);
    // Two chains of five relations each: without packing the two parts drift
    // to opposite corners and the canvas has to zoom far out to fit them.
    expect(width).toBeLessThan(2600);
    expect(height).toBeLessThan(1400);
  });
});

describe("平行关系", () => {
  it("fans relations that share a pair and leaves a lone relation straight", () => {
    const edges: LayoutEdge[] = [
      { id: "r1", source: "a", target: "b" },
      { id: "r2", source: "a", target: "b" },
      { id: "r3", source: "b", target: "a" },
      { id: "solo", source: "b", target: "c" },
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
