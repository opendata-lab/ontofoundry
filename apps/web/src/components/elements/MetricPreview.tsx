import { Alert, Button, DatePicker, Spin, Table, Tabs, Typography } from "antd";
import { PanelToolbar, SectionTitle } from "../layout";
import type { Dayjs } from "dayjs";
import { Play, RefreshCw } from "lucide-react";
import { useLayoutEffect, useRef, useState } from "react";
import { metricsApi } from "../../api/client";
import type { Draft, Metric, MetricPreview as Preview, MetricPreviewRequest, SQLReference } from "../../api/types";
import { metricErrors, previewRequest } from "../../lib/metricEditing";

const { Text } = Typography;

export type PreviewContext = Pick<
  MetricPreviewRequest,
  "session_id" | "expected_session_revision" | "expected_current_version_id"
>;

const REASONS: Record<string, string> = {
  expression_not_supported: "平台预览暂不支持这个表达式",
  engine_not_supported: "当前数据库不支持这种计算",
  binding_not_ready: "数据集、列清单或结果类型还没有就绪",
  source_ambiguous: "数据集对应的连接不唯一",
  forbidden: "没有读取这个数据集的权限",
  query_timeout: "查询超时",
  query_failed: "查询失败",
};

function Sql({ query }: { query: SQLReference }) {
  return (
    <div className="flex flex-col gap-1">
      <pre className="m-0 overflow-auto rounded-md bg-surface-soft p-3 font-mono text-sm leading-5 whitespace-pre-wrap">
        {query.sql}
      </pre>
      {Object.keys(query.params).length > 0 && (
        <Text type="secondary" className="text-xs">
          参数：{Object.entries(query.params).map(([k, v]) => `${k} = ${JSON.stringify(v)}`).join("，")}
        </Text>
      )}
      {query.note && (
        <Text type="secondary" className="text-xs">
          {query.note}
        </Text>
      )}
    </div>
  );
}

const display = (value: unknown) =>
  value === null || value === undefined ? "空" : typeof value === "number" ? value.toLocaleString("zh-CN", { maximumFractionDigits: 6 }) : String(value);

/**
 * Runs the current, unsaved form read-only. A result belongs to the request
 * that produced it: a later edit marks it out of date, and a slow answer to
 * an older request never replaces a newer one.
 */
export function MetricPreview({ draft, metric, context, active = true }: { draft: Draft; metric: Metric; context: PreviewContext; active?: boolean }) {
  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [result, setResult] = useState<{ key: string; preview: Preview } | null>(null);
  const [error, setError] = useState<{ key: string; message: string } | null>(null);
  const [running, setRunning] = useState(false);
  const sequence = useRef(0);
  const contextKey = JSON.stringify(context);
  useLayoutEffect(() => {
    setRunning(false);
    return () => { sequence.current += 1; };
  }, [active, draft.workspace_id, metric.id, contextKey]);
  const timeRange = range
    ? { start: range[0].format("YYYY-MM-DD"), end: range[1].add(1, "day").format("YYYY-MM-DD") }
    : undefined;
  const request = previewRequest(draft, metric, context, timeRange);
  const key = JSON.stringify(request);
  const invalid = Object.values(metricErrors(draft, metric))[0];
  const run = async () => {
    if (!active) return;
    const id = ++sequence.current;
    setRunning(true);
    setError(null);
    try {
      const preview = await metricsApi.preview(draft.workspace_id, request);
      if (id === sequence.current) setResult({ key, preview });
    } catch (e) {
      if (id === sequence.current) setError({ key, message: e instanceof Error ? e.message : "预览失败" });
    } finally {
      if (id === sequence.current) setRunning(false);
    }
  };
  const stale = !!result && result.key !== key;
  const preview = result?.preview;
  return (
    <section className="flex max-w-settings flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Button
          icon={running ? <Spin size="small" /> : preview ? <RefreshCw size={15} /> : <Play size={15} />}
          disabled={!active || !!invalid || undefined}
          onClick={() => void run()}
        >
          {running ? "预览中…" : preview ? "重新预览" : "预览数值"}
        </Button>
        <DatePicker.RangePicker
          aria-label="预览时间范围"
          allowEmpty={[false, false]}
          value={range}
          onChange={(value) => setRange(value && value[0] && value[1] ? [value[0], value[1]] : null)}
          placeholder={["开始日期", "结束日期"]}
        />
        <Text type="secondary" className="text-xs">
          {invalid ? `表单未完成：${invalid}` : "按当前表单只读执行，不保存任何内容；选择时间范围后按月显示趋势。"}
        </Text>
      </div>
      {error && error.key === key && <Alert type="error" showIcon message={error.message} />}
      {stale && (
        <Alert
          type="warning"
          showIcon
          message="表单或时间范围已修改，下面是修改前的结果，需重新预览"
          action={
            <Button size="small" onClick={() => void run()}>
              重新预览
            </Button>
          }
        />
      )}
      {preview && preview.status === "unable" && (
        <Alert
          type="warning"
          showIcon
          message={`无法预览：${preview.reason || REASONS[preview.reason_code ?? ""] || preview.reason_code || "未知原因"}`}
        />
      )}
      {preview && preview.status === "ok" && (
        <div className={`flex flex-col gap-3 ${stale ? "opacity-50" : ""}`}>
          <div className="grid grid-cols-2 gap-4">
            <section className="flex flex-col gap-2 border-r border-rule pr-4">
              <SectionTitle title="总值" />
              <Text strong className="text-base">{display(preview.value)}</Text>
              {preview.snapshot_dates.some((s) => s.date && s.period === null) && (
                <Text type="secondary" className="text-xs">
                  快照日期：{preview.snapshot_dates.filter((s) => s.period === null && s.date).map((s) => s.date).join("、")}
                </Text>
              )}
            </section>
            <section className="min-w-0">
              <SectionTitle title="按月趋势" />
              {preview.trend?.length ? (
                <Table
                  size="small"
                  rowKey="period"
                  pagination={false}
                  className="mt-1"
                  dataSource={preview.trend}
                  columns={[
                    { title: "月份", key: "period", render: (_, p) => p.period.slice(0, 7) },
                    { title: "值", key: "value", align: "right", render: (_, p) => display(p.value) },
                  ]}
                />
              ) : (
                <div className="mt-2 text-sm text-muted">
                  {range ? "这个范围内没有趋势数据" : "选择时间范围后显示按月趋势"}
                </div>
              )}
            </section>
          </div>
          {preview.warnings.map((w) => (
            <Alert key={w} type="info" showIcon message={w} />
          ))}
        </div>
      )}
      {preview && (preview.total_query || preview.trend_query) && (
        <Tabs
          size="small"
          renderTabBar={(props, DefaultTabBar) => <PanelToolbar tabBar={<DefaultTabBar {...props} />} />}
          items={[
            ...(preview.total_query ? [{ key: "total", label: "总值查询", children: <Sql query={preview.total_query} /> }] : []),
            ...(preview.trend_query ? [{ key: "trend", label: "趋势查询", children: <Sql query={preview.trend_query} /> }] : []),
          ]}
        />
      )}
    </section>
  );
}
