import "./shadcn.css";
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { Info, Plus, Trash2, TriangleAlert, X } from "lucide-react";
import { DATASETS, KINDS, OPERATORS, datasetOf, formatNumber, kindLabel } from "../shared/model";
import { Sparkline, useMetricForm } from "../shared/useMetricForm";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Combobox } from "./ui/combobox";
import { Input, Textarea } from "./ui/input";
import { Field } from "./ui/label";
import { Select } from "./ui/select";
import { Sheet } from "./ui/sheet";
import { Segmented } from "./ui/toggle-group";

const Section = ({ title, children }: { title: string; children: React.ReactNode }) => (
  <section className="flex flex-col gap-4 border-b border-rule-soft py-5 first:pt-0 last:border-0">
    <h3 className="text-sm font-semibold text-ink">{title}</h3>
    {children}
  </section>
);

function SynonymInput({ values, onAdd, onRemove }: { values: string[]; onAdd: (s: string) => void; onRemove: (s: string) => void }) {
  const [draft, setDraft] = useState("");
  return (
    <div className="flex min-h-9 flex-wrap items-center gap-1 rounded-sm border border-rule bg-surface px-2 py-1 focus-within:border-accent focus-within:ring-3 focus-within:ring-accent/15">
      {values.map((v) => (
        <Badge key={v}>{v}<button onClick={() => onRemove(v)} aria-label={`删除 ${v}`} className="text-muted hover:text-ink"><X size={12} /></button></Badge>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); onAdd(draft); setDraft(""); } }}
        placeholder={values.length ? "" : "输入后回车"}
        className="h-7 min-w-24 flex-1 bg-transparent text-sm outline-none"
      />
    </div>
  );
}

