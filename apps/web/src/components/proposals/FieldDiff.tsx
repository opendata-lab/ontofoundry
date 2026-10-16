import { Table, Typography } from "antd";
import type { FieldChange } from "../../api/types";
import { FIELD_LABELS } from "./elementMeta";
import { valueText } from "./reviewMeta";

const { Text } = Typography;

const isEmpty = (value: unknown) =>
  value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);

const cell = (value: unknown, removed: boolean, names?: Map<string, string>) =>
  isEmpty(value) ? (
    <Text type="secondary">（空）</Text>
  ) : (
    <span className={`text-xs whitespace-pre-wrap break-all ${removed ? "text-danger line-through" : "text-success"}`}>
      {typeof value === "string" && names?.has(value) ? names.get(value) : valueText(value)}
    </span>
  );

/** Field-by-field before/after, reused by proposals and the publish preview. */
export function FieldDiff({
  changes,
  beforeLabel = "当前值",
  afterLabel = "提案值",
  limit,
  names,
}: {
  changes: FieldChange[];
  beforeLabel?: string;
  afterLabel?: string;
  limit?: number;
  /** Element names by id, so reference fields read as names. */
  names?: Map<string, string>;
}) {
  const rows = limit ? changes.slice(0, limit) : changes;
  if (!rows.length) return null;
  return (
    <div className="flex flex-col gap-1">
      <Table
        size="small"
        rowKey="path"
        pagination={false}
        dataSource={rows}
        columns={[
          { title: "字段", key: "path", width: 140, render: (_, c) => FIELD_LABELS[c.path] ?? c.path },
          { title: beforeLabel, key: "before", render: (_, c) => cell(c.before, true, names) },
          { title: afterLabel, key: "after", render: (_, c) => cell(c.after, false, names) },
        ]}
      />
      {limit && changes.length > limit && (
        <Text type="secondary" className="text-xs">
          另有 {changes.length - limit} 处修改
        </Text>
      )}
    </div>
  );
}
