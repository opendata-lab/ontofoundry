import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  ArrowRight,
  Database,
  GitBranch,
  Plus,
  Search,
  Sigma,
  Trash2,
  X,
} from "lucide-react";
import { ApiError, workspaceRequest } from "../api/client";
import type {
  MetricSQLPreview,
  SemanticCatalog,
  SemanticChange,
  SemanticConcept,
  SemanticExpression,
  SemanticKind,
  SemanticMetric,
  SemanticModel,
  ModelingSession,
  VersionSummary,
} from "../api/types";
import { ConceptTag } from "./ConceptTag";
import { HintIcon } from "./HintIcon";
import { TagList } from "./TagList";
import { useElementInspector } from "../hooks/useElementInspector";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import {
  notifyOntologySaved,
  ONTOLOGY_SAVED,
  type ElementRequest,
} from "../lib/elementInspector";
import { MappingTreeEditor } from "./semantic/MappingTreeEditor";
import {
  SemanticObjectForm,
  type SemanticFormTarget,
} from "./semantic/SemanticObjectForm";
import { contextSynonyms, semanticLabel } from "../lib/semanticEditing";
import { newId } from "../lib/id";

function Expression({ value }: { value: SemanticExpression }) {
  const [selected, setSelected] = useState(0);
  const index = Math.min(selected, value.dialects.length - 1);
  return (
    <div className="semantic-expression">
      <div className="semantic-row">
        {value.dialects.map((d, i) => (
          <button
            key={i}
            type="button"
            aria-pressed={index === i}
            onClick={() => setSelected(i)}
          >
            {d.dialect}
          </button>
        ))}
      </div>
      <pre>{value.dialects[index]?.expression || "—"}</pre>
    </div>
  );
}
function Pages<T>({
  items,
  label,
  size = 12,
  render,
}: {
  items: T[];
  label: string;
  size?: number;
  render: (item: T) => ReactNode;
}) {
  const [page, setPage] = useState(0);
  const current = Math.min(
    page,
    Math.max(0, Math.ceil(items.length / size) - 1),
  );
  return (
    <>
      {items.slice(current * size, (current + 1) * size).map(render)}
      {items.length > size && (
        <div className="semantic-pagination" aria-label={label + "分页"}>
          <button
            type="button"
            disabled={current === 0}
            onClick={() => setPage(current - 1)}
          >
            上一页
          </button>
          <span>
            {current + 1} / {Math.ceil(items.length / size)} · {items.length} 项
          </span>
          <button
            type="button"
            disabled={(current + 1) * size >= items.length}
            onClick={() => setPage(current + 1)}
          >
            下一页
          </button>
        </div>
      )}
    </>
  );
}
function ConceptChips({
  concepts,
  open,
}: {
  concepts: SemanticConcept[];
  open?: (request: ElementRequest) => void;
}) {
  return (
    <div className="semantic-chips">
      {concepts.length ? (
        concepts.map((c) => (
          <ConceptTag
            key={c.id}
            label={c.name}
            kind={c.kind ?? "object_type"}
            id={c.id}
            open={open}
          />
        ))
      ) : (
        <span className="muted">尚未关联概念</span>
      )}
    </div>
  );
}
type Tab = "datasets" | "relationships" | "metrics" | "concept_mappings";
const tabs: { id: Tab; label: string }[] = [
  { id: "datasets", label: "数据集" },
  { id: "relationships", label: "数据集关系" },
  { id: "metrics", label: "指标" },
  { id: "concept_mappings", label: "概念映射" },
];
const kinds: Record<Tab, SemanticKind> = {
  datasets: "dataset",
  relationships: "dataset_relationship",
  metrics: "metric",
  concept_mappings: "concept_mapping",
};
const emptyModel: SemanticModel = {
  id: "",
  name: "",
  connection_alias: null,
  datasets: [],
  relationships: [],
  metrics: [],
  concept_mappings: [],
};

