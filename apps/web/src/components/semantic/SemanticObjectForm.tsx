import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type {
  ConceptRef,
  MappingNode,
  SemanticChange,
  SemanticConcept,
  SemanticExpression,
  SemanticKind,
  SemanticModel,
} from "../../api/types";
import {
  cleanNodes,
  contextSynonyms,
  semanticLabel,
} from "../../lib/semanticEditing";
import { HintIcon } from "../HintIcon";
import { MappingTreeEditor } from "./MappingTreeEditor";

export type SemanticFormTarget = {
  kind: SemanticKind;
  id: string;
  parent_id?: string;
  original: Record<string, unknown>;
  operation: "create" | "update";
};
const lists = (value: string) =>
  value
    .split(/[,，\n]/)
    .map((s) => s.trim())
    .filter(Boolean);
const slots = new Set([
  "name",
  "description",
  "source",
  "primary_key",
  "unique_keys",
  "expression",
  "datatype",
  "dimension",
  "label",
  "ai_context",
  "custom_extensions",
  "from",
  "to",
  "from_columns",
  "to_columns",
  "concept_id",
]);
const equal = (a: unknown, b: unknown) =>
  JSON.stringify(a) === JSON.stringify(b);

function DelimitedInput({
  label,
  initial,
  onValue,
  multiline = false,
  placeholder,
}: {
  label: string;
  initial: string;
  onValue: (value: string) => void;
  multiline?: boolean;
  placeholder?: string;
}) {
  const [text, setText] = useState(initial);
  const update = (value: string) => {
    setText(value);
    onValue(value);
  };
  return multiline ? (
    <textarea
      aria-label={label}
      rows={2}
      placeholder={placeholder}
      value={text}
      onChange={(e) => update(e.target.value)}
    />
  ) : (
    <input
      aria-label={label}
      placeholder={placeholder}
      value={text}
      onChange={(e) => update(e.target.value)}
    />
  );
}

