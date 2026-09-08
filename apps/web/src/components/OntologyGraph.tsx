import {
  Background,
  BackgroundVariant,
  BaseEdge,
  Controls,
  Edge,
  EdgeLabelRenderer,
  EdgeProps,
  Handle,
  MarkerType,
  MiniMap,
  Node,
  NodeProps,
  Position,
  ReactFlow,
  ReactFlowInstance,
  useInternalNode,
  useNodesState,
} from "@xyflow/react";
import { Box } from "lucide-react";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import type {
  GraphEdge as ApiGraphEdge,
  GraphNode as ApiGraphNode,
  TypeGraph,
} from "../api/types";
import {
  NODE_HEIGHT,
  NODE_WIDTH,
  edgeGeometry,
  layoutGraph,
  parallelOffsets,
  selfLoopGeometry,
  type Rect,
} from "../lib/graphLayout";

export type SelectedGraphItem =
  | { category: "node"; item: ApiGraphNode }
  | { category: "edge"; item: ApiGraphEdge }
  | null;

type Emphasis = "normal" | "match" | "dimmed";

type OntologyNodeData = {
  item: ApiGraphNode;
  emphasis: Emphasis;
  focused: boolean;
};
type OntologyEdgeData = {
  item: ApiGraphEdge;
  emphasis: Emphasis;
  offset: number;
  loop: number;
};
type OntologyFlowNode = Node<OntologyNodeData, "ontology">;
type OntologyFlowEdge = Edge<OntologyEdgeData, "ontology">;

// Edge labels render outside the SVG, so they reach the page's select handler
// through context instead of React Flow's onEdgeClick.
const EdgeSelectContext = createContext<(item: ApiGraphEdge) => void>(
  () => undefined,
);

function classes(...values: (string | false | undefined)[]) {
  return values.filter(Boolean).join(" ");
}

