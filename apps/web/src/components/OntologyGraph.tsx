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
import { Box, Braces } from "lucide-react";
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
  if (item.kind === "link_type")
    return (
      <div
        className={classes(
          "ontology-node",
          "ontology-node--hyperedge",
          emphasis === "dimmed" && "is-dimmed",
          emphasis === "match" && "is-match",
          selected && "is-selected",
          focused && "is-focused",
        )}
        title={[item.label, ...(item.verbalizes ?? [])].join("\n")}
        aria-label={`多元关系：${item.label}`}
      >
        <Handle type="target" position={Position.Left} />
        <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
          <path d="M13 1L25 13L13 25L1 13Z" />
        </svg>
        <strong>{item.label}</strong>
        <Handle type="source" position={Position.Right} />
      </div>
    );
  return (
    <div
      className={classes(
        "ontology-node",
        item.kind === "value_type"
          ? "ontology-node--value"
          : "ontology-node--object",
        emphasis === "dimmed" && "is-dimmed",
        emphasis === "match" && "is-match",
        focused && "is-focused",
        selected && "is-selected",
      )}
      title={item.description || item.label}
    >
      <Handle type="target" position={Position.Left} />
      <span className="ontology-node__icon">
        {item.kind === "value_type" ? <Braces size={14} /> : <Box size={14} />}
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
function buildElements(graph: TypeGraph, includeValues = false) {
  const roleTargets = new Set(
    graph.edges
      .filter((e) => e.kind !== "attribute")
      .flatMap((e) => [e.source, e.target]),
  );
  const shown = graph.nodes.filter(
    (node) =>
      node.kind === "object_type" ||
      node.kind === "link_type" ||
      roleTargets.has(node.id) ||
      includeValues,
  );
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
      ariaLabel: item.label,
    };
  });
  const flowEdges: OntologyFlowEdge[] = edges.map((item) => {
    const loop =
      item.source === item.target ? (loops.get(item.source) ?? 0) : 0;
    if (item.source === item.target) loops.set(item.source, loop + 1);
    return {
      id: item.id,
      ariaLabel: item.label,
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
  selection,
  onOpen,
  semantic = false,
  viewportKey,
}: {
  graph: TypeGraph;
  query: string;
  onSelect: (item: SelectedGraphItem) => void;
  selection?: SelectedGraphItem;
  onOpen?: (item: SelectedGraphItem) => void;
  semantic?: boolean;
  viewportKey?: boolean;
}) {
  const elements = useMemo(
    () => buildElements(graph, semantic),
    [graph, semantic],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(elements.nodes);
  const [focus, setFocus] = useState("");
  const [hover, setHover] = useState("");
  const [zoom, setZoom] = useState(100);
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

  const selectedId = selection?.item.id ?? "";
  const active = selection !== undefined ? selectedId : hover || focus;
  const neighbourhood = useMemo(() => {
    if (!active) return null;
    const ids = new Set([active]);
    const chosenEdge =
      selection?.category === "edge"
        ? selection.item
        : elements.edges.find((e) => e.id === active)?.data?.item;
    const relationId = chosenEdge?.link_type_id ?? chosenEdge?.id;
    const valueRelations =
      selection?.category === "node" && selection.item.kind === "value_type"
        ? new Set(
            elements.edges
              .filter((e) => e.source === active || e.target === active)
              .map((e) => e.data?.item.link_type_id ?? e.id),
          )
        : null;
    for (const edge of elements.edges) {
      if (
        relationId
          ? edge.id === relationId ||
            edge.data?.item.link_type_id === relationId
          : valueRelations
            ? valueRelations.has(edge.data?.item.link_type_id ?? edge.id)
            : edge.source === active || edge.target === active
      ) {
        ids.add(edge.source);
        ids.add(edge.target);
      }
    }
    return ids;
  }, [active, elements.edges, selection]);
  useEffect(() => {
    if (selection === undefined) return;
    const frame = requestAnimationFrame(() => {
      const targets =
        selection?.category === "edge"
          ? [...(neighbourhood ?? [])].filter((id) =>
              elements.nodes.some((n) => n.id === id),
            )
          : selectedId
            ? [selectedId]
            : [];
      void flow.current?.fitView({
        ...(targets.length ? { nodes: targets.map((id) => ({ id })) } : {}),
        padding: 0.3,
        maxZoom: selectedId ? 1.1 : 1.05,
        duration: 220,
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [selection, selectedId, elements.nodes, neighbourhood, viewportKey]);
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
          !semantic &&
          selection === undefined &&
          node.data.emphasis === state &&
          node.data.focused === (node.id === active)
        )
          return node;
        return {
          ...node,
          selected: node.id === selectedId,
          hidden:
            semantic &&
            node.data.item.kind === "value_type" &&
            (!(
              selection?.category === "edge" ||
              (selection?.category === "node" &&
                selection.item.kind === "value_type")
            ) ||
              !neighbourhood?.has(node.id)),
          data: { ...node.data, emphasis: state, focused: node.id === active },
        };
      }),
    [nodes, emphasis, active, selectedId, semantic, neighbourhood, selection],
  );
  const shownEdges = useMemo<OntologyFlowEdge[]>(
    () =>
      elements.edges.map((edge) => {
        const selectedRelation =
          selection?.category === "edge"
            ? (selection.item.link_type_id ?? selection.item.id)
            : active;
        const valueSelected =
          selection?.category === "node" &&
          selection.item.kind === "value_type";
        const touched =
          !active ||
          (valueSelected &&
            !!neighbourhood?.has(edge.source) &&
            !!neighbourhood?.has(edge.target)) ||
          edge.id === selectedRelation ||
          edge.data?.item.link_type_id === selectedRelation ||
          edge.source === active ||
          edge.target === active;
        const ends =
          emphasis.get(edge.source) === "dimmed" ||
          emphasis.get(edge.target) === "dimmed";
        const state: Emphasis =
          !touched || ends ? "dimmed" : active ? "match" : "normal";
        return {
          ...edge,
          selected: edge.id === selectedRelation,
          hidden:
            semantic &&
            edge.data?.item.kind === "role" &&
            !(
              (selection?.category === "edge" && touched) ||
              (selection?.category === "node" &&
                selection.item.kind === "value_type" &&
                touched)
            ),
          data: { ...edge.data!, emphasis: state },
        };
      }),
    [elements.edges, emphasis, active, selection, semantic, neighbourhood],
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
        proOptions={{ hideAttribution: true }}
        elementsSelectable
        onPaneClick={() => {
          setFocus("");
          onSelect(null);
        }}
        onNodeMouseEnter={(_, node) => setHover(node.id)}
        onNodeMouseLeave={() => setHover("")}
        onNodeDoubleClick={(_, node) =>
          onOpen?.({ category: "node", item: node.data.item })
        }
        onEdgeDoubleClick={(_, edge) =>
          onOpen?.({ category: "edge", item: edge.data!.item })
        }
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
        onMove={(_, viewport) => setZoom(Math.round(viewport.zoom * 100))}
        ariaLabelConfig={{
          "controls.ariaLabel": "画布操作",
          "controls.zoomIn.ariaLabel": "放大",
          "controls.zoomOut.ariaLabel": "缩小",
          "controls.fitView.ariaLabel": "适应画布",
          "minimap.ariaLabel": "缩略图，点击定位；方向键移动画布",
        }}
        aria-label="语义图谱"
      >
        {!semantic && (
          <Background
            variant={BackgroundVariant.Dots}
            gap={26}
            size={1}
            color="var(--color-rule)"
          />
        )}
        <Controls showInteractive={false} position="bottom-right">
          {semantic && (
            <span className="semantic-zoom-percentage">{zoom}%</span>
          )}
        </Controls>
        {/* React Flow reads the map's size from style, and lays the viewport
            rectangle out with it — CSS-only sizing letterboxes the picture and
            skews panning, so the box is declared here. */}
        <MiniMap
          position="bottom-right"
          pannable
          zoomable
          nodeBorderRadius={3}
          style={
            semantic
              ? { width: 147, height: 96, marginRight: 56, marginBottom: 17 }
              : { width: 168, height: 104, marginRight: 52 }
          }
        />
      </ReactFlow>
    </EdgeSelectContext.Provider>
  );
}