export function DialectEditor({
  value,
  onChange,
}: {
  value: SemanticExpression;
  onChange: (value: SemanticExpression) => void;
}) {
  return (
    <div className="dialect-editor">
      {value.dialects.map((d, i) => (
        <div key={i} className="dialect-row">
          <select
            aria-label="表达式方言"
            value={d.dialect}
            onChange={(e) =>
              onChange({
                dialects: value.dialects.map((v, j) =>
                  j === i ? { ...v, dialect: e.target.value } : v,
                ),
              })
            }
          >
            {[
              ...new Set([
                d.dialect,
                "ANSI_SQL",
                "SNOWFLAKE",
                "MDX",
                "TABLEAU",
                "DATABRICKS",
                "MAQL",
                "BIGQUERY",
              ]),
            ].map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
          <textarea
            required
            aria-label="SQL 表达式"
            rows={3}
            value={d.expression}
            onChange={(e) =>
              onChange({
                dialects: value.dialects.map((v, j) =>
                  j === i ? { ...v, expression: e.target.value } : v,
                ),
              })
            }
          />
          <button
            type="button"
            aria-label="删除方言表达式"
            disabled={value.dialects.length < 2}
            onClick={() =>
              onChange({ dialects: value.dialects.filter((_, j) => j !== i) })
            }
          >
            <Trash2 size={13} />
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() =>
          onChange({
            dialects: [
              ...value.dialects,
              { dialect: "ANSI_SQL", expression: "" },
            ],
          })
        }
      >
        <Plus size={12} />
        添加方言
      </button>
    </div>
  );
}
export function JoinColumns({
  value,
  onChange,
  model,
  editing = true,
}: {
  value: {
    from: string;
    to: string;
    from_columns: string[];
    to_columns: string[];
  };
  onChange: (patch: Partial<typeof value>) => void;
  model: SemanticModel;
  editing?: boolean;
}) {
  const fieldSelect = (side: "from" | "to", i: number) => (
    <select
      aria-label={`${side === "from" ? "起始" : "目标"}连接字段 ${i + 1}`}
      value={value[`${side}_columns`][i] ?? ""}
      onChange={(e) =>
        onChange({
          [`${side}_columns`]: value[`${side}_columns`].map((c, j) =>
            j === i ? e.target.value : c,
          ),
        })
      }
    >
      <option value="">选择字段</option>
      {model.datasets
        .find((d) => d.name === value[side])
        ?.fields.map((f) => (
          <option key={f.id} value={f.name}>
            {f.name}
          </option>
        ))}
    </select>
  );
  return (
    <div className="join-editor">
      <div className="semantic-columns">
        {(["from", "to"] as const).map((side) => (
          <label key={side}>
            {side === "from" ? "起始数据集" : "目标数据集"}
            {editing ? (
              <select
                aria-label={side === "from" ? "起始数据集" : "目标数据集"}
                value={value[side]}
                onChange={(e) =>
                  onChange({
                    [side]: e.target.value,
                    [`${side}_columns`]: value[`${side}_columns`].map(() => ""),
                  })
                }
              >
                <option value="">选择数据集</option>
                {model.datasets.map((d) => (
                  <option value={d.name} key={d.id}>
                    {semanticLabel(d)}
                  </option>
                ))}
              </select>
            ) : (
              <code>{value[side]}</code>
            )}
          </label>
        ))}
      </div>
      {value.from_columns.map((c, i) => (
        <div className="join-pair" key={i}>
          {editing ? fieldSelect("from", i) : <code>{c}</code>}
          <span>=</span>
          {editing ? fieldSelect("to", i) : <code>{value.to_columns[i]}</code>}
          {editing && (
            <button
              type="button"
              aria-label={`删除连接键 ${i + 1}`}
              disabled={value.from_columns.length < 2}
              onClick={() =>
                onChange({
                  from_columns: value.from_columns.filter((_, j) => j !== i),
                  to_columns: value.to_columns.filter((_, j) => j !== i),
                })
              }
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      ))}
      {editing && (
        <button
          type="button"
          onClick={() =>
            onChange({
              from_columns: [...value.from_columns, ""],
              to_columns: [...value.to_columns, ""],
            })
          }
        >
          <Plus size={12} />
          添加连接键
        </button>
      )}
    </div>
  );
}

export function SemanticObjectForm({
  target,
  model,
  concepts,
  onSubmit,
  busy = false,
  submitLabel = "保存并发布",
  error,
  onPreview,
}: {
  target: SemanticFormTarget;
  model: SemanticModel;
  concepts: SemanticConcept[];
  onSubmit: (change: SemanticChange) => void;
  busy?: boolean;
  submitLabel?: string;
  error?: string;
  onPreview?: (change: SemanticChange) => void;
}) {
  const [values, setValues] = useState<Record<string, unknown>>(() =>
    Object.fromEntries(
      Object.entries(target.original).filter(([k]) => slots.has(k)),
    ),
  );
  const [nodes, setNodes] = useState<MappingNode[]>(() =>
    cleanNodes((target.original.nodes as MappingNode[] | undefined) ?? []),
  );
  const [display, setDisplay] = useState(() =>
    String(target.original.display_name ?? target.original.name ?? ""),
  );
  const [localError, setLocalError] = useState("");
  const set = (key: string, value: unknown) =>
    setValues((v) => ({ ...v, [key]: value }));
  const text = (key: string) => String(values[key] ?? "");
  const makeChange = (): SemanticChange => ({
    kind: target.kind,
    id: target.id,
    operation: target.operation,
    parent_id: target.parent_id,
    values: Object.fromEntries(
      Object.entries(values).filter(
        ([k, v]) =>
          !(["datatype", "dimension", "label"].includes(k) && v === null) &&
          (target.operation === "create" || !equal(target.original[k], v)),
      ),
    ),
    unset_fields: Object.keys(values).filter(
      (k) =>
        ["datatype", "dimension", "label"].includes(k) &&
        values[k] === null &&
        target.original[k] != null,
    ),
    ...(target.kind === "concept_mapping" ? { nodes: cleanNodes(nodes) } : {}),
    ...(display !==
      String(target.original.display_name ?? target.original.name ?? "") &&
    target.kind !== "concept_mapping"
      ? { display_name: display === text("name") ? "" : display }
      : {}),
  });
  const submit = () => {
    setLocalError("");
    if (target.kind !== "concept_mapping" && !text("name").trim()) {
      setLocalError("请填写名称");
      return;
    }
    onSubmit(makeChange());
  };
  const synonyms = contextSynonyms(values.ai_context);
  const updateSynonyms = (input: string) => {
    const old = values.ai_context;
    set("ai_context", {
      ...(old && typeof old === "object"
        ? old
        : typeof old === "string"
          ? { instructions: old }
          : {}),
      synonyms: lists(input),
    });
  };
  return (
    <div className="semantic-object-form">
      <fieldset disabled={busy}>
        <div className="semantic-columns">
          {target.kind !== "concept_mapping" && (
            <>
              <label>
                原生名称
                <input
                  required
                  aria-label="原生名称"
                  value={text("name")}
                  onChange={(e) => set("name", e.target.value)}
                />
              </label>
              <label>
                平台显示名
                <HintIcon text="仅写入 ONTOFOUNDRY 扩展；未配置时显示原生名称，不从说明推断。" />
                <input
                  aria-label="平台显示名"
                  value={display}
                  onChange={(e) => setDisplay(e.target.value)}
                />
              </label>
            </>
          )}
          {target.kind === "dataset" && (
            <>
              <label>
                物理来源
                <input
                  required
                  aria-label="物理来源"
                  value={text("source")}
                  placeholder="public.table_name"
                  onChange={(e) => set("source", e.target.value)}
                />
              </label>
              <label>
                主键
                <HintIcon text="按顺序填写字段名，多个字段用逗号分隔。" />
                <DelimitedInput
                  label="主键"
                  initial={((values.primary_key as string[]) ?? []).join(", ")}
                  onValue={(value) => set("primary_key", lists(value))}
                />
              </label>
            </>
          )}
          {(target.kind === "dataset_field" || target.kind === "metric") && (
            <label>
              数据类型
              <select
                aria-label="数据类型"
                value={text("datatype")}
                onChange={(e) => set("datatype", e.target.value || null)}
              >
                {[
                  "",
                  "String",
                  "Integer",
                  "Decimal",
                  "Float",
                  "Boolean",
                  "Date",
                  "Time",
                  "DateTime",
                  "DateTimeTz",
                  "Opaque",
                ].map((d) => (
                  <option key={d} value={d}>
                    {d || "未声明"}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        {!(
          ["concept_mapping", "dataset_relationship"] as SemanticKind[]
        ).includes(target.kind) && (
          <label>
            说明
            <textarea
              aria-label="说明"
              rows={3}
              value={text("description")}
              onChange={(e) => set("description", e.target.value)}
            />
          </label>
        )}
        {target.kind !== "concept_mapping" && (
          <label>
            同义词
            <DelimitedInput
              label="同义词"
              initial={synonyms.join(", ")}
              placeholder="用逗号分隔"
              onValue={updateSynonyms}
            />
          </label>
        )}
        {target.kind !== "concept_mapping" && (
          <label>
            AI 说明
            <HintIcon text="字符串 AIContext 保持字符串；对象中的 instructions 仅在明确编辑时更新，其他键与同义词保留。" />
            <textarea
              aria-label="AI 说明"
              rows={3}
              value={
                typeof values.ai_context === "string"
                  ? values.ai_context
                  : values.ai_context &&
                      typeof values.ai_context === "object" &&
                      "instructions" in values.ai_context
                    ? String(values.ai_context.instructions ?? "")
                    : ""
              }
              onChange={(e) => {
                const context = values.ai_context;
                set(
                  "ai_context",
                  typeof context === "string"
                    ? e.target.value
                    : {
                        ...(context && typeof context === "object"
                          ? context
                          : {}),
                        instructions: e.target.value,
                      },
                );
              }}
            />
          </label>
        )}
        {target.kind === "dataset" && (
          <label>
            唯一键组
            <DelimitedInput
              label="唯一键组"
              multiline
              initial={((values.unique_keys as string[][]) ?? [])
                .map((g) => g.join(", "))
                .join("\n")}
              placeholder="每行一组，组内用逗号分隔"
              onValue={(value) =>
                set("unique_keys", value.split("\n").filter(Boolean).map(lists))
              }
            />
          </label>
        )}
        {target.kind === "dataset_field" && (
          <div className="semantic-columns">
            <label>
              维度
              <select
                aria-label="维度"
                value={
                  values.dimension == null
                    ? "none"
                    : (values.dimension as { is_time?: boolean }).is_time ===
                        true
                      ? "time"
                      : (values.dimension as { is_time?: boolean }).is_time ===
                          false
                        ? "dimension"
                        : "declared"
                }
                onChange={(e) =>
                  set(
                    "dimension",
                    e.target.value === "none"
                      ? null
                      : e.target.value === "declared"
                        ? {}
                        : {
                            ...((values.dimension as object) ?? {}),
                            is_time: e.target.value === "time",
                          },
                  )
                }
              >
                <option value="none">未声明</option>
                <option value="declared">已声明（未指定时间角色）</option>
                <option value="dimension">普通维度</option>
                <option value="time">时间维度</option>
              </select>
            </label>
            <label>
              标签
              <input
                aria-label="字段标签"
                value={text("label")}
                onChange={(e) => set("label", e.target.value || null)}
              />
            </label>
          </div>
        )}
        {(target.kind === "dataset_field" || target.kind === "metric") && (
          <label>
            表达式
            <DialectEditor
              value={
                (values.expression as SemanticExpression) ?? {
                  dialects: [{ dialect: "ANSI_SQL", expression: "" }],
                }
              }
              onChange={(v) => set("expression", v)}
            />
          </label>
        )}
        {target.kind === "dataset_relationship" && (
          <JoinColumns
            model={model}
            value={{
              from: text("from"),
              to: text("to"),
              from_columns: (values.from_columns as string[]) ?? [""],
              to_columns: (values.to_columns as string[]) ?? [""],
            }}
            onChange={(patch) => setValues((v) => ({ ...v, ...patch }))}
          />
        )}
        {target.kind === "concept_mapping" && (
          <>
            <label>
              所属概念
              <select
                aria-label="所属概念"
                value={(values.concept_id as ConceptRef | undefined)?.ref ?? ""}
                onChange={(e) => {
                  const c = concepts.find((c) => c.id === e.target.value);
                  if (c)
                    set("concept_id", {
                      kind: c.kind ?? "object_type",
                      ref: c.id,
                    });
                }}
              >
                <option value="">选择概念</option>
                {concepts.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <MappingTreeEditor
              nodes={nodes}
              onChange={setNodes}
              concepts={concepts}
            />
          </>
        )}
        {target.kind === "semantic_model" && (
          <label>
            数据连接别名
            <input
              aria-label="数据连接别名"
              defaultValue={
                target.operation === "create"
                  ? ""
                  : (model.connection_alias ?? "")
              }
              onChange={(e) => {
                const extensions = [
                  ...((values.custom_extensions as {
                    vendor_name: string;
                    data: string;
                  }[]) ?? []),
                ];
                const i = extensions.findIndex(
                  (v) => v.vendor_name === "ONTOFOUNDRY",
                );
                let data: Record<string, unknown> = {};
                try {
                  data = i >= 0 ? JSON.parse(extensions[i].data) : {};
                } catch {
                  setLocalError(
                    "已有扩展不是 JSON，不能覆盖；请在高级扩展中处理",
                  );
                  return;
                }
                const extension = {
                  vendor_name: "ONTOFOUNDRY",
                  data: JSON.stringify({
                    ...data,
                    connection_alias: e.target.value,
                  }),
                };
                if (i >= 0) extensions[i] = extension;
                else extensions.push(extension);
                set("custom_extensions", extensions);
              }}
            />
          </label>
        )}
        {target.kind !== "concept_mapping" && (
          <details>
            <summary>
              执行参数与扩展
              <HintIcon text="快照参数写入 custom_extensions(ONTOFOUNDRY)：time_semantics 与 time_field。保留其他 vendor 的内容。" />
            </summary>
            <label>
              custom_extensions
              <textarea
                aria-label="执行参数与扩展"
                rows={4}
                defaultValue={JSON.stringify(
                  values.custom_extensions ?? [],
                  null,
                  2,
                )}
                onChange={(e) => {
                  try {
                    const v: unknown = JSON.parse(e.target.value);
                    if (!Array.isArray(v)) throw new Error();
                    if (!equal(v, values.custom_extensions ?? []))
                      set("custom_extensions", v);
                    setLocalError("");
                  } catch {
                    setLocalError("扩展必须是合法 JSON 数组");
                  }
                }}
              />
            </label>
          </details>
        )}
        {(localError || error) && (
          <p className="inline-error" role="alert">
            {localError || error}
          </p>
        )}
        <div className="semantic-form-footer">
          {onPreview && (
            <button
              type="button"
              disabled={!!localError}
              onClick={() => onPreview(makeChange())}
            >
              SQL 预览
            </button>
          )}
          <button
            type="button"
            className="button button--primary"
            disabled={!!localError}
            onClick={submit}
          >
            {busy ? "正在保存…" : submitLabel}
          </button>
        </div>
      </fieldset>
    </div>
  );
}
