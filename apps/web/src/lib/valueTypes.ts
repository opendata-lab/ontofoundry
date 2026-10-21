import type { Draft } from "../api/types";

/** Constraint rules owned by a value type. */
export const valueTypeRules = (draft: Draft, id: string) =>
  draft.rules.filter((r) => r.owner_kind === "value_type" && r.owner_id === id);

/** Properties referencing a value type; derived on read, never stored. */
export const valueTypeUsages = (draft: Draft, id: string) =>
  draft.properties.filter((p) => p.value_type_id === id);
