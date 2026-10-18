import { Alert, Descriptions, Form, Input, Select, Table, Tag, Typography } from "antd";
import { SectionTitle } from "../layout";
import type { Dataset, Draft } from "../../api/types";
import { DATE_KINDS, physicalValueKind, upsert } from "../../lib/coreModel";
import { DIALECTS } from "../../lib/datasetEditing";
import type { ElementRequest } from "../../lib/elementInspector";
import { ElementLink } from "./ElementPanels";

const { Text, Paragraph } = Typography;


const location = (d: Dataset) => [d.schema_name, d.table_name].filter(Boolean).join(".");

function ColumnsTable({ dataset }: { dataset: Dataset }) {
  if (!dataset.columns)
    return <Alert type="info" showIcon message="没有登记列清单。从数据目录重新登记可以带入列和注释。" />;
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
  const dateColumns = (dataset.columns ?? []).filter((c) => {
    const kind = physicalValueKind(c.physical_type ?? null);
    return kind === null || DATE_KINDS.has(kind);
  });
  if (editing)
    return (
      <div className="flex max-w-settings flex-col gap-4">
        <Form layout="vertical" component="div" requiredMark>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item label="名称" required>
              <Input aria-label="数据集名称" value={dataset.name} onChange={(e) => update({ name: e.target.value })} />
            </Form.Item>
            <Form.Item label="数据库类型">
              <Select
                aria-label="数据库类型"
                allowClear
                placeholder="未指定"
                value={dataset.dialect ?? undefined}
                options={DIALECTS}
                onChange={(dialect?: string) => update({ dialect: dialect ?? null })}
              />
            </Form.Item>
          </div>
          <div className="grid grid-cols-2 gap-x-4">
            <Form.Item label="库 / schema">
              <Input
                aria-label="库或 schema"
                className="font-mono"
                value={dataset.schema_name ?? ""}
                onChange={(e) => update({ schema_name: e.target.value.trim() || null })}
              />
            </Form.Item>
            <Form.Item label="表或视图" required>
              <Input
                aria-label="表或视图"
                className="font-mono"
                value={dataset.table_name}
                onChange={(e) => update({ table_name: e.target.value.trim() })}
              />
            </Form.Item>
          </div>
          <Form.Item label="描述">
            <Input.TextArea
              aria-label="数据集描述"
              autoSize={{ minRows: 2, maxRows: 6 }}
              placeholder="一行代表什么、数据范围和更新方式"
              value={dataset.description}
              onChange={(e) => update({ description: e.target.value })}
            />
          </Form.Item>
          <Form.Item
            label="每日快照日期列"
            extra="表里每天保存一份全量时选择；浏览实例和不按时间的指标只取最新一天。"
          >
            {dataset.columns ? (
              <Select
                aria-label="每日快照日期列"
                allowClear
                placeholder="不是快照表"
                value={dataset.snapshot_date_column ?? undefined}
                options={dateColumns.map((c) => ({ value: c.name, label: c.comment ? `${c.comment}（${c.name}）` : c.name }))}
                onChange={(column?: string) => update({ snapshot_date_column: column ?? null })}
              />
            ) : (
              <Input
                aria-label="每日快照日期列"
                className="font-mono"
                placeholder="不是快照表"
                value={dataset.snapshot_date_column ?? ""}
                onChange={(e) => update({ snapshot_date_column: e.target.value.trim() || null })}
              />
            )}
          </Form.Item>
        </Form>
        <section className="flex flex-col gap-3 border-t border-rule pt-4">
          <SectionTitle title="列清单" />
          <ColumnsTable dataset={dataset} />
        </section>
      </div>
    );
  return (
    <div className="flex max-w-settings flex-col gap-4">
      {dataset.description ? (
        <Paragraph className="m-0 whitespace-pre-wrap">{dataset.description}</Paragraph>
      ) : (
        <Text type="secondary">暂无描述</Text>
      )}
      <Descriptions
        size="small"
        column={2}
        items={[
          { key: "location", label: "物理位置", children: <code>{location(dataset)}</code> },
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
        <SectionTitle title="列清单" />
        <ColumnsTable dataset={dataset} />
      </section>
    </div>
  );
}
