import "@ant-design/v5-patch-for-react-19";
import "./antd.css";
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Alert, Button, ConfigProvider, Drawer, Empty, Form, Input, Segmented, Select, Space, Table, Tag, Typography,
} from "antd";
import { StyleProvider } from "@ant-design/cssinjs";
import zhCN from "antd/locale/zh_CN";
import { Plus, Trash2 } from "lucide-react";
import { DATASETS, KINDS, OPERATORS, datasetOf, formatNumber, kindLabel } from "../shared/model";
import { Sparkline, useMetricForm } from "../shared/useMetricForm";

function App() {
  const m = useMetricForm();
  const [open, setOpen] = useState(false);
  const { form } = m;
  const showColumn = form.kind !== "count" && form.kind !== "ratio" && form.kind !== "expression";

  return (
    <div className="mx-auto max-w-[1180px] p-6">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <Typography.Title level={4} className="!m-0">语义视图 · 指标</Typography.Title>
          <Typography.Text type="secondary">Ant Design 5 + Tailwind v4</Typography.Text>
        </div>
        <Button type="primary" icon={<Plus size={16} />} onClick={() => setOpen(true)}>新建指标</Button>
      </header>

      <Table
        rowKey="id"
        size="middle"
        pagination={false}
        dataSource={m.metrics}
        columns={[
          { title: "指标", dataIndex: "name", render: (v: string) => <span className="font-medium">{v}</span> },
          { title: "数据集", dataIndex: "datasetId", render: (id: string) => datasetOf(id)?.name },
          { title: "计算方式", dataIndex: "kind", render: (k) => <Tag>{kindLabel(k)}</Tag> },
          { title: "列", dataIndex: "column", render: (c?: string) => (c ? <code>{c}</code> : "—") },
          { title: "时间字段", dataIndex: "timeField", render: (c?: string) => c ?? "不按时间" },
          { title: "说明", dataIndex: "description", ellipsis: true },
        ]}
      />

      <Drawer
        title="新建指标"
        width={760}
        open={open}
        onClose={() => setOpen(false)}
        footer={
          <div className="flex justify-end gap-2">
            <Button onClick={() => { m.reset(); setOpen(false); }}>取消</Button>
            <Button type="primary" disabled={!m.canSave} onClick={() => m.save() && setOpen(false)}>保存为提案</Button>
          </div>
        }
      >
        <Form layout="vertical" requiredMark="optional">
          <Typography.Title level={5}>基本信息</Typography.Title>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item label="名称" required>
              <Input value={form.name} onChange={(e) => m.patch({ name: e.target.value })} placeholder="例如：已完成订单金额" />
            </Form.Item>
            <Form.Item label="同义词">
              <Select
                mode="tags"
                value={form.synonyms}
                onChange={(v: string[]) => m.patch({ synonyms: v })}
                placeholder="输入后回车"
                open={false}
                suffixIcon={null}
              />
            </Form.Item>
          </div>
          <Form.Item label="说明">
            <Input.TextArea rows={2} value={form.description} onChange={(e) => m.patch({ description: e.target.value })} />
          </Form.Item>

          <Typography.Title level={5}>数据集与算法</Typography.Title>
          <Form.Item label="数据集" required extra={m.dataset && (
            <span>{m.dataset.rowMeaning}{m.dataset.snapshotColumn && <Tag color="blue" className="ml-2">每日快照 · {m.dataset.snapshotColumn}</Tag>}</span>
          )}>
            <Select
              showSearch
              value={form.datasetId}
              onChange={m.setDataset}
              optionFilterProp="label"
              options={DATASETS.map((d) => ({ value: d.id, label: `${d.name} ${d.table}` }))}
              optionRender={(o) => {
                const d = datasetOf(o.value as string)!;
                return (
                  <div className="flex flex-col py-0.5">
                    <span>{d.name}</span>
                    <span className="text-xs text-muted">{d.table} · {d.rowMeaning}</span>
                  </div>
                );
              }}
              labelRender={(o) => datasetOf(o.value as string)?.name}
            />
          </Form.Item>
          <Form.Item label="计算方式" required>
            <Segmented
              value={form.kind}
              onChange={(v) => m.setKind(v as typeof form.kind)}
              options={KINDS.map((k) => ({ value: k.id, label: k.label }))}
              className="flex-wrap"
            />
          </Form.Item>

          {showColumn && (
            <Form.Item label="列" required>
              <Select
                value={form.column}
                onChange={(v) => m.patch({ column: v })}
                options={m.columns.map((c) => ({ value: c.name, label: `${c.comment}（${c.name}）` }))}
              />
            </Form.Item>
          )}

          {form.kind === "ratio" && (
            <div className="grid grid-cols-2 gap-x-4">
              {(["numeratorId", "denominatorId"] as const).map((key) => {
                const picked = m.metricById(form[key]);
                return (
                  <Form.Item key={key} label={key === "numeratorId" ? "分子" : "分母"} required
                    extra={picked && `时间口径：${picked.timeField ?? "不按时间"}`}>
                    <Select
                      value={form[key]}
                      onChange={(v) => m.patch({ [key]: v })}
                      placeholder="选择同一数据集上的指标"
                      options={m.components.map((x) => ({ value: x.id, label: x.name }))}
                    />
                  </Form.Item>
                );
              })}
            </div>
          )}

          {form.kind === "expression" && (
            <Form.Item label="表达式" required extra="只能引用所选数据集的列">
              <Input.TextArea
                rows={3}
                className="font-mono"
                value={form.expression}
                onChange={(e) => m.patch({ expression: e.target.value })}
                placeholder="SUM(CASE WHEN status = '已完成' THEN amount END)"
              />
            </Form.Item>
          )}

          {form.kind !== "ratio" && (
            <>
              <Typography.Title level={5}>条件</Typography.Title>
              <div className="mb-4 flex flex-col gap-2">
                {form.conditions.length === 0 && <Typography.Text type="secondary">没有条件，统计全部行</Typography.Text>}
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
                <Button type="dashed" icon={<Plus size={15} />} onClick={m.addCondition} className="self-start">添加条件</Button>
              </div>

              <Typography.Title level={5}>时间</Typography.Title>
              <Form.Item label="时间字段" extra={
                m.dataset?.snapshotColumn
                  ? `该数据集是每日快照：按 ${m.dataset.snapshotColumn} 时每个周期取最后一天；选其他字段或不选时只取最新一天`
                  : "决定按哪个日期把数据归到周期；不选则不按时间"
              }>
                <Select allowClear placeholder="不按时间" value={form.timeField} onChange={(v) => m.patch({ timeField: v ?? null })}
                  options={m.dates.map((c) => ({ value: c.name, label: `${c.comment}（${c.name}）` }))} />
              </Form.Item>
            </>
          )}

          <Typography.Title level={5}>SQL 参考</Typography.Title>
          {"sql" in m.sql
            ? <pre className="mb-4 overflow-auto rounded-md bg-surface-soft p-3 font-mono text-[13px] leading-5">{m.sql.sql}</pre>
            : <Alert className="mb-4" type="info" showIcon message={m.sql.reason} />}

          <Typography.Title level={5}>数值预览</Typography.Title>
          {m.result.ok ? (
            <div className="flex items-center gap-8 rounded-md border border-rule p-4">
              <div>
                <div className="text-xs text-muted">{form.timeField ? "全部周期" : "当前值"}</div>
                <div className="text-3xl font-semibold text-ink">{formatNumber(m.result.total)}</div>
              </div>
              {m.result.trend && m.result.trend.length > 1 ? (
                <div className="text-accent">
                  <Sparkline points={m.result.trend} />
                  <div className="flex justify-between text-xs text-muted">
                    {m.result.trend.map((p) => <span key={p.month}>{p.month.slice(5)}月 {formatNumber(p.value)}</span>)}
                  </div>
                </div>
              ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="选择时间字段后显示按月趋势" />}
            </div>
          ) : <Alert type="warning" showIcon message={`无法预览：${m.result.reason}`} />}
        </Form>
      </Drawer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <StyleProvider layer>
      <ConfigProvider
        locale={zhCN}
        theme={{
          token: {
            colorPrimary: "#0061ef",
            colorText: "#20252d",
            colorTextSecondary: "#67717e",
            colorBorder: "#e3e9f1",
            colorBgLayout: "#f5f7fb",
            borderRadius: 6,
            fontFamily: '"PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif',
          },
        }}
      >
        <App />
      </ConfigProvider>
    </StyleProvider>
  </StrictMode>,
);
