// Registered datasets: labels, blank forms and catalog registration.
import { modelingApi } from "../api/client";
import type { AssetTable, DataConnection, Dataset, Draft, Workspace } from "../api/types";
import { upsert } from "./coreModel";
import { newId } from "./id";

export const DIALECTS = [
  { value: "mysql", label: "MySQL" },
  { value: "doris", label: "Doris" },
  { value: "postgresql", label: "PostgreSQL" },
];

/** "名称（库.表）", or just the location when the name repeats it. */
export function datasetLabel(dataset: Dataset | undefined) {
  if (!dataset) return "数据集已删除";
  const location = [dataset.schema_name, dataset.table_name].filter(Boolean).join(".");
  return `${dataset.display_name || dataset.name}（${dataset.source_kind === "query" ? "表达式" : location}）`;
}

export function newDataset(id: string): Dataset {
  return {
    id,
    name: "",
    display_name: null,
    connection_id: null,
    source_kind: "table",
    query_sql: null,
    description: "",
    dialect: null,
    schema_name: null,
    table_name: "",
    snapshot_date_column: null,
    columns: null,
  };
}

/** Datasets already registered for the same physical location. */
export function sameLocation(draft: Draft, dataset: Pick<Dataset, "id" | "schema_name" | "table_name">) {
  return draft.datasets.filter(
    (d) =>
      d.id !== dataset.id &&
      (d.schema_name ?? "") === (dataset.schema_name ?? "") &&
      d.table_name === dataset.table_name,
  );
}

/** A Dataset for one catalog table; columns copy name, type and comment only. */
export function datasetFromTable(connection: DataConnection, table: AssetTable, name: string): Dataset {
  return {
    id: newId(),
    name: /^[A-Za-z_][A-Za-z0-9_]*$/.test(table.name) ? table.name : "dataset",
    display_name: name,
    connection_id: connection.id,
    source_kind: "table",
    query_sql: null,
    description: table.comment ?? "",
    dialect: connection.kind,
    schema_name: table.schema,
    table_name: table.name,
    snapshot_date_column: null,
    columns: table.columns.map((c) => ({ name: c.name, physical_type: c.type, comment: c.comment ?? "" })),
  };
}

/**
 * Registers a dataset as a session element save (never publishes). Outside a
 * session it targets the user's personal session in this workspace.
 */
export async function registerDataset(workspace: Workspace, _draft: Draft, sessionId: string | null, dataset: Dataset) {
  const session = sessionId
    ? await modelingApi.get(workspace.id, sessionId)
    : await modelingApi.personal(workspace.id);
  return modelingApi.saveElement(workspace.id, session.id, {
    target_kind: "dataset",
    target_id: dataset.id,
    expected_session_revision: session.revision,
    idempotency_key: newId(),
    draft: upsert(session.draft, "datasets", dataset),
  });
}
