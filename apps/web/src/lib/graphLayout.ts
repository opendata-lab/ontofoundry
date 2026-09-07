// Deterministic geometry for the ontology canvas: a fixed force layout plus the
// floating-edge maths React Flow does not provide. Pure functions so the same
// model always draws the same picture and can be tested without a DOM.
export type LayoutNode = {
  id: string;
  kind: "object_type" | "value_type";
};
export type LayoutEdge = {
  id: string;
  kind: "attribute" | "link_type" | "extends";
  source: string;
  target: string;
};
export type Point = { x: number; y: number };
export type Rect = { x: number; y: number; width: number; height: number };

export const NODE_WIDTH = 176;
export const NODE_HEIGHT = 46;
const IDEAL_DISTANCE = 250;
// The simulation only fixes relative placement; this is the density the canvas
// is finally scaled to, so a five-node chain and a fifty-node web read alike.
const TARGET_EDGE_LENGTH = 250;
const VALUE_RING = 158;
const VALUE_RING_STEP = 96;
const VALUE_PER_RING = 5;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const MARGIN = 60;
const PARALLEL_GAP = 40;

function center(rect: Rect): Point {
  return { x: rect.x + rect.width / 2, y: rect.y + rect.height / 2 };
}

// Sunflower seeding: spread out, deterministic and free of the rotational
// symmetry that leaves a ring layout stuck in its initial shape.
function seed(count: number, index: number): Point {
  const radius = IDEAL_DISTANCE * 0.62 * Math.sqrt(index + 0.5);
  const angle = index * GOLDEN_ANGLE;
  return {
    x: Math.cos(angle) * radius * (count > 1 ? 1 : 0),
    y: Math.sin(angle) * radius * (count > 1 ? 1 : 0),
  };
}

function simulate(count: number, links: [number, number][]) {
  const x = new Float64Array(count);
  const y = new Float64Array(count);
  for (let i = 0; i < count; i++) {
    const start = seed(count, i);
    x[i] = start.x;
    y[i] = start.y;
  }
  if (count < 2) return { x, y };
  const dx = new Float64Array(count);
  const dy = new Float64Array(count);
  const steps = Math.max(90, Math.min(320, Math.round(9000 / count)));
  let temperature = IDEAL_DISTANCE * 0.85;
  const cooling = temperature / (steps + 1);
  for (let step = 0; step < steps; step++) {
    dx.fill(0);
    dy.fill(0);
    for (let i = 0; i < count; i++) {
      for (let j = i + 1; j < count; j++) {
        let ox = x[i] - x[j];
        let oy = y[i] - y[j];
        let distance = Math.hypot(ox, oy);
        if (distance < 0.5) {
          // Deterministic nudge so coincident nodes still separate.
          ox = ((i % 5) + 1) * 0.2;
          oy = ((j % 7) + 1) * 0.2;
          distance = Math.hypot(ox, oy);
        }
        const force = (IDEAL_DISTANCE * IDEAL_DISTANCE) / distance;
        dx[i] += (ox / distance) * force;
        dy[i] += (oy / distance) * force;
        dx[j] -= (ox / distance) * force;
        dy[j] -= (oy / distance) * force;
      }
    }
    for (const [a, b] of links) {
      const ox = x[a] - x[b];
      const oy = y[a] - y[b];
      const distance = Math.max(Math.hypot(ox, oy), 0.5);
      const force = (distance * distance) / IDEAL_DISTANCE;
      dx[a] -= (ox / distance) * force;
      dy[a] -= (oy / distance) * force;
      dx[b] += (ox / distance) * force;
      dy[b] += (oy / distance) * force;
    }
    for (let i = 0; i < count; i++) {
      dx[i] -= x[i] * 0.035;
      dy[i] -= y[i] * 0.045;
      const length = Math.max(Math.hypot(dx[i], dy[i]), 0.001);
      const move = Math.min(length, temperature);
      x[i] += (dx[i] / length) * move;
      y[i] += (dy[i] / length) * move;
    }
    temperature -= cooling;
  }
  return { x, y };
}

