import type { LinkedTable } from "../api/types";

/** Stable identity of a registered table within a workspace. */
export const tableKey = (t: LinkedTable) => `${t.connection_id}\u0000${t.schema_name}\u0000${t.table_name}`;

export const tableLabel = (t: LinkedTable) => (t.schema_name ? `${t.schema_name}.${t.table_name}` : t.table_name);
