import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { SemanticCatalog, NativeDraft } from "../api/types";
import nativeJson from "../lib/nativeDraft.fixture.json";
import { editorDraft } from "../lib/nativeDraft";
import { SemanticCatalogView } from "./SemanticModels";
import { MappingPanel } from "./elements/ElementPanels";
import { nativeSemanticModels } from "../lib/semanticEditing";

const catalog: SemanticCatalog = {
  concepts: [
    { id: "c1", kind: "object_type", name: "系统", technical_name: "system" },
  ],
  mapping_status: {},
  items: [
    {
      id: "model",
      name: "治理",
      description: "说明不得推断成名称",
      connection_alias: "governance",
      datasets: Array.from({ length: 41 }, (_, i) => ({
        id: `d${i}`,
        name: `dataset_${i}`,
        source: `public.table_${i}`,
        primary_key: ["id"],
        unique_keys: [],
        ai_context: { synonyms: ["组件"] },
        fields: Array.from({ length: i === 0 ? 35 : 8 }, (_, j) => ({
          id: `f${i}_${j}`,
          name: `field_${i}_${j}`,
          datatype: "String",
          dimension: { is_time: false },
          expression: {
            dialects: [{ dialect: "ANSI_SQL", expression: `column_${j}` }],
          },
          ai_context: { synonyms: ["字段别名"] },
        })),
      })),
      relationships: [
        {
          id: "r",
          name: "连接",
          from: "dataset_0",
          to: "dataset_1",
          from_columns: ["id", "tenant"],
          to_columns: ["parent_id", "tenant_id"],
        },
      ],
      metrics: Array.from({ length: 27 }, (_, i) => ({
        id: `m${i}`,
        name: `metric_${i}`,
        description: "指标说明",
        datatype: "Integer",
        expression: {
          dialects: [
            { dialect: "ANSI_SQL", expression: "COUNT(dataset_0.id)" },
          ],
        },
        ai_context: { synonyms: ["核心服务数"] },
        query: {
          executable: false,
          reason: "未配置连接",
          requires_snapshot_filter: true,
          time_semantics: "snapshot",
          time_field: "snapshot_date",
          group_by_fields: [{ name: "env_name" }],
        },
        concepts:
          i === 0
            ? [
                {
                  id: "c1",
                  kind: "object_type",
                  name: "系统",
                  technical_name: "system",
                },
                {
                  id: "c2",
                  kind: "object_type",
                  name: "组件",
                  technical_name: "component",
                },
              ]
            : [],
      })),
    },
  ],
};
afterEach(cleanup);
describe("语义模型工作台", () => {
  it("paginates catalog and fields while deferring other tabs", () => {
    render(<SemanticCatalogView catalog={catalog} />);
    expect(screen.getByText("41 数据集")).toBeInTheDocument();
    expect(screen.queryByText("metric_0")).not.toBeInTheDocument();
    expect(screen.queryByText("dataset_12")).not.toBeInTheDocument();
    expect(screen.queryByText("field_0_12")).not.toBeInTheDocument();
    fireEvent.click(
      within(screen.getByLabelText("字段分页")).getByText("下一页"),
    );
    fireEvent.click(
      within(screen.getByLabelText("字段分页")).getByText("下一页"),
    );
    expect(screen.getByText("field_0_34")).toBeInTheDocument();
    expect(screen.queryByText("field_0_0")).not.toBeInTheDocument();
    fireEvent.click(
      within(screen.getByLabelText("数据集分页")).getByText("下一页"),
    );
    expect(screen.getByText("dataset_12")).toBeInTheDocument();
  });
  it("searches aliases and presents concepts as clickable neutral tags", () => {
    const open = vi.fn();
    render(<SemanticCatalogView catalog={catalog} open={open} />);
    fireEvent.click(screen.getByRole("button", { name: /^指标/ }));
    fireEvent.change(screen.getByLabelText("搜索语义对象"), {
      target: { value: "核心服务数" },
    });
    expect(screen.getByText("COUNT(dataset_0.id)")).toBeInTheDocument();
    const tag = screen.getByRole("button", { name: "系统" });
    expect(tag).toHaveClass("tag--concept");
    fireEvent.click(tag);
    expect(open).toHaveBeenCalledWith({ kind: "object_type", id: "c1" });
    expect(screen.getByText("核心服务数")).toHaveClass("tag--label");
    expect(screen.queryByText(/只读|暂只读|读法/)).not.toBeInTheDocument();
  });
  it("shows all composite keys and follows a dataset reference", () => {
    render(<SemanticCatalogView catalog={catalog} />);
    fireEvent.click(screen.getByRole("button", { name: /^数据集关系/ }));
    expect(screen.getByText("dataset_0.tenant")).toBeInTheDocument();
    expect(screen.getByText("dataset_1.tenant_id")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "dataset_1" }));
    expect(
      screen.getByRole("heading", { name: "dataset_1" }),
    ).toBeInTheDocument();
  });
  it("sends only changed native fields, not the clean catalog projection", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    render(<SemanticCatalogView catalog={catalog} canEdit onSave={save} />);
    const row = screen.getByText("field_0_0").closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "编辑" }));
    fireEvent.change(screen.getByLabelText("原生名称"), {
      target: { value: "renamed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存并发布" }));
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith([
        {
          kind: "dataset_field",
          id: "f0_0",
          operation: "update",
          parent_id: "d0",
          values: { name: "renamed" },
          unset_fields: [],
        },
      ]),
    );
  });
  it("creates dataset and keeps rejected deletion open with an error", async () => {
    const save = vi
      .fn()
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error("元素仍被指标引用"));
    render(<SemanticCatalogView catalog={catalog} canEdit onSave={save} />);
    fireEvent.click(screen.getByRole("button", { name: "新增" }));
    fireEvent.change(screen.getByLabelText("原生名称"), {
      target: { value: "new_dataset" },
    });
    fireEvent.change(screen.getByLabelText("物理来源"), {
      target: { value: "public.new_table" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存并发布" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(save.mock.calls[0][0][0]).toMatchObject({
      kind: "dataset",
      operation: "create",
      parent_id: "model",
      values: { name: "new_dataset", source: "public.new_table" },
    });
    fireEvent.click(screen.getByRole("button", { name: "删除dataset_0" }));
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "元素仍被指标引用",
    );
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });
  it("compiles a draft with explicit snapshot date and grouping", async () => {
    const sql = vi.fn().mockResolvedValue({
      executed: false,
      executable: false,
      sql: "SELECT COUNT(id) FROM data",
      parameters: { p0: "2026-10-08" },
    });
    render(<SemanticCatalogView catalog={catalog} onSQL={sql} />);
    fireEvent.click(screen.getByRole("button", { name: /^指标/ }));
    fireEvent.click(screen.getByRole("button", { name: "SQL 预览" }));
    fireEvent.input(screen.getByLabelText("截至日期"), {
      target: { value: "2026-10-08" },
    });
    fireEvent.click(screen.getByLabelText("env_name"));
    fireEvent.click(screen.getByRole("button", { name: "生成 SQL" }));
    expect(
      await screen.findByText("SELECT COUNT(id) FROM data"),
    ).toBeInTheDocument();
    expect(sql.mock.calls[0][1]).toEqual({
      dialect: "POSTGRESQL",
      group_by: ["env_name"],
      as_of: "2026-10-08",
      changes: [],
    });
  });
  it("does not infer display names from descriptions or aliases", () => {
    const original = structuredClone(catalog);
    original.items[0].datasets[0].description = "中文数据集说明";
    original.items[0].datasets[0].display_name = "正式显示名";
    render(<SemanticCatalogView catalog={original} />);
    expect(
      screen.getByRole("heading", { name: "正式显示名" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "中文数据集说明" }),
    ).not.toBeInTheDocument();
  });
  it("edits a complex native mapping without replacing semantic branches in the draft", () => {
    const native = structuredClone(nativeJson) as NativeDraft;
    native.semantic_models = [
      { id: "model", name: "semantic", map_name: "semantic" },
    ];
    native.concept_mappings = [
      {
        id: "cm",
        semantic_model_id: "model",
        concept_id: { kind: "object_type", ref: native.object_types[0].id },
      },
    ];
    native.mapping_nodes = [
      {
        id: "root",
        concept_mapping_id: "cm",
        parent_id: null,
        slot: "object_mappings",
        kind: "object",
        concept: null,
        expression: "dataset.field + 2",
        position: 0,
      },
    ];
    const legacy = editorDraft(native);
    const models = nativeSemanticModels(native);
    const cm = models[0]?.concept_mappings?.[0];
    // Complex tree editing uses explicit changes outside the legacy draft.
    expect(cm).toBeDefined();
    const type = [...legacy.object_types, ...(legacy.value_types ?? [])].find(
      (t) => t.id === cm!.concept_id.ref,
    )!;
    const change = vi.fn();
    legacy.mapping_status = {
      [type.id]: {
        state: "readonly",
        reason: "multiple_roots",
        message: "复杂映射暂不支持实例查询",
        dataset_id: null,
      },
    };
    render(
      <MappingPanel
        draft={legacy}
        nativeDraft={native}
        type={type}
        editing
        change={change}
        open={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "编辑映射树" }));
    fireEvent.change(screen.getAllByLabelText("映射表达式")[0], {
      target: { value: "dataset.field + 1" },
    });
    fireEvent.click(screen.getByRole("button", { name: "应用到元素" }));
    expect(
      change.mock.calls[0][0]._semantic_changes[0].nodes[0].expression,
    ).toBe("dataset.field + 1");
    expect(change.mock.calls[0][0]).not.toHaveProperty("semantic_models");
  });
});

