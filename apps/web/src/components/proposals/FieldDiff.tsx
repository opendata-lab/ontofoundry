import { Table, Tooltip, Typography } from "antd";
import type { ReactNode } from "react";
import type { FieldChange } from "../../api/types";
import { parseActionField, type ActionFieldLine } from "../../lib/actionFormat";
import { LOCKED_PROPOSAL_FIELDS } from "../../lib/elementKinds";
import { fieldLabel } from "./elementMeta";
import { InlineValueEditor } from "./InlineValueEditor";
import { valueText } from "./reviewMeta";

const { Text } = Typography;

// References and identity are chosen elsewhere (source issues, relations), not typed in.
const LOCKED = LOCKED_PROPOSAL_FIELDS;

const isEmpty = (value: unknown) =>
  value === null || value === undefined || value === "" || (Array.isArray(value) && value.length === 0);

/** Renders parsed action parameter/effect lines with resolved names and UUID tooltips. */
export function ActionFieldLines({ lines }: { lines: ActionFieldLine[] }) {
  return (
    <span className="flex flex-col gap-0.5">
      {lines.map((line) => (
        <span key={line.key}>
          {line.prefix}
          {line.refId ? (
            <Tooltip title={line.refId}>
              <span>{line.targetLabel}</span>
            </Tooltip>
          ) : (
            line.targetLabel
          )}
          {line.suffix}
        </span>
      ))}
    </span>
  );
}

const cell = (
  path: string,
  value: unknown,
  removed: boolean,
  names?: Map<string, string>,
  actionNames?: Map<string, string>,
) => {
  if (isEmpty(value)) return <Text type="secondary">（空）</Text>;
  const actionLines = parseActionField(path, value, actionNames ?? names);
  return (
    <span className={`text-xs whitespace-pre-wrap break-all ${removed ? "text-danger line-through" : "text-success"}`}>
      {/* Shown by name; the change itself is the id, kept in the tooltip for same-named items. */}
      {actionLines !== null
        ? <ActionFieldLines lines={actionLines} />
        : typeof value === "string" && names?.has(value)
          ? <Tooltip title={value}><span>{names.get(value)}</span></Tooltip>
          : valueText(value)}
    </span>
  );
};

/** Field-by-field before/after, reused by proposals and the publish preview. */
export function FieldDiff({
  changes,
  beforeLabel = "当前值",
  afterLabel = "提案值",
  limit,
  names,
  beforeNames,
  actionNames,
  beforeActionNames,
  onEdit,
  editDisabled = false,
  annotations = {},
}: {
  changes: FieldChange[];
  beforeLabel?: string;
  afterLabel?: string;
  limit?: number;
  /** Element names by id, so reference fields read as names (after side). */
  names?: Map<string, string>;
  /** Element names for the before column; defaults to `names`. */
  beforeNames?: Map<string, string>;
  /** Qualified names (`owner.property`, `link（src → tgt）`) for action parameters/effects (after side). */
  actionNames?: Map<string, string>;
  /** Qualified names for action parameters/effects (before side); defaults to `actionNames ?? beforeNames ?? names`. */
  beforeActionNames?: Map<string, string>;
  /** Save one proposed value in place; omitted for read-only diffs. */
  onEdit?: (path: string, value: unknown) => Promise<boolean>;
  editDisabled?: boolean;
  /** Status shown right of a proposed value, e.g. an unsynced table with its fix. */
  annotations?: Record<string, ReactNode>;
}) {
  const rows = limit ? changes.slice(0, limit) : changes;
  if (!rows.length) return null;
  const resolvedBefore = beforeNames ?? names;
  const resolvedAfterAction = actionNames ?? names;
  const resolvedBeforeAction = beforeActionNames ?? actionNames ?? resolvedBefore;
  return (
    <div className="flex flex-col gap-1">
      <Table
        size="small"
        rowKey="path"
        pagination={false}
        dataSource={rows}
        columns={[
          { title: "字段", key: "path", width: 140, render: (_, c) => fieldLabel(c.path) },
          { title: beforeLabel, key: "before", render: (_, c) => cell(c.path, c.before, true, resolvedBefore, resolvedBeforeAction) },
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
                    display={cell(c.path, c.after, false, names, resolvedAfterAction)}
                    disabled={editDisabled}
                    onSave={(next) => onEdit(c.path, next)}
                  />
                ) : (
                  cell(c.path, c.after, false, names, resolvedAfterAction)
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
