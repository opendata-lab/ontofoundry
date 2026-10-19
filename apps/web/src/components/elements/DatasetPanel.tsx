import { Alert, Descriptions, Form, Input, Table, Tag, Typography } from "antd";
import { SectionTitle } from "../layout";
import type { Dataset, Draft } from "../../api/types";
import { upsert } from "../../lib/coreModel";
import { DIALECTS } from "../../lib/datasetEditing";
import type { ElementRequest } from "../../lib/elementInspector";
import { ElementLink } from "./ElementPanels";
import { DatasetLocationFields } from "./DatasetLocationFields";
import { DatasetSnapshotFields } from "../DatasetSnapshotFields";

const { Text, Paragraph } = Typography;


const location = (d: Dataset) => [d.schema_name, d.table_name].filter(Boolean).join(".");

function ColumnsTable({ dataset }: { dataset: Dataset }) {
  if (!dataset.columns)
    return <Alert type="info" showIcon message="未登记字段。从数据目录重新登记可以带入字段和注释。" />;
  return (
    <Table
      size="small"
      rowKey="name"
      pagination={dataset.columns.length > 20 ? { pageSize: 20, size: "small" } : false}
      dataSource={dataset.columns}
      columns={[
        {
          title: "列",
          key: "name",
          render: (_, c) => (
            <span className="inline-flex items-center gap-2">
              <code>{c.name}</code>
              {c.name === dataset.snapshot_date_column && <Tag className="m-0">快照日期</Tag>}
            </span>
          ),
        },
        { title: "物理类型", key: "type", render: (_, c) => c.physical_type ?? <Text type="secondary">未知</Text> },
        { title: "注释", key: "comment", render: (_, c) => c.comment || <Text type="secondary">—</Text> },
      ]}
    />
  );
}

/**
 * A registered dataset. Location and columns come from catalog registration;
 * here people rename, describe and choose the daily snapshot column.
 */
export function DatasetPanel({
  draft,
  dataset,
  editing,
  change,
  open,
}: {
  draft: Draft;
  dataset: Dataset;
  editing: boolean;
  change: (next: Draft) => void;
  open: (request: ElementRequest) => void;
}) {
  const update = (patch: Partial<Dataset>) => change(upsert(draft, "datasets", { ...dataset, ...patch }));
  const metrics = draft.metrics.filter((m) => m.kind !== "ratio" && m.dataset_id === dataset.id);
  if (editing)
    return (
      <div className="flex min-w-0 flex-col gap-4">
        <Form layout="vertical" component="div" requiredMark className="max-w-settings">
          <SectionTitle title="基本信息" className="mb-4" />
          <DatasetLocationFields workspaceId={draft.workspace_id} dataset={dataset} onChange={update} nameField={
            <Form.Item label="名称" required>
              <Input aria-label="数据集名称" value={dataset.name} onChange={(e) => update({ name: e.target.value })} />
            </Form.Item>
          } />
          <Form.Item label="描述">
            <Input.TextArea
              aria-label="数据集描述"
              autoSize={{ minRows: 2, maxRows: 6 }}
              placeholder="一行代表什么、数据范围和更新方式"
              value={dataset.description}
              onChange={(e) => update({ description: e.target.value })}
            />
          </Form.Item>
          <DatasetSnapshotFields dataset={dataset} onChange={update} />
        </Form>
        <section className="flex flex-col gap-3 border-t border-rule pt-4">
          <SectionTitle title="字段" />
          <ColumnsTable dataset={dataset} />
        </section>
      </div>
    );
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <SectionTitle title="基本信息" />
      {dataset.description ? (
        <Paragraph className="m-0 whitespace-pre-wrap">{dataset.description}</Paragraph>
      ) : (
        <Text type="secondary">暂无描述</Text>
      )}
      <Descriptions
        size="small"
        column={2}
        items={[
          { key: "name", label: "名称", children: dataset.name },
          { key: "location", label: "物理位置", span: 2, children: <code>{location(dataset)}</code> },
          {
            key: "dialect",
            label: "数据库类型",
            children: DIALECTS.find((d) => d.value === dataset.dialect)?.label ?? dataset.dialect ?? "未指定",
          },
          {
            key: "snapshot",
            label: "快照",
            children: dataset.snapshot_date_column ? `每日快照（${dataset.snapshot_date_column}）` : "不是快照表",
          },
          {
            key: "metrics",
            label: "指标",
            children: metrics.length ? (
              <span className="flex flex-wrap gap-x-3">
                {metrics.map((m) => (
                  <ElementLink key={m.id} onClick={() => open({ kind: "metric", id: m.id })}>
                    {m.name}
                  </ElementLink>
                ))}
              </span>
            ) : (
              <Text type="secondary">无</Text>
            ),
          },
        ]}
      />
      <section className="flex flex-col gap-3 border-t border-rule pt-4">
        <SectionTitle title="字段" />
        <ColumnsTable dataset={dataset} />
      </section>
    </div>
  );
}
