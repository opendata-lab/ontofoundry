import { RelationshipRoles } from "../RelationshipRoles";
import { relationReadOnly } from "../../lib/nativeDraft";
import {
  ArrowRight,
  Box,
  Check,
  Database,
  FileText,
  Info,
  Plus,
  Trash2,
} from "lucide-react";
import type { ReactNode } from "react";
import { useState } from "react";
import type {
  LegacyDraft,
  Evidence,
  PropertyElement,
  RuleElement,
} from "../../api/types";
import { workspaceRequest } from "../../api/client";
import { toView } from "../../lib/draftView";
import { MappingForm } from "../MappingForm";
import { TagList } from "../TagList";
import { TagEditor } from "../TagEditor";
import {
  changeType,
  inheritedProperties,
  isObject,
  rulesFor,
  VALUE_KINDS,
  MULTIPLICITY,
  type ElementType,
  type PanelProps,
} from "../../lib/elementModel";

export function EvidenceSection({
  workspaceId,
  evidence,
}: {
  workspaceId: string;
  evidence: Evidence[];
}) {
  if (!evidence.length) return null;
  return (
    <section className="element-section element-evidence">
      <h3>来源证据</h3>
      {evidence.map((ev) => (
        <div className="element-evidence-row" key={ev.id}>
          {ev.kind === "material" ? (
            <>
              <a
                href={`/api/v1/workspaces/${workspaceId}/materials/${encodeURIComponent(ev.material_id)}`}
                target="_blank"
                rel="noreferrer"
              >
                <FileText size={18} />
                <span>
                  查看来源材料 · {ev.locator.line_start}–{ev.locator.line_end}{" "}
                  行
                </span>
              </a>
              <blockquote>“{ev.quote}”</blockquote>
            </>
          ) : (
            <>
              <FileText size={18} />
              <span>{ev.note}</span>
            </>
          )}
        </div>
      ))}
    </section>
  );
}
export function Field({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <label className="element-field">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function BasicPanel(props: PanelProps) {
  const { type, draft, editing, open } = props;
  const update = (patch: Partial<ElementType>) => changeType(props, patch);
  return (
    <section className="element-section">
      <h3>基本信息</h3>
      <div className="element-basic-grid">
        <Field label="名称">
          {editing ? (
            <input
              required
              maxLength={240}
              value={type.name}
              onChange={(e) => update({ name: e.target.value })}
            />
          ) : (
            <span className="element-value">{type.name}</span>
          )}
        </Field>
        <Field label="英文名称">
          {editing ? (
            <input
              required
              pattern="[A-Za-z_][A-Za-z0-9_]*"
              value={type.technical_name}
              onChange={(e) => update({ technical_name: e.target.value })}
            />
          ) : (
            <span className="element-value">{type.technical_name}</span>
          )}
        </Field>
        <div className="element-field">
          <span>标签</span>
          {editing ? (
            <TagEditor key={type.id} tags={type.tags} onChange={(tags) => update({ tags })} />
          ) : (
            <TagList tags={type.tags} />
          )}
        </div>
        {isObject(type) && (
          <div className="element-field">
            <span>继承自</span>
            {editing ? (
              <select
                aria-label="继承自"
                value={type.extends[0] ?? ""}
                onChange={(e) => update({ extends: e.target.value ? [e.target.value] : [] })}
              >
                <option value="">无</option>
                {draft.object_types
                  .filter((t) => t.id !== type.id)
                  .map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
              </select>
            ) : (
              <span className="element-value">
                {type.extends.length
                  ? type.extends.map((id) => (
                      <button
                        className="element-text-button"
                        type="button"
                        key={id}
                        onClick={() => open({ kind: "object_type", id })}
                      >
                        {draft.object_types.find((t) => t.id === id)?.name ??
                          id}
                      </button>
                    ))
                  : "无"}
              </span>
            )}
          </div>
        )}
        <div className="element-field-wide">
          <Field label="描述">
            {editing ? (
              <textarea
                maxLength={4000}
                rows={4}
                value={type.description}
                placeholder="描述这个对象或关系"
                onChange={(e) => update({ description: e.target.value })}
              />
            ) : (
              <span className="element-value">
                {type.description || "尚未填写描述"}
              </span>
            )}
          </Field>
        </div>
      </div>
    </section>
  );
}
export function PropertiesPanel(props: PanelProps) {
  const { draft, type, editing, change, open } = props;
  if (!isObject(type)) return null;
  const properties = draft.properties.filter(
    (p) => p.owner_type_id === type.id,
  );
  const inherited = inheritedProperties(draft, type);
  const update = (id: string, patch: Partial<PropertyElement>) =>
    change({
      ...draft,
      properties: draft.properties.map((p) =>
        p.id === id ? { ...p, ...patch } : p,
      ),
    });
  const mark = (yes: boolean) =>
    yes ? (
      <span className="element-check">
        <Check size={12} strokeWidth={3} />
      </span>
    ) : (
      <span className="muted">—</span>
    );
  return (
    <>
      <section className="element-section">
        <div className="element-section-title">
          <h3>属性定义</h3>
          <span className="muted">
            本地 {properties.length} · 继承 {inherited.length}
          </span>
          {editing && (
            <button
              className="element-text-button"
              type="button"
              onClick={() =>
                change({
                  ...draft,
                  properties: [
                    ...draft.properties,
                    {
                      id: crypto.randomUUID(),
                      owner_type_id: type.id,
                      name: "",
                      technical_name: "",
                      description: "",
                      value_kind: "string",
                      required: false,
                      identifier: false,
                      verbalizes: [],
                      evidence: [],
                    },
                  ],
                })
              }
            >
              <Plus size={14} />
              新增属性
            </button>
          )}
        </div>
        <div className="element-table-wrap">
          <table className="element-table">
            <thead>
              <tr>
                <th>名称</th>
                <th>英文名称</th>
                <th>类型</th>
                <th>标识</th>
                <th>必填</th>
                <th>来源</th>
                {editing && <th />}
              </tr>
            </thead>
            <tbody>
              {properties.map((p, i) => (
                <tr key={p.id} data-element-id={p.id}>
                  <td>
                    {editing ? (
                      <input
                        aria-label={`属性名称 ${i + 1}`}
                        required
                        value={p.name}
                        onChange={(e) => update(p.id, { name: e.target.value })}
                      />
                    ) : (
                      p.name
                    )}
                  </td>
                  <td>
                    {editing ? (
                      <input
                        aria-label={`属性英文名称 ${i + 1}`}
                        required
                        value={p.technical_name}
                        pattern="[A-Za-z_][A-Za-z0-9_]*"
                        onChange={(e) => {
                          const nextName = e.target.value;
                          const mappings = draft.mappings.map((m) => {
                            if (
                              m.type_id !== type.id ||
                              !(p.technical_name in m.fields)
                            )
                              return m;
                            const fields = { ...m.fields };
                            const column = fields[p.technical_name];
                            delete fields[p.technical_name];
                            if (nextName) fields[nextName] = column;
                            return { ...m, fields };
                          });
                          change({
                            ...draft,
                            mappings,
                            properties: draft.properties.map((item) =>
                              item.id === p.id
                                ? { ...item, technical_name: nextName }
                                : item,
                            ),
                          });
                        }}
                      />
                    ) : (
                      p.technical_name
                    )}
                  </td>
                  <td>
                    {editing ? (
                      <select
                        aria-label={`属性类型 ${i + 1}`}
                        value={p.value_kind}
                        onChange={(e) =>
                          update(p.id, { value_kind: e.target.value })
                        }
                      >
                        {Object.entries(VALUE_KINDS).map(([k, v]) => (
                          <option value={k} key={k}>
                            {v}
                          </option>
                        ))}
                      </select>
                    ) : (
                      (VALUE_KINDS[p.value_kind] ?? p.value_kind)
                    )}
                  </td>
                  <td>
                    {editing ? (
                      <input
                        type="checkbox"
                        aria-label={`标识属性 ${i + 1}`}
                        checked={p.identifier}
                        onChange={(e) =>
                          update(p.id, { identifier: e.target.checked })
                        }
                      />
                    ) : (
                      mark(p.identifier)
                    )}
                  </td>
                  <td>
                    {editing ? (
                      <input
                        type="checkbox"
                        aria-label={`必填属性 ${i + 1}`}
                        checked={p.required}
                        onChange={(e) =>
                          update(p.id, { required: e.target.checked })
                        }
                      />
                    ) : (
                      mark(p.required)
                    )}
                  </td>
                  <td>本地</td>
                  {editing && (
                    <td>
                      <button
                        className="icon-button"
                        type="button"
                        aria-label={`删除属性 ${p.name || i + 1}`}
                        onClick={() => {
                          const mappings = draft.mappings.map((m) => {
                            if (m.type_id !== type.id) return m;
                            const fields = { ...m.fields };
                            delete fields[p.technical_name];
                            return { ...m, fields };
                          });
                          change({
                            ...draft,
                            mappings,
                            properties: draft.properties.filter(
                              (item) => item.id !== p.id,
                            ),
                            rules: draft.rules.filter(
                              (r) =>
                                !(
                                  r.owner_kind === "property" &&
                                  r.owner_id === p.id
                                ),
                            ),
                          });
                        }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
              {inherited.map(({ property: p, owner }) => (
                <tr key={p.id}>
                  <td>{p.name}</td>
                  <td>{p.technical_name}</td>
                  <td>{VALUE_KINDS[p.value_kind] ?? p.value_kind}</td>
                  <td>{mark(p.identifier)}</td>
                  <td>{mark(p.required)}</td>
                  <td>
                    <button
                      type="button"
                      className="element-inherited"
                      onClick={() =>
                        open({
                          kind: "object_type",
                          id: owner.id,
                          tab: "properties",
                        })
                      }
                    >
                      继承自{owner.name}
                    </button>
                  </td>
                  {editing && <td />}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!properties.length && !inherited.length && (
          <p className="element-empty">
            暂无属性{editing ? "，点击新增属性定义数据结构。" : "。"}
          </p>
        )}
        {!!inherited.length && (
          <div className="element-info">
            <Info size={16} />
            <span>继承属性由所属对象类型维护</span>
            <button
              type="button"
              className="element-text-button"
              onClick={() =>
                open({
                  kind: "object_type",
                  id: inherited[0].owner.id,
                  tab: "properties",
                })
              }
            >
              查看{inherited[0].owner.name}
            </button>
          </div>
        )}
      </section>
      <EvidenceSection
        workspaceId={draft.workspace_id}
        evidence={type.evidence}
      />
    </>
  );
}
export function EndpointsPanel(props: PanelProps) {
  const { type, draft, editing, open } = props;
  if (isObject(type)) return null;
  if (relationReadOnly(type)) return <section className="element-section"><RelationshipRoles link={type} /><p className="muted">暂只读</p></section>;
  return (
    <section className="element-section">
      <h3>关系端点</h3>
      <div className="element-endpoints">
        {(["source_type_id", "target_type_id"] as const).map((key, i) => (
          <div className="element-endpoint-group" key={key}>
            {i === 1 && (
              <div className="element-endpoint-arrow">
                <span>{type.name}</span>
                <svg
                  width="104"
                  height="36"
                  viewBox="0 0 104 36"
                  fill="none"
                  stroke="currentColor"
                  aria-hidden="true"
                >
                  <path d="M2 18H100M94 12L100 18L94 24" />
                </svg>
              </div>
            )}
            <div className="element-endpoint">
              <Box size={32} strokeWidth={1.8} />
              <Field label={i ? "目标对象" : "源对象"}>
                {editing ? (
                  <select
                    required
                    value={type[key]}
                    onChange={(e) =>
                      changeType(props, { [key]: e.target.value })
                    }
                  >
                    <option value="">请选择对象</option>
                    {draft.object_types.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                ) : (
                  <button
                    type="button"
                    className="element-endpoint-value"
                    aria-label={`${i ? "目标" : "源"}对象：${draft.object_types.find((t) => t.id === type[key])?.name ?? "未指定"}`}
                    onClick={() => open({ kind: "object_type", id: type[key] })}
                  >
                    {draft.object_types.find((t) => t.id === type[key])?.name ??
                      "未指定"}
                  </button>
                )}
              </Field>
            </div>
          </div>
        ))}
      </div>
      <Field label="关系基数">
        {editing ? (
          <select
            value={type.multiplicity}
            onChange={(e) =>
              changeType(props, { multiplicity: e.target.value })
            }
          >
            {Object.entries(MULTIPLICITY).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        ) : (
          <span className="element-value">
            {MULTIPLICITY[type.multiplicity] ?? type.multiplicity}
          </span>
        )}
      </Field>
      <label className="element-checkbox">
        <input
          type="checkbox"
          checked={!!type.identifier}
          disabled={!editing}
          onChange={(e) => changeType(props, { identifier: e.target.checked })}
        />
        此关系用作标识
      </label>
      <p className="element-note">
        <Info size={15} />
        修改端点会影响关系映射与实例引用。
      </p>
    </section>
  );
}
export function MappingPanel(
  props: PanelProps & {
    suggestedSource?: {
      connection_alias: string;
      table_name: string;
      schema_name: string | null;
    };
  },
) {
  const { draft, type, editing, change, suggestedSource } = props;
  const mapping = draft.mappings.find((m) => m.type_id === type.id);
  if (isObject(type)) {
    const object = toView(draft).object_types.find((t) => t.id === type.id)!;
    if (editing)
      return (
        <>
          <MappingForm
            workspaceId={draft.workspace_id}
            type={object}
            mapping={mapping}
            suggestedSource={suggestedSource}
            onChange={(value) =>
              change({
                ...draft,
                mappings: [
                  ...draft.mappings.filter((m) => m.type_id !== type.id),
                  value,
                ],
              })
            }
          />
          <MappingPreview draft={draft} type={type} showSource={false} />
        </>
      );
    return (
      <>
        <section className="element-section">
          <h3>数据映射</h3>
          {mapping ? (
            <>
              <div className="element-source">
                <Database size={22} />
                <div>
                  <strong>
                    {mapping.schema_name ? `${mapping.schema_name}.` : ""}
                    {mapping.table_name}
                  </strong>
                  <span>
                    {mapping.connection_alias} · 标识字段 {mapping.key_column}
                  </span>
                </div>
              </div>
              <table className="element-table">
                <thead>
                  <tr>
                    <th>本体属性</th>
                    <th>数据字段</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(mapping.fields).map(([name, column]) => (
                    <tr key={name}>
                      <td>
                        {object.attributes.find(
                          (p) => p.technical_name === name,
                        )?.name ?? name}
                        <small>{name}</small>
                      </td>
                      <td>{column}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <p className="element-empty">
              暂无映射，点击右上角“编辑”配置数据表和属性映射。
            </p>
          )}
        </section>
        <MappingPreview draft={draft} type={type} showSource={false} />
      </>
    );
  }
  return (
    <>
      <section className="element-section">
        <h3>关系映射</h3>
        <p className="element-note">
          根据两端对象的数据映射，按字段相等查找关系。
        </p>
        <label className="element-checkbox">
          <input
            type="checkbox"
            checked={!!type.data_join}
            disabled={!editing}
            onChange={(e) =>
              changeType(props, {
                data_join: e.target.checked
                  ? { source_column: "", target_column: "" }
                  : null,
              })
            }
          />
          配置字段关联
        </label>
        {type.data_join ? (
          <div className="element-basic-grid">
            {(["source", "target"] as const).map((side) => {
              const m = draft.mappings.find(
                (m) => m.type_id === type[`${side}_type_id`],
              );
              return (
                <Field
                  key={side}
                  label={`${side === "source" ? "源" : "目标"}字段 · ${m?.table_name ?? "尚未配置对象映射"}`}
                >
                  {editing ? (
                    <input
                      required
                      list={`element-join-${side}`}
                      value={type.data_join![`${side}_column`]}
                      onChange={(e) =>
                        changeType(props, {
                          data_join: {
                            ...type.data_join!,
                            [`${side}_column`]: e.target.value,
                          },
                        })
                      }
                    />
                  ) : (
                    <span className="element-value">
                      {type.data_join![`${side}_column`]}
                    </span>
                  )}
                  <datalist id={`element-join-${side}`}>
                    {[
                      ...new Set(
                        m ? [m.key_column, ...Object.values(m.fields)] : [],
                      ),
                    ].map((c) => (
                      <option key={c} value={c} />
                    ))}
                  </datalist>
                </Field>
              );
            })}
          </div>
        ) : (
          <p className="element-empty">尚未配置关系映射。</p>
        )}
        <p className="element-note">
          <Info size={15} />
          两端数据须来自同一数据源，跨数据源关系暂不可查询。
        </p>
      </section>
      <MappingPreview draft={draft} type={type} />
    </>
  );
}
export function DataSample({
  workspaceId,
  mapping,
  showSource = true,
}: {
  workspaceId: string;
  mapping: LegacyDraft["mappings"][number];
  showSource?: boolean;
}) {
  const [rows, setRows] = useState<Record<string, unknown>[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const preview = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await workspaceRequest<{
        items: Record<string, unknown>[];
      }>(workspaceId, "/mapping-preview", { mapping, limit: 10 });
      setRows(result.items);
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取失败");
    } finally {
      setBusy(false);
    }
  };
  const columns = rows?.length
    ? Object.keys(rows[0]).filter((k) => k !== "__key")
    : [];
  return (
    <div className="element-sample">
      <div className={showSource ? "element-source" : "element-section-title"}>
        {showSource && (
          <>
            <Database size={22} />
            <div>
              <strong>
                {mapping.schema_name ? `${mapping.schema_name}.` : ""}
                {mapping.table_name}
              </strong>
              <span>{mapping.connection_alias}</span>
            </div>
          </>
        )}
        <button
          type="button"
          className="button button--secondary"
          disabled={busy || !mapping.key_column}
          onClick={() => void preview()}
        >
          {busy ? "正在读取…" : "预览数据"}
        </button>
      </div>
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      {rows && (
        <div className="element-table-wrap">
          <table className="element-table">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c}>{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr key={i}>
                  {columns.map((c) => (
                    <td key={c}>{String(row[c] ?? "—")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {!rows.length && <p className="element-empty">暂无数据。</p>}
        </div>
      )}
    </div>
  );
}
function MappingPreview({
  draft,
  type,
  showSource = true,
}: Pick<PanelProps, "draft" | "type"> & { showSource?: boolean }) {
  const ids = isObject(type)
    ? [type.id]
    : [type.source_type_id, type.target_type_id];
  const mappings = draft.mappings.filter((m) => ids.includes(m.type_id));
  if (!mappings.length) return null;
  return (
    <section className="element-section">
      <h3>{isObject(type) ? "数据预览" : "端点数据预览"}</h3>
      {mappings.map((m) => (
        <DataSample
          key={JSON.stringify(m)}
          workspaceId={draft.workspace_id}
          mapping={m}
          showSource={showSource}
        />
      ))}
      <p className="element-note">
        按需读取最多 10 条映射结果；查看全部实例请切换到“实例”。
      </p>
    </section>
  );
}
export function RelationsPanel({ draft, type, editing, open }: PanelProps) {
  const relations = draft.link_types.filter(
    (r) => r.source_type_id === type.id || r.target_type_id === type.id,
  );
  return (
    <section className="element-section">
      <div className="element-section-title">
        <h3>关联关系</h3>
        {editing && (
          <button
            type="button"
            className="element-text-button"
            onClick={() => open({ kind: "link_type", id: "new", mode: "edit" })}
          >
            <Plus size={14} />
            新增关系
          </button>
        )}
      </div>
      {relations.length ? (
        relations.map((r) => (
          <button
            key={r.id}
            type="button"
            className="element-relation-row"
            onClick={() =>
              open({ kind: "link_type", id: r.id, tab: "endpoints" })
            }
          >
            <strong>{r.name}</strong>
            <span>
              {draft.object_types.find((t) => t.id === r.source_type_id)?.name}{" "}
              <ArrowRight size={14} />{" "}
              {draft.object_types.find((t) => t.id === r.target_type_id)?.name}
            </span>
          </button>
        ))
      ) : (
        <p className="element-empty">暂无关联关系。</p>
      )}
    </section>
  );
}
export function RulesPanel({ draft, type, editing, change }: PanelProps) {
  const rules = rulesFor(draft, type);
  const owners = [
    {
      kind: isObject(type) ? "object_type" : "link_type",
      id: type.id,
      name: type.name,
    },
    ...draft.properties
      .filter((p) => p.owner_type_id === type.id)
      .map((p) => ({ kind: "property", id: p.id, name: p.name })),
    ...draft.actions
      .filter((a) => a.input_type_id === type.id)
      .map((a) => ({ kind: "action", id: a.id, name: a.name })),
  ];
  const update = (id: string, patch: Partial<RuleElement>) =>
    change({
      ...draft,
      rules: draft.rules.map((r) => (r.id === id ? { ...r, ...patch } : r)),
    });
  return (
    <section className="element-section">
      <div className="element-section-title">
        <h3>规则</h3>
        {editing && (
          <button
            className="element-text-button"
            type="button"
            onClick={() => {
              const id = crypto.randomUUID();
              change({
                ...draft,
                rules: [
                  ...draft.rules,
                  {
                    id,
                    name: "新规则",
                    technical_name: `rule_${id.replaceAll("-", "").slice(0, 8)}`,
                    description: "",
                    owner_kind: isObject(type) ? "object_type" : "link_type",
                    owner_id: type.id,
                    rule_kind: "constraint",
                    expression: "",
                    verbalizes: [],
                    evidence: [],
                  },
                ],
              });
            }}
          >
            <Plus size={14} />
            新增规则
          </button>
        )}
      </div>
      {rules.map((r) => (
        <div className="element-rule" key={r.id} data-element-id={r.id}>
          <div className="element-section-title">
            {editing ? (
              <input
                aria-label="规则名称"
                value={r.name}
                onChange={(e) => update(r.id, { name: e.target.value })}
              />
            ) : (
              <strong>{r.name}</strong>
            )}
            <span className="element-pill">
              {r.rule_kind === "constraint" ? "约束" : "派生"}
            </span>
            {editing && (
              <button
                className="icon-button"
                type="button"
                aria-label={`删除规则 ${r.name}`}
                onClick={() =>
                  change({
                    ...draft,
                    rules: draft.rules.filter((item) => item.id !== r.id),
                  })
                }
              >
                <Trash2 size={14} />
              </button>
            )}
          </div>
          {editing && (
            <div className="element-basic-grid">
              <Field label="所属元素">
                <select
                  value={`${r.owner_kind}:${r.owner_id}`}
                  onChange={(e) => {
                    const owner = owners.find(
                      (o) => `${o.kind}:${o.id}` === e.target.value,
                    )!;
                    update(r.id, {
                      owner_kind: owner.kind as RuleElement["owner_kind"],
                      owner_id: owner.id,
                    });
                  }}
                >
                  {owners.map((o) => (
                    <option
                      key={`${o.kind}:${o.id}`}
                      value={`${o.kind}:${o.id}`}
                    >
                      {o.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="规则类型">
                <select
                  value={r.rule_kind}
                  onChange={(e) =>
                    update(r.id, {
                      rule_kind: e.target.value as RuleElement["rule_kind"],
                    })
                  }
                >
                  <option value="constraint">约束</option>
                  <option value="derivation">派生</option>
                </select>
              </Field>
            </div>
          )}
          {editing ? (
            <Field label="表达式">
              <textarea
                required
                rows={2}
                value={r.expression}
                onChange={(e) => update(r.id, { expression: e.target.value })}
              />
            </Field>
          ) : (
            <>
              <span className="muted">
                {
                  owners.find(
                    (o) => o.kind === r.owner_kind && o.id === r.owner_id,
                  )?.name
                }
              </span>
              <code>{r.expression}</code>
            </>
          )}
        </div>
      ))}
      {!rules.length && <p className="element-empty">暂无规则。</p>}
      <p className="element-note">规则用于模型校验与定义，当前不执行推理。</p>
    </section>
  );
}
