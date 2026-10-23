import { Checkbox, Form, Select } from "antd";
import type { Dataset } from "../api/types";
import { DATE_KINDS, physicalValueKind } from "../lib/coreModel";

/** A blank column is an unfinished form value, never a persisted snapshot flag. */
export function DatasetSnapshotFields({ dataset, onChange }: {
  dataset: Pick<Dataset, "columns" | "snapshot_date_column">;
  onChange: (patch: Partial<Dataset>) => void;
}) {
  const enabled = dataset.snapshot_date_column != null;
  const columns = (dataset.columns ?? []).filter((column) => {
    const kind = physicalValueKind(column.physical_type ?? null);
    return kind === null || DATE_KINDS.has(kind) || kind === "string" || kind === "integer";
  });
  return <>
    <Form.Item extra="每天保存一份全量数据时启用。">
      <Checkbox aria-label="快照表" checked={enabled}
        onChange={(event) => onChange({ snapshot_date_column: event.target.checked ? "" : null })}>快照表</Checkbox>
    </Form.Item>
    {enabled && <Form.Item label="快照日期字段" required extra={
      !dataset.columns ? "请先选择表并读取字段。" : "日期类，或可按日期排序的文本/整数列（如 2026-10-23、20261023）"
    }>
      <Select aria-label="快照日期字段" showSearch optionFilterProp="label" disabled={!dataset.columns}
        placeholder="选择快照日期字段" value={dataset.snapshot_date_column || undefined}
        notFoundContent="没有可选的快照日期字段"
        options={columns.map((column) => ({ value: column.name, label: column.comment ? `${column.comment}（${column.name}）` : column.name }))}
        onChange={(column: string) => onChange({ snapshot_date_column: column })} />
    </Form.Item>}
  </>;
}
