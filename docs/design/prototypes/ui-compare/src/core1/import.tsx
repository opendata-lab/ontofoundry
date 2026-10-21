import { useMemo, useState } from "react";
import {
  Alert, Button, Descriptions, Modal, Radio, Result, Select, Statistic, Steps, Table, Tabs, Tag, Typography, Upload,
} from "antd";
import { FileJson, FileText, Inbox, Upload as UploadIcon } from "lucide-react";
import { mount } from "./shell";

const { Text, Title, Paragraph } = Typography;

type Outcome = "converted" | "dropped" | "error";
type Severity = "info" | "warning" | "error";

interface Item {
  id: string;
  line: string;
  construct: string;
  name: string;
  outcome: Outcome;
  severity: Severity;
  rule?: string;
  message: string;
  target?: string;
  change?: "create" | "update" | "same";
  original: string;
  /** Needs a person (or later AI completion) before a proposal can be formed. */
  pending?: "pick_dataset" | "rewrite";
}

const ITEMS: Item[] = [
  { id: "i1", line: "4–18", construct: "概念", name: "订单", outcome: "converted", severity: "info", message: "转为业务对象 sales_order", target: "订单", change: "update", original: "- concept: Order\n  type: EntityType\n  identify_by: [order_no]" },
  { id: "i2", line: "19–30", construct: "概念", name: "客户", outcome: "converted", severity: "info", message: "转为业务对象 customer", target: "客户", change: "create", original: "- concept: Customer\n  type: EntityType" },
  { id: "i3", line: "31–36", construct: "关系", name: "订单.下单客户", outcome: "converted", severity: "info", message: "转为关系 多对一", target: "下单客户", change: "create", original: "- name: placed_by\n  roles: [{concept: Customer}]\n  multiplicity: ManyToOne" },
  { id: "i4", line: "37–45", construct: "值类型", name: "金额", outcome: "converted", severity: "warning", rule: "RT-24", message: "值类型折叠为 decimal；约束“金额 ≥ 0”转为 2 条属性规则（订单金额、退款金额），导出时不还原值类型", target: "订单金额 / 退款金额", change: "create", original: "- concept: Amount\n  type: ValueType\n  extends: [Decimal]\n  requires: [\"Amount >= 0\"]" },
  { id: "i5", line: "46–60", construct: "多元关系", name: "仓库.运往", outcome: "converted", severity: "warning", rule: "RT-27", message: "转为中间对象“运往”，生成 起点仓库编码、终点仓库编码 两个标识属性（按 ManyToOne）；导出时不还原多元结构", target: "运往", change: "create", original: "- name: ships_to\n  roles: [{concept: Warehouse, name: destination}, {concept: Integer, name: days}]\n  multiplicity: ManyToOne" },
  { id: "i6", line: "61–66", construct: "概念", name: "VIP会员", outcome: "converted", severity: "warning", rule: "RT-34", message: "多父继承只保留第一个父类“客户”；第二个父类“会员”未继承。可在会话中改写为派生条件或关系（需审阅，不是等价转换）", target: "VIP会员", change: "create", original: "- concept: VipMember\n  extends: [Customer, Member]" },
  { id: "i7", line: "67–72", construct: "标识", name: "许可证.identify_by", outcome: "dropped", severity: "warning", rule: "RT-32", message: "标识含关系 acct，整组标识不导入；许可证照常导入但没有标识，需补建“账户编号”属性", target: "许可证", original: "identify_by: [acct, seat_nr]", pending: "rewrite" },
  { id: "i8", line: "88–90", construct: "指标", name: "total_rows", outcome: "error", severity: "error", rule: "RT-61", message: "COUNT(*) 没有指明数据集，文件里有 2 个数据集，选择后生成计数指标", original: "- name: total_rows\n  expression: COUNT(*)", pending: "pick_dataset" },
  { id: "i9", line: "91–95", construct: "指标", name: "east_order_amount", outcome: "error", severity: "error", rule: "RT-69", message: "指标引用了 orders 和 customers 两个数据集，首版不承载跨数据集指标；原文保留，可改写为单个数据集上的指标", original: "- name: east_order_amount\n  expression: SUM(CASE WHEN customers.region = '华东' THEN orders.amount END)", pending: "rewrite" },
  { id: "i10", line: "96–98", construct: "指标", name: "order_amount", outcome: "converted", severity: "info", message: "转为数据集 orders 上的求和指标", target: "订单金额", change: "same", original: "- name: order_amount\n  expression: SUM(orders.amount)" },
  { id: "i11", line: "2", construct: "文档说明", name: "ai_context", outcome: "converted", severity: "info", rule: "RT-02", message: "说明并入工作空间描述", change: "update", original: "ai_context: 订单与客户的销售本体" },
];

const OUTCOME_TAG: Record<Outcome, { color: string; label: string }> = {
  converted: { color: "success", label: "已转换" },
  dropped: { color: "default", label: "未导入" },
  error: { color: "error", label: "错误" },
};
const SEVERITY_TAG: Record<Severity, { color: string; label: string } | null> = {
  info: null, warning: { color: "warning", label: "提醒" }, error: { color: "error", label: "需处理" },
};
const CHANGE_LABEL = { create: "新增", update: "修改", same: "无变化" } as const;

