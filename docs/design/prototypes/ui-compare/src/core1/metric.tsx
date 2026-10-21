import { useMemo, useState } from "react";
import {
  Alert, Button, Descriptions, Drawer, Empty, Form, Input, Segmented, Select, Space, Table, Tag, Tooltip, Typography,
} from "antd";
import { Database, Play, Plus, RefreshCw, Trash2 } from "lucide-react";
import { mount } from "./shell";
import {
  type FormState, type Preview, type SavedMetric, DATASETS, KINDS, OPERATORS,
  datasetOf, emptyForm, formatNumber, kindLabel, preview, referenceSql,
} from "../shared/model";
import { Sparkline, useMetricForm } from "../shared/useMetricForm";

const { Text, Title } = Typography;

/** Conditions of the saved simple metrics, so a ratio can be previewed from its parts. */
const SAVED_CONDITIONS: Record<string, FormState["conditions"]> = {
  m3: [{ id: "s1", column: "status", operator: "eq", value: "已完成" }],
};

function savedAsForm(m: SavedMetric): FormState {
  return { ...emptyForm(), datasetId: m.datasetId, kind: m.kind, column: m.column ?? null,
    conditions: SAVED_CONDITIONS[m.id] ?? [], timeField: m.timeField ?? null };
}

/** Columns a metric expression may use: only the chosen dataset's registered columns. */
function checkExpression(text: string, datasetId: string | null): string | null {
  const ds = datasetOf(datasetId);
  if (!ds) return "请先选择数据集";
  if (!text.trim()) return "请填写表达式";
  if (/\b(select|from|join)\b/i.test(text)) return "表达式只能是本数据集上的一个聚合，不能包含 SELECT、FROM 或 JOIN";
  const short = ds.table.split(".").at(-1)!;
  for (const [, prefix, col] of text.replace(/'[^']*'/g, "''").matchAll(/\b([a-z_]+)\.([a-z_]+)\b/gi)) {
    if (prefix !== short) return `引用了其他数据集的列 ${prefix}.${col}；指标只能使用 ${ds.name}（${short}）的列`;
    if (!ds.columns.some((c) => c.name === col)) return `${short} 没有登记列 ${col}`;
  }
  return null;
}

function PreviewPanel({ m, ran, stale, onRun }: {
  m: ReturnType<typeof useMetricForm>; ran: Preview | null; stale: boolean; onRun: () => void;
}) {
  const { form } = m;
  const ds = m.dataset;
  const blocked = ds?.readable === false || ds?.connected === false;
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <Button icon={ran ? <RefreshCw size={15} /> : <Play size={15} />} onClick={onRun} disabled={!ds}>
          {ran ? "重新预览" : "预览数值"}
        </Button>
        <Text type="secondary" className="text-xs">平台按当前表单编译 SQL，在数据集的已登记连接上只读执行；不保存任何内容</Text>
      </div>
      {!ran && !blocked && <Text type="secondary">还没有预览。改完表单后点“预览数值”查看实际结果。</Text>}
      {ran && stale && (
        <Alert type="warning" showIcon message="表单已修改，下面是修改前的结果，已过期" action={<Button size="small" onClick={onRun}>重新预览</Button>} />
      )}
      {ran && !ran.ok && <Alert type="error" showIcon message={`无法预览：${ran.reason}`} />}
      {ran?.ok && (
        <div className={`grid grid-cols-[200px_1fr] gap-4 ${stale ? "opacity-45" : ""}`}>
          <div className="rounded-md bg-surface-soft p-4">
            <div className="text-xs text-muted">总值</div>
            <div className="mt-1 text-3xl font-semibold">{formatNumber(ran.total)}</div>
            <div className="mt-2 text-xs leading-5 text-muted">
              {form.timeField ? `全部周期合计；按 ${form.timeField} 归周期` : "不按时间，统计全部行"}
              {ds?.snapshotColumn && form.timeField !== ds.snapshotColumn && <><br />快照表：只取最新一天</>}
            </div>
          </div>
          <div className="rounded-md bg-surface-soft p-4">
            <div className="text-xs text-muted">按月趋势</div>
            {ran.trend && ran.trend.length > 1 ? (
              <div className="mt-1 text-accent">
                <Sparkline points={ran.trend} />
                <div className="flex justify-between text-xs text-muted">
                  {ran.trend.map((p) => <span key={p.month}>{p.month.slice(5)}月 {formatNumber(p.value)}</span>)}
                </div>
                <div className="mt-1 text-xs text-muted">
                  每月一个值{ds?.snapshotColumn === form.timeField ? "，每月取最后一个有数据的日期" : ""}
                </div>
              </div>
            ) : <div className="mt-2 text-sm text-muted">{form.timeField ? "数据只覆盖一个月" : "未选时间字段，不显示趋势"}</div>}
          </div>
        </div>
      )}
    </div>
  );
}

