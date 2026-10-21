import { cleanup, render, screen } from "@testing-library/react";
import type { ComponentType } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Draft, GraphNode, TypeGraph } from "../api/types";
import { example } from "../test/drafts";
import { OntologyGraph } from "./OntologyGraph";

vi.mock("@xyflow/react", async (original) => ({
  ...(await original<typeof import("@xyflow/react")>()),
  Handle: () => null,
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
  ReactFlow: ({
    nodes,
    edges,
    nodeTypes,
  }: {
    nodes: {
      id: string;
      hidden?: boolean;
      selected?: boolean;
      data: { item: GraphNode; emphasis: string; focused: boolean };
    }[];
    edges: {
      id: string;
      source: string;
      target: string;
      hidden?: boolean;
      selected?: boolean;
      data: { emphasis: string };
    }[];
    nodeTypes: {
      ontology: ComponentType<{
        data: { item: GraphNode; emphasis: string; focused: boolean };
        selected: boolean;
      }>;
    };
  }) => (
    <div>
      {nodes
        .filter((n) => !n.hidden)
        .map((n) => {
          const View = nodeTypes.ontology;
          return <View key={n.id} data={n.data} selected={!!n.selected} />;
        })}
      {edges
        .filter((e) => !e.hidden)
        .map((e) => (
          <span
            key={e.id}
            data-testid={`edge:${e.id}`}
            data-emphasis={e.data.emphasis}
            data-selected={String(e.selected ?? false)}
          >
            {e.source} → {e.target}
          </span>
        ))}
    </div>
  ),
}));
afterEach(cleanup);

// The type graph the server derives from a draft: object types as nodes,
// relations and inheritance as edges.
function graphOf(draft: Draft): TypeGraph {
  return {
    workspace_id: draft.workspace_id,
    version_id: "v",
    version_sha256: "h",
    version_content_sha256: "h",
    normalized_snapshot_sha256: "h",
    nodes: draft.object_types.map((o) => ({
      id: o.id,
      kind: "object_type",
      label: (o.display_name || o.name),
      name: o.name,
      description: o.description,
      tags: o.tags,
    })),
    edges: [
      ...draft.link_types.map((l) => ({
        id: l.id,
        kind: "link_type" as const,
        label: (l.display_name || l.name),
        name: (l.display_name || l.name),
        source: l.source_type_id,
        target: l.target_type_id,
        link_type_id: l.id,
      })),
      ...draft.object_types
        .filter((o) => o.extends)
        .map((o) => ({
          id: `extends:${o.id}`,
          kind: "extends" as const,
          label: "继承",
          name: "extends",
          source: o.id,
          target: o.extends!,
        })),
    ],
  };
}

const nodeOf = (graph: TypeGraph, name: string) =>
  graph.nodes.find((n) => n.name === name)!;
const linkOf = (draft: Draft, name: string) =>
  draft.link_types.find((l) => (l.display_name || l.name) === name)!;
// The node card is the element wrapping the label.
const card = (label: string) =>
  screen.getByText(label, { selector: "strong" }).closest("div");

describe("ontology canvas", () => {
  it("draws every object type as a card and every relation as an edge between them", () => {
    const draft = example("08-rules");
    const graph = graphOf(draft);
    render(<OntologyGraph graph={graph} query="" onSelect={() => undefined} />);
    for (const name of ["订单", "员工", "客户", "退款"]) expect(card(name)).toBeInTheDocument();
    const belongs = linkOf(draft, "customer");
    expect(screen.getByTestId(`edge:${belongs.id}`)).toHaveTextContent(
      `${belongs.source_type_id} → ${belongs.target_type_id}`,
    );
    expect(screen.getAllByTestId(/^edge:/)).toHaveLength(2);
  });

  it("draws inheritance as an edge from the child to its parent", () => {
    const draft = example("06-inheritance");
    const graph = graphOf(draft);
    render(<OntologyGraph graph={graph} query="" onSelect={() => undefined} />);
    const person = draft.object_types.find((o) => o.name === "person")!;
    expect(screen.getByTestId(`edge:extends:${person.id}`)).toHaveTextContent(
      `${person.id} → ${person.extends}`,
    );
  });

  it("highlights the cards matching the search and dims the rest", () => {
    const graph = graphOf(example("08-rules"));
    render(<OntologyGraph graph={graph} query="refund" onSelect={() => undefined} />);
    expect(card("退款")).toHaveClass("border-accent");
    expect(card("退款")).not.toHaveClass("opacity-20");
    expect(card("订单")).toHaveClass("opacity-20");
  });
});

describe("controlled semantic selection", () => {
  it("dims unrelated nodes and edges and clears emphasis when the selection clears", () => {
    const draft = example("08-rules");
    const graph = graphOf(draft);
    const customer = nodeOf(graph, "customer");
    const belongs = graph.edges.find((e) => e.id === linkOf(draft, "customer").id)!;
    const handler = linkOf(draft, "handler");
    const view = render(
      <OntologyGraph
        graph={graph}
        query=""
        selection={{ category: "node", item: customer }}
        semantic
        onSelect={() => undefined}
      />,
    );
    expect(card("客户")).toHaveClass("border-accent");
    expect(card("订单")).not.toHaveClass("opacity-20");
    expect(card("员工")).toHaveClass("opacity-20");
    expect(card("退款")).toHaveClass("opacity-20");
    expect(screen.getByTestId(`edge:${belongs.id}`)).toHaveAttribute("data-emphasis", "match");
    expect(screen.getByTestId(`edge:${handler.id}`)).toHaveAttribute("data-emphasis", "dimmed");

    view.rerender(
      <OntologyGraph
        graph={graph}
        query=""
        selection={{ category: "edge", item: belongs }}
        semantic
        onSelect={() => undefined}
      />,
    );
    expect(screen.getByTestId(`edge:${belongs.id}`)).toHaveAttribute("data-selected", "true");
    expect(screen.getByTestId(`edge:${handler.id}`)).toHaveAttribute("data-selected", "false");
    expect(card("订单")).not.toHaveClass("opacity-20");
    expect(card("客户")).not.toHaveClass("opacity-20");
    expect(card("员工")).toHaveClass("opacity-20");

    view.rerender(
      <OntologyGraph graph={graph} query="" selection={null} semantic onSelect={() => undefined} />,
    );
    for (const name of ["订单", "员工", "客户", "退款"]) expect(card(name)).not.toHaveClass("opacity-20");
    expect(card("客户")).not.toHaveClass("border-accent");
    expect(screen.getByTestId(`edge:${handler.id}`)).toHaveAttribute("data-emphasis", "normal");
  });
});