// Pull overlapping cards apart along their shallowest axis; screens are wide, so
// horizontal room is cheaper than vertical room.
function separate(
  points: Point[],
  gapX = NODE_WIDTH + 52,
  gapY = NODE_HEIGHT + 46,
) {
  for (let pass = 0; pass < 60; pass++) {
    let moved = false;
    for (let i = 0; i < points.length; i++) {
      for (let j = i + 1; j < points.length; j++) {
        const dx = points[j].x - points[i].x;
        const dy = points[j].y - points[i].y;
        const overlapX = gapX - Math.abs(dx);
        const overlapY = gapY - Math.abs(dy);
        if (overlapX <= 0 || overlapY <= 0) continue;
        moved = true;
        if (overlapX < overlapY) {
          const shift = (overlapX / 2 + 1) * (dx < 0 ? -1 : 1);
          points[i].x -= shift;
          points[j].x += shift;
        } else {
          const shift = (overlapY / 2 + 1) * (dy < 0 ? -1 : 1);
          points[i].y -= shift;
          points[j].y += shift;
        }
      }
    }
    if (!moved) break;
  }
}

// Turn the drawing so its longest axis lies flat: canvases are landscape, and a
// diagonal cloud wastes the room a horizontal one fills.
function alignToCanvas(points: Point[]) {
  if (points.length < 3) return;
  let cx = 0;
  let cy = 0;
  for (const point of points) {
    cx += point.x / points.length;
    cy += point.y / points.length;
  }
  let xx = 0;
  let yy = 0;
  let xy = 0;
  for (const point of points) {
    xx += (point.x - cx) ** 2;
    yy += (point.y - cy) ** 2;
    xy += (point.x - cx) * (point.y - cy);
  }
  const angle = 0.5 * Math.atan2(2 * xy, xx - yy);
  const cos = Math.cos(-angle);
  const sin = Math.sin(-angle);
  for (const point of points) {
    const dx = point.x - cx;
    const dy = point.y - cy;
    point.x = cx + dx * cos - dy * sin;
    point.y = cy + dx * sin + dy * cos;
  }
}

// Force layouts stretch with node count, which then forces the canvas to zoom
// out until labels are unreadable. Rescale so the median relation keeps a fixed
// on-screen length instead.
function densityScale(points: Point[], links: [number, number][]) {
  if (links.length < 1) return 1;
  const lengths = links
    .map(([a, b]) =>
      Math.hypot(points[a].x - points[b].x, points[a].y - points[b].y),
    )
    .sort((one, two) => one - two);
  const median = lengths[Math.floor(lengths.length / 2)];
  if (!median) return 1;
  return Math.min(2.5, Math.max(0.35, TARGET_EDGE_LENGTH / median));
}

// Attributes belong on the side of a card that its relations do not use, so the
// relation lanes and their labels stay clear.
function satelliteDirection(
  base: Point,
  positions: Map<string, Point>,
  neighbours: string[] | undefined,
) {
  let x = 0;
  let y = 0;
  for (const id of neighbours ?? []) {
    const other = positions.get(id);
    if (!other) continue;
    const length = Math.hypot(other.x - base.x, other.y - base.y) || 1;
    x += (other.x - base.x) / length;
    y += (other.y - base.y) / length;
  }
  if (Math.hypot(x, y) > 0.15) return Math.atan2(-y, -x);
  return Math.atan2(base.y, base.x) || 0;
}

/** Groups of node indices that are reachable from each other. */
function components(count: number, links: [number, number][]): number[][] {
  const parent = [...Array(count)].map((_, index) => index);
  const find = (index: number): number => {
    while (parent[index] !== index) {
      parent[index] = parent[parent[index]];
      index = parent[index];
    }
    return index;
  };
  for (const [a, b] of links) {
    const rootA = find(a);
    const rootB = find(b);
    if (rootA !== rootB) parent[rootA] = rootB;
  }
  const grouped = new Map<number, number[]>();
  for (let index = 0; index < count; index++) {
    const root = find(index);
    grouped.set(root, [...(grouped.get(root) ?? []), index]);
  }
  // Biggest first so the main model sits at the top left of the canvas.
  return [...grouped.values()].sort(
    (one, two) => two.length - one.length || one[0] - two[0],
  );
}

/** Shelf packing: parts sit side by side and wrap into a landscape block. */
function packComponents(
  boxes: { indices: number[]; width: number; height: number }[],
  points: Point[],
) {
  const gap = 120;
  // Count the gap as part of each part's footprint, then aim for a block
  // wider than it is tall.
  const area = boxes.reduce(
    (sum, box) => sum + (box.width + gap) * (box.height + gap),
    0,
  );
  const target = Math.max(boxes[0]?.width ?? 0, Math.sqrt(area * 1.9));
  let cursorX = 0;
  let cursorY = 0;
  let rowHeight = 0;
  for (const box of boxes) {
    if (cursorX > 0 && cursorX + box.width > target) {
      cursorX = 0;
      cursorY += rowHeight + gap;
      rowHeight = 0;
    }
    for (const index of box.indices) {
      points[index] = {
        x: points[index].x + cursorX,
        y: points[index].y + cursorY,
      };
    }
    cursorX += box.width + gap;
    rowHeight = Math.max(rowHeight, box.height);
  }
}

