import { Alert, Form, Select } from "antd";
import { useEffect, useState, type ReactNode } from "react";
import { catalogApi } from "../../api/client";
import type { AssetTable, DataConnection, Dataset } from "../../api/types";
import { FormRow } from "../layout";

/** Only collected tables can become a table source. Discovery belongs to sync. */
export function DatasetLocationFields({ workspaceId, dataset, nameField, onChange }: {
  workspaceId: string; dataset: Dataset; nameField: ReactNode; onChange: (patch: Partial<Dataset>) => void;
}) {
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [schemas, setSchemas] = useState<string[]>([]);
  const [tables, setTables] = useState<AssetTable[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    let live = true;
    catalogApi.connections(workspaceId).then((r) => { if (live) setConnections(r.items); }).catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [workspaceId]);
  useEffect(() => {
    let live = true;
    if (!dataset.connection_id) { setSchemas([]); return; }
    catalogApi.schemas(workspaceId, dataset.connection_id).then((r) => { if (live) setSchemas(r.items); }).catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [workspaceId, dataset.connection_id]);
  useEffect(() => {
    let live = true;
    setTables([]);
    if (!dataset.connection_id || dataset.source_kind === "query") return;
    setLoading(true); setError("");
    catalogApi.assets(workspaceId, dataset.connection_id, { schema_name: dataset.schema_name ?? undefined }).then((r) => { if (live) setTables(r.items.filter((t) => !t.missing)); }).catch((e: Error) => { if (live) setError(e.message); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [workspaceId, dataset.connection_id, dataset.schema_name, dataset.source_kind]);
  return <>
    <FormRow>{nameField}<Form.Item label="数据库连接" required>
      <Select aria-label="数据库连接" placeholder="选择数据连接" value={dataset.connection_id ?? undefined} options={connections.map((c) => ({ value: c.id, label: c.name }))}
        onChange={(id: string) => onChange({ connection_id: id, dialect: connections.find((c) => c.id === id)?.kind ?? null, schema_name: null, table_name: dataset.source_kind === "query" ? null : "", columns: null, snapshot_date_column: null })} />
    </Form.Item></FormRow>
    {dataset.source_kind !== "query" && <FormRow>
      <Form.Item label="库 / Schema"><Select aria-label="库或 schema" allowClear value={dataset.schema_name ?? undefined} placeholder="默认库 / Schema" disabled={!dataset.connection_id} options={schemas.map((name) => ({ value: name, label: name }))} onChange={(schema?: string) => onChange({ schema_name: schema ?? null, table_name: "", columns: null, snapshot_date_column: null })} /></Form.Item>
      <Form.Item label="已登记表或视图" required><Select aria-label="表或视图" showSearch loading={loading} optionFilterProp="label" value={dataset.table_name || undefined} options={tables.map((t) => ({ value: t.name, label: t.name }))} notFoundContent="请先在数据管理同步数据表" onChange={(name: string) => {
        const table = tables.find((t) => t.name === name);
        if (table) onChange({ table_name: name, columns: table.columns.map((c) => ({ name: c.name, physical_type: c.type, comment: c.comment ?? "" })), snapshot_date_column: null });
      }} /></Form.Item>
    </FormRow>}
    {error && <Alert type="error" showIcon message={error} />}
  </>;
}
