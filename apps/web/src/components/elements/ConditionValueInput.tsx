import { DatePicker, Input, InputNumber, Select, Typography } from "antd";
import dayjs from "dayjs";
import type { Operator, Scalar, ValueKind } from "../../api/types";
import { coerceConditionValue, operatorArity } from "../../lib/derivedEditing";

const { Text } = Typography;

/** Shared typed values for property and dataset-column conditions. */
export function ConditionValueInput({
  kind,
  operator,
  values,
  label,
  onChange,
}: {
  kind: ValueKind | null;
  operator: Operator;
  values: Scalar[];
  label: string;
  onChange: (values: Scalar[]) => void;
}) {
  const arity = operatorArity(operator);
  if (arity === 0) return <span />;
  const numeric = kind === "integer" || kind === "decimal" || kind === "float";
  if (arity === "many") {
    return (
      <Select
        mode={kind === "boolean" ? "multiple" : "tags"}
        aria-label={label}
        placeholder="输入后回车，可填多个"
        value={values.map(String)}
        options={
          kind === "boolean"
            ? [
                { value: "true", label: "是" },
                { value: "false", label: "否" },
              ]
            : undefined
        }
        onChange={(next: string[]) => onChange(next.map((v) => coerceConditionValue(kind, v)))}
        open={kind === "boolean" ? undefined : false}
        tokenSeparators={[",", "，"]}
      />
    );
  }
  const one = (index: number) => {
    const value = values[index] ?? null;
    const set = (next: Scalar) => {
      const copy = [...values];
      while (copy.length < (arity === 2 ? 2 : 1)) copy.push(null);
      copy[index] = next;
      onChange(copy);
    };
    const name = arity === 2 ? `${label}${index ? "止" : "起"}` : label;
    if (kind === "boolean")
      return (
        <Select
          aria-label={name}
          value={value === null ? undefined : String(value)}
          onChange={(v) => set(v === "true")}
          options={[
            { value: "true", label: "是" },
            { value: "false", label: "否" },
          ]}
        />
      );
    if (numeric)
      return (
        <InputNumber
          aria-label={name}
          className="!w-full"
          value={typeof value === "number" ? value : null}
          onChange={(v) => set(v ?? null)}
        />
      );
    if (kind === "date" || kind === "datetime")
      return (
        <DatePicker
          aria-label={name}
          className="!w-full"
          showTime={kind === "datetime"}
          value={typeof value === "string" && value && dayjs(value).isValid() ? dayjs(value) : null}
          onChange={(d) => set(d ? (kind === "date" ? d.format("YYYY-MM-DD") : d.toISOString()) : null)}
        />
      );
    return <Input aria-label={name} value={value === null ? "" : String(value)} onChange={(e) => set(e.target.value)} />;
  };
  return arity === 2 ? (
    <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-1">
      {one(0)}
      <Text type="secondary">至</Text>
      {one(1)}
    </div>
  ) : (
    one(0)
  );
}