function App() {
  const m = useMetricForm();
  const { form } = m;
  const [open, setOpen] = useState(false);
  const [ran, setRan] = useState<{ result: Preview; snapshot: string } | null>(null);
  const formKey = JSON.stringify({ ...form, name: "", synonyms: [], description: "" });
  const stale = ran != null && ran.snapshot !== formKey;
  const exprError = form.kind === "expression" ? checkExpression(form.expression, form.datasetId) : null;
  const numerator = m.metricById(form.numeratorId);
  const denominator = m.metricById(form.denominatorId);

  const run = () => {
    let result: Preview;
    if (form.kind === "ratio") {
      const ds = m.dataset;
      if (ds?.readable === false || ds?.connected === false) result = preview(form);
      else if (!numerator || !denominator) result = { ok: false, reason: "请选择分子和分母" };
      else {
        const n = preview(savedAsForm(numerator)), d = preview(savedAsForm(denominator));
        const div = (a?: number | null, b?: number | null) => (a == null || !b ? null : a / b);
        const months = [...new Set([...(n.trend ?? []), ...(d.trend ?? [])].map((p) => p.month))].sort();
        result = { ok: true, total: div(n.total, d.total), trend: months.map((month) => ({
          month,
          value: div(n.trend?.find((p) => p.month === month)?.value, d.trend?.find((p) => p.month === month)?.value),
        })) };
      }
    } else if (form.kind === "expression") {
      const ds = m.dataset;
      result = ds?.readable === false || ds?.connected === false ? preview(form)
        : exprError ? { ok: false, reason: exprError }
        : { ok: false, reason: "原型不执行表达式；实际由平台编译并经白名单检查后只读执行，引擎不支持的函数会在这里说明" };
    } else result = preview(form);
    setRan({ result, snapshot: formKey });
  };

  const sql = form.kind === "expression" && exprError ? { reason: exprError } : referenceSql(form);
  const showColumn = !["count", "ratio", "expression"].includes(form.kind);
  const metricRows = useMemo(() => m.metrics, [m.metrics]);

  return (
    <div className="mx-auto max-w-[1180px] p-6">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <Title level={4} className="!m-0">语义视图 · 指标</Title>
          <Text type="secondary">指标只挂在数据集上，只使用该数据集的列</Text>
        </div>
        <Button type="primary" icon={<Plus size={16} />} onClick={() => { setRan(null); setOpen(true); }}>新建指标</Button>
      </header>

      <Table rowKey="id" size="middle" pagination={false} dataSource={metricRows} columns={[
        { title: "指标", dataIndex: "name", render: (v: string) => <span className="font-medium">{v}</span> },
        { title: "数据集", dataIndex: "datasetId", render: (id: string) => <span className="inline-flex items-center gap-1"><Database size={13} className="text-muted" />{datasetOf(id)?.name}</span> },
        { title: "计算方式", dataIndex: "kind", render: (k) => <Tag>{kindLabel(k)}</Tag> },
        { title: "列", dataIndex: "column", render: (c?: string) => (c ? <code>{c}</code> : "—") },
        { title: "时间字段", dataIndex: "timeField", render: (c?: string) => c ?? "不按时间" },
        { title: "说明", dataIndex: "description", ellipsis: true },
      ]} />

      <Drawer title="新建指标" width={820} open={open} onClose={() => setOpen(false)} destroyOnHidden
        footer={<div className="flex items-center justify-end gap-2">
          <Text type="secondary" className="mr-auto text-xs">保存后生成一条“新增指标”提案，在提案面板审阅接受后进入草稿</Text>
          <Button onClick={() => { m.reset(); setOpen(false); }}>取消</Button>
          <Button type="primary" disabled={!m.canSave || !!exprError} onClick={() => m.save() && setOpen(false)}>保存为提案</Button>
        </div>}>
        <Form layout="vertical" requiredMark>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item label="名称" required>
              <Input value={form.name} onChange={(e) => m.patch({ name: e.target.value })} placeholder="例如：已完成订单金额" />
            </Form.Item>
            <Form.Item label="同义词">
              <Select mode="tags" value={form.synonyms} onChange={(v: string[]) => m.patch({ synonyms: v })} open={false} suffixIcon={null} placeholder="输入后回车" />
            </Form.Item>
          </div>
          <Form.Item label="说明">
            <Input.TextArea rows={2} value={form.description} onChange={(e) => m.patch({ description: e.target.value })} placeholder="业务含义、口径说明" />
          </Form.Item>

          <Title level={5} className="!mt-2">数据集与算法</Title>
          <Form.Item label="数据集" required>
            <Select showSearch value={form.datasetId} onChange={m.setDataset} optionFilterProp="label"
              options={DATASETS.map((d) => ({ value: d.id, label: `${d.name} ${d.table}` }))}
              labelRender={(o) => datasetOf(o.value as string)?.name}
              optionRender={(o) => {
                const d = datasetOf(o.value as string)!;
                return (
                  <div className="flex items-center justify-between gap-3 py-0.5">
                    <div className="flex flex-col">
                      <span>{d.name}</span>
                      <span className="text-xs text-muted">{d.table} · {d.rowMeaning}</span>
                    </div>
                    <span className="flex gap-1">
                      {d.snapshotColumn && <Tag color="blue">每日快照</Tag>}
                      {d.connected === false && <Tag>无连接</Tag>}
                      {d.readable === false && <Tag color="orange">无映射权限</Tag>}
                    </span>
                  </div>
                );
              }} />
          </Form.Item>
          {m.dataset && (
            <Descriptions size="small" column={3} className="mb-4" items={[
              { label: "一行代表", children: m.dataset.rowMeaning.replace("一行 = ", "") },
              { label: "物理表", children: <code>{m.dataset.table}</code> },
              { label: "快照", children: m.dataset.snapshotColumn ? `每日快照（${m.dataset.snapshotColumn}）` : "不是快照表" },
            ]} />
          )}

          <Form.Item label="计算方式" required>
            <Segmented block value={form.kind} onChange={(v) => m.setKind(v as typeof form.kind)}
              options={KINDS.map((k) => ({ value: k.id, label: k.label }))} />
          </Form.Item>

          {form.kind === "count" && <Alert className="mb-4" type="info" showIcon message="计数统计满足条件的行数，不需要选择列" />}

          {showColumn && (
            <Form.Item label="列" required extra={["sum", "avg", "median"].includes(form.kind) ? "只列出数值列" : undefined}>
              <Select value={form.column} onChange={(v) => m.patch({ column: v })}
                options={m.columns.map((c) => ({ value: c.name, label: `${c.comment}（${c.name}）` }))}
                notFoundContent="该数据集没有可用于此算法的列" />
            </Form.Item>
          )}

          {form.kind === "ratio" && (
            <>
              <div className="grid grid-cols-2 gap-x-4">
                {(["numeratorId", "denominatorId"] as const).map((key) => {
                  const picked = m.metricById(form[key]);
                  return (
                    <Form.Item key={key} label={key === "numeratorId" ? "分子" : "分母"} required
                      extra={picked ? `时间口径：${picked.timeField ?? "不按时间"}` : "只能选同一数据集上的计数或求和等简单指标"}>
                      <Select value={form[key]} onChange={(v) => m.patch({ [key]: v })} placeholder="选择指标"
                        options={m.components.map((x) => ({ value: x.id, label: x.name }))}
                        notFoundContent="该数据集上还没有可用的简单指标" />
                    </Form.Item>
                  );
                })}
              </div>
              {numerator && denominator && (
                <Alert className="mb-4" type="info" showIcon
                  message={`${form.name || "比率"} = ${numerator.name} ÷ ${denominator.name}`}
                  description={`分子按 ${numerator.timeField ?? "不按时间"}、分母按 ${denominator.timeField ?? "不按时间"} 归周期；要换口径就换分子或分母指标。分母为 0 时结果为空。`} />
              )}
            </>
          )}

          {form.kind === "expression" && (
            <Form.Item label="表达式" required validateStatus={exprError && form.expression ? "error" : undefined}
              help={form.expression ? exprError ?? "引用检查通过" : "只能使用所选数据集的列，写成一个聚合表达式"}>
              <Input.TextArea rows={3} className="font-mono" value={form.expression}
                onChange={(e) => m.patch({ expression: e.target.value })}
                placeholder={`SUM(CASE WHEN orders.status = '已完成' THEN orders.amount END)`} />
            </Form.Item>
          )}
          {form.kind === "expression" && m.dataset && (
            <div className="-mt-2 mb-4 flex flex-wrap items-center gap-1 text-xs text-muted">
              可用列：{m.dataset.columns.map((c) => {
                const ref = `${m.dataset!.table.split(".").at(-1)}.${c.name}`;
                return (
                  <Tooltip key={c.name} title={`${c.comment} · ${c.type}`}>
                    <Tag className="cursor-pointer" onClick={() => m.patch({ expression: `${form.expression}${ref}` })}>{c.name}</Tag>
                  </Tooltip>
                );
              })}
            </div>
          )}

          {form.kind !== "ratio" && (
            <>
              <Title level={5} className="!mt-2">条件</Title>
              <div className="mb-4 flex flex-col gap-2">
                {form.conditions.length === 0 && <Text type="secondary">没有条件，统计全部行</Text>}
                {form.conditions.map((c) => (
                  <Space.Compact key={c.id} className="w-full">
                    <Select className="!w-48" value={c.column} onChange={(v) => m.updateCondition(c.id, { column: v })}
                      options={m.dataset?.columns.map((col) => ({ value: col.name, label: col.comment }))} />
                    <Select className="!w-32" value={c.operator} onChange={(v) => m.updateCondition(c.id, { operator: v })}
                      options={OPERATORS.map((o) => ({ value: o.id, label: o.label }))} />
                    <Input value={c.value} disabled={c.operator === "is_null" || c.operator === "not_null"}
                      onChange={(e) => m.updateCondition(c.id, { value: e.target.value })}
                      placeholder={c.operator === "in" ? "多个值用逗号分隔" : c.operator === "between" ? "起, 止" : "值"} />
                    <Button icon={<Trash2 size={15} />} onClick={() => m.removeCondition(c.id)} aria-label="删除条件" />
                  </Space.Compact>
                ))}
                <Button type="dashed" icon={<Plus size={15} />} onClick={m.addCondition} className="self-start">添加条件（同时满足）</Button>
              </div>

              <Title level={5}>时间</Title>
              <Form.Item label="时间字段"
                extra={m.dates.length === 0 ? "该数据集没有日期类列，指标不按时间统计"
                  : m.dataset?.snapshotColumn
                    ? `每日快照表：选 ${m.dataset.snapshotColumn} 时每个周期取最后一个有数据的日期；选其他日期或不选时只取最新一天`
                    : "决定按哪个日期把数据归到周期；不选则不按时间"}>
                <Select allowClear placeholder={m.dates.length ? "不按时间" : "没有可选的日期列"} disabled={m.dates.length === 0}
                  value={form.timeField} onChange={(v) => m.patch({ timeField: v ?? null })}
                  options={m.dates.map((c) => ({ value: c.name, label: `${c.comment}（${c.name}）${c.name === m.dataset?.snapshotColumn ? " · 快照日期" : ""}` }))} />
              </Form.Item>
            </>
          )}

          <Title level={5} className="!mt-2">SQL 参考</Title>
          {"sql" in sql
            ? <pre className="mb-4 overflow-auto rounded-md bg-surface-soft p-3 font-mono text-[13px] leading-5">{sql.sql}</pre>
            : <Alert className="mb-4" type={m.dataset?.readable === false ? "warning" : "info"} showIcon message={sql.reason} />}

          <Title level={5}>数值预览</Title>
          <PreviewPanel m={m} ran={ran?.result ?? null} stale={stale} onRun={run} />
          {!m.dataset && <Empty />}
        </Form>
      </Drawer>
    </div>
  );
}

mount(<App />);
