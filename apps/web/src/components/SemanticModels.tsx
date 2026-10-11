import { useEffect, useState, type ReactNode } from "react";
import { workspaceRequest } from "../api/client";
import type { SemanticCatalog, SemanticDataset, SemanticExpression } from "../api/types";

function synonyms(context: unknown) {
  if (!context || typeof context !== "object" || !("synonyms" in context)) return "—";
  const values = (context as { synonyms?: unknown }).synonyms;
  return Array.isArray(values) ? values.filter((s): s is string => typeof s === "string").join("、") || "—" : "—";
}
function Expression({ value }: { value: SemanticExpression }) {
  return <>{value.dialects.map((d, i) => <pre key={i} style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{d.dialect}: {d.expression}</pre>)}</>;
}
function Pages<T>({ items, label, size = 10, render }: { items: T[]; label: string; size?: number; render: (item: T) => ReactNode }) {
  const [page, setPage] = useState(0);
  const current = Math.min(page, Math.max(0, Math.ceil(items.length / size) - 1));
  return <><p className="muted">{label}：{items.length} 项</p>{items.slice(current * size, (current + 1) * size).map(render)}{items.length > size && <div className="pagination" aria-label={label + "分页"}><button disabled={current === 0} onClick={() => setPage(current - 1)}>上一页</button><span>{current + 1} / {Math.ceil(items.length / size)}</span><button disabled={(current + 1) * size >= items.length} onClick={() => setPage(current + 1)}>下一页</button></div>}</>;
}
function Dataset({ dataset }: { dataset: SemanticDataset }) {
  const [open, setOpen] = useState(false);
  return <details onToggle={e => setOpen(e.currentTarget.open)}><summary>{dataset.name} · {dataset.fields.length} 字段</summary>{open && <><p>来源：{dataset.source}</p><p>主键：{dataset.primary_key.join("、") || "未声明"}</p>{dataset.unique_keys.length > 0 && <p>唯一键：{dataset.unique_keys.map(key => key.join(" + ")).join("；")}</p>}<p>{dataset.description}</p><p>同义词：{synonyms(dataset.ai_context)}</p><Pages items={dataset.fields} size={20} label={dataset.name + "字段"} render={field => <article className="element-section" key={field.id}><h4>{field.name} · {field.datatype ?? "未声明类型"}</h4><p>{field.description}</p><Expression value={field.expression} /><p>维度：{field.dimension ? field.dimension.is_time === true ? "时间维度" : field.dimension.is_time === false ? "非时间维度" : "已声明维度" : "未声明"} · 同义词：{synonyms(field.ai_context)}</p></article>} /></>}</details>;
}
function Model({ model }: { model: SemanticCatalog["items"][number] }) {
  const [open, setOpen] = useState(false);
  return <details onToggle={e => setOpen(e.currentTarget.open)}><summary>{model.name} · {model.datasets.length} 数据集 · {model.metrics.length} 指标</summary>{open && <><p>{model.description}</p><p>连接：{model.connection_alias ?? "暂不可查询"} · 同义词：{synonyms(model.ai_context)}</p><Pages items={model.datasets} label="数据集" render={d => <Dataset key={d.id} dataset={d} />} /><h3>数据集连接</h3><Pages items={model.relationships} size={20} label="连接" render={r => <article key={r.id}><h4>{r.name}</h4><p>{r.from} → {r.to}</p><ul>{r.from_columns.map((column, i) => <li key={i}>{column} = {r.to_columns[i]}</li>)}</ul></article>} /><h3>指标</h3><p className="muted">归属概念根据映射树引用及指标的数据集引用推导，可对应多个概念。</p><Pages items={model.metrics} label="指标" render={m => <article className="element-section" key={m.id}><h4>{m.name} · {m.datatype ?? "未声明类型"}</h4><p>{m.description}</p><p>同义词：{synonyms(m.ai_context)}</p><Expression value={m.expression} /><p>归属概念：{m.ambiguous && "（多个候选）"}{m.concepts.map(c => `${c.name} (${c.technical_name})`).join("、") || "无"}</p></article>} /></>}</details>;
}
export function SemanticCatalogView({ catalog }: { catalog: SemanticCatalog }) {
  return <section className="detail-section"><h2>语义模型 · 只读</h2>{catalog.items.length ? catalog.items.map(model => <Model key={model.id} model={model} />) : <p>暂无语义模型</p>}</section>;
}
export function SemanticModels({ workspaceId, sessionId }: { workspaceId: string; sessionId: string | null }) {
  const [catalog, setCatalog] = useState<SemanticCatalog | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    workspaceRequest<SemanticCatalog>(workspaceId, "/semantic-models" + (sessionId ? "?session_id=" + encodeURIComponent(sessionId) : ""))
      .then(value => { if (active) { setCatalog(value); setError(""); } })
      .catch((e: Error) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [workspaceId, sessionId]);
  return error ? <p className="inline-error">{error}</p> : catalog ? <SemanticCatalogView catalog={catalog} /> : <p>正在读取语义模型…</p>;
}
