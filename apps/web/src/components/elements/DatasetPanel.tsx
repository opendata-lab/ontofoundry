import { Alert, Button, Descriptions, Empty, Form, Input, Modal, Radio, Table, Typography } from "antd";
import { useConnectionNames } from "../../hooks/useConnectionNames";
import { Eye, ScanLine } from "lucide-react";
import { useRef, useState } from "react";
import { datasetApi } from "../../api/client";
import type { Dataset, DatasetCheckResult, DatasetPreview, Draft } from "../../api/types";
import { upsert, metricsOnDataset } from "../../lib/coreModel";
import type { ElementRequest, ElementTab } from "../../lib/elementInspector";
import { ContentBlock, SectionTitle, SourceFieldsLayout } from "../layout";
import { ElementLink } from "./ElementPanels";
import { DatasetLocationFields } from "./DatasetLocationFields";
import { DatasetSnapshotFields } from "../DatasetSnapshotFields";

const { Text, Paragraph } = Typography;

export function DatasetPanel({ draft, dataset, editing, change, open, tab = "basic", canPreview = false, revision }: {
  draft: Draft; dataset: Dataset; editing: boolean; change: (next: Draft) => void; open: (request: ElementRequest) => void;
  tab?: ElementTab; canPreview?: boolean; revision?: number | null;
}) {
  const [checked, setChecked] = useState<{ signature: string; result: DatasetCheckResult } | null>(null);
  const [preview, setPreview] = useState<{ signature: string; result: DatasetPreview } | null>(null);
  const [busy, setBusy] = useState<"validate" | "preview" | null>(null);
  const [error, setError] = useState("");
  const generation = useRef(0);
  const signature = JSON.stringify(dataset);
  const currentSignature = useRef(signature);
  currentSignature.current = signature;
  const result = checked?.signature === signature ? checked.result : null;
  const rows = preview?.signature === signature ? preview.result : null;
  const connectionNames = useConnectionNames(draft.workspace_id);
  const update = (patch: Partial<Dataset>) => {
    generation.current += 1;
    setBusy(null);
    setError("");
    change(upsert(draft, "datasets", { ...dataset, ...patch }));
  };
  const check = async (showPreview = false) => {
    if (showPreview && !canPreview) return;
    const attempt = ++generation.current;
    setBusy(showPreview ? "preview" : "validate");
    setError("");
    try {
      if (showPreview) {
        const value = await datasetApi.preview(draft.workspace_id, dataset);
        if (attempt === generation.current && currentSignature.current === signature) setPreview({ signature, result: value });
      } else {
        const value = await datasetApi.validate(draft.workspace_id, dataset, revision);
        if (attempt !== generation.current || currentSignature.current !== signature) return;
        const next = { ...dataset, columns: value.columns ?? dataset.columns };
        if (value.valid) change(upsert(draft, "datasets", next));
        setChecked({ signature: JSON.stringify(value.valid ? next : dataset), result: value });
      }
    } catch (problem) {
      if (attempt === generation.current) setError(problem instanceof Error ? problem.message : "来源校验失败");
    } finally {
      if (attempt === generation.current) setBusy(null);
    }
  };
  const source = dataset.source_kind === "query";
  const objects = draft.object_types.filter((object) => draft.mappings.some((mapping) => mapping.type_id === object.id && mapping.sources.some((item) => item.dataset_id === dataset.id)));
  const links = draft.link_types.filter((link) =>
    (link.data_join?.kind === "mapping_table" && link.data_join.dataset_id === dataset.id) ||
    draft.mappings.some((mapping) => {
      const binding = mapping.inherited_link_bindings[link.id];
      return binding?.kind === "mapping_table" && binding.dataset_id === dataset.id;
    }));

  if (tab === "fields") return <SourceFieldsLayout source={<div className="flex min-w-0 flex-col gap-4">
    {error && <Alert type="error" showIcon message={error} />}
    <ContentBlock className="source-fields-source" data-dataset-section="source">
      <SectionTitle title="来源定义">
        <Button size="small" icon={<ScanLine size={14} />} loading={busy === "validate"} disabled={!!busy || !dataset.connection_id} onClick={() => void check()}>校验并探测列</Button>
      </SectionTitle>
      {editing ? <Form layout="vertical" component="div" size="small">
        <Form.Item label="来源方式"><Radio.Group value={dataset.source_kind ?? "table"} options={[{ label: "基于表", value: "table" }, { label: "基于表达式", value: "query" }]} onChange={(event) => Modal.confirm({ title: "切换来源方式", content: "切换后需重新选择表或填写 SQL，并重新探测列。", okText: "切换", cancelText: "取消", onOk: () => update({ source_kind: event.target.value, schema_name: null, table_name: event.target.value === "table" ? "" : null, query_sql: event.target.value === "query" ? "" : null, columns: null, snapshot_date_column: null }) })} /></Form.Item>
        <DatasetLocationFields workspaceId={draft.workspace_id} dataset={dataset} nameField={null} onChange={update} />
        {source && <Form.Item label="只读 SELECT" className="mb-0" extra="支持非递归 CTE、JOIN、UNION；只能使用同一连接的已登记表。"><Input.TextArea aria-label="数据集 SQL" value={dataset.query_sql ?? ""} autoSize={{ minRows: 4, maxRows: 20 }} onChange={(event) => update({ query_sql: event.target.value, columns: null })} /></Form.Item>}
      </Form> : <>
        <Descriptions size="small" column={1} items={[
          { key: "kind", label: "来源方式", children: source ? "基于表达式" : "基于表" },
          { key: "table", label: "表位置", children: source ? "只读 SELECT" : [dataset.schema_name, dataset.table_name].filter(Boolean).join(".") || "未指定" },
        ]} />
        {source && <Paragraph className="mb-0 whitespace-pre-wrap break-words font-mono">{dataset.query_sql}</Paragraph>}
      </>}
    </ContentBlock>
    {result && <ContentBlock>
      <SectionTitle title="校验结果" />
      <Alert type={result.valid ? "success" : "error"} showIcon message={result.valid ? "来源校验通过" : "来源尚未就绪"} />
      {result.diagnostics.length > 0 && <Table size="small" rowKey={(diagnostic) => diagnostic.code + diagnostic.path} pagination={false} dataSource={result.diagnostics} columns={[{ title: "位置", dataIndex: "path" }, { title: "说明", dataIndex: "message" }]} />}
    </ContentBlock>}
    </div>} fields={<ContentBlock data-dataset-section="columns">
      <SectionTitle title="字段结构" note={`${dataset.columns?.length ?? 0} 个`} />
      <Table size="small" rowKey="name" pagination={false} dataSource={dataset.columns ?? []} locale={{ emptyText: <Empty description="请先校验并探测列" /> }} columns={[
        { title: "列名", dataIndex: "name", render: (value: string) => <code>{value}</code> },
        { title: "物理类型", dataIndex: "physical_type" },
        { title: "注释", dataIndex: "comment" },
        { title: "用途", key: "usage", render: (_, column) => [column.name === dataset.snapshot_date_column ? "快照日期" : "", ...draft.metrics.filter((metric) => metric.kind !== "ratio" && metric.dataset_id === dataset.id && metric.time_field?.column === column.name).map(() => "指标时间")].filter(Boolean).join("、") || "—" },
      ]} />
    </ContentBlock>}>
    {canPreview && <ContentBlock data-dataset-section="preview">
      <SectionTitle title="数据预览">
        <Button size="small" icon={<Eye size={14} />} loading={busy === "preview"} disabled={!!busy || !dataset.connection_id} onClick={() => void check(true)}>预览前 20 行</Button>
      </SectionTitle>
      <Text type="secondary" className="text-xs">按当前权限执行只读查询，不统计全表行数。</Text>
      {rows ? <Table size="small" rowKey={(_, index) => String(index)} pagination={false} dataSource={rows.items} columns={rows.columns.map((column) => ({ title: column.name, dataIndex: column.name, render: (value: unknown) => value == null ? "—" : String(value) }))} scroll={{ x: true }} /> : <Empty description="点击预览查看样例数据" />}
    </ContentBlock>}
  </SourceFieldsLayout>;

  return <div className="flex flex-col gap-4">
    <ContentBlock>
      <SectionTitle title="基本信息" />
      <Form component="div" size="small"><Descriptions column={2} size="small" items={[
        { key: "name", label: "名称", children: editing ? <Input aria-label="数据集名称" value={dataset.display_name ?? ""} onChange={(event) => update({ display_name: event.target.value })} /> : dataset.display_name || dataset.name },
        { key: "id", label: "英文标识", children: editing ? <Input aria-label="数据集英文标识" value={dataset.name} onChange={(event) => update({ name: event.target.value })} /> : dataset.name },
        { key: "source", label: "来源方式", children: source ? "基于表达式" : "基于表" },
        { key: "connection", label: "连接", children: dataset.connection_id ? connectionNames.get(dataset.connection_id) ?? "已绑定连接" : "未绑定连接" },
        { key: "dialect", label: "引擎", children: dataset.dialect ?? "未指定" },
        { key: "snapshot", label: "快照日期列", children: editing ? <DatasetSnapshotFields dataset={dataset} onChange={update} /> : dataset.snapshot_date_column ?? "不是快照" },
        { key: "description", label: "描述", span: 2, children: editing ? <Input.TextArea aria-label="数据集描述" value={dataset.description} autoSize={{ minRows: 1, maxRows: 6 }} onChange={(event) => update({ description: event.target.value })} /> : dataset.description || "暂无描述" },
      ]} /></Form>
    </ContentBlock>
    <div className="flex flex-col gap-4" data-dataset-section="references">
      {([{ label: "对象映射", kind: "object_type", items: objects }, { label: "关系映射", kind: "link_type", items: links }, { label: "指标", kind: "metric", items: metricsOnDataset(draft, dataset.id) }] as const).map((group) => <ContentBlock key={group.kind}>
        <SectionTitle title={group.label} note={`${group.items.length} 个引用`} />
        {group.items.length ? <Table size="small" rowKey="id" pagination={false} dataSource={[...group.items]} columns={[{ title: "名称", key: "name", render: (_, item) => <ElementLink onClick={() => open({ kind: group.kind, id: item.id })}>{item.display_name || item.name}</ElementLink> }]} /> : <Text type="secondary">暂无引用</Text>}
      </ContentBlock>)}
    </div>
  </div>;
}
