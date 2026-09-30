import type { FieldChange } from "../../api/types";
import { FIELD_LABELS } from "./elementMeta";


function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "（空）";
  if (typeof value === "string") return value;
  if (typeof value === "boolean") return value ? "是" : "否";
  if (Array.isArray(value) && value.every((v) => typeof v === "string"))
    return "[" + value.join(", ") + "]";
  return JSON.stringify(value);
}

/** Field-by-field before/after, reused by proposals and the publish preview. */
export function FieldDiff({
  changes,
  beforeLabel = "当前值",
  afterLabel = "提案值",
  limit,
}: {
  changes: FieldChange[];
  beforeLabel?: string;
  afterLabel?: string;
  limit?: number;
}) {
  const rows = limit ? changes.slice(0, limit) : changes;
  if (!rows.length) return null;
  return (
    <table className="field-diff">
      <thead>
        <tr>
          <th>字段</th>
          <th>{beforeLabel}</th>
          <th>{afterLabel}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((change) => (
          <tr key={change.path}>
            <th scope="row">{FIELD_LABELS[change.path] ?? change.path}</th>
            <td>
              <del>{show(change.before)}</del>
            </td>
            <td>
              <ins>{show(change.after)}</ins>
            </td>
          </tr>
        ))}
        {limit && changes.length > limit && (
          <tr>
            <td colSpan={3} className="muted">
              另有 {changes.length - limit} 处修改
            </td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