const FILES = [
  { id: "sales", name: "sales-ontology.yaml", format: "ossie", size: "18 KB", ok: true },
  { id: "broken", name: "backup-2026-09.ontofoundry.json", format: "native", size: "42 KB", ok: false },
];

function App() {
  const [open, setOpen] = useState(true);
  const [step, setStep] = useState(0);
  const [format, setFormat] = useState<"ossie" | "native">("ossie");
  const [file, setFile] = useState<string | null>(null);
  const [tab, setTab] = useState("all");
  const [picks, setPicks] = useState<Record<string, string>>({});
  const [done, setDone] = useState(false);
  const chosen = FILES.find((f) => f.id === file);

  const resolved = (i: Item) => i.pending === "pick_dataset" && !!picks[i.id];
  const rows = useMemo(() => ITEMS.filter((i) =>
    tab === "all" ? true : tab === "warning" ? i.severity === "warning" : tab === "pending" ? !!i.pending : i.outcome === tab), [tab]);
  const counts = {
    converted: ITEMS.filter((i) => i.outcome === "converted").length,
    warning: ITEMS.filter((i) => i.severity === "warning").length,
    dropped: ITEMS.filter((i) => i.outcome === "dropped").length,
    error: ITEMS.filter((i) => i.outcome === "error").length,
    pending: ITEMS.filter((i) => i.pending && !resolved(i)).length,
  };
  const proposals = ITEMS.filter((i) => (i.outcome === "converted" && i.change !== "same") || resolved(i));
  const creates = proposals.filter((i) => i.change === "create" || resolved(i)).length;
  const updates = proposals.filter((i) => i.change === "update").length;
  const same = ITEMS.filter((i) => i.change === "same").length;

  const reset = () => { setStep(0); setFile(null); setPicks({}); setDone(false); setTab("all"); };

  return (
    <div className="mx-auto max-w-[1180px] p-6">
      <header className="mb-4 flex items-center justify-between">
        <div>
          <Title level={4} className="!m-0">全局</Title>
          <Text type="secondary">导入会在新的建模会话中生成提案，不直接发布</Text>
        </div>
        <Button type="primary" icon={<UploadIcon size={15} />} onClick={() => { reset(); setOpen(true); }}>导入</Button>
      </header>
      <Alert type="info" showIcon message="点击右上角“导入”打开对话框" />

      <Modal open={open} width={980} title="导入本体" onCancel={() => setOpen(false)} destroyOnHidden
        footer={done ? null : (
          <div className="flex items-center justify-end gap-2">
            {step > 0 && <Button onClick={() => setStep(step - 1)}>上一步</Button>}
            <Button onClick={() => setOpen(false)}>取消</Button>
            {step === 0 && <Button type="primary" disabled={!file} onClick={() => setStep(1)}>转换并查看报告</Button>}
            {step === 1 && <Button type="primary" disabled={!chosen?.ok} onClick={() => setStep(2)}>下一步</Button>}
            {step === 2 && <Button type="primary" onClick={() => setDone(true)}>生成提案并进入会话</Button>}
          </div>
        )}>
        <Steps size="small" current={done ? 3 : step} className="!mb-6" items={[{ title: "选择文件" }, { title: "转换报告" }, { title: "确认" }]} />

        {step === 0 && (
          <div className="flex flex-col gap-4">
            <div>
              <Text strong>格式</Text>
              <Radio.Group className="!mt-2 !flex gap-3" value={format} onChange={(e) => { setFormat(e.target.value); setFile(null); }}>
                <Radio.Button value="ossie"><span className="inline-flex items-center gap-1"><FileText size={14} />Apache Ossie（YAML / JSON）</span></Radio.Button>
                <Radio.Button value="native"><span className="inline-flex items-center gap-1"><FileJson size={14} />OntoFoundry 原生单文件</span></Radio.Button>
              </Radio.Group>
            </div>
            <Upload.Dragger beforeUpload={() => false} showUploadList={false} openFileDialogOnClick={false}>
              <div className="flex flex-col items-center gap-2 py-4 text-muted">
                <Inbox size={32} />
                <span>拖入文件，或从下面的示例文件中选择（原型）</span>
              </div>
            </Upload.Dragger>
            <div className="flex flex-col gap-2">
              {FILES.filter((f) => f.format === format).map((f) => (
                <label key={f.id} className={`flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2 ${file === f.id ? "border-accent bg-accent-soft" : "border-rule"}`}>
                  <Radio checked={file === f.id} onChange={() => setFile(f.id)} />
                  <span className="font-medium">{f.name}</span>
                  <Text type="secondary" className="text-xs">{f.size}</Text>
                </label>
              ))}
            </div>
            <Alert type="info" showIcon message="导入只新增和修改，不会删除已有内容"
              description="需要删除时，在会话中手动删除或让 AI 提出删除提案，照常审阅。" />
          </div>
        )}

        {step === 1 && chosen && !chosen.ok && (
          <Result status="error" title="文件无法读取，没有生成任何内容"
            subTitle="schema_version 为 core-0（不支持的版本）。文件级错误会让整份文件停止转换，请确认文件来源或导出版本。"
            extra={<Button onClick={() => setStep(0)}>重新选择文件</Button>} />
        )}

        {step === 1 && chosen?.ok && (
          <div className="flex flex-col gap-4">
            <Descriptions size="small" column={3} items={[
              { label: "文件", children: chosen.name },
              { label: "格式", children: "Apache Ossie" },
              { label: "条目", children: `${ITEMS.length} 条` },
            ]} />
            <div className="grid grid-cols-5 gap-3">
              <Statistic title="已转换" value={counts.converted} valueStyle={{ color: "#127a45" }} />
              <Statistic title="其中有提醒" value={counts.warning} valueStyle={{ color: "#ad6800" }} />
              <Statistic title="未导入" value={counts.dropped} />
              <Statistic title="错误" value={counts.error} valueStyle={{ color: "#b42318" }} />
              <Statistic title="待补全" value={counts.pending} valueStyle={{ color: "#0061ef" }} />
            </div>
            <Tabs activeKey={tab} onChange={setTab} items={[
              { key: "all", label: `全部 ${ITEMS.length}` },
              { key: "converted", label: `已转换 ${counts.converted}` },
              { key: "warning", label: `有提醒 ${counts.warning}` },
              { key: "dropped", label: `未导入 ${counts.dropped}` },
              { key: "error", label: `错误 ${counts.error}` },
              { key: "pending", label: `待补全 ${ITEMS.filter((i) => i.pending).length}` },
            ]} />
            <Table size="small" rowKey="id" pagination={false} dataSource={rows}
              expandable={{ expandedRowRender: (i) => (
                <div className="flex flex-col gap-1">
                  <Text type="secondary" className="text-xs">原文（第 {i.line} 行）{i.rule ? ` · 规则 ${i.rule}` : ""}</Text>
                  <pre className="m-0 rounded-md bg-surface-soft p-2 font-mono text-xs leading-5">{i.original}</pre>
                </div>
              ) }}
              columns={[
                { title: "位置", dataIndex: "line", width: 70, render: (v: string) => <Text type="secondary">{v}</Text> },
                { title: "原文", width: 190, render: (_: unknown, i: Item) => <div className="flex flex-col"><span>{i.name}</span><Text type="secondary" className="text-xs">{i.construct}</Text></div> },
                { title: "结果", width: 120, render: (_: unknown, i: Item) => (
                  <span className="flex flex-wrap gap-1">
                    <Tag color={OUTCOME_TAG[i.outcome].color}>{OUTCOME_TAG[i.outcome].label}</Tag>
                    {SEVERITY_TAG[i.severity] && i.outcome === "converted" && <Tag color={SEVERITY_TAG[i.severity]!.color}>{SEVERITY_TAG[i.severity]!.label}</Tag>}
                  </span>
                ) },
                { title: "说明", dataIndex: "message" },
                { title: "处理", width: 210, render: (_: unknown, i: Item) => {
                  if (i.pending === "pick_dataset") return (
                    <Select size="small" className="w-full" placeholder="选择数据集" value={picks[i.id]}
                      onChange={(v) => setPicks({ ...picks, [i.id]: v })}
                      options={[{ value: "orders", label: "orders（一行 = 一张订单）" }, { value: "customers", label: "customers（一行 = 一个客户）" }]} />
                  );
                  if (i.pending === "rewrite") return <Text type="secondary" className="text-xs">原文保留，进入会话后手动改写</Text>;
                  if (i.change) return <Tag>{CHANGE_LABEL[i.change]}{i.target ? ` · ${i.target}` : ""}</Tag>;
                  return null;
                } },
              ]} />
          </div>
        )}

        {step === 2 && !done && (
          <div className="flex flex-col gap-4">
            <Paragraph>将创建建模会话 <Text strong>导入 {chosen?.name}</Text>，并生成以下提案：</Paragraph>
            <div className="grid grid-cols-4 gap-3">
              <Statistic title="新增" value={creates} />
              <Statistic title="修改" value={updates} />
              <Statistic title="无变化（不生成提案）" value={same} />
              <Statistic title="待补全（留在报告）" value={counts.pending} />
            </div>
            <Alert type="info" showIcon message="提案在会话的提案面板审阅，接受后进入草稿，再照常在发布面板发布"
              description="原文件保存为一份材料，每条提案附原文行号作为证据。待补全的条目不生成提案，可在会话中手动处理。" />
          </div>
        )}

        {done && (
          <Result status="success" title={`已生成 ${proposals.length} 条提案`}
            subTitle={`会话“导入 ${chosen?.name}”已创建，${counts.pending} 条待补全保留在转换报告中`}
            extra={[<Button type="primary" key="open">打开会话审阅提案</Button>, <Button key="close" onClick={() => setOpen(false)}>关闭</Button>]} />
        )}
      </Modal>
    </div>
  );
}

mount(<App />);
