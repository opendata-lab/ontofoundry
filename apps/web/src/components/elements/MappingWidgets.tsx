import { Check, Info, Minus, TriangleAlert, Lock } from "lucide-react";
import { useEffect, useRef } from "react";
import { HintIcon } from "../HintIcon";
import {
  fullField,
  literal,
  shortField,
  sourceColumns,
  type MappingEntry,
} from "../../lib/objectMapping";
import type { SemanticDataset } from "../../api/types";

export function MappingStatusIcon({
  state,
  label,
  onClick,
}: {
  state: "mapped" | "partial" | "unmapped";
  label?: string;
  onClick?: () => void;
}) {
  const text =
    label ??
    { mapped: "已映射", partial: "部分映射", unmapped: "未映射" }[state];
  const icon =
    state === "mapped" ? (
      <Check size={16} />
    ) : state === "partial" ? (
      <TriangleAlert size={16} />
    ) : (
      <Minus size={16} />
    );
  return onClick ? (
    <button
      type="button"
      className={`om-status om-status-${state} icon-button`}
      aria-label={`${text}：查看详情`}
      title={text}
      onClick={onClick}
    >
      {icon}
    </button>
  ) : (
    <span
      className={`om-status om-status-${state}`}
      role="img"
      aria-label={text}
      title={text}
    >
      {icon}
    </span>
  );
}
export function ReadonlyIcon({ reason }: { reason: string | null }) {
  return reason ? (
    <span className="om-readonly" title={reason}>
      <HintIcon icon={Lock} text={`只读：${reason}`} />
    </span>
  ) : null;
}
export function InfoButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className="icon-button om-info"
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.currentTarget.focus();
        onClick();
      }}
    >
      <Info size={14} />
    </button>
  );
}
export function FieldValue({
  entry,
  main,
  shorten = false,
}: {
  entry: MappingEntry;
  main?: SemanticDataset;
  shorten?: boolean;
}) {
  if (!entry.expression) return <span className="muted">未绑定</span>;
  return (
    <span className="om-field-value" title={fullField(entry)}>
      <code>{shorten ? shortField(entry, main) : entry.expression}</code>
      {entry.mode === "constant" && <span className="om-pill">常量</span>}
      {entry.pending && <small className="om-row-message">属性未绑定</small>}
      {shorten &&
        entry.mode === "expression" &&
        shortField(entry, main) !== entry.expression && (
          <small className="om-sub">
            <code>{entry.expression}</code>
          </small>
        )}
    </span>
  );
}
export function FieldEditor({
  entry,
  label,
  onChange,
  native = true,
}: {
  entry: MappingEntry;
  label: string;
  onChange: (next: MappingEntry) => void;
  native?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.setCustomValidity(
      entry.mode === "constant" &&
        !!entry.expression &&
        !literal(entry.expression)
        ? "填写字符串、数字、布尔值或 NULL；字符串须使用单引号。"
        : "",
    );
  }, [entry.mode, entry.expression]);
  return (
    <div className="om-entry-editor">
      <select
        className="om-mode"
        aria-label={`${label}映射方式`}
        value={entry.mode}
        onChange={(e) =>
          onChange({
            ...entry,
            mode: e.target.value as MappingEntry["mode"],
            expression: "",
            pending: false,
          })
        }
      >
        <option value="field">字段</option>
        <option value="expression" disabled={!native}>
          表达式
        </option>
        <option value="constant" disabled={!native}>
          常量
        </option>
      </select>
      {entry.mode === "field" ? (
        <select
          aria-label={`${label}字段`}
          value={entry.pending ? "" : entry.expression}
          onChange={(e) =>
            onChange({ ...entry, expression: e.target.value, pending: false })
          }
        >
          <option value="">选择字段</option>
          {[
            ...new Set([
              ...sourceColumns(entry.dataset),
              ...(entry.expression && !entry.pending ? [entry.expression] : []),
            ]),
          ].map((column) => (
            <option key={column} value={column}>
              {column}
            </option>
          ))}
        </select>
      ) : (
        <input
          ref={input}
          aria-label={`${label}${entry.mode === "constant" ? "常量" : "表达式"}`}
          value={entry.expression}
          onChange={(e) => {
            e.currentTarget.setCustomValidity(
              entry.mode === "constant" &&
                !!e.target.value &&
                !literal(e.target.value)
                ? "填写字符串、数字、布尔值或 NULL；字符串须使用单引号。"
                : "",
            );
            onChange({ ...entry, expression: e.target.value, pending: false });
          }}
        />
      )}
    </div>
  );
}
