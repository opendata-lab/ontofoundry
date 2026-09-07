import {
  Controls,
  Edge,
  Handle,
  MarkerType,
  Node,
  NodeProps,
  Position,
  ReactFlow,
  MiniMap,
  useNodesState,
} from "@xyflow/react";
import { Box, Braces } from "lucide-react";
import { useEffect, useMemo } from "react";

import type {
  GraphEdge as ApiGraphEdge,
  GraphNode as ApiGraphNode,
  TypeGraph,
} from "../api/types";

export type SelectedGraphItem =
  | { category: "node"; item: ApiGraphNode }
  | { category: "edge"; item: ApiGraphEdge }
  | null;

type OntologyNodeData = {
  item: ApiGraphNode;
  dimmed: boolean;
};

type OntologyFlowNode = Node<OntologyNodeData, "ontology">;

function OntologyNodeView({ data }: NodeProps<OntologyFlowNode>) {
  const { item, dimmed } = data;
  const isObject = item.kind === "object_type";
  return (
    <div
      className={[
        "ontology-node",
        isObject ? "ontology-node--object" : "ontology-node--value",
        dimmed ? "is-dimmed" : "",
      ].join(" ")}
    >
      <Handle type="target" position={Position.Left} />
      <span className="ontology-node__icon">
        {isObject ? <Box size={14} /> : <Braces size={13} />}
      </span>
      <span>
        <strong>{item.label}</strong>
        <small>{item.technical_name}</small>
      </span>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { ontology: OntologyNodeView };

function layoutGraph(
  graph: TypeGraph,
  mode: "global" | "semantic",
  query = "",
): { nodes: OntologyFlowNode[]; edges: Edge[] } {
  const normalized = query.trim().toLocaleLowerCase();
  const objectNodes = graph.nodes.filter((node) => node.kind === "object_type");
  const shownNodes = mode === "global" ? objectNodes : graph.nodes;
  const shownIds = new Set(shownNodes.map((node) => node.id));
  const nodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const attributesBySource = new Map<string, ApiGraphNode[]>();

  for (const edge of graph.edges.filter((item) => item.kind === "attribute")) {
    const value = nodeById.get(edge.target);
    if (!value) continue;
    const values = attributesBySource.get(edge.source) ?? [];
    values.push(value);
    attributesBySource.set(edge.source, values);
  }

  const positions = new Map<string, { x: number; y: number }>();
  if (mode === "global" || graph.nodes.every((n) => n.kind === "object_type")) {
    const radiusX = Math.max(280, objectNodes.length * 62);
    const radiusY = Math.max(180, objectNodes.length * 38);
    objectNodes.forEach((node, index) => {
      const angle =
        (index / Math.max(objectNodes.length, 1)) * Math.PI * 2 - Math.PI / 2;
      positions.set(node.id, {
        x: 430 + Math.cos(angle) * radiusX,
        y: 280 + Math.sin(angle) * radiusY,
      });
    });
  } else {
    objectNodes.forEach((node, index) => {
      const y = 80 + index * 220;
      positions.set(node.id, { x: 80, y });
      const values = (attributesBySource.get(node.id) ?? []).sort((a, b) =>
        a.technical_name.localeCompare(b.technical_name),
      );
      values.forEach((value, valueIndex) => {
        positions.set(value.id, {
          x: 420,
          y: y - ((values.length - 1) * 54) / 2 + valueIndex * 54,
        });
      });
    });
  }

  const matches = (item: ApiGraphNode) =>
    !normalized ||
    [item.label, item.technical_name, item.description, ...item.tags]
      .join(" ")
      .toLocaleLowerCase()
      .includes(normalized);

  return {
    nodes: shownNodes.map((item) => ({
      id: item.id,
      type: "ontology",
      position: positions.get(item.id) ?? { x: 0, y: 0 },
      data: { item, dimmed: !matches(item) },
      draggable: true,
    })),
    edges: graph.edges
      .filter((edge) => shownIds.has(edge.source) && shownIds.has(edge.target))
      .map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label,
        type: "default",
        className:
          edge.kind === "link_type"
            ? "ontology-edge ontology-edge--relation"
            : "ontology-edge ontology-edge--attribute",
        labelStyle: {
          fontFamily: "var(--font-body)",
          fontSize: 10,
          fontWeight: 400,
        },
        labelBgStyle: {
          fill: "var(--color-canvas)",
          fillOpacity: 0.94,
        },
        markerEnd:
          edge.kind === "link_type"
            ? { type: MarkerType.ArrowClosed, color: "var(--color-graph-edge)" }
            : undefined,
        data: { item: edge },
      })),
  };
}

export function OntologyGraph({
  graph,
  mode,
  query,
  onSelect,
}: {
  graph: TypeGraph;
  mode: "global" | "semantic";
  query: string;
  onSelect: (item: SelectedGraphItem) => void;
}) {
  const elements = useMemo(
    () => layoutGraph(graph, mode, query),
    [graph, mode, query],
  );
  const [nodes, setNodes, onNodesChange] = useNodesState(elements.nodes);
  useEffect(() => setNodes(elements.nodes), [elements.nodes, setNodes]);

  return (
    <ReactFlow
      nodes={nodes}
      onNodesChange={onNodesChange}
      edges={elements.edges}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.18 }}
      minZoom={0.25}
      maxZoom={1.8}
      nodesConnectable={false}
      elementsSelectable
      onPaneClick={() => onSelect(null)}
      onNodeClick={(_, node) =>
        onSelect({ category: "node", item: node.data.item })
      }
      onEdgeClick={(_, edge) =>
        onSelect({
          category: "edge",
          item: (edge.data as { item: ApiGraphEdge }).item,
        })
      }
      aria-label={mode === "semantic" ? "语义图谱" : "图谱概览"}
    >
      <Controls showInteractive={false} position="bottom-right" />
      <MiniMap
        position="bottom-right"
        pannable
        zoomable
        nodeColor="var(--color-object-soft)"
        style={{ marginRight: 52 }}
      />
    </ReactFlow>
  );
}
