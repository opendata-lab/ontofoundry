import { Table, Tooltip, Typography } from "antd";
import type { ReactNode } from "react";
import type { FieldChange } from "../../api/types";
import { fieldLabel } from "./elementMeta";
import { InlineValueEditor } from "./InlineValueEditor";
import { valueText } from "./reviewMeta";

const { Text } = Typography;

// References and identity are chosen elsewhere (source issues, relations), not typed in.
const LOCKED = new Set(["id", "evidence", "extends", "type_id"]);

const isEmpty = (value: unknown) =>
  value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);

const cell = (value: unknown, removed: boolean, names?: Map<string, string>) =>
  isEmpty(value) ? (
    <Text type="secondary">（空）</Text>
  ) : (
    <span className={`text-xs whitespace-pre-wrap break-all ${removed ? "text-danger line-through" : "text-success"}`}>
      {/* Shown by name; the change itself is the id, kept in the tooltip for same-named items. */}
      {typeof value === "string" && names?.has(value) ? <Tooltip title={value}><span>{names.get(value)}</span></Tooltip> : valueText(value)}
    </span>
  );

/** Field-by-field before/after, reused by proposals and the publish preview. */
export function FieldDiff({
  changes,
  beforeLabel = "当前值",
  afterLabel = "提案值",
  limit,
  names,
  onEdit,
  editDisabled = false,
  annotations = {},
}: {
  changes: FieldChange[];
  beforeLabel?: string;
  afterLabel?: string;
  limit?: number;
  /** Element names by id, so reference fields read as names. */
  names?: Map<string, string>;
  /** Save one proposed value in place; omitted for read-only diffs. */
  onEdit?: (path: string, value: unknown) => Promise<boolean>;
  editDisabled?: boolean;
  /** Status shown right of a proposed value, e.g. an unsynced table with its fix. */
  annotations?: Record<string, ReactNode>;
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
          { title: "字段", key: "path", width: 140, render: (_, c) => fieldLabel(c.path) },
          { title: beforeLabel, key: "before", render: (_, c) => cell(c.before, true, names) },
          {
            title: afterLabel,
            key: "after",
            render: (_, c) => {
              const value =
                onEdit && !LOCKED.has(c.path) && !c.path.endsWith("_id") ? (
                  <InlineValueEditor
                    path={c.path}
                    label={fieldLabel(c.path)}
                    value={c.after}
                    display={cell(c.after, false, names)}
                    disabled={editDisabled}
                    onSave={(next) => onEdit(c.path, next)}
                  />
                ) : (
                  cell(c.after, false, names)
                );
              const note = annotations[c.path];
              return note ? (
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">{value}</div>
                  <div className="flex flex-col items-end gap-1">{note}</div>
                </div>
              ) : (
                value
              );
            },
          },
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
