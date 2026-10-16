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
        "flex min-h-[46px] w-[184px] items-center gap-2 rounded-md border bg-surface px-3 py-2 text-object transition-[opacity,box-shadow,border-color] duration-200",
        String.raw`[&_.react-flow\_\_handle]:!size-px [&_.react-flow\_\_handle]:!min-h-px [&_.react-flow\_\_handle]:!min-w-px [&_.react-flow\_\_handle]:!border-0 [&_.react-flow\_\_handle]:!bg-transparent [&_.react-flow\_\_handle]:opacity-0`,
        emphasis === "dimmed" ? "opacity-20 shadow-none" : "shadow-[0_1px_3px_var(--color-shadow)]",
        emphasis === "match" || focused || selected ? "border-accent" : "border-rule",
        (focused || selected) && "shadow-[0_0_0_3px_var(--color-accent-soft)]",
      )}
      title={item.description || item.label}
    >
      <Handle type="target" position={Position.Left} />
      <span className="flex size-6 flex-none items-center justify-center rounded-xs bg-ink-2 text-surface">
        <Box size={14} />
      </span>
      <span className="grid min-w-0">
        <strong className="truncate text-sm text-ink">{item.label}</strong>
        <small className="truncate font-mono text-[10px] text-muted">{item.technical_name}</small>
      </span>
      {!!item.attribute_count && (
        <span className="ml-auto flex-none rounded-full bg-surface-soft px-[7px] py-px text-[10px] text-muted">
          {item.attribute_count}
        </span>
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
  const extendsEdge = data.item.kind === "extends";
  const strong = data.emphasis === "match" || selected;
  const className = classes(
    "transition-opacity duration-200",
    extendsEdge
      ? "!stroke-object [stroke-dasharray:8_4] [stroke-width:1.4]"
      : strong
        ? "!stroke-accent [stroke-width:2]"
        : "!stroke-graph-edge [stroke-width:1.4]",
    data.emphasis === "dimmed" && "opacity-[0.12]",
  );
  const labelClass = classes(
    "nodrag nopan pointer-events-auto absolute max-w-[140px] truncate rounded-full border bg-surface px-2 py-px font-sans text-[11px] leading-normal",
    extendsEdge
      ? "border-object-soft text-object"
      : strong
        ? "border-accent text-accent"
        : "border-rule text-muted hover:border-rule-strong hover:text-ink-2",
    data.emphasis === "dimmed" && "pointer-events-none border-transparent opacity-[0.14]",
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
          className={labelClass}
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

// Only object types are drawn, with the links and inheritance between them.
function buildElements(graph: TypeGraph) {
  const shown = graph.nodes;
  const ids = new Set(shown.map((node) => node.id));
  const edges = graph.edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target));
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
    () => buildElements(graph),
    [graph],
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
    for (const edge of elements.edges) {
      if (
        relationId
          ? edge.id === relationId ||
            edge.data?.item.link_type_id === relationId
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
          data: { ...node.data, emphasis: state, focused: node.id === active },
        };
      }),
    [nodes, emphasis, active, selectedId, semantic, selection],
  );
  const shownEdges = useMemo<OntologyFlowEdge[]>(
    () =>
      elements.edges.map((edge) => {
        const selectedRelation =
          selection?.category === "edge"
            ? (selection.item.link_type_id ?? selection.item.id)
            : active;
        const touched =
          !active ||
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
          data: { ...edge.data!, emphasis: state },
        };
      }),
    [elements.edges, emphasis, active, selection],
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
        className={classes(
          "!bg-canvas [--xy-edge-stroke:var(--color-graph-edge)] [--xy-edge-stroke-selected:var(--color-accent)]",
          String.raw`[&_.react-flow\_\_minimap]:rounded-md [&_.react-flow\_\_minimap]:border [&_.react-flow\_\_minimap]:border-rule [&_.react-flow\_\_minimap]:!bg-surface`,
          String.raw`[&_.react-flow\_\_minimap-mask]:fill-ink/[0.07] [&_.react-flow\_\_minimap-mask]:stroke-rule-strong`,
          String.raw`[&_.react-flow\_\_minimap-node]:fill-object-soft [&_.react-flow\_\_minimap-node]:stroke-rule-strong [&_.react-flow\_\_minimap-node]:[stroke-width:2]`,
          String.raw`[&_.react-flow\_\_controls]:overflow-hidden [&_.react-flow\_\_controls]:rounded-sm [&_.react-flow\_\_controls]:border [&_.react-flow\_\_controls]:border-rule [&_.react-flow\_\_controls]:!shadow-none`,
          String.raw`[&_.react-flow\_\_controls_button]:!size-8 [&_.react-flow\_\_controls_button]:!bg-surface [&_.react-flow\_\_controls_button]:!text-ink-2`,
          String.raw`max-[1000px]:[&_.react-flow\_\_minimap]:hidden`,
        )}
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
            <span className="flex h-7 items-center justify-center bg-surface px-1 text-[10px] text-muted">{zoom}%</span>
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