it("reviews reference impact before publishing a rename", async () => {
  const review = vi.fn().mockResolvedValue({
    references: [{ name: "core_service_count", field: "expression" }],
  });
  const save = vi.fn().mockResolvedValue(undefined);
  render(
    <SemanticCatalogView
      catalog={catalog}
      canEdit
      onSave={save}
      onReview={review}
    />,
  );
  fireEvent.click(
    within(screen.getByText("field_0_0").closest("tr")!).getByRole("button", {
      name: "编辑",
    }),
  );
  fireEvent.change(screen.getByLabelText("原生名称"), {
    target: { value: "renamed" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存并发布" }));
  expect(
    await screen.findByText("core_service_count · expression"),
  ).toBeInTheDocument();
  expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "确认修改并发布" }));
  await waitFor(() => expect(save).toHaveBeenCalledOnce());
});

it("sends snapshot equality and structured field filters", async () => {
  const sql = vi.fn().mockResolvedValue({ executed: false, sql: "SELECT 1" });
  render(<SemanticCatalogView catalog={catalog} onSQL={sql} />);
  fireEvent.click(screen.getByRole("button", { name: /^指标/ }));
  fireEvent.click(screen.getByRole("button", { name: "SQL 预览" }));
  fireEvent.change(screen.getByLabelText("时间选择"), {
    target: { value: "equal" },
  });
  fireEvent.change(screen.getByLabelText("截至日期"), {
    target: { value: "2026-10-08" },
  });
  fireEvent.click(screen.getByText("字段筛选"));
  fireEvent.click(screen.getByRole("button", { name: "添加筛选" }));
  fireEvent.change(screen.getByLabelText("筛选字段 1"), {
    target: { value: "env_name" },
  });
  fireEvent.change(screen.getByLabelText("筛选值 1"), {
    target: { value: "PROD" },
  });
  fireEvent.click(screen.getByRole("button", { name: "生成 SQL" }));
  await waitFor(() => expect(sql).toHaveBeenCalled());
  expect(sql.mock.calls[0][1]).toMatchObject({
    as_of: null,
    filters: [
      { field: "env_name", op: "=", value: "PROD" },
      { field: "snapshot_date", op: "=", value: "2026-10-08" },
    ],
  });
});

