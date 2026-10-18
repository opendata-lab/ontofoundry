// Display text of a document fact, derived the same way the server does
// (design §3.2): title property → complete identifier → first visible quote
// (by evidence UUID, first 80 characters) → fact UUID. Facts never store a name.
import type { Draft, MaterialObject, Scalar } from "../api/types";
import { compareUuidBytes, identifier, titleProperty } from "./coreModel";

const hasValue = (value: Scalar | undefined) => value !== null && value !== undefined && value !== "";

export function documentDisplayText(draft: Draft, fact: MaterialObject): string {
  const title = titleProperty(draft, fact.type_id);
  if (title && hasValue(fact.values[title.technical_name])) return String(fact.values[title.technical_name]);
  const keys = identifier(draft, fact.type_id);
  if (keys.length && keys.every((p) => hasValue(fact.values[p.technical_name]))) {
    return keys.map((p) => String(fact.values[p.technical_name])).join(" · ");
  }
  const quote = [...fact.evidence]
    .sort((a, b) => compareUuidBytes(a.id, b.id))
    .map((e) => (e.kind === "material" ? (e.quote ?? "").trim() : ""))
    .find((q) => q.length > 0);
  if (quote) return quote.length > 80 ? quote.slice(0, 80) + "…" : quote;
  return fact.id;
}

/** Text a search box matches: display text plus every property value. */
export function documentSearchText(draft: Draft, fact: MaterialObject): string {
  return [documentDisplayText(draft, fact), ...Object.values(fact.values).filter(hasValue).map(String)]
    .join(" ")
    .toLowerCase();
}
