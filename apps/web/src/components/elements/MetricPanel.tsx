import { Descriptions, Typography } from "antd";
import { ContentBlock, SectionTitle } from "../layout";
import type { Draft, Metric } from "../../api/types";
import {
  AGGREGATIONS,
  VALUE_KINDS,
  byId,
  isRatio,
  isSimple,
  metricDatasetId,
  metricValueKind,
  upsert,
} from "../../lib/coreModel";
import { OPERATORS } from "../../lib/derivedEditing";
import type { ElementRequest } from "../../lib/elementInspector";
import { METRIC_KINDS } from "../../lib/metricEditing";
import { ElementLink, EvidenceSection, TagsText } from "./ElementPanels";
import { MetricForm } from "./MetricForm";
import { MetricPreview, type PreviewContext } from "./MetricPreview";

const { Text, Paragraph } = Typography;

function MetricSummary({ draft, metric, open }: { draft: Draft; metric: Metric; open: (r: ElementRequest) => void }) {
  const dataset = byId(draft.datasets, metricDatasetId(draft, metric));
  const kind = metricValueKind(draft, metric);
  const metricLink = (id: string) => {
    const m = byId(draft.metrics, id);
    return m ? <ElementLink onClick={() => open({ kind: "metric", id })}>{(m.display_name || m.name)}</ElementLink> : "?";
  };
  const items = [
    { key: "technical", label: "英文标识", children: <code>{metric.name}</code> },
    { key: "kind", label: "计算方式", children: METRIC_KINDS[metric.kind] },
    {
      key: "dataset",
      label: "数据集",
      children: dataset ? <ElementLink onClick={() => open({ kind: "dataset", id: dataset.id })}>{dataset.name}</ElementLink> : "?",
    },
    { key: "value", label: "结果类型", children: kind ? VALUE_KINDS[kind] : "待定" },
    ...(isSimple(metric)
      ? [
          {
            key: "aggregation",
            label: "聚合",
            children: `${AGGREGATIONS[metric.aggregation]}${metric.measure ? ` ${metric.measure.column}` : ""}`,
          },
          {
            key: "filters",
            label: "条件",
            children: metric.filters.length
              ? metric.filters
                  .map((f) => `${f.column.column} ${OPERATORS[f.operator]} ${(f.values ?? []).map(String).join("、")}`.trim())
                  .join("；并且 ")
              : "无，统计全部行",
          },
        ]
      : []),
    ...(isRatio(metric)
      ? [
          { key: "numerator", label: "分子", children: metricLink(metric.numerator_id) },
          { key: "denominator", label: "分母", children: metricLink(metric.denominator_id) },
        ]
      : []),
    ...(metric.kind === "expression"
      ? [{ key: "expression", label: "表达式", span: 2, children: <code className="whitespace-pre-wrap">{metric.expression}</code> }]
      : []),
    ...(!isRatio(metric)
      ? [{ key: "time", label: "时间字段", children: metric.time_field?.column ?? "不按时间" }]
      : []),
    { key: "synonyms", label: "同义词", children: <TagsText items={metric.synonyms} /> },
  ];
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionTitle title="指标定义" />
      {metric.description ? (
        <Paragraph className="m-0 whitespace-pre-wrap">{metric.description}</Paragraph>
      ) : (
        <Text type="secondary">暂无说明</Text>
      )}
      <Descriptions size="small" column={2} items={items} />
    </div>
  );
}

/** A metric: definition (read or edit) and a read-only value preview of the current form. */
export function MetricPanel({
  draft,
  metric,
  editing,
  canPreview,
  showErrors,
  context,
  change,
  open,
}: {
  draft: Draft;
  metric: Metric;
  editing: boolean;
  canPreview: boolean;
  showErrors: boolean;
  context: PreviewContext;
  change: (next: Draft) => void;
  open: (request: ElementRequest) => void;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <ContentBlock>
      {editing ? (
        <MetricForm
          draft={draft}
          metric={metric}
          showErrors={showErrors}
          onChange={(next) => change(upsert(draft, "metrics", next))}
        />
      ) : (
        <MetricSummary draft={draft} metric={metric} open={open} />
      )}
      </ContentBlock>
      {!editing && <EvidenceSection workspaceId={draft.workspace_id} evidence={metric.evidence} />}
      {canPreview && (
        <ContentBlock>
          <SectionTitle title="数值预览" />
          <MetricPreview draft={draft} metric={metric} context={context} />
        </ContentBlock>
      )}
    </div>
  );
}
