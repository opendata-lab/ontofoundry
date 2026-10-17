// Pure helpers for the metric form: switching kinds, removing read-only
// fields before saving, checking a definition, and building a preview request.
import type {
  Condition,
  Draft,
  Metric,
  MetricPreviewRequest,
  RatioMetric,
  SimpleMetric,
  UUID,
  Scalar,
  ValueKind,
} from "../api/types";
import { NUMERIC_KINDS, byId, isRatio, isSimple, physicalValueKind, ratioComponents } from "./coreModel";
import { isEmptyConditionValue, operatorArity } from "./derivedEditing";

export const METRIC_KINDS: Record<Metric["kind"], string> = {
  simple: "聚合",
  ratio: "比率",
  expression: "表达式",
};

type Common = Pick<Metric, "id" | "name" | "technical_name" | "description" | "synonyms" | "evidence">;

function common(metric: Common): Common {
  return {
    id: metric.id,
    name: metric.name,
    technical_name: metric.technical_name,
    description: metric.description,
    synonyms: metric.synonyms,
    evidence: metric.evidence,
  };
}

export function newMetric(id: UUID, datasetId: UUID | null): SimpleMetric {
  return {
    id,
    kind: "simple",
    name: "",
    technical_name: "",
    description: "",
    synonyms: [],
    evidence: [],
    dataset_id: datasetId ?? "",
    aggregation: "count",
    measure: null,
    filters: [],
    time_field: null,
  };
}

/** Keeps name, description and the dataset when the kind changes. */
export function switchKind(draft: Draft, metric: Metric, kind: Metric["kind"]): Metric {
  if (metric.kind === kind) return metric;
  const datasetId = isRatio(metric)
    ? (byId(draft.metrics, metric.numerator_id) as SimpleMetric | undefined)?.dataset_id ?? ""
    : metric.dataset_id;
  const timeField = isRatio(metric) ? null : metric.time_field;
  if (kind === "simple") return { ...newMetric(metric.id, datasetId), ...common(metric), time_field: timeField };
  if (kind === "expression")
    return {
      ...common(metric),
      kind: "expression",
      dataset_id: datasetId,
      expression: "",
      value_kind: null,
      time_field: timeField,
    };
  return { ...common(metric), kind: "ratio", numerator_id: "", denominator_id: "" };
}

/** Exactly the stored fields; read projections (value_kind of a ratio, components, status) are dropped. */
export function storedMetric(metric: Metric): Metric {
  const base = common(metric);
  if (metric.kind === "ratio")
    return { ...base, kind: "ratio", numerator_id: metric.numerator_id, denominator_id: metric.denominator_id };
  if (metric.kind === "expression")
    return {
      ...base,
      kind: "expression",
      dataset_id: metric.dataset_id,
      expression: metric.expression,
      value_kind: metric.value_kind ?? null,
      time_field: metric.time_field ?? null,
    };
  return {
    ...base,
    kind: "simple",
    dataset_id: metric.dataset_id,
    aggregation: metric.aggregation,
    measure: metric.aggregation === "count" ? null : (metric.measure ?? null),
    filters: (metric.filters ?? []).map((f) => ({
      column: f.column,
      operator: f.operator,
      values: operatorArity(f.operator) === 0 ? [] : (f.values ?? []),
    })),
    time_field: metric.time_field ?? null,
  };
}

export function newFilter(datasetId: UUID): Condition {
  return { column: { dataset_id: datasetId, column: "" }, operator: "eq", values: [] };
}

export type MetricErrors = Partial<Record<"name" | "technical_name" | "dataset" | "measure" | "numerator" | "denominator" | "expression" | `filter.${number}`, string>>;

function conditionValueMatches(value: Scalar, kind: ValueKind): boolean {
  if (kind === "string") return typeof value === "string";
  if (kind === "boolean") return typeof value === "boolean";
  if (NUMERIC_KINDS.has(kind))
    return typeof value === "number" && Number.isFinite(value) && (kind !== "integer" || Number.isInteger(value));
  if (typeof value !== "string") return false;
  if (kind === "date") {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
    const date = new Date(value);
    return !Number.isNaN(date.valueOf()) && date.toISOString().slice(0, 10) === value;
  }
  return /[T ]/.test(value) && !Number.isNaN(Date.parse(value));
}

