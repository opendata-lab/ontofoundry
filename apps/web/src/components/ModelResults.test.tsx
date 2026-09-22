import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ModelResults } from "./ModelResults";
import type { Draft, ModelingSession } from "../api/types";

vi.mock("./OntologyGraph", () => ({
  OntologyGraph: () => <div data-testid="semantic-graph" />,
}));
afterEach(cleanup);
const draft: Draft = {
  workspace_id: "w",
  schema_version: "1",
  object_types: [
    {
      id: "material",
      name: "物料",
      technical_name: "material",
      description: "材料定义",
      tags: [],
      attributes: [
        {
          id: "name",
          name: "物料名称",
          technical_name: "name",
          description: "",
          value_kind: "string",
          identifier: false,
          required: false,
        },
      ],
    },
  ],
  link_types: [],
  objects: [],
  links: [],
  mappings: [],
};
function session(): ModelingSession {
  return {
    id: "s",
    title: "测试",
    workspace_id: "w",
    base_version_id: null,
    revision: 0,
    draft: structuredClone(draft),
    graph: {
      workspace_id: "w",
      version_id: "v",
      version_sha256: "",
      nodes: [],
      edges: [],
    },
    candidates: [],
    material_ids: [],
    task_status: "idle",
    task_detail: "",
    updated_at: "",
  };
}

describe("建模结果", () => {
  it("only has the two agreed tabs, with real model counts and searchable attributes", () => {
    render(
      <MemoryRouter>
        <ModelResults session={session()} />
      </MemoryRouter>,
    );
    expect(screen.getAllByRole("tab")).toHaveLength(2);
    expect(screen.getByRole("button", { name: "实体 1" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "属性 1" }));
    expect(screen.getByText("物料名称")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("textbox", { name: "搜索模型" }), {
      target: { value: "不存在" },
    });
    expect(screen.queryByText("物料名称")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "语义图谱概览" }));
    expect(screen.getByTestId("semantic-graph")).toBeInTheDocument();
  });
  it("shows the complete result as a version draft without candidate actions", () => {
    const s = session();
    s.draft.object_types[0].name = "新版本物料";
    render(
      <MemoryRouter>
        <ModelResults session={s} />
      </MemoryRouter>,
    );
    expect(screen.getByText("新版本物料")).toBeInTheDocument();
    expect(screen.getByText(/完整的新版本草稿/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /接受/ })).not.toBeInTheDocument();
  });
  it("has an honest empty state before generation", () => {
    render(
      <MemoryRouter>
        <ModelResults session={null} />
      </MemoryRouter>,
    );
    expect(screen.getByText("暂无构建结果")).toBeInTheDocument();
    expect(screen.queryByText("接受全部无冲突项")).not.toBeInTheDocument();
  });
});

describe("version draft mappings", () => {
  const mapping = {
    id: "map-1",
    type_id: "material",
    connection_alias: "warehouse",
    table_name: "dim_material",
    schema_name: "ods",
    key_column: "material_id",
    fields: {},
  };

  const withMapping = (): ModelingSession => {
    const value = session();
    value.draft.mappings = [mapping];
    return value;
  };

  it("labels a mapping by its connection alias and table", () => {
    // DataMapping has no name field on purpose: a published model carries an
    // alias rather than a connection, so this pair is the only stable label.
    render(
      <MemoryRouter>
        <ModelResults session={withMapping()} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /映射/ }));

    expect(screen.getByText(/warehouse · ods\.dim_material/)).toBeInTheDocument();
    expect(screen.getByText(/主键 material_id/)).toBeInTheDocument();
  });

});

describe("result warnings", () => {
  it("surfaces notes from the last run so they are not lost silently", () => {
    // Top-level ontology constraints are not turned into candidates in v1.
    // Without this the agent's proposal would vanish with no trace at all.
    const warned: ModelingSession = {
      ...session(),
      result_warnings: ["本轮结果包含顶层本体约束变更，v1 不生成候选"],
    };

    render(
      <MemoryRouter>
        <ModelResults session={warned} />
      </MemoryRouter>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("顶层本体约束变更");
  });
});
