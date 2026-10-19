import { Alert, Button, Descriptions, Form, Input, Segmented, Select, Tag, Tooltip, Typography } from "antd";
import { SectionTitle } from "../layout";
import { Plus, Trash2 } from "lucide-react";
import type { Aggregation, Condition, Dataset, Draft, Metric, Operator, ValueKind } from "../../api/types";
import {
  AGGREGATIONS,
  DATE_KINDS,
  NUMERIC_KINDS,
  VALUE_KINDS,
  byId,
  isRatio,
  isSimple,
  metricDatasetId,
  metricValueKind,
  physicalValueKind,
} from "../../lib/coreModel";
import { OPERATORS } from "../../lib/derivedEditing";
import { METRIC_KINDS, metricErrors, newFilter, ratioChoices, switchKind } from "../../lib/metricEditing";
import { datasetLabel } from "../../lib/datasetEditing";

import { ConditionValueInput } from "./ConditionValueInput";

const { Text } = Typography;

const columnKind = (dataset: Dataset | undefined, column: string): ValueKind | null =>
  physicalValueKind(dataset?.columns?.find((c) => c.name === column)?.physical_type ?? null);

function columnOptions(dataset: Dataset | undefined, accept?: (kind: ValueKind | null) => boolean) {
  return (dataset?.columns ?? [])
    .filter((c) => !accept || accept(physicalValueKind(c.physical_type ?? null)))
    .map((c) => ({ value: c.name, label: c.comment ? `${c.comment}（${c.name}）` : c.name }));
}

/** Free text when the dataset has no registered column list. */
function ColumnSelect({
  dataset,
  value,
  label,
  accept,
  allowClear,
  placeholder,
  onChange,
}: {
  dataset: Dataset | undefined;
  value: string | null | undefined;
  label: string;
  accept?: (kind: ValueKind | null) => boolean;
  allowClear?: boolean;
  placeholder?: string;
  onChange: (column: string | null) => void;
}) {
  if (!dataset?.columns)
    return (
      <Input
        aria-label={label}
        className="font-mono"
        placeholder="数据集未登记列清单，输入列名"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value.trim() || null)}
      />
    );
  return (
    <Select
      className="w-full"
      aria-label={label}
      showSearch
      allowClear={allowClear}
      optionFilterProp="label"
      placeholder={placeholder}
      value={value || undefined}
      options={columnOptions(dataset, accept)}
      onChange={(v?: string) => onChange(v ?? null)}
      notFoundContent="没有可选的列"
    />
  );
}

