import type { AttributeDefinition } from "../api/types";

// Which concept an attribute's value role points at once compiled. The API
// compiler is authoritative (ossie/compiler.py); this mirrors its rule so the
// editor can show writers the placeholder they are allowed to use. A stale hint
// only misleads about a name — the official lint still checks placeholders at
// publish time.
const VALUE_BASES: Record<string, string> = {
  string: "String",
  integer: "Integer",
  decimal: "Decimal",
  float: "Float",
  boolean: "Boolean",
  date: "Date",
  datetime: "DateTime",
};

export function valueConcept(
  objectKey: string,
  attribute: Pick<
    AttributeDefinition,
    | "technical_name"
    | "value_kind"
    | "identifier"
    | "value_concept"
    | "target_role_name"
  >,
): string {
  const concept = attribute.value_concept
    ? attribute.value_concept
    : attribute.identifier
      ? `${objectKey}_${attribute.technical_name}_value`
      : (VALUE_BASES[attribute.value_kind] ?? "String");
  // A named role is addressed as `{concept:role}`; the bare concept would not
  // resolve for readers or for the official lint.
  return attribute.target_role_name
    ? `${concept}:${attribute.target_role_name}`
    : concept;
}

/** The placeholders a reading of this relationship may use. */
export function placeholders(names: (string | undefined)[]): string[] {
  return [...new Set(names.filter((name): name is string => !!name))];
}
