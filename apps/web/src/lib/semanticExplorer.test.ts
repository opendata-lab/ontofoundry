import { describe, expect, it } from "vitest";
import type { GraphNode, TypeGraph } from "../api/types";
import { semanticCanvas, semanticResources } from "./semanticExplorer";
const object = (id: string): GraphNode => ({
  id,
  kind: "object_type",
  label: id,
  technical_name: id,
  description: "",
  tags: [],
});
describe("semantic canvas projection", () => {
  it("preserves record self-relations and all extra roles while keeping one main relation edge", () => {
    const relation: GraphNode = {
      id: "calls",
      kind: "link_type",
      label: "调用观测",
      technical_name: "calls",
      description: "",
      tags: [],
      owner_ref: { kind: "object_type", ref: "component" },
      roles: [
        {
          id: "called",
          name: "called",
          concept: { kind: "object_type", ref: "component" },
        },
        {
          id: "env",
          name: "environment",
          concept: { kind: "object_type", ref: "environment" },
        },
        {
          id: "count",
          name: "count",
          concept: { kind: "builtin", ref: "Integer" },
        },
      ],
    };
    const graph: TypeGraph = {
      workspace_id: "w",
      version_id: "v",
      version_sha256: "h",
      nodes: [
        object("component"),
        object("environment"),
        relation,
        {
          id: "builtin:Integer",
          kind: "value_type",
          label: "Integer",
          technical_name: "Integer",
          description: "",
          tags: [],
        },
      ],
      edges: [
        { role_id: "owner", target: "component" },
        { role_id: "called", target: "component" },
        { role_id: "env", target: "environment" },
        { role_id: "count", target: "builtin:Integer" },
      ].map((role) => ({
        ...role,
        id: `role:${role.role_id}`,
        source: "calls",
        kind: "role",
        link_type_id: "calls",
        label: role.role_id,
        technical_name: "calls",
      })),
    };
    const resources = semanticResources(graph);
    const canvas = semanticCanvas(graph, resources);
    expect(resources.filter((r) => r.kind === "relation")).toHaveLength(1);
    expect(resources.find((r) => r.id === "builtin:Integer")?.name).toBe(
      "整数",
    );
    expect(canvas.nodes.some((n) => n.kind === "link_type")).toBe(false);
    expect(canvas.edges.find((e) => e.id === "calls")).toMatchObject({
      source: "component",
      target: "component",
    });
    expect(
      canvas.edges.filter((e) => e.kind === "role").map((e) => e.target),
    ).toEqual(["environment", "builtin:Integer"]);
  });
});