it("keeps delimiters while typing composite keys and synonym lists", async () => {
  const save = vi.fn().mockResolvedValue(undefined);
  render(<SemanticCatalogView catalog={catalog} canEdit onSave={save} />);
  fireEvent.click(screen.getByRole("button", { name: "新增" }));
  fireEvent.change(screen.getByLabelText("原生名称"), {
    target: { value: "new_ds" },
  });
  fireEvent.change(screen.getByLabelText("物理来源"), {
    target: { value: "public.new_ds" },
  });
  fireEvent.change(screen.getByLabelText("主键"), { target: { value: "id," } });
  expect(screen.getByLabelText("主键")).toHaveValue("id,");
  fireEvent.change(screen.getByLabelText("主键"), {
    target: { value: "id, tenant" },
  });
  fireEvent.change(screen.getByLabelText("同义词"), {
    target: { value: "别名," },
  });
  expect(screen.getByLabelText("同义词")).toHaveValue("别名,");
  fireEvent.change(screen.getByLabelText("同义词"), {
    target: { value: "别名, 业务别名" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存并发布" }));
  await waitFor(() => expect(save).toHaveBeenCalled());
  expect(save.mock.calls[0][0][0].values).toMatchObject({
    primary_key: ["id", "tenant"],
    ai_context: { synonyms: ["别名", "业务别名"] },
  });
});

it("preserves string AIContext during an unrelated edit and edits it as text", async () => {
  const original = structuredClone(catalog);
  original.items[0].datasets[0].ai_context = "原生字符串\n不要转换格式";
  const save = vi.fn().mockResolvedValue(undefined);
  render(<SemanticCatalogView catalog={original} canEdit onSave={save} />);
  fireEvent.click(
    within(
      document.querySelector(".semantic-detail-heading") as HTMLElement,
    ).getByRole("button", { name: "编辑" }),
  );
  expect(screen.getByLabelText("AI 说明")).toHaveValue(
    "原生字符串\n不要转换格式",
  );
  fireEvent.change(screen.getByLabelText("说明"), {
    target: { value: "字段说明" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存并发布" }));
  await waitFor(() => expect(save).toHaveBeenCalled());
  expect(save.mock.calls[0][0][0].values).toEqual({ description: "字段说明" });
});
