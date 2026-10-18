// Plain-language notes over the instances on screen: where live rows disagree
// with the property types, and which document facts are still missing values.
// The server keeps the authoritative checks; these make them visible.
import { VALUE_KINDS } from "./elementModel";

type HintProperty = {
  name: string;
  technical_name: string;
  value_kind: string;
  required?: boolean;
  identifier?: boolean;
};

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const DATETIME = /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;

export function valueMatches(kind: string, value: unknown): boolean {
  switch (kind) {
    case "string":
      return typeof value === "string";
    case "boolean":
      return typeof value === "boolean";
    // Same rule as the server: a plain numeral written as text is valid.
    case "integer":
      return (
        (typeof value === "number" && Number.isInteger(value)) ||
        (typeof value === "string" && /^-?\d+$/.test(value))
      );
    case "decimal":
    case "float":
      return (
        (typeof value === "number" && Number.isFinite(value)) ||
        (typeof value === "string" && /^-?\d+(?:\.\d+)?$/.test(value))
      );
    case "date":
      return typeof value === "string" && DATE.test(value);
    case "datetime":
      return typeof value === "string" && DATETIME.test(value);
    default:
      return true;
  }
}

function describe(value: unknown): string {
  if (typeof value === "number") return Number.isInteger(value) ? "整数" : "小数";
  if (typeof value === "boolean") return "布尔";
  if (typeof value === "string") return "文本";
  return typeof value;
}

const kindName = (kind: string) => (VALUE_KINDS as Record<string, string>)[kind] ?? kind;

/** Preview rows come back keyed by property technical name; only mapped
 * properties (those in `fields`) have values to compare. */
export function databaseTypeHints(
  properties: HintProperty[],
  fields: Record<string, string>,
  rows: Record<string, unknown>[],
): string[] {
  const hints: string[] = [];
  for (const property of properties) {
    if (!fields[property.technical_name]) continue;
    const wrong = rows
      .map((row) => row[property.technical_name])
      .filter((value) => value !== null && value !== undefined)
      .filter((value) => !valueMatches(property.value_kind, value));
    if (!wrong.length) continue;
    hints.push(
      `${property.name}：本体定义为「${kindName(property.value_kind)}」，数据中为` +
        `「${describe(wrong[0])}」（本页 ${wrong.length} 行）。可在「属性」中调整类型。`,
    );
  }
  return hints;
}

export function documentGapHints(
  properties: HintProperty[],
  objects: { values: Record<string, unknown> }[],
): string[] {
  return properties
    .filter((property) => property.required || property.identifier)
    .map((property) => {
      const missing = objects.filter((object) => {
        const value = object.values[property.technical_name];
        return value === null || value === undefined || (typeof value === "string" && !value.trim());
      }).length;
      return missing
        ? `${property.name} 待补全：${missing} 个实例的原文未提供该值。`
        : "";
    })
    .filter(Boolean);
}
