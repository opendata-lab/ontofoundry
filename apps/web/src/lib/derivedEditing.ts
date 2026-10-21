// Editing a child object's membership definition (ObjectType.derived_by).
// The editor offers one level of conditions that must all hold: property
// comparisons on the direct parent, and "has / has no" related instances.
// Property-only rows save as one simple branch; any relation row saves the
// whole level as one expression with EXISTS, because a collection is never a
// scalar path. Anything else (several branches, multi-hop paths, hand-written
// expressions) is shown and edited as expression text.
import type {
  DerivedBranch,
  Draft,
  LinkType,
  Operator,
  PathCondition,
  Property,
  Scalar,
  UUID,
  ValueKind,
} from "../api/types";
import { NUMERIC_KINDS, byId, effectiveLinks, effectiveProperties } from "./coreModel";
import { newId } from "./id";

export const OPERATORS: Record<Operator, string> = {
  eq: "等于",
  ne: "不等于",
  gt: "大于",
  ge: "大于等于",
  lt: "小于",
  le: "小于等于",
  in: "属于",
  not_in: "不属于",
  between: "介于",
  is_null: "为空",
  not_null: "不为空",
};

const SQL_OPERATORS: Partial<Record<Operator, string>> = {
  eq: "=",
  ne: "<>",
  gt: ">",
  ge: ">=",
  lt: "<",
  le: "<=",
};

/** How many values an operator takes; "many" means at least one. */
export function operatorArity(operator: Operator): 0 | 1 | 2 | "many" {
  if (operator === "is_null" || operator === "not_null") return 0;
  if (operator === "between") return 2;
  if (operator === "in" || operator === "not_in") return "many";
  return 1;
}

/** Operators that make sense for a value kind. */
export function operatorsFor(kind: ValueKind | null): Operator[] {
  if (kind === "boolean") return ["eq", "ne", "in", "not_in", "is_null", "not_null"];
  if (kind === "string") return ["eq", "ne", "in", "not_in", "is_null", "not_null"];
  return ["eq", "ne", "gt", "ge", "lt", "le", "in", "not_in", "between", "is_null", "not_null"];
}

export type PropertyRow = {
  key: string;
  kind: "property";
  propertyId: UUID;
  operator: Operator;
  values: Scalar[];
};
export type LinkRow = {
  key: string;
  kind: "link";
  linkId: UUID;
  direction: "forward" | "reverse";
  has: boolean;
};
export type DerivedRow = PropertyRow | LinkRow;

export type DerivedForm =
  | { mode: "simple"; rows: DerivedRow[] }
  | { mode: "expression"; expression: string };

/** Definitions a child may reference: its direct parent's effective ones. */
export function derivedContext(draft: Draft, parentId: UUID | null) {
  if (!parentId) return { parent: undefined, properties: [], links: [] };
  return {
    parent: byId(draft.object_types, parentId),
    properties: effectiveProperties(draft, parentId).map((p) => p.definition),
    links: effectiveLinks(draft, parentId).map((l) => ({ link: l.definition, direction: l.direction })),
  };
}

export function newPropertyRow(property: Property | undefined): PropertyRow {
  return { key: newId(), kind: "property", propertyId: property?.id ?? "", operator: "eq", values: [] };
}

export function newLinkRow(link: { link: LinkType; direction: "forward" | "reverse" }): LinkRow {
  return { key: newId(), kind: "link", linkId: link.link.id, direction: link.direction, has: true };
}

// --- text rendering -----------------------------------------------------------

const quoteName = (name: string) => (/^[A-Za-z_]\w*$/.test(name) ? name : `"${name.replace(/"/g, '""')}"`);

export function literal(value: Scalar): string {
  if (value === null) return "NULL";
  if (typeof value === "boolean") return value ? "TRUE" : "FALSE";
  if (typeof value === "number") return String(value);
  return `'${value.replace(/'/g, "''")}'`;
}

function pathText(draft: Draft, root: string, condition: PathCondition) {
  const hops = (condition.path.links ?? []).map((step) => {
    const name = quoteName(byId(draft.link_types, step.link_type_id)?.name ?? "?");
    return step.direction === "reverse" ? `REVERSE(${name})` : name;
  });
  const property = byId(draft.properties, condition.path.property_id)?.name ?? "?";
  return [quoteName(root), ...hops, quoteName(property)].join(".");
}