export function metricErrors(draft: Draft, metric: Metric): MetricErrors {
  const errors: MetricErrors = {};
  if (!metric.name.trim()) errors.name = "请填写名称";
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(metric.technical_name)) errors.technical_name = "技术名只能使用字母、数字和下划线，且不能以数字开头";
  else if (draft.metrics.some((m) => m.id !== metric.id && m.technical_name.toLowerCase() === metric.technical_name.toLowerCase()))
    errors.technical_name = "技术名已被其他指标使用";
  if (isRatio(metric)) {
    const numerator = byId(draft.metrics, metric.numerator_id);
    const denominator = byId(draft.metrics, metric.denominator_id);
    if (!numerator || !isSimple(numerator)) errors.numerator = "请选择分子指标";
    if (!denominator || !isSimple(denominator)) errors.denominator = "请选择分母指标";
    else if (numerator && isSimple(numerator) && numerator.dataset_id !== denominator.dataset_id)
      errors.denominator = "分子和分母须来自同一个数据集";
    return errors;
  }
  const dataset = byId(draft.datasets, metric.dataset_id);
  if (!dataset) errors.dataset = "请选择数据集";
  if (metric.kind === "expression") {
    if (!metric.expression.trim()) errors.expression = "请填写表达式";
    return errors;
  }
  if (metric.aggregation !== "count" && !metric.measure?.column) errors.measure = "请选择度量列";
  (metric.filters ?? []).forEach((f, i) => {
    const arity = operatorArity(f.operator);
    const rawValues = f.values ?? [];
    const values = rawValues.filter((v) => !isEmptyConditionValue(v));
    const colKind = physicalValueKind(
      dataset?.columns?.find((c) => c.name === f.column.column)?.physical_type ?? null,
    );
    if (!f.column.column) errors[`filter.${i}`] = "请选择列";
    else if (f.operator === "not_in" && rawValues.some(isEmptyConditionValue))
      errors[`filter.${i}`] = "“不属于”的值不能包含空值";
    else if (arity === 1 && values.length !== 1) errors[`filter.${i}`] = "请填写一个值";
    else if (arity === 2 && values.length !== 2) errors[`filter.${i}`] = "请填写起止两个值";
    else if (arity === "many" && !values.length) errors[`filter.${i}`] = "至少填写一个值";
    else if (arity !== 0 && colKind && NUMERIC_KINDS.has(colKind) && values.some((v) => !conditionValueMatches(v, colKind)))
      errors[`filter.${i}`] = "数值列的条件值必须是数字";
    else if (arity !== 0 && colKind && values.some((v) => !conditionValueMatches(v, colKind)))
      errors[`filter.${i}`] = "条件值与列类型不匹配，请重新填写";
    else if (arity !== 0 && colKind === "boolean" && ["gt", "ge", "lt", "le", "between"].includes(f.operator))
      errors[`filter.${i}`] = "布尔列不能使用大小比较";
  });
  return errors;
}

/** A ratio sends both components; a simple component being edited overrides the stored one. */
export function previewRequest(
  draft: Draft,
  metric: Metric,
  context: Pick<MetricPreviewRequest, "session_id" | "expected_session_revision" | "expected_current_version_id">,
  range?: MetricPreviewRequest["time_range"],
): MetricPreviewRequest {
  const request: MetricPreviewRequest = { ...context, metric: storedMetric(metric) };
  if (isRatio(metric)) {
    // One component may cover both references when numerator and denominator are the same metric.
    request.components = [...new Set([metric.numerator_id, metric.denominator_id])]
      .map((id) => byId(draft.metrics, id))
      .filter((m): m is SimpleMetric => !!m && isSimple(m))
      .map((m) => storedMetric(m) as SimpleMetric);
  }
  if (range) {
    request.time_range = range;
    request.trend_grain = "month";
  }
  return request;
}

/** Simple metrics a ratio may pick, limited to the numerator's dataset once chosen. */
export function ratioChoices(draft: Draft, metric: RatioMetric, side: "numerator" | "denominator") {
  const other = byId(draft.metrics, side === "numerator" ? metric.denominator_id : metric.numerator_id);
  const datasetId = other && isSimple(other) ? other.dataset_id : null;
  return ratioComponents(draft, datasetId).filter((m) => m.id !== metric.id);
}