function OntologyNodeView({ data, selected }: NodeProps<OntologyFlowNode>) {
  const { item, emphasis, focused } = data;
  return (
    <div
      className={classes(
        "ontology-node",
        "ontology-node--object",
        emphasis === "dimmed" && "is-dimmed",
        emphasis === "match" && "is-match",
        focused && "is-focused",
        selected && "is-selected",
      )}
      title={item.description || item.label}
    >
      <Handle type="target" position={Position.Left} />
      <span className="ontology-node__icon">
        <Box size={14} />
      </span>
      <span className="ontology-node__text">
        <strong>{item.label}</strong>
        <small>{item.technical_name}</small>
      </span>
      {/* Attributes are not drawn as nodes; this badge and the inspector are
          how a card reports how many it declares. */}
      {!!item.attribute_count && (
        <span className="ontology-node__count">{item.attribute_count}</span>
      )}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function rectOf(
  position: { x: number; y: number },
  measured: { width?: number | null; height?: number | null } | undefined,
): Rect {
  return {
    x: position.x,
    y: position.y,
    width: measured?.width || NODE_WIDTH,
    height: measured?.height || NODE_HEIGHT,
  };
}

function OntologyEdgeView({
  id,
  source,
  target,
  data,
  markerEnd,
  selected,
}: EdgeProps<OntologyFlowEdge>) {
  const sourceNode = useInternalNode(source);
  const targetNode = useInternalNode(target);
  const select = useContext(EdgeSelectContext);
  if (!sourceNode || !targetNode || !data) return null;
  const from = rectOf(
    sourceNode.internals.positionAbsolute,
    sourceNode.measured,
  );
  const to = rectOf(targetNode.internals.positionAbsolute, targetNode.measured);
  const geometry =
    source === target
      ? selfLoopGeometry(from, data.loop)
      : edgeGeometry(from, to, data.offset);
  const className = classes(
    "ontology-edge",
    data.item.kind === "extends"
      ? "ontology-edge--extends"
      : "ontology-edge--relation",
    data.emphasis === "dimmed" && "is-dimmed",
    data.emphasis === "match" && "is-match",
    selected && "is-selected",
  );
  return (
    <>
      <BaseEdge
        id={id}
        path={geometry.path}
        markerEnd={markerEnd}
        className={className}
        interactionWidth={18}
      />
      <EdgeLabelRenderer>
        <button
          type="button"
          className={classes(
            "ontology-edge__label",
            "nodrag",
            "nopan",
            className,
          )}
          style={{
            transform: `translate(-50%, -50%) translate(${geometry.labelX}px, ${geometry.labelY}px)`,
          }}
          onClick={(event) => {
            event.stopPropagation();
            select(data.item);
          }}
        >
          {data.item.label}
        </button>
      </EdgeLabelRenderer>
    </>
  );
}

const nodeTypes = { ontology: OntologyNodeView };
const edgeTypes = { ontology: OntologyEdgeView };

// Attributes are entity fields, not graph nodes: only object types are drawn,
// and only the edges that run between two of them.
function buildElements(graph: TypeGraph) {
  const shown = graph.nodes.filter((node) => node.kind === "object_type");
  const ids = new Set(shown.map((node) => node.id));
  const edges = graph.edges.filter(
    (edge) =>
      edge.kind !== "attribute" && ids.has(edge.source) && ids.has(edge.target),
  );
  const positions = layoutGraph(shown, edges);
  const offsets = parallelOffsets(edges);
  const loops = new Map<string, number>();
  const nodes: OntologyFlowNode[] = shown.map((item) => {
    const point = positions.get(item.id) ?? { x: 0, y: 0 };
    return {
      id: item.id,
      type: "ontology",
      position: { x: point.x - NODE_WIDTH / 2, y: point.y - NODE_HEIGHT / 2 },
      data: { item, emphasis: "normal", focused: false },
      draggable: true,
    };
  });
  const flowEdges: OntologyFlowEdge[] = edges.map((item) => {
    const loop =
      item.source === item.target ? (loops.get(item.source) ?? 0) : 0;
    if (item.source === item.target) loops.set(item.source, loop + 1);
    return {
      id: item.id,
      source: item.source,
      target: item.target,
      type: "ontology",
      data: {
        item,
        emphasis: "normal" as Emphasis,
        offset: offsets.get(item.id) ?? 0,
        loop,
      },
      // Marker colour comes from CSS: SVG presentation attributes cannot read
      // tokens.
      markerEnd: { type: MarkerType.ArrowClosed, width: 13, height: 13 },
    };
  });
  return { nodes, edges: flowEdges };
}

function matches(item: ApiGraphNode, query: string) {
  if (!query) return true;
  return [item.label, item.technical_name, item.description, ...item.tags]
    .join(" ")
    .toLocaleLowerCase()
    .includes(query);
}

export function OntologyGraph({
  graph,
  query,
  onSelect,
}: {
  graph: TypeGraph;
  query: string;
  onSelect: (item: SelectedGraphItem) => void;
}) {
  const elements = useMemo(() => buildElements(graph), [graph]);
  const [nodes, setNodes, onNodesChange] = useNodesState(elements.nodes);
  const [focus, setFocus] = useState("");
  const [hover, setHover] = useState("");
  const flow =
    useRef<ReactFlowInstance<OntologyFlowNode, OntologyFlowEdge>>(null);
  const select = useRef(onSelect);
  useEffect(() => {
    select.current = onSelect;
  }, [onSelect]);
  useEffect(() => {
    setNodes(elements.nodes);
    setFocus("");
    setHover("");
    // Re-frame when the model behind the canvas changes, not on every hover.
    const frame = requestAnimationFrame(() =>
      flow.current?.fitView({ padding: 0.16, maxZoom: 1.05, duration: 220 }),
    );
    return () => cancelAnimationFrame(frame);
  }, [elements.nodes, setNodes]);

  const active = hover || focus;
  const neighbourhood = useMemo(() => {
    if (!active) return null;
    const ids = new Set([active]);
    for (const edge of elements.edges) {
      if (edge.source === active) ids.add(edge.target);
      if (edge.target === active) ids.add(edge.source);
    }
    return ids;
  }, [active, elements.edges]);
  const normalized = query.trim().toLocaleLowerCase();

  const emphasis = useMemo(() => {
    const byNode = new Map<string, Emphasis>();
    for (const node of elements.nodes) {
      const hit = matches(node.data.item, normalized);
      byNode.set(
        node.id,
        neighbourhood && !neighbourhood.has(node.id)
          ? "dimmed"
          : !hit
            ? "dimmed"
            : normalized
              ? "match"
              : "normal",
      );
    }
    return byNode;
  }, [elements.nodes, neighbourhood, normalized]);

  const shownNodes = useMemo(
    () =>
      nodes.map((node) => {
        const state = emphasis.get(node.id) ?? "normal";
        if (
          node.data.emphasis === state &&
          node.data.focused === (node.id === active)
        )
          return node;
        return {
          ...node,
          data: { ...node.data, emphasis: state, focused: node.id === active },
        };
      }),
    [nodes, emphasis, active],
  );
  const shownEdges = useMemo<OntologyFlowEdge[]>(
    () =>
      elements.edges.map((edge) => {
        const touched =
          !active || edge.source === active || edge.target === active;
        const ends =
          emphasis.get(edge.source) === "dimmed" ||
          emphasis.get(edge.target) === "dimmed";
        const state: Emphasis =
          !touched || ends ? "dimmed" : active ? "match" : "normal";
        return { ...edge, data: { ...edge.data!, emphasis: state } };
      }),
    [elements.edges, emphasis, active],
  );

  return (
    <EdgeSelectContext.Provider
      value={(item) => select.current({ category: "edge", item })}
    >
      <ReactFlow
        nodes={shownNodes}
        onNodesChange={onNodesChange}
        edges={shownEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onInit={(instance) => {
          flow.current = instance;
        }}
        fitView
        fitViewOptions={{ padding: 0.16, maxZoom: 1.05 }}
        minZoom={0.15}
        maxZoom={1.8}
        nodesConnectable={false}
        elementsSelectable
        onPaneClick={() => {
          setFocus("");
          onSelect(null);
        }}
        onNodeMouseEnter={(_, node) => setHover(node.id)}
        onNodeMouseLeave={() => setHover("")}
        onNodeClick={(_, node) => {
          setFocus(node.id);
          onSelect({ category: "node", item: node.data.item });
        }}
        onEdgeClick={(_, edge) =>
          onSelect({
            category: "edge",
            item: (edge.data as OntologyEdgeData).item,
          })
        }
        aria-label="语义图谱"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={26}
          size={1}
          color="var(--color-rule)"
        />
        <Controls showInteractive={false} position="bottom-right" />
        {/* React Flow reads the map's size from style, and lays the viewport
            rectangle out with it — CSS-only sizing letterboxes the picture and
            skews panning, so the box is declared here. */}
        <MiniMap
          position="bottom-right"
          pannable
          zoomable
          nodeBorderRadius={3}
          style={{ width: 168, height: 104, marginRight: 52 }}
        />
      </ReactFlow>
    </EdgeSelectContext.Provider>
  );
}
