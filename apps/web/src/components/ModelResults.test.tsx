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
    messages: [],
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
        <ModelResults session={session()} busy={false} onCandidate={vi.fn()} />
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
  it("preview does not mutate the draft and bulk acceptance omits conflicts", () => {
    const s = session(),
      accept = vi.fn();
    s.candidates = [
      {
        id: "candidate1",
        kind: "object_type",
        status: "pending",
        reason: "原文",
        value: { ...draft.object_types[0], name: "候选物料" },
      },
      {
        id: "candidate2",
        kind: "object_type",
        status: "pending",
        reason: "原文",
        conflict: "已有人工修改",
        value: { ...draft.object_types[0], id: "other", name: "冲突项" },
      },
    ];
    render(
      <MemoryRouter>
        <ModelResults session={s} busy={false} onCandidate={accept} />
      </MemoryRouter>,
    );
    expect(screen.getByText("候选物料")).toBeInTheDocument();
    expect(s.draft.object_types[0].name).toBe("物料");
    fireEvent.click(screen.getByRole("button", { name: "接受全部无冲突项" }));
    expect(accept).toHaveBeenCalledWith(["candidate1"], "accept");
  });
  it("has an honest empty state before generation", () => {
    render(
      <MemoryRouter>
        <ModelResults session={null} busy={false} onCandidate={vi.fn()} />
      </MemoryRouter>,
    );
    expect(screen.getByText("暂无构建结果")).toBeInTheDocument();
    expect(screen.queryByText("接受全部无冲突项")).not.toBeInTheDocument();
  });
});
