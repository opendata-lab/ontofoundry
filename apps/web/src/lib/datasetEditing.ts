// Registered datasets: labels, blank forms and catalog registration.
import { api, modelingApi } from "../api/client";
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
  return dataset.name === location || dataset.name === dataset.table_name ? location : `${dataset.name}（${location}）`;
}

export function newDataset(id: string): Dataset {
  return {
    id,
    name: "",
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
    name,
    description: table.comment ?? "",
    dialect: connection.kind,
    schema_name: table.schema,
    table_name: table.name,
    snapshot_date_column: null,
    columns: table.columns.map((c) => ({ name: c.name, physical_type: c.type, comment: c.comment ?? "" })),
  };
}

/**
 * Registers a dataset as its own element save. In a session the save also
 * returns the session, which keeps its other unpublished changes.
 */
export async function registerDataset(workspace: Workspace, draft: Draft, sessionId: string | null, dataset: Dataset) {
  const session = sessionId ? await modelingApi.get(workspace.id, sessionId) : null;
  const base = session?.draft ?? draft;
  const current = await api.workspace(workspace.id);
  return modelingApi.saveElement(workspace.id, {
    target_kind: "dataset",
    target_id: dataset.id,
    expected_current_version_id: current.version_id,
    session_id: session?.id ?? null,
    expected_session_revision: session?.revision ?? null,
    draft: upsert(base, "datasets", dataset),
  });
}