function comparisonText(path: string, operator: Operator, values: Scalar[]) {
  const sql = SQL_OPERATORS[operator];
  if (sql) return `${path} ${sql} ${literal(values[0] ?? null)}`;
  if (operator === "is_null") return `${path} IS NULL`;
  if (operator === "not_null") return `${path} IS NOT NULL`;
  if (operator === "between") return `${path} BETWEEN ${literal(values[0] ?? null)} AND ${literal(values[1] ?? null)}`;
  return `${path} ${operator === "in" ? "IN" : "NOT IN"} (${values.map(literal).join(", ")})`;
}

function linkText(draft: Draft, root: string, row: LinkRow) {
  const name = quoteName(byId(draft.link_types, row.linkId)?.name ?? "?");
  const hop = row.direction === "reverse" ? `REVERSE(${name})` : name;
  return `${row.has ? "" : "NOT "}EXISTS (${quoteName(root)}.${hop})`;
}

function rowText(draft: Draft, root: string, row: DerivedRow) {
  if (row.kind === "link") return linkText(draft, root, row);
  return comparisonText(
    pathText(draft, root, { path: { links: [], property_id: row.propertyId }, operator: row.operator, values: row.values }),
    row.operator,
    row.values,
  );
}

/** Readable text of stored branches, OR between branches. */
export function branchesText(draft: Draft, parentId: UUID | null, branches: DerivedBranch[]): string {
  const root = byId(draft.object_types, parentId)?.name ?? "parent";
  const texts = branches.map((branch) =>
    branch.kind === "expression"
      ? branch.expression
      : branch.conditions
          .map((c) => comparisonText(pathText(draft, root, c as PathCondition), c.operator, c.values ?? []))
          .join(" AND "),
  );
  return texts.length > 1 ? texts.map((t) => `(${t})`).join(" OR ") : (texts[0] ?? "");
}

/** One-line Chinese summary for read-only display. */
export function branchSummary(draft: Draft, branch: DerivedBranch): string {
  if (branch.kind === "expression") return branch.expression;
  return branch.conditions
    .map((c) => {
      const hops = (c.path.links ?? []).map((s) => (byId(draft.link_types, s.link_type_id)?.display_name || byId(draft.link_types, s.link_type_id)?.name) ?? "?");
      const property = (byId(draft.properties, c.path.property_id)?.display_name || byId(draft.properties, c.path.property_id)?.name) ?? "?";
      const values = c.values ?? [];
      const shown =
        c.operator === "between" ? `${values[0]} 至 ${values[1]}` : values.map((v) => String(v)).join("、");
      return [[...hops, property].join(" 的 "), OPERATORS[c.operator], shown].filter(Boolean).join(" ");
    })
    .join("，并且 ");
}

// --- reading stored branches into the form -----------------------------------

function unquote(name: string) {
  return name.startsWith('"') ? name.slice(1, -1).replace(/""/g, '"') : name;
}

const NAME = String.raw`(?:[A-Za-z_]\w*|"(?:[^"]|"")+")`;
const EXISTS_TERM = new RegExp(String.raw`^(NOT\s+)?EXISTS\s*\(\s*(${NAME})\s*\.\s*(?:REVERSE\s*\(\s*(${NAME})\s*\)|(${NAME}))\s*\)$`, "i");

/** Splits on top-level AND, keeping BETWEEN … AND … together. */
function splitAnd(text: string): string[] | null {
  const parts: string[] = [];
  let depth = 0;
  let quote = "";
  let start = 0;
  let between = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (quote) {
      if (ch === quote) quote = text[i + 1] === quote ? (i++, quote) : "";
      continue;
    }
    if (ch === "'" || ch === '"') quote = ch;
    else if (ch === "(") depth++;
    else if (ch === ")") depth--;
    else if (depth === 0 && /\s/.test(ch)) {
      const word = /^(AND|OR|BETWEEN)\b/i.exec(text.slice(i + 1));
      if (!word) continue;
      const w = word[1].toUpperCase();
      if (w === "OR") return null;
      if (w === "BETWEEN") between = true;
      else if (between) between = false;
      else {
        parts.push(text.slice(start, i).trim());
        start = i + 1 + word[0].length;
      }
    }
  }
  parts.push(text.slice(start).trim());
  return parts.filter(Boolean);
}