/** simple / ratio / expression metric on one registered dataset. */
export function MetricForm({
  draft,
  metric,
  onChange,
  showErrors,
}: {
  draft: Draft;
  metric: Metric;
  onChange: (metric: Metric) => void;
  showErrors: boolean;
}) {
  const errors = showErrors ? metricErrors(draft, metric) : {};
  const datasetId = metricDatasetId(draft, metric);
  const dataset = byId(draft.datasets, datasetId);
  const datasets = draft.datasets.map((d) => ({ value: d.id, label: datasetLabel(d) }));
  const status = (key: keyof typeof errors) => (errors[key] ? { validateStatus: "error" as const, help: errors[key] } : {});
  const valueKind = metricValueKind(draft, metric);
  const timeField = !isRatio(metric) ? (
    <Form.Item
      label="时间字段"
      extra={
        dataset?.snapshot_date_column
          ? `每日快照表：选 ${dataset.snapshot_date_column} 时每个周期取最后一个有数据的日期；其他情况只取最新一天`
          : "决定按哪个日期把数据归到周期；不选则不按时间"
      }
    >
      <ColumnSelect
        dataset={dataset}
        label="时间字段"
        allowClear
        placeholder="不按时间"
        accept={(kind) => kind === null || DATE_KINDS.has(kind)}
        value={metric.time_field?.column}
        onChange={(column) =>
          onChange({ ...metric, time_field: column && datasetId ? { dataset_id: datasetId, column } : null })
        }
      />
    </Form.Item>
  ) : null;
  return (
    <Form layout="vertical" component="div" requiredMark className="max-w-settings">
      <SectionTitle title="基本信息" className="mb-4" />
      <div className="grid grid-cols-2 gap-x-4">
        <Form.Item label="名称" required {...status("name")}>
          <Input aria-label="指标名称" value={metric.name} placeholder="例如：已完成订单金额" onChange={(e) => onChange({ ...metric, name: e.target.value })} />
        </Form.Item>
        <Form.Item label="技术名" required {...status("technical_name")}>
          <Input
            aria-label="指标技术名"
            className="font-mono"
            value={metric.technical_name}
            onChange={(e) => onChange({ ...metric, technical_name: e.target.value.trim() })}
          />
        </Form.Item>
      </div>
      <div className="grid grid-cols-2 gap-x-4">
        <Form.Item label="说明">
          <Input.TextArea
            aria-label="指标说明"
            autoSize={{ minRows: 1, maxRows: 4 }}
            placeholder="业务含义、口径说明"
            value={metric.description}
            onChange={(e) => onChange({ ...metric, description: e.target.value })}
          />
        </Form.Item>
        <Form.Item label="同义词">
          <Select
            mode="tags"
            aria-label="指标同义词"
            open={false}
            placeholder="输入后回车"
            value={metric.synonyms}
            onChange={(synonyms: string[]) => onChange({ ...metric, synonyms })}
          />
        </Form.Item>
      </div>
      <SectionTitle title="指标定义" className="mb-4 border-t border-rule pt-4" />
      <Form.Item label="计算方式" required>
        <Segmented
          block
          value={metric.kind}
          onChange={(kind) => onChange(switchKind(draft, metric, kind as Metric["kind"]))}
          options={Object.entries(METRIC_KINDS).map(([value, label]) => ({ value, label }))}
        />
      </Form.Item>
      {!isRatio(metric) && (
        <Form.Item label="数据集" required {...status("dataset")}>
          <Select
            aria-label="指标数据集"
            showSearch
            optionFilterProp="label"
            placeholder={draft.datasets.length ? "选择已登记的数据集" : "还没有登记数据集"}
            value={metric.dataset_id || undefined}
            options={datasets}
            onChange={(id: string) =>
              onChange(
                isSimple(metric)
                  ? { ...metric, dataset_id: id, measure: null, filters: [], time_field: null }
                  : { ...metric, dataset_id: id, time_field: null },
              )
            }
          />
        </Form.Item>
      )}
      {dataset && (
        <Descriptions
          size="small"
          column={3}
          className="mb-4"
          items={[
            { key: "table", label: "物理表", children: <code>{[dataset.schema_name, dataset.table_name].filter(Boolean).join(".")}</code> },
            { key: "snapshot", label: "快照", children: dataset.snapshot_date_column ? `每日快照（${dataset.snapshot_date_column}）` : "不是快照表" },
            { key: "kind", label: "结果类型", children: valueKind ? VALUE_KINDS[valueKind] : "待定" },
          ]}
        />
      )}
      {isSimple(metric) && (
        <>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item label="聚合" required>
              <Select
                aria-label="聚合方式"
                value={metric.aggregation}
                options={Object.entries(AGGREGATIONS).map(([value, label]) => ({ value, label }))}
                onChange={(aggregation: Aggregation) =>
                  onChange({
                    ...metric,
                    aggregation,
                    measure:
                      aggregation === "count"
                        ? null
                        : (metric.measure ?? (metric.dataset_id ? { dataset_id: metric.dataset_id, column: "" } : null)),
                  })
                }
              />
            </Form.Item>
            {metric.aggregation !== "count" && (
              <Form.Item
                label="度量列"
                required
                {...status("measure")}
                extra={["sum", "avg", "median"].includes(metric.aggregation) ? "只列出数值列" : undefined}
              >
                <ColumnSelect
                  dataset={dataset}
                  label="度量列"
                  accept={
                    ["sum", "avg", "median"].includes(metric.aggregation)
                      ? (kind) => kind === null || NUMERIC_KINDS.has(kind)
                      : undefined
                  }
                  value={metric.measure?.column}
                  onChange={(column) =>
                    onChange({ ...metric, measure: column ? { dataset_id: metric.dataset_id, column } : null })
                  }
                />
              </Form.Item>
            )}
          </div>
          {metric.aggregation === "count" && <Alert className="mb-4" type="info" showIcon message="计数统计满足条件的行数，不需要选择列。" />}
        </>
      )}
      {isRatio(metric) && (
        <>
          <div className="grid grid-cols-2 gap-x-4">
            {(["numerator", "denominator"] as const).map((side) => {
              const key = side === "numerator" ? "numerator_id" : "denominator_id";
              const picked = byId(draft.metrics, metric[key]);
              return (
                <Form.Item
                  key={side}
                  label={side === "numerator" ? "分子" : "分母"}
                  required
                  {...status(side)}
                  extra={
                    picked && isSimple(picked)
                      ? `时间口径：${picked.time_field?.column ?? "不按时间"}`
                      : "只能选同一数据集上的聚合指标"
                  }
                >
                  <Select
                    aria-label={side === "numerator" ? "分子指标" : "分母指标"}
                    showSearch
                    optionFilterProp="label"
                    placeholder="选择指标"
                    value={metric[key] || undefined}
                    options={ratioChoices(draft, metric, side).map((m) => ({ value: m.id, label: m.name }))}
                    notFoundContent="该数据集上还没有可用的聚合指标"
                    onChange={(id: string) => onChange({ ...metric, [key]: id })}
                  />
                </Form.Item>
              );
            })}
          </div>
          {byId(draft.metrics, metric.numerator_id) && byId(draft.metrics, metric.denominator_id) && (
            <Alert
              className="mb-4"
              type="info"
              showIcon
              message={`${metric.name || "比率"} = ${byId(draft.metrics, metric.numerator_id)!.name} ÷ ${byId(draft.metrics, metric.denominator_id)!.name}`}
              description="分子、分母各自按自己的条件和时间口径计算；分母为 0 时结果为空。"
            />
          )}
        </>
      )}
      {metric.kind === "expression" && (
        <>
          <Form.Item
            label="表达式"
            required
            {...status("expression")}
            extra={errors.expression ? undefined : "只使用所选数据集的列，写成一个聚合表达式；保存和预览时由服务器校验"}
          >
            <Input.TextArea
              aria-label="指标表达式"
              rows={3}
              className="font-mono"
              placeholder={`SUM(CASE WHEN "${dataset?.name ?? "数据集"}".status = 'done' THEN "${dataset?.name ?? "数据集"}".amount END)`}
              value={metric.expression}
              onChange={(e) => onChange({ ...metric, expression: e.target.value })}
            />
          </Form.Item>
          {dataset?.columns && (
            <div className="-mt-2 mb-4 flex flex-wrap items-center gap-1 text-xs text-muted">
              可用列：
              {dataset.columns.map((c) => (
                <Tooltip key={c.name} title={[c.comment, c.physical_type].filter(Boolean).join(" · ") || c.name}>
                  <Tag
                    className="cursor-pointer"
                    onClick={() => onChange({ ...metric, expression: `${metric.expression}"${dataset.name}".${c.name}` })}
                  >
                    {c.name}
                  </Tag>
                </Tooltip>
              ))}
            </div>
          )}
          <Form.Item label="结果类型" extra="可选；未指定时留空待补全">
            <Select
              aria-label="结果类型"
              allowClear
              placeholder="未指定"
              value={metric.value_kind ?? undefined}
              options={Object.entries(VALUE_KINDS).map(([value, label]) => ({ value, label }))}
              onChange={(value_kind?: ValueKind) => onChange({ ...metric, value_kind: value_kind ?? null })}
            />
          </Form.Item>
        </>
      )}
      {isSimple(metric) && (
        <>
          <SectionTitle title="条件" className="mb-3 border-t border-rule pt-4" />
          <div className="mb-4 flex flex-col gap-2">
            {!metric.filters.length && <Text type="secondary">没有条件，统计全部行</Text>}
            {metric.filters.map((filter, i) => {
              const set = (next: Condition) =>
                onChange({ ...metric, filters: metric.filters.map((f, j) => (j === i ? next : f)) });
              const error = errors[`filter.${i}`] ?? (filter.values?.length ? metricErrors(draft, metric)[`filter.${i}`] : undefined);
              const kind = filter.column.column ? columnKind(dataset, filter.column.column) : null;
              return (
                <Form.Item
                  key={i}
                  className="mb-0"
                  validateStatus={error ? "error" : undefined}
                  help={error}
                  extra={kind ? `${VALUE_KINDS[kind]}列` : undefined}
                >
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <ColumnSelect
                        dataset={dataset}
                        label={`条件 ${i + 1} 的列`}
                        value={filter.column.column}
                        onChange={(column) => set({ ...filter, column: { dataset_id: metric.dataset_id, column: column ?? "" } })}
                      />
                    </div>
                    <Select
                      className="w-28 flex-none"
                      aria-label={`条件 ${i + 1} 的运算`}
                      value={filter.operator}
                      options={Object.entries(OPERATORS).map(([value, label]) => ({ value, label }))}
                      onChange={(operator: Operator) => set({ ...filter, operator, values: [] })}
                    />
                    <div className="min-w-0 flex-1">
                      <ConditionValueInput kind={kind} operator={filter.operator} values={filter.values ?? []} label={`条件 ${i + 1} 的值`} onChange={(values) => set({ ...filter, values })} />
                    </div>
                    <Button
                      type="text"
                      aria-label={`删除条件 ${i + 1}`}
                      icon={<Trash2 size={15} />}
                      onClick={() => onChange({ ...metric, filters: metric.filters.filter((_, j) => j !== i) })}
                    />
                  </div>
                </Form.Item>
              );
            })}
            <Button
              type="dashed"
              icon={<Plus size={15} />}
              className="self-start"
              disabled={!metric.dataset_id || undefined}
              onClick={() => onChange({ ...metric, filters: [...metric.filters, newFilter(metric.dataset_id)] })}
            >
              添加条件（同时满足）
            </Button>
          </div>
        </>
      )}
      {timeField}
    </Form>
  );
}
