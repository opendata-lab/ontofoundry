import { useMemo, useState } from "react";
import {
  type Condition, type FormState, type Kind, type SavedMetric, SAVED_METRICS,
  dateColumns, datasetOf, emptyForm, measureColumns, newConditionId, preview, referenceSql,
} from "./model";

/** Form state and derived values shared by all three prototypes. */
export function useMetricForm() {
  const [form, setForm] = useState<FormState>(emptyForm);
  const [metrics, setMetrics] = useState<SavedMetric[]>(SAVED_METRICS);

  const dataset = datasetOf(form.datasetId);
  const columns = measureColumns(dataset, form.kind);
  const dates = dateColumns(dataset);
  const sql = useMemo(() => referenceSql(form), [form]);
  const result = useMemo(() => preview(form), [form]);
  const components = metrics.filter(
    (m) => m.datasetId === form.datasetId && m.kind !== "ratio" && m.kind !== "expression",
  );

  const patch = (p: Partial<FormState>) => setForm((f) => ({ ...f, ...p }));

  const setDataset = (id: string | null) => {
    const ds = datasetOf(id);
    const cols = measureColumns(ds, form.kind);
    patch({
      datasetId: id,
      column: cols[0]?.name ?? null,
      conditions: [],
      timeField: dateColumns(ds)[0]?.name ?? null,
      numeratorId: null,
      denominatorId: null,
    });
  };

  const setKind = (kind: Kind) => {
    const cols = measureColumns(dataset, kind);
    patch({ kind, column: cols.some((c) => c.name === form.column) ? form.column : cols[0]?.name ?? null });
  };

  const addCondition = () =>
    patch({ conditions: [...form.conditions, { id: newConditionId(), column: dataset?.columns[0]?.name ?? "", operator: "eq", value: "" }] });
  const updateCondition = (id: string, p: Partial<Condition>) =>
    patch({ conditions: form.conditions.map((c) => (c.id === id ? { ...c, ...p } : c)) });
  const removeCondition = (id: string) => patch({ conditions: form.conditions.filter((c) => c.id !== id) });

  const addSynonym = (s: string) => {
    const v = s.trim();
    if (v && !form.synonyms.includes(v)) patch({ synonyms: [...form.synonyms, v] });
  };
  const removeSynonym = (s: string) => patch({ synonyms: form.synonyms.filter((x) => x !== s) });

  const metricById = (id: string | null) => metrics.find((m) => m.id === id) ?? null;

  const canSave = form.name.trim() !== "" && "sql" in sql;
  const save = () => {
    if (!canSave || !form.datasetId) return false;
    setMetrics((ms) => [
      ...ms,
      {
        id: `m${ms.length + 1}`,
        name: form.name.trim(),
        datasetId: form.datasetId!,
        kind: form.kind,
        column: form.column ?? undefined,
        timeField: form.kind === "ratio" ? undefined : form.timeField ?? undefined,
        description: form.description,
      },
    ]);
    setForm(emptyForm());
    return true;
  };
  const reset = () => setForm(emptyForm());

  return {
    form, patch, dataset, columns, dates, sql, result, components, metrics,
    setDataset, setKind, addCondition, updateCondition, removeCondition,
    addSynonym, removeSynonym, metricById, canSave, save, reset,
  };
}

export type MetricForm = ReturnType<typeof useMetricForm>;

/** Small monthly trend line drawn with currentColor so each library can tint it. */
export function Sparkline({ points, className }: { points: { month: string; value: number | null }[]; className?: string }) {
  const values = points.map((p) => p.value ?? 0);
  if (points.length < 2) return null;
  const w = 260, h = 64, pad = 6;
  const max = Math.max(...values), min = Math.min(...values);
  const span = max - min || 1;
  const xy = values.map((v, i) => [pad + (i * (w - 2 * pad)) / (values.length - 1), h - pad - ((v - min) / span) * (h - 2 * pad)]);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className={className} width={w} height={h} role="img" aria-label="按月趋势">
      <polyline points={xy.map((p) => p.join(",")).join(" ")} fill="none" stroke="currentColor" strokeWidth="2" />
      {xy.map(([x, y], i) => <circle key={points[i].month} cx={x} cy={y} r="3" fill="currentColor" />)}
    </svg>
  );
}