function parseLiteral(text: string, kind: ValueKind): Scalar | undefined {
  const t = text.trim();
  if (/^NULL$/i.test(t)) return null;
  if (/^TRUE$/i.test(t)) return kind === "boolean" ? true : undefined;
  if (/^FALSE$/i.test(t)) return kind === "boolean" ? false : undefined;
  if (/^'(?:[^']|'')*'$/.test(t)) return t.slice(1, -1).replace(/''/g, "'");
  if (/^-?\d+(\.\d+)?$/.test(t) && kind !== "string") return Number(t);
  return undefined;
}

function parseList(text: string, kind: ValueKind): Scalar[] | null {
  const items = text.match(/'(?:[^']|'')*'|[^,\s][^,]*/g) ?? [];
  const values = items.map((item) => parseLiteral(item, kind));
  return values.every((v) => v !== undefined) ? (values as Scalar[]) : null;
}

function parseTerm(term: string, root: string, context: ReturnType<typeof derivedContext>): DerivedRow | null {
  const exists = EXISTS_TERM.exec(term);
  if (exists) {
    if (unquote(exists[2]).toLowerCase() !== root.toLowerCase()) return null;
    const reverse = exists[3] !== undefined;
    const name = unquote(exists[3] ?? exists[4]).toLowerCase();
    const match = context.links.find(
      (l) => l.link.name.toLowerCase() === name && l.direction === (reverse ? "reverse" : "forward"),
    );
    return match ? { key: newId(), kind: "link", linkId: match.link.id, direction: match.direction, has: !exists[1] } : null;
  }
  const head = new RegExp(String.raw`^(${NAME})\s*\.\s*(${NAME})\s+(.*)$`, "is").exec(term);
  if (!head || unquote(head[1]).toLowerCase() !== root.toLowerCase()) return null;
  const property = context.properties.find((p) => p.name.toLowerCase() === unquote(head[2]).toLowerCase());
  if (!property) return null;
  const rest = head[3].trim();
  const row = (operator: Operator, values: Scalar[]): PropertyRow => ({
    key: newId(),
    kind: "property",
    propertyId: property.id,
    operator,
    values,
  });
  if (/^IS\s+NULL$/i.test(rest)) return row("is_null", []);
  if (/^IS\s+NOT\s+NULL$/i.test(rest)) return row("not_null", []);
  const between = /^BETWEEN\s+(.+?)\s+AND\s+(.+)$/is.exec(rest);
  if (between) {
    const a = parseLiteral(between[1], property.value_kind);
    const b = parseLiteral(between[2], property.value_kind);
    return a === undefined || b === undefined ? null : row("between", [a, b]);
  }
  const list = /^(NOT\s+)?IN\s*\((.*)\)$/is.exec(rest);
  if (list) {
    const values = parseList(list[2], property.value_kind);
    return values ? row(list[1] ? "not_in" : "in", values) : null;
  }
  const compare = /^(<>|!=|>=|<=|=|>|<)\s*(.+)$/s.exec(rest);
  if (!compare) return null;
  const value = parseLiteral(compare[2], property.value_kind);
  const op = ({ "=": "eq", "<>": "ne", "!=": "ne", ">": "gt", ">=": "ge", "<": "lt", "<=": "le" } as const)[
    compare[1] as "="
  ];
  return value === undefined ? null : row(op, [value]);
}

export function formFromBranches(draft: Draft, parentId: UUID | null, branches: DerivedBranch[]): DerivedForm {
  if (branches.length === 0) return { mode: "simple", rows: [] };
  const context = derivedContext(draft, parentId);
  if (branches.length === 1) {
    const [branch] = branches;
    if (branch.kind === "simple" && branch.conditions.every((c) => !(c.path.links ?? []).length)) {
      return {
        mode: "simple",
        rows: branch.conditions.map((c) => ({
          key: newId(),
          kind: "property",
          propertyId: c.path.property_id,
          operator: c.operator,
          values: c.values ?? [],
        })),
      };
    }
    if (branch.kind === "expression" && context.parent) {
      const terms = splitAnd(branch.expression);
      const rows = terms?.map((t) => parseTerm(t, context.parent!.name, context));
      if (rows && rows.length && rows.every(Boolean) && rows.some((r) => r!.kind === "link")) {
        return { mode: "simple", rows: rows as DerivedRow[] };
      }
    }
  }
  return { mode: "expression", expression: branchesText(draft, parentId, branches) };
}

