import { cleanup, render, screen } from "@testing-library/react";
import type { ComponentType } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { GraphNode, TypeGraph } from "../api/types";
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
const node = (
  id: string,
  kind: GraphNode["kind"] = "object_type",
): GraphNode => ({
  id,
  kind,
  label: id,
  technical_name: id,
  description: "",
  tags: [],
});

describe("native semantic canvas", () => {
  it("draws a small diamond with all role incidence edges, including value/Any roles", () => {
    const graph: TypeGraph = {
      workspace_id: "w",
      version_id: "v",
      version_sha256: "h",
      nodes: [
        node("owner"),
        node("entity"),
        node("sale", "link_type"),
        node("amount", "value_type"),
        node("Any", "value_type"),
        node("attribute_value", "value_type"),
      ],
      edges: ["owner", "entity", "amount", "Any"].map((target, i) => ({
        id: `role${i}`,
        kind: "role",
        source: "sale",
        target,
        label: target,
        technical_name: "sale",
      })),
    };
    const { container } = render(
      <OntologyGraph graph={graph} query="" onSelect={() => undefined} />,
    );
    expect(screen.getByLabelText("多元关系：sale")).toBeInTheDocument();
    expect(
      container.querySelector(".ontology-node--hyperedge svg path"),
    ).toHaveAttribute("d", "M13 1L25 13L13 25L1 13Z");
    for (let i = 0; i < 4; i++)
      expect(screen.getByTestId(`edge:role${i}`)).toBeInTheDocument();
    expect(
      screen.getByText("amount", { selector: "strong" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("attribute_value")).not.toBeInTheDocument();
  });
  it("keeps binary relations as an edge between the existing object cards", () => {
    const graph: TypeGraph = {
      workspace_id: "w",
      version_id: "v",
      version_sha256: "h",
      nodes: [node("A"), node("B")],
      edges: [
        {
          id: "binary",
          kind: "link_type",
          source: "A",
          target: "B",
          label: "关联",
          technical_name: "binary",
        },
      ],
    };
    const { container } = render(
      <OntologyGraph graph={graph} query="" onSelect={() => undefined} />,
    );
    expect(container.querySelector(".ontology-node--hyperedge")).toBeNull();
    expect(screen.getByTestId("edge:binary")).toHaveTextContent("A → B");
  });
});

describe("controlled semantic selection", () => {
  it("dims unrelated nodes and edges and clears emphasis when the selection clears", () => {
    const a = node("A"),
      b = node("B"),
      c = node("C");
    const edge = {
      id: "ab",
      kind: "link_type" as const,
      source: "A",
      target: "B",
      label: "关联",
      technical_name: "ab",
    };
    const graph: TypeGraph = {
      workspace_id: "w",
      version_id: "v",
      version_sha256: "h",
      nodes: [a, b, c],
      edges: [edge],
    };
    const view = render(
      <OntologyGraph
        graph={graph}
        query=""
        selection={{ category: "node", item: a }}
        semantic
        onSelect={() => undefined}
      />,
    );
    expect(
      screen.getByText("A", { selector: "strong" }).closest(".ontology-node"),
    ).toHaveClass("is-selected");
    expect(
      screen.getByText("B", { selector: "strong" }).closest(".ontology-node"),
    ).not.toHaveClass("is-dimmed");
    expect(
      screen.getByText("C", { selector: "strong" }).closest(".ontology-node"),
    ).toHaveClass("is-dimmed");
    view.rerender(
      <OntologyGraph
        graph={graph}
        query=""
        selection={{ category: "edge", item: edge }}
        semantic
        onSelect={() => undefined}
      />,
    );
    expect(screen.getByTestId("edge:ab")).toHaveAttribute(
      "data-selected",
      "true",
    );
    view.rerender(
      <OntologyGraph
        graph={graph}
        query=""
        selection={null}
        semantic
        onSelect={() => undefined}
      />,
    );
    expect(
      screen.getByText("C", { selector: "strong" }).closest(".ontology-node"),
    ).not.toHaveClass("is-dimmed");
  });
});