function App() {
  const m = useMetricForm();
  const [open, setOpen] = useState(false);
  const { form } = m;
  const showColumn = form.kind !== "count" && form.kind !== "ratio" && form.kind !== "expression";

  return (
    <div className="mx-auto max-w-[1180px] p-6">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">语义视图 · 指标</h1>
          <p className="text-sm text-muted">shadcn/ui（Radix）+ Tailwind v4</p>
        </div>
        <Button variant="primary" onClick={() => setOpen(true)}><Plus size={16} />新建指标</Button>
      </header>

      <div className="overflow-hidden rounded-md border border-rule bg-surface">
        <table className="w-full text-sm">
          <thead className="bg-surface-soft text-left text-xs text-muted">
            <tr>{["指标", "数据集", "计算方式", "列", "时间字段", "说明"].map((h) => <th key={h} className="px-4 py-2.5 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {m.metrics.map((x) => (
              <tr key={x.id} className="border-t border-rule-soft hover:bg-surface-soft/60">
                <td className="px-4 py-2.5 font-medium">{x.name}</td>
                <td className="px-4 py-2.5">{datasetOf(x.datasetId)?.name}</td>
                <td className="px-4 py-2.5"><Badge>{kindLabel(x.kind)}</Badge></td>
                <td className="px-4 py-2.5 font-mono text-xs">{x.column ?? "—"}</td>
                <td className="px-4 py-2.5">{x.timeField ?? "不按时间"}</td>
                <td className="max-w-[260px] truncate px-4 py-2.5 text-muted">{x.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Sheet
        open={open}
        onOpenChange={setOpen}
        title="新建指标"
        footer={<>
          <Button onClick={() => { m.reset(); setOpen(false); }}>取消</Button>
          <Button variant="primary" disabled={!m.canSave} onClick={() => m.save() && setOpen(false)}>保存为提案</Button>
        </>}
      >
        <Section title="基本信息">
          <div className="grid grid-cols-2 gap-4">
            <Field label="名称" required>
              <Input value={form.name} onChange={(e) => m.patch({ name: e.target.value })} placeholder="例如：已完成订单金额" />
            </Field>
            <Field label="同义词">
              <SynonymInput values={form.synonyms} onAdd={m.addSynonym} onRemove={m.removeSynonym} />
            </Field>
          </div>
          <Field label="说明">
            <Textarea rows={2} value={form.description} onChange={(e) => m.patch({ description: e.target.value })} />
          </Field>
        </Section>

        <Section title="数据集与算法">
          <Field label="数据集" required hint={m.dataset && (
            <>{m.dataset.rowMeaning}{m.dataset.snapshotColumn && <Badge className="ml-2 border-accent/30 bg-accent-soft text-accent">每日快照 · {m.dataset.snapshotColumn}</Badge>}</>
          )}>
            <Combobox
              value={form.datasetId}
              onChange={m.setDataset}
              placeholder="选择数据集"
              searchPlaceholder="搜索名称或表名"
              options={DATASETS.map((d) => ({ value: d.id, label: d.name, hint: `${d.table} · ${d.rowMeaning}` }))}
            />
          </Field>
          <Field label="计算方式" required>
            <Segmented value={form.kind} onChange={(v) => m.setKind(v as typeof form.kind)} options={KINDS.map((k) => ({ value: k.id, label: k.label }))} />
          </Field>
          {showColumn && (
            <Field label="列" required>
              <Select value={form.column} onChange={(v) => m.patch({ column: v })}
                options={m.columns.map((c) => ({ value: c.name, label: `${c.comment}（${c.name}）` }))} />
            </Field>
          )}
          {form.kind === "ratio" && (
            <div className="grid grid-cols-2 gap-4">
              {(["numeratorId", "denominatorId"] as const).map((key) => {
                const picked = m.metricById(form[key]);
                return (
                  <Field key={key} label={key === "numeratorId" ? "分子" : "分母"} required hint={picked && `时间口径：${picked.timeField ?? "不按时间"}`}>
                    <Select value={form[key]} onChange={(v) => m.patch({ [key]: v })} placeholder="选择同一数据集上的指标"
                      options={m.components.map((x) => ({ value: x.id, label: x.name }))} />
                  </Field>
                );
              })}
            </div>
          )}
          {form.kind === "expression" && (
            <Field label="表达式" required hint="只能引用所选数据集的列">
              <Textarea rows={3} className="font-mono" value={form.expression} onChange={(e) => m.patch({ expression: e.target.value })}
                placeholder="SUM(CASE WHEN status = '已完成' THEN amount END)" />
            </Field>
          )}
        </Section>

        {form.kind !== "ratio" && (
          <Section title="条件">
            {form.conditions.length === 0 && <p className="text-sm text-muted">没有条件，统计全部行</p>}
            {form.conditions.map((c) => (
              <div key={c.id} className="grid grid-cols-[180px_120px_1fr_36px] gap-2">
                <Select value={c.column} onChange={(v) => m.updateCondition(c.id, { column: v ?? "" })}
                  options={(m.dataset?.columns ?? []).map((col) => ({ value: col.name, label: col.comment }))} />
                <Select value={c.operator} onChange={(v) => m.updateCondition(c.id, { operator: v as typeof c.operator })}
                  options={OPERATORS.map((o) => ({ value: o.id, label: o.label }))} />
                <Input value={c.value} disabled={c.operator === "is_null" || c.operator === "not_null"}
                  onChange={(e) => m.updateCondition(c.id, { value: e.target.value })}
                  placeholder={c.operator === "in" ? "多个值用逗号分隔" : c.operator === "between" ? "起, 止" : "值"} />
                <Button size="icon" variant="ghost" onClick={() => m.removeCondition(c.id)} aria-label="删除条件"><Trash2 size={15} /></Button>
              </div>
            ))}
            <Button variant="dashed" size="sm" className="self-start" onClick={m.addCondition}><Plus size={15} />添加条件</Button>
          </Section>
        )}

        {form.kind !== "ratio" && (
          <Section title="时间">
            <Field label="时间字段" hint={m.dataset?.snapshotColumn
              ? `该数据集是每日快照：按 ${m.dataset.snapshotColumn} 时每个周期取最后一天；选其他字段或不选时只取最新一天`
              : "决定按哪个日期把数据归到周期；不选则不按时间"}>
              <Select allowClear clearLabel="不按时间" value={form.timeField} onChange={(v) => m.patch({ timeField: v })}
                options={m.dates.map((c) => ({ value: c.name, label: `${c.comment}（${c.name}）` }))} />
            </Field>
          </Section>
        )}

        <Section title="SQL 参考">
          {"sql" in m.sql
            ? <pre className="overflow-auto rounded-md bg-surface-soft p-3 font-mono text-[13px] leading-5">{m.sql.sql}</pre>
            : <p className="flex items-center gap-2 rounded-md bg-accent-soft px-3 py-2 text-sm text-accent"><Info size={15} />{m.sql.reason}</p>}
        </Section>

        <Section title="数值预览">
          {m.result.ok ? (
            <div className="flex items-center gap-8 rounded-md border border-rule p-4">
              <div>
                <div className="text-xs text-muted">{form.timeField ? "全部周期" : "当前值"}</div>
                <div className="text-3xl font-semibold">{formatNumber(m.result.total)}</div>
              </div>
              {m.result.trend && m.result.trend.length > 1 ? (
                <div className="text-accent">
                  <Sparkline points={m.result.trend} />
                  <div className="flex justify-between text-xs text-muted">
                    {m.result.trend.map((p) => <span key={p.month}>{p.month.slice(5)}月 {formatNumber(p.value)}</span>)}
                  </div>
                </div>
              ) : <p className="text-sm text-muted">选择时间字段后显示按月趋势</p>}
            </div>
          ) : (
            <p className="flex items-center gap-2 rounded-md bg-[#fff7e6] px-3 py-2 text-sm text-[#ad6800]"><TriangleAlert size={15} />无法预览：{m.result.reason}</p>
          )}
        </Section>
      </Sheet>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