export function isEmptyConditionValue(value: Scalar | undefined): boolean {
  return value === null || value === undefined || (typeof value === "string" && value.trim() === "");
}

export function isNumericConditionValue(value: Scalar): boolean {
  if (typeof value === "number") return Number.isFinite(value);
  if (typeof value === "string" && value.trim() !== "") return !Number.isNaN(Number(value.trim()));
  return false;
}

export function coerceConditionValue(kind: ValueKind | null | undefined, value: Scalar): Scalar {
  if (kind === "boolean" && typeof value === "string") {
    const t = value.trim();
    if (/^(true|是)$/i.test(t)) return true;
    if (/^(false|否)$/i.test(t)) return false;
  }
  if (kind && NUMERIC_KINDS.has(kind) && typeof value === "string" && isNumericConditionValue(value)) {
    return Number(value.trim());
  }
  return value;
}

/** The branches the form saves. An empty simple form saves no branch. */
export function branchesFromForm(draft: Draft, parentId: UUID | null, form: DerivedForm): DerivedBranch[] {
  if (form.mode === "expression") {
    const expression = form.expression.trim();
    return expression ? [{ kind: "expression", expression }] : [];
  }
  if (!form.rows.length) return [];
  if (form.rows.every((r): r is PropertyRow => r.kind === "property")) {
    const conditions = form.rows.map((r): PathCondition => {
      const kind = byId(draft.properties, r.propertyId)?.value_kind;
      return {
        path: { links: [], property_id: r.propertyId },
        operator: r.operator,
        values: operatorArity(r.operator) === 0 ? [] : r.values.map((v) => coerceConditionValue(kind, v)),
      };
    }) as [PathCondition, ...PathCondition[]];
    return [{ kind: "simple", conditions }];
  }
  const root = byId(draft.object_types, parentId)?.name ?? "parent";
  return [{ kind: "expression", expression: form.rows.map((r) => rowText(draft, root, r)).join(" AND ") }];
}

/** Row-level problems, keyed by row key; empty when the form can be saved. */
export function formErrors(draft: Draft, form: DerivedForm): Record<string, string> {
  const errors: Record<string, string> = {};
  if (form.mode === "expression") return errors;
  for (const row of form.rows) {
    if (row.kind === "link") continue;
    const property = byId(draft.properties, row.propertyId);
    if (!property) {
      errors[row.key] = "请选择属性";
      continue;
    }
    const arity = operatorArity(row.operator);
    const hasEmpty = row.values.some(isEmptyConditionValue);
    const filled = row.values.filter((v) => !isEmptyConditionValue(v));
    if (row.operator === "not_in" && hasEmpty) errors[row.key] = "“不属于”的值不能包含空值";
    else if (arity === 1 && filled.length !== 1) errors[row.key] = "请填写一个值";
    else if (arity === 2 && filled.length !== 2) errors[row.key] = "请填写起止两个值";
    else if (arity === "many" && filled.length === 0) errors[row.key] = "至少填写一个值";
    else if (arity !== 0 && NUMERIC_KINDS.has(property.value_kind) && filled.some((v) => !isNumericConditionValue(v)))
      errors[row.key] = "数值属性的条件值必须是数字";
  }
  return errors;
}

/** First problem in stored branches that the server would reject, or null. */
export function branchProblem(draft: Draft, branches: DerivedBranch[]): string | null {
  for (const [i, branch] of branches.entries()) {
    const where = branches.length > 1 ? `成员条件第 ${i + 1} 组` : "成员条件";
    if (branch.kind === "expression") {
      if (!branch.expression.trim()) return `${where}的表达式为空`;
      continue;
    }
    for (const [j, condition] of branch.conditions.entries()) {
      const row: PropertyRow = {
        key: String(j),
        kind: "property",
        propertyId: condition.path.property_id,
        operator: condition.operator,
        values: condition.values ?? [],
      };
      const problem = formErrors(draft, { mode: "simple", rows: [row] })[row.key];
      if (problem) return `${where}第 ${j + 1} 个条件：${problem}`;
    }
  }
  return null;
}