export function SemanticCatalogView({
  catalog,
  canEdit = false,
  onSave,
  onSQL,
  onReview,
  open,
  onEditingChange,
}: {
  catalog: SemanticCatalog;
  canEdit?: boolean;
  onSave?: (changes: SemanticChange[]) => Promise<void>;
  onReview?: (
    changes: SemanticChange[],
  ) => Promise<{ references: { name: string; field: string }[] }>;
  onSQL?: (
    metric: SemanticMetric,
    parameters: Record<string, unknown>,
  ) => Promise<MetricSQLPreview>;
  open?: (request: ElementRequest) => void;
  onEditingChange?: (busy: boolean) => void;
}) {
  const [modelId, setModelId] = useState(catalog.items[0]?.id ?? "");
  const model =
    catalog.items.find((m) => m.id === modelId) ??
    catalog.items[0] ??
    emptyModel;
  const [tab, setTab] = useState<Tab>("datasets");
  const [query, setQuery] = useState("");
  const [selection, setSelection] = useState<string | null>(null);
  const [fieldPage, setFieldPage] = useState(0);
  const [form, setForm] = useState<SemanticFormTarget | null>(null);
  const [deleting, setDeleting] = useState<SemanticFormTarget | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [review, setReview] = useState<{
    changes: SemanticChange[];
    references: { name: string; field: string }[];
  } | null>(null);
  const [sqlMetric, setSQLMetric] = useState<SemanticMetric | null>(null);
  const [pendingMetric, setPendingMetric] = useState<SemanticChange | null>(
    null,
  );
  const [sql, setSQL] = useState<MetricSQLPreview | null>(null);
  const [asOf, setAsOf] = useState("");
  const [timeMode, setTimeMode] = useState("as_of");
  const [filters, setFilters] = useState<
    { field: string; op: string; value: string }[]
  >([]);
  const [groupBy, setGroupBy] = useState<string[]>([]);
  const [firstDataset, setFirstDataset] = useState({ name: "", source: "" });
  const [dialect, setDialect] = useState("POSTGRESQL");
  useEffect(() => {
    onEditingChange?.(!!form || !!deleting || busy);
    return () => onEditingChange?.(false);
  }, [form, deleting, busy, onEditingChange]);
  useEffect(() => {
    if (!form && !deleting && !busy) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [form, deleting, busy]);
  const concepts = catalog.concepts ?? [];
  const source =
    tab === "concept_mappings"
      ? (model.concept_mappings ?? []).map((c) => ({
          ...c,
          name: c.concept?.name ?? c.concept_id.ref,
          description: c.concept?.technical_name,
        }))
      : model[tab];
  const items = source.filter((item) =>
    [
      item.name,
      "description" in item ? item.description : "",
      "ai_context" in item ? contextSynonyms(item.ai_context).join(" ") : "",
      "source" in item ? item.source : "",
    ]
      .join(" ")
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const selected = items.find((i) => i.id === selection) ?? items[0];
  const dataset =
    tab === "datasets"
      ? model.datasets.find((d) => d.id === selected?.id)
      : undefined;
  const metric =
    tab === "metrics"
      ? model.metrics.find((m) => m.id === selected?.id)
      : undefined;
  const relationship =
    tab === "relationships"
      ? model.relationships.find((r) => r.id === selected?.id)
      : undefined;
  const cm =
    tab === "concept_mappings"
      ? model.concept_mappings?.find((c) => c.id === selected?.id)
      : undefined;
  const target = (
    kind: SemanticKind,
    item?: { id: string },
    parent_id = model.id,
  ): SemanticFormTarget => ({
    kind,
    id: item?.id ?? newId(),
    parent_id: kind === "semantic_model" ? undefined : parent_id,
    operation: item ? "update" : "create",
    original: item
      ? { ...item }
      : kind === "dataset"
        ? { name: "", source: "", primary_key: [], unique_keys: [] }
        : kind === "dataset_field" || kind === "metric"
          ? {
              name: "",
              expression: {
                dialects: [{ dialect: "ANSI_SQL", expression: "" }],
              },
            }
          : kind === "dataset_relationship"
            ? {
                name: "",
                from: "",
                to: "",
                from_columns: [""],
                to_columns: [""],
              }
            : {},
  });
  const edit = (value: SemanticFormTarget) => {
    setError("");
    setForm(value);
  };
  const save = async (change: SemanticChange, approved = false) => {
    if (!onSave) return;
    setBusy(true);
    setError("");
    try {
      const changes = [change];
      if (change.kind === "semantic_model" && change.operation === "create") {
        if (!firstDataset.name.trim() || !firstDataset.source.trim())
          throw new Error("新语义模型需填写首个数据集的名称与来源");
        changes.push({
          kind: "dataset",
          operation: "create",
          id: newId(),
          parent_id: change.id,
          values: firstDataset,
        });
      }
      if (
        change.kind === "dataset" &&
        change.operation === "delete" &&
        model.datasets.length === 1 &&
        !model.metrics.length &&
        !model.relationships.length &&
        !model.concept_mappings?.length
      ) {
        changes.push({
          kind: "semantic_model",
          operation: "delete",
          id: model.id,
          values: {},
        });
      }
      if (
        onReview &&
        !approved &&
        (change.operation === "delete" || "name" in change.values)
      ) {
        const impact = await onReview(changes);
        if (impact.references.length) {
          setReview({ changes, references: impact.references });
          return;
        }
      }
      await onSave(changes);
      setReview(null);
      setForm(null);
      setDeleting(null);
      setSelection(change.operation === "delete" ? null : change.id);
    } catch (e) {
      setError(
        e instanceof ApiError && e.references.length
          ? e.message +
              "：" +
              e.references.map((r) => `${r.name} (${r.field})`).join("、")
          : e instanceof Error
            ? e.message
            : "保存失败",
      );
    } finally {
      setBusy(false);
    }
  };
  const addModel = () => {
    setFirstDataset({ name: "", source: "" });
    edit(target("semantic_model"));
  };
  const beginSQL = (
    m: SemanticMetric,
    change: SemanticChange | null = null,
  ) => {
    setSQLMetric(m);
    setPendingMetric(change);
    setSQL(null);
    setError("");
    setAsOf("");
    setTimeMode("as_of");
    setFilters([]);
    setGroupBy([]);
  };
  const compile = async () => {
    if (!sqlMetric || !onSQL) return;
    setBusy(true);
    setError("");
    try {
      setSQL(
        await onSQL(sqlMetric, {
          dialect,
          group_by: groupBy,
          as_of: timeMode === "as_of" ? asOf || null : null,
          ...(filters.length || (timeMode === "equal" && asOf)
            ? {
                filters: [
                  ...filters.map((f) =>
                    ["is_null", "not_null"].includes(f.op)
                      ? { field: f.field, op: f.op }
                      : {
                          ...f,
                          value: ["in", "between"].includes(f.op)
                            ? f.value.split(",").map((v) => v.trim())
                            : f.value,
                        },
                  ),
                  ...(timeMode === "equal" && asOf
                    ? [
                        {
                          field: sqlMetric.query?.time_field ?? "snapshot_date",
                          op: "=",
                          value: asOf,
                        },
                      ]
                    : []),
                ],
              }
            : {}),
          changes: pendingMetric ? [pendingMetric] : [],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "SQL 编译失败");
    } finally {
      setBusy(false);
    }
  };
  const controls = (
    kind: SemanticKind,
    item: { id: string },
    parent?: string,
  ) =>
    canEdit && (
      <span className="semantic-actions">
        <button type="button" onClick={() => edit(target(kind, item, parent))}>
          编辑
        </button>
        <button
          type="button"
          aria-label={`删除${"name" in item ? item.name : "映射"}`}
          onClick={() => {
            setError("");
            setDeleting(target(kind, item, parent));
          }}
        >
          <Trash2 size={13} />
        </button>
      </span>
    );
  const fieldCurrent = Math.min(
    fieldPage,
    Math.max(0, Math.ceil((dataset?.fields.length ?? 0) / 12) - 1),
  );
  return (
    <section className="semantic-workbench" aria-label="语义模型工作台">
      <header className="semantic-overview">
        <div className="semantic-row">
          <GitBranch size={18} />
          <select
            aria-label="语义模型"
            value={model.id}
            disabled={busy || !!form}
            onChange={(e) => {
              setModelId(e.target.value);
              setSelection(null);
              setQuery("");
            }}
          >
            {catalog.items.map((m) => (
              <option key={m.id} value={m.id}>
                {semanticLabel(m)}
              </option>
            ))}
          </select>
          <HintIcon
            text={model.description || "语义模型包含数据集、指标与概念映射。"}
          />
          <span className="semantic-spacer" />
          {canEdit && (
            <>
              <button type="button" onClick={addModel}>
                <Plus size={12} />
                语义模型
              </button>
              {model.id && controls("semantic_model", model)}
            </>
          )}
        </div>
        <div className="semantic-overview-bottom">
          <span>
            <Database size={12} />
            {model.connection_alias ?? "未绑定连接"}
          </span>
          <span>{model.datasets.length} 数据集</span>
          <span>{model.relationships.length} 关系</span>
          <span>{model.metrics.length} 指标</span>
          <span>{model.concept_mappings?.length ?? 0} 概念映射</span>
          {model.ai_context != null && (
            <HintIcon
              text={
                typeof model.ai_context === "string"
                  ? model.ai_context
                  : JSON.stringify(model.ai_context, null, 2)
              }
            />
          )}
        </div>
      </header>
      <nav className="semantic-tabs" aria-label="语义模型目录">
        {tabs.map((t) => (
          <button
            type="button"
            key={t.id}
            aria-pressed={t.id === tab}
            disabled={busy || !!form}
            onClick={() => {
              setTab(t.id);
              setSelection(null);
              setQuery("");
              setFieldPage(0);
            }}
          >
            {t.label}
            <small>{(model[t.id] ?? []).length}</small>
          </button>
        ))}
      </nav>
      <div className="semantic-body">
        <aside className="semantic-sidebar">
          <label className="semantic-search">
            <Search size={13} />
            <input
              aria-label="搜索语义对象"
              placeholder={`搜索${tabs.find((t) => t.id === tab)?.label}、同义词`}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="semantic-row">
            <span className="muted">{items.length} 项</span>
            <span className="semantic-spacer" />
            {canEdit && model.id && (
              <button type="button" onClick={() => edit(target(kinds[tab]))}>
                <Plus size={12} />
                新增
              </button>
            )}
          </div>
          {tab === "datasets" ? (
            [true, false].map((mapped) => {
              const group = items.filter(
                (i) =>
                  !!model.datasets.find((d) => d.id === i.id)?.concepts
                    ?.length === mapped,
              );
              return group.length ? (
                <div key={String(mapped)}>
                  <h4>
                    {mapped ? "已关联概念" : "其他数据集"}
                    <small>{group.length}</small>
                  </h4>
                  <Pages
                    key={`${tab}:${query}:${mapped}:${model.id}`}
                    items={group}
                    label={mapped ? "已关联数据集" : "数据集"}
                    render={(item) => (
                      <button
                        type="button"
                        className="semantic-catalog-item"
                        key={item.id}
                        aria-current={selected?.id === item.id}
                        onClick={() => {
                          setSelection(item.id);
                          setFieldPage(0);
                        }}
                      >
                        <Database size={14} />
                        <span>
                          {semanticLabel(item)}
                          <small>
                            {
                              model.datasets.find((d) => d.id === item.id)
                                ?.source
                            }
                          </small>
                        </span>
                        <small>
                          {
                            model.datasets.find((d) => d.id === item.id)?.fields
                              .length
                          }
                        </small>
                      </button>
                    )}
                  />
                </div>
              ) : null;
            })
          ) : (
            <Pages
              key={`${tab}:${query}:${model.id}`}
              items={items}
              label={tabs.find((t) => t.id === tab)?.label ?? "目录"}
              render={(item) => (
                <button
                  type="button"
                  className="semantic-catalog-item"
                  key={item.id}
                  aria-current={selected?.id === item.id}
                  onClick={() => setSelection(item.id)}
                >
                  {tab === "metrics" ? (
                    <Sigma size={14} />
                  ) : (
                    <GitBranch size={14} />
                  )}
                  <span>
                    {semanticLabel(item)}
                    <small>{item.name}</small>
                  </span>
                </button>
              )}
            />
          )}
          {!items.length && <p className="muted">暂无匹配项</p>}
        </aside>
        <article className="semantic-detail">
          {selected ? (
            <>
              <div className="semantic-detail-heading">
                <div>
                  <h2>{semanticLabel(selected)}</h2>
                  <code>{selected.name}</code>
                </div>
                {controls(kinds[tab], selected)}
              </div>
              {"description" in selected && selected.description && (
                <div className="semantic-description">
                  <span>说明</span>
                  <HintIcon text={selected.description} />
                </div>
              )}
              {"ai_context" in selected && (
                <TagList tags={contextSynonyms(selected.ai_context)} />
              )}
              {dataset && (
                <>
                  <div className="semantic-facts">
                    <div>
                      <span>物理来源</span>
                      <code>{dataset.source}</code>
                    </div>
                    <div>
                      <span>主键</span>
                      <code>{dataset.primary_key.join(" + ") || "未声明"}</code>
                    </div>
                    <div>
                      <span>唯一键</span>
                      <code>
                        {dataset.unique_keys
                          .map((k) => k.join(" + "))
                          .join("；") || "未声明"}
                      </code>
                    </div>
                  </div>
                  <div className="semantic-row">
                    <h3>
                      字段 <small>{dataset.fields.length}</small>
                    </h3>
                    <span className="semantic-spacer" />
                    {canEdit && (
                      <button
                        type="button"
                        onClick={() =>
                          edit(target("dataset_field", undefined, dataset.id))
                        }
                      >
                        <Plus size={12} />
                        字段
                      </button>
                    )}
                  </div>
                  <div className="semantic-table-scroll">
                    <table className="semantic-table">
                      <thead>
                        <tr>
                          <th>字段</th>
                          <th>表达式 / 方言</th>
                          <th>类型</th>
                          <th>维度</th>
                          <th>同义词</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {dataset.fields
                          .slice(fieldCurrent * 12, (fieldCurrent + 1) * 12)
                          .map((f) => (
                            <tr key={f.id}>
                              <td>
                                <strong>{semanticLabel(f)}</strong>
                                {f.description && (
                                  <HintIcon text={f.description} />
                                )}
                                {semanticLabel(f) !== f.name && (
                                  <small>{f.name}</small>
                                )}
                              </td>
                              <td>
                                <Expression value={f.expression} />
                              </td>
                              <td>{f.datatype ?? "—"}</td>
                              <td>
                                {f.dimension == null
                                  ? "—"
                                  : f.dimension.is_time
                                    ? "时间"
                                    : "普通"}
                              </td>
                              <td>
                                <TagList tags={contextSynonyms(f.ai_context)} />
                              </td>
                              <td>
                                {controls("dataset_field", f, dataset.id)}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                  {dataset.fields.length > 12 && (
                    <div className="semantic-pagination" aria-label="字段分页">
                      <button
                        type="button"
                        disabled={fieldCurrent === 0}
                        onClick={() => setFieldPage(fieldCurrent - 1)}
                      >
                        上一页
                      </button>
                      <span>
                        {fieldCurrent + 1} /{" "}
                        {Math.ceil(dataset.fields.length / 12)}
                      </span>
                      <button
                        type="button"
                        disabled={
                          (fieldCurrent + 1) * 12 >= dataset.fields.length
                        }
                        onClick={() => setFieldPage(fieldCurrent + 1)}
                      >
                        下一页
                      </button>
                    </div>
                  )}
                  <h3>引用此数据集</h3>
                  <ConceptChips concepts={dataset.concepts ?? []} open={open} />
                  <div className="semantic-chips">
                    {model.metrics
                      .filter((m) => dataset.metrics?.includes(m.id))
                      .map((m) => (
                        <button
                          type="button"
                          key={m.id}
                          onClick={() => {
                            setTab("metrics");
                            setSelection(m.id);
                            setQuery("");
                          }}
                        >
                          <Sigma size={12} />
                          {semanticLabel(m)}
                        </button>
                      ))}
                  </div>
                </>
              )}
              {relationship && (
                <>
                  <div className="semantic-relationship-diagram">
                    <button
                      type="button"
                      onClick={() => {
                        setTab("datasets");
                        setSelection(
                          model.datasets.find(
                            (d) => d.name === relationship.from,
                          )?.id ?? null,
                        );
                      }}
                    >
                      {relationship.from}
                    </button>
                    <ArrowRight size={20} />
                    <button
                      type="button"
                      onClick={() => {
                        setTab("datasets");
                        setSelection(
                          model.datasets.find((d) => d.name === relationship.to)
                            ?.id ?? null,
                        );
                      }}
                    >
                      {relationship.to}
                    </button>
                  </div>
                  <h3>
                    等值连接键 <small>{relationship.from_columns.length}</small>
                  </h3>
                  {relationship.from_columns.map((c, i) => (
                    <div className="join-pair" key={i}>
                      <code>
                        {relationship.from}.{c}
                      </code>
                      <span>=</span>
                      <code>
                        {relationship.to}.{relationship.to_columns[i]}
                      </code>
                    </div>
                  ))}
                </>
              )}
              {metric && (
                <>
                  <div className="semantic-facts">
                    <div>
                      <span>数据类型</span>
                      <code>{metric.datatype ?? "未声明"}</code>
                    </div>
                    <div>
                      <span>执行状态</span>
                      <strong>
                        {metric.query?.executable ? "可执行" : "可编译性检查"}
                      </strong>
                      {metric.query?.reason && (
                        <HintIcon text={metric.query.reason} />
                      )}
                    </div>
                    <div>
                      <span>时间语义</span>
                      <code>{metric.query?.time_semantics ?? "未声明"}</code>
                      {metric.query?.requires_snapshot_filter && (
                        <HintIcon
                          text={`必须对 ${metric.query.time_field} 等值过滤或提供 as_of，以免跨快照聚合。`}
                        />
                      )}
                    </div>
                  </div>
                  <h3>表达式</h3>
                  <Expression value={metric.expression} />
                  <h3>数据集</h3>
                  <div className="semantic-chips">
                    {model.datasets
                      .filter((d) =>
                        metric.query?.datasets ? metric.query.datasets.some(ref => ref.id === d.id) : metric.expression.dialects.some((e) => e.expression.includes(d.name + ".")),
                      )
                      .map((d) => (
                        <button
                          type="button"
                          key={d.id}
                          onClick={() => {
                            setTab("datasets");
                            setSelection(d.id);
                          }}
                        >
                          {d.name}
                        </button>
                      ))}
                  </div>
                  <h3>
                    关联概念{" "}
                    {metric.ambiguous && (
                      <HintIcon text="根据概念映射推导出多个归属候选。" />
                    )}
                  </h3>
                  <ConceptChips concepts={metric.concepts} open={open} />
                  <button type="button" onClick={() => beginSQL(metric)}>
                    SQL 预览
                  </button>
                </>
              )}
              {cm && (
                <>
                  <ConceptChips
                    concepts={cm.concept ? [cm.concept] : []}
                    open={open}
                  />
                  <MappingTreeEditor
                    nodes={cm.nodes}
                    onChange={() => {}}
                    editing={false}
                    concepts={concepts}
                  />
                </>
              )}
            </>
          ) : (
            <div className="semantic-empty">
              <Database size={30} />
              <p>
                {model.id
                  ? "选择目录项，或新增语义对象"
                  : "创建语义模型并添加首个数据集"}
              </p>
              {canEdit && !model.id && (
                <button type="button" onClick={addModel}>
                  创建语义模型
                </button>
              )}
            </div>
          )}
        </article>
      </div>
      {(form || deleting || sqlMetric) && (
        <div className="semantic-sheet-backdrop">
          <section
            className="semantic-sheet"
            role="dialog"
            aria-modal="true"
            aria-label={
              deleting
                ? "确认删除语义对象"
                : sqlMetric
                  ? "SQL 预览"
                  : "编辑语义对象"
            }
          >
            <header>
              <h3>
                {deleting
                  ? "删除语义对象"
                  : sqlMetric
                    ? `SQL 预览 · ${semanticLabel(sqlMetric)}`
                    : form?.operation === "create"
                      ? "新增语义对象"
                      : "编辑语义对象"}
              </h3>
              <button
                type="button"
                disabled={busy}
                aria-label="关闭编辑抽屉"
                onClick={() => {
                  if (sqlMetric) {
                    setSQLMetric(null);
                    setSQL(null);
                  } else {
                    setForm(null);
                    setDeleting(null);
                    setReview(null);
                  }
                  setError("");
                }}
              >
                <X size={16} />
              </button>
            </header>
            <div className="semantic-sheet-content">
              {review ? (
                <>
                  <h3>同步更新引用</h3>
                  <p>
                    以下对象引用当前元素；逻辑名称引用将同步更新，物理表达式保持原样。
                  </p>
                  <ul>
                    {review.references.map((r, i) => (
                      <li key={i}>
                        {r.name} · {r.field}
                      </li>
                    ))}
                  </ul>
                  {error && (
                    <p className="inline-error" role="alert">
                      {error}
                    </p>
                  )}
                  <button
                    type="button"
                    disabled={busy}
                    className="button button--primary"
                    onClick={() => void save(review.changes[0], true)}
                  >
                    确认修改并发布
                  </button>
                </>
              ) : sqlMetric ? (
                <>
                  <p className="semantic-row">
                    基于当前草稿编译
                    <HintIcon text="仅编译与展示参数，不执行 SQL。快照数据必须指定日期。" />
                  </p>
                  <label>
                    目标方言
                    <select
                      value={dialect}
                      onChange={(e) => setDialect(e.target.value)}
                    >
                      <option>POSTGRESQL</option>
                      <option>MYSQL</option>
                      <option>ANSI_SQL</option>
                    </select>
                  </label>
                  <label>
                    时间选择
                    <select
                      aria-label="时间选择"
                      value={timeMode}
                      onChange={(e) => setTimeMode(e.target.value)}
                    >
                      <option value="as_of">截至日期的最新快照 (as_of)</option>
                      <option value="equal">指定快照日期 (=)</option>
                    </select>
                  </label>
                  <label>
                    快照日期
                    <input
                      type="date"
                      aria-label="截至日期"
                      value={asOf}
                      onInput={(e) => setAsOf(e.currentTarget.value)}
                      onChange={(e) => setAsOf(e.target.value)}
                    />
                  </label>
                  <fieldset className="semantic-group-fields">
                    <legend>分组字段</legend>
                    {(sqlMetric.query?.group_by_fields ?? []).map((f) => (
                      <label key={f.name}>
                        <input
                          type="checkbox"
                          checked={groupBy.includes(f.name)}
                          onChange={(e) =>
                            setGroupBy(
                              e.target.checked
                                ? [...groupBy, f.name]
                                : groupBy.filter((n) => n !== f.name),
                            )
                          }
                        />
                        {f.name}
                      </label>
                    ))}
                  </fieldset>
                  <details>
                    <summary>字段筛选</summary>
                    {filters.map((filter, i) => (
                      <div className="semantic-filter-row" key={i}>
                        <select
                          aria-label={`筛选字段 ${i + 1}`}
                          value={filter.field}
                          onChange={(e) =>
                            setFilters(
                              filters.map((f, j) =>
                                j === i ? { ...f, field: e.target.value } : f,
                              ),
                            )
                          }
                        >
                          <option value="">选择字段</option>
                          {(
                            sqlMetric.query?.filter_fields ??
                            sqlMetric.query?.group_by_fields ??
                            []
                          ).map((f) => (
                            <option key={f.name}>{f.name}</option>
                          ))}
                        </select>
                        <select
                          aria-label={`筛选操作 ${i + 1}`}
                          value={filter.op}
                          onChange={(e) =>
                            setFilters(
                              filters.map((f, j) =>
                                j === i ? { ...f, op: e.target.value } : f,
                              ),
                            )
                          }
                        >
                          {[
                            "=",
                            "!=",
                            "<",
                            "<=",
                            ">",
                            ">=",
                            "in",
                            "between",
                            "is_null",
                            "not_null",
                          ].map((op) => (
                            <option key={op}>{op}</option>
                          ))}
                        </select>
                        <input
                          aria-label={`筛选值 ${i + 1}`}
                          disabled={filter.op.endsWith("null")}
                          placeholder="in / between 用逗号分隔"
                          value={filter.value}
                          onChange={(e) =>
                            setFilters(
                              filters.map((f, j) =>
                                j === i ? { ...f, value: e.target.value } : f,
                              ),
                            )
                          }
                        />
                        <button
                          type="button"
                          aria-label={`删除筛选 ${i + 1}`}
                          onClick={() =>
                            setFilters(filters.filter((_, j) => j !== i))
                          }
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() =>
                        setFilters([
                          ...filters,
                          { field: "", op: "=", value: "" },
                        ])
                      }
                    >
                      添加筛选
                    </button>
                  </details>
                  <button
                    type="button"
                    disabled={busy || !onSQL}
                    onClick={() => void compile()}
                  >
                    {busy ? "正在编译…" : "生成 SQL"}
                  </button>
                  {error && (
                    <p className="inline-error" role="alert">
                      {error}
                    </p>
                  )}
                  {sql && (
                    <>
                      <pre className="semantic-sql">
                        {sql.sql ?? sql.reason}
                      </pre>
                      <pre>{JSON.stringify(sql.parameters, null, 2)}</pre>
                      {sql.reason && <p>{sql.reason}</p>}
                    </>
                  )}
                </>
              ) : deleting ? (
                <>
                  <p>
                    删除「{String(deleting.original.name ?? "概念映射")}
                    」？已被映射、指标或连接引用的对象需要先解除引用。
                  </p>
                  {error && (
                    <p className="inline-error" role="alert">
                      {error}
                    </p>
                  )}
                  <button
                    type="button"
                    className="button"
                    disabled={busy}
                    onClick={() =>
                      void save({
                        ...deleting,
                        operation: "delete",
                        values: {},
                      })
                    }
                  >
                    确认删除
                  </button>
                </>
              ) : (
                form && (
                  <>
                    {form.kind === "semantic_model" &&
                      form.operation === "create" && (
                        <div className="semantic-columns">
                          <label>
                            首个数据集名称
                            <input
                              aria-label="首个数据集名称"
                              value={firstDataset.name}
                              onChange={(e) =>
                                setFirstDataset((v) => ({
                                  ...v,
                                  name: e.target.value,
                                }))
                              }
                            />
                          </label>
                          <label>
                            首个数据集来源
                            <input
                              aria-label="首个数据集来源"
                              value={firstDataset.source}
                              onChange={(e) =>
                                setFirstDataset((v) => ({
                                  ...v,
                                  source: e.target.value,
                                }))
                              }
                            />
                          </label>
                        </div>
                      )}
                    <SemanticObjectForm
                      key={form.id}
                      target={form}
                      model={model}
                      concepts={concepts}
                      busy={busy}
                      error={error}
                      onSubmit={(change) => void save(change)}
                      onPreview={
                        form.kind === "metric"
                          ? (change) =>
                              beginSQL(
                                model.metrics.find(
                                  (m) => m.id === change.id,
                                ) ?? {
                                  ...form.original,
                                  id: change.id,
                                  name: String(
                                    change.values.name ??
                                      form.original.name ??
                                      "新指标",
                                  ),
                                  expression: change.values
                                    .expression as SemanticExpression,
                                  concepts: [],
                                },
                                change,
                              )
                          : undefined
                      }
                    />
                  </>
                )
              )}
            </div>
          </section>
        </div>
      )}
    </section>
  );
}

export function SemanticModels({
  workspaceId,
  sessionId,
  canEdit = false,
  onBusyChange,
}: {
  workspaceId: string;
  sessionId: string | null;
  canEdit?: boolean;
  onBusyChange?: (busy: boolean) => void;
}) {
  const [catalog, setCatalog] = useState<SemanticCatalog | null>(null);
  const [error, setError] = useState("");
  const [epoch, setEpoch] = useState(0);
  const [editing, setEditing] = useState(false);
  const reportEditing = useCallback(
    (value: boolean) => {
      setEditing(value);
      onBusyChange?.(value);
    },
    [onBusyChange],
  );
  const { refresh } = useWorkspaceContext();
  const inspector = useElementInspector();
  useEffect(() => {
    const reload = () => setEpoch((n) => n + 1);
    window.addEventListener(ONTOLOGY_SAVED, reload);
    return () => window.removeEventListener(ONTOLOGY_SAVED, reload);
  }, []);
  useEffect(() => {
    if (editing) return;
    let active = true;
    workspaceRequest<SemanticCatalog>(
      workspaceId,
      "/semantic-models" +
        (sessionId ? "?session_id=" + encodeURIComponent(sessionId) : ""),
    )
      .then((value) => {
        if (active) {
          setCatalog(value);
          setError("");
        }
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [workspaceId, sessionId, epoch, editing]);
  const context = () => ({
    expected_current_version_id: catalog?.current_version_id ?? null,
    session_id: sessionId,
    expected_session_revision: catalog?.session_revision ?? null,
  });
  const save = async (changes: SemanticChange[]) => {
    const result = await workspaceRequest<{
      version: VersionSummary;
      session: ModelingSession | null;
    }>(workspaceId, "/semantic-saves", { ...context(), changes });
    notifyOntologySaved({ workspaceId, session: result.session });
    refresh();
  };
  const review = (changes: SemanticChange[]) =>
    workspaceRequest<{ references: { name: string; field: string }[] }>(
      workspaceId,
      "/semantic-change-preview",
      { ...context(), changes },
    );
  const sql = (metric: SemanticMetric, parameters: Record<string, unknown>) =>
    workspaceRequest<MetricSQLPreview>(
      workspaceId,
      `/metrics/${metric.id}/sql-preview`,
      { ...context(), ...parameters },
    );
  return error ? (
    <p className="inline-error" role="alert">
      {error}
    </p>
  ) : catalog ? (
    <SemanticCatalogView
      key={workspaceId + ":" + sessionId}
      catalog={catalog}
      canEdit={canEdit}
      onSave={save}
      onSQL={sql}
      onReview={review}
      open={(request) => inspector.open({ ...request, sessionId })}
      onEditingChange={reportEditing}
    />
  ) : (
    <p>正在读取语义模型…</p>
  );
}