/**
 * Centre positions for every node. Object types run through the force
 * simulation; value types are fanned around the object that declares them so
 * attributes read as satellites instead of a second column.
 */
export function layoutGraph(
  nodes: LayoutNode[],
  edges: LayoutEdge[],
): Map<string, Point> {
  const objectIds = new Set(
    nodes.filter((node) => node.kind === "object_type").map((node) => node.id),
  );
  const owners = new Map<string, string>();
  for (const edge of edges) {
    if (edge.kind !== "attribute") continue;
    if (!objectIds.has(edge.source) || objectIds.has(edge.target)) continue;
    if (!owners.has(edge.target)) owners.set(edge.target, edge.source);
  }
  const anchors = nodes.filter(
    (node) => node.kind === "object_type" || !owners.has(node.id),
  );
  const anchorIndex = new Map(anchors.map((node, index) => [node.id, index]));
  const links: [number, number][] = [];
  for (const edge of edges) {
    const a = anchorIndex.get(edge.source);
    const b = anchorIndex.get(edge.target);
    if (a === undefined || b === undefined || a === b) continue;
    links.push([a, b]);
  }
  // Unconnected parts of a model repel each other without any edge pulling them
  // back, which leaves the canvas mostly empty. Lay each part out on its own,
  // then pack the parts.
  const points = anchors.map(() => ({ x: 0, y: 0 }));
  const groups = components(anchors.length, links);
  const boxes: { indices: number[]; width: number; height: number }[] = [];
  for (const indices of groups) {
    const local = new Map(indices.map((index, position) => [index, position]));
    const inner: [number, number][] = links
      .filter(([a]) => local.has(a))
      .map(([a, b]) => [local.get(a)!, local.get(b)!]);
    const { x, y } = simulate(indices.length, inner);
    const laid = indices.map((_, position) => ({
      x: x[position],
      y: y[position],
    }));
    alignToCanvas(laid);
    // Widen before collision removal: the canvas is landscape, so should the graph.
    for (const point of laid) {
      point.x *= 1.18;
      point.y *= 0.82;
    }
    const scale = densityScale(laid, inner);
    for (const point of laid) {
      point.x *= scale;
      point.y *= scale;
    }
    separate(laid);
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const point of laid) {
      minX = Math.min(minX, point.x);
      minY = Math.min(minY, point.y);
      maxX = Math.max(maxX, point.x);
      maxY = Math.max(maxY, point.y);
    }
    indices.forEach((index, position) => {
      points[index] = {
        x: laid[position].x - minX,
        y: laid[position].y - minY,
      };
    });
    boxes.push({
      indices,
      width: maxX - minX + NODE_WIDTH,
      height: maxY - minY + NODE_HEIGHT,
    });
  }
  packComponents(boxes, points);
  const positions = new Map<string, Point>();
  anchors.forEach((node, index) => positions.set(node.id, points[index]));

  const satellites = new Map<string, string[]>();
  for (const node of nodes) {
    const owner = owners.get(node.id);
    if (!owner || !positions.has(owner)) continue;
    satellites.set(owner, [...(satellites.get(owner) ?? []), node.id]);
  }
  const relatives = new Map<string, string[]>();
  for (const edge of edges) {
    if (edge.kind !== "link_type") continue;
    if (!positions.has(edge.source) || !positions.has(edge.target)) continue;
    relatives.set(edge.source, [
      ...(relatives.get(edge.source) ?? []),
      edge.target,
    ]);
    relatives.set(edge.target, [
      ...(relatives.get(edge.target) ?? []),
      edge.source,
    ]);
  }
  for (const [owner, values] of satellites) {
    const base = positions.get(owner)!;
    const outward = satelliteDirection(base, positions, relatives.get(owner));
    values.forEach((id, index) => {
      const ring = Math.floor(index / VALUE_PER_RING);
      const inRing = Math.min(
        VALUE_PER_RING,
        values.length - ring * VALUE_PER_RING,
      );
      const slot = index % VALUE_PER_RING;
      const span = Math.min(
        Math.PI * 0.95,
        0.34 * Math.max(inRing - 1, 0) + 0.2,
      );
      const angle =
        outward + (inRing > 1 ? (slot / (inRing - 1) - 0.5) * span : 0);
      const radius = VALUE_RING + ring * VALUE_RING_STEP;
      positions.set(id, {
        x: base.x + Math.cos(angle) * radius,
        y: base.y + Math.sin(angle) * radius * 0.9,
      });
    });
  }

  // Satellites are placed geometrically, so give the whole picture one last
  // narrow-gap pass to stop attribute cards from sitting on their neighbours.
  const placed = nodes.filter((node) => positions.has(node.id));
  const all = placed.map((node) => positions.get(node.id)!);
  separate(all, NODE_WIDTH - 32, NODE_HEIGHT + 12);
  placed.forEach((node, index) => positions.set(node.id, all[index]));

  let minX = Infinity;
  let minY = Infinity;
  for (const point of positions.values()) {
    minX = Math.min(minX, point.x);
    minY = Math.min(minY, point.y);
  }
  if (!positions.size) return positions;
  for (const [id, point] of positions)
    positions.set(id, {
      x: Math.round(point.x - minX + MARGIN),
      y: Math.round(point.y - minY + MARGIN),
    });
  return positions;
}

