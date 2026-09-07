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
    "technical_name" | "value_kind" | "identifier" | "value_concept"
  >,
): string {
  if (attribute.value_concept) return attribute.value_concept;
  if (attribute.identifier)
    return `${objectKey}_${attribute.technical_name}_value`;
  return VALUE_BASES[attribute.value_kind] ?? "String";
}

/** The placeholders a reading of this relationship may use. */
export function placeholders(names: (string | undefined)[]): string[] {
  return [...new Set(names.filter((name): name is string => !!name))];
}