/**
 * Perpendicular offset per edge so relations sharing two nodes fan out instead
 * of stacking into one unreadable line. Direction is canonical, so A→B and B→A
 * bend to opposite sides.
 */
export function parallelOffsets(edges: LayoutEdge[]): Map<string, number> {
  const groups = new Map<string, LayoutEdge[]>();
  for (const edge of edges) {
    const key = [edge.source, edge.target].sort().join(" ");
    groups.set(key, [...(groups.get(key) ?? []), edge]);
  }
  const offsets = new Map<string, number>();
  for (const [key, group] of groups) {
    const first = key.split(" ")[0];
    const ordered = [...group].sort((a, b) => a.id.localeCompare(b.id));
    ordered.forEach((edge, index) => {
      const slot = index - (ordered.length - 1) / 2;
      const direction = edge.source === first ? 1 : -1;
      offsets.set(edge.id, slot * PARALLEL_GAP * direction);
    });
  }
  return offsets;
}

/** Point where a line towards `toward` leaves the card, so edges float around the border. */
export function borderPoint(rect: Rect, toward: Point, padding = 5): Point {
  const middle = center(rect);
  const dx = toward.x - middle.x;
  const dy = toward.y - middle.y;
  if (!dx && !dy) return middle;
  const halfWidth = rect.width / 2 + padding;
  const halfHeight = rect.height / 2 + padding;
  const scale = Math.min(
    Math.abs(dx) < 1e-6 ? Infinity : halfWidth / Math.abs(dx),
    Math.abs(dy) < 1e-6 ? Infinity : halfHeight / Math.abs(dy),
  );
  return { x: middle.x + dx * scale, y: middle.y + dy * scale };
}

/** Quadratic path between two cards, bent by `offset`, plus its label anchor. */
export function edgeGeometry(source: Rect, target: Rect, offset = 0) {
  const from = center(source);
  const to = center(target);
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const length = Math.max(Math.hypot(dx, dy), 1);
  const control = {
    x: (from.x + to.x) / 2 + (-dy / length) * offset,
    y: (from.y + to.y) / 2 + (dx / length) * offset,
  };
  const start = borderPoint(source, control);
  const end = borderPoint(target, control);
  return {
    path: `M ${start.x},${start.y} Q ${control.x},${control.y} ${end.x},${end.y}`,
    labelX: start.x * 0.25 + control.x * 0.5 + end.x * 0.25,
    labelY: start.y * 0.25 + control.y * 0.5 + end.y * 0.25,
  };
}

/** Loop drawn above a card for a relation whose two ends are the same type. */
export function selfLoopGeometry(rect: Rect, index = 0) {
  const reach = 46 + index * 18;
  const start = { x: rect.x + rect.width, y: rect.y + rect.height * 0.35 };
  const end = { x: rect.x + rect.width * 0.62, y: rect.y };
  const first = { x: start.x + reach, y: start.y - reach * 0.7 };
  const second = { x: end.x + reach * 0.5, y: end.y - reach * 1.5 };
  return {
    path: `M ${start.x},${start.y} C ${first.x},${first.y} ${second.x},${second.y} ${end.x},${end.y}`,
    labelX: (start.x + 3 * first.x + 3 * second.x + end.x) / 8,
    labelY: (start.y + 3 * first.y + 3 * second.y + end.y) / 8,
  };
}
