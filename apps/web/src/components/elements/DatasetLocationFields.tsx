import { Alert, Button, Form, Select } from "antd";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { catalogApi } from "../../api/client";
import type { DataConnection, DataTable, Dataset } from "../../api/types";
import { FormRow } from "../layout";

/** Connection selection browses the catalog; only the physical location is stored. */
export function DatasetLocationFields({ workspaceId, dataset, nameField, onChange }: {
  workspaceId: string;
  dataset: Dataset;
  nameField: ReactNode;
  onChange: (patch: Partial<Dataset>) => void;
}) {
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [connectionId, setConnectionId] = useState<string>();
  const [schemas, setSchemas] = useState<string[]>([]);
  const [tables, setTables] = useState<DataTable[]>([]);
  const [loadingConnections, setLoadingConnections] = useState(true);
  const [loadingSchemas, setLoadingSchemas] = useState(false);
  const [loadingTables, setLoadingTables] = useState(false);
  const [loadingFields, setLoadingFields] = useState(false);
  const [connectionError, setConnectionError] = useState("");
  const [schemaError, setSchemaError] = useState("");
  const [tableError, setTableError] = useState("");
  const [fieldError, setFieldError] = useState("");
  const [reload, setReload] = useState(0);
  const selection = useRef(0);
  const latestChange = useRef(onChange);
  useEffect(() => { latestChange.current = onChange; }, [onChange]);
  const candidates = connections.filter((item) => !dataset.dialect || item.kind === dataset.dialect);
  const connection = connections.find((item) => item.id === connectionId) ?? (candidates.length === 1 ? candidates[0] : undefined);
  const activeConnectionId = connection?.id;

  useEffect(() => {
    let live = true;
    setLoadingConnections(true);
    setConnectionError("");
    catalogApi.connections(workspaceId)
      .then((result) => { if (live) setConnections(result.items); })
      .catch((error: Error) => { if (live) setConnectionError(error.message); })
      .finally(() => { if (live) setLoadingConnections(false); });
    return () => { live = false; };
  }, [workspaceId, reload]);

  useEffect(() => {
    let live = true;
    setSchemas([]);
    setSchemaError("");
    setLoadingSchemas(!!activeConnectionId);
    if (activeConnectionId) {
      catalogApi.schemas(workspaceId, activeConnectionId)
        .then((result) => { if (live) setSchemas(result.items); })
        .catch((error: Error) => { if (live) setSchemaError(error.message); })
        .finally(() => { if (live) setLoadingSchemas(false); });
    }
    return () => { live = false; };
  }, [workspaceId, activeConnectionId, reload]);

  useEffect(() => {
    let live = true;
    selection.current += 1;
    setLoadingFields(false);
    setFieldError("");
    setTables([]);
    setTableError("");
    setLoadingTables(!!activeConnectionId);
    if (activeConnectionId) {
      catalogApi.tables(workspaceId, activeConnectionId, { schema_name: dataset.schema_name ?? undefined })
        .then((result) => { if (live) setTables(result.items); })
        .catch((error: Error) => { if (live) setTableError(error.message); })
        .finally(() => { if (live) setLoadingTables(false); });
    }
    return () => { live = false; selection.current += 1; };
  }, [workspaceId, activeConnectionId, dataset.schema_name, reload]);

  const chooseTable = async (name: string) => {
    if (!connection) return;
    const request = ++selection.current;
    setLoadingFields(true);
    setFieldError("");
    try {
      const result = await catalogApi.tables(workspaceId, connection.id, {
        schema_name: dataset.schema_name ?? undefined, table: name,
      });
      if (request !== selection.current) return;
      const table = result.items.find((item) => item.name === name);
      if (!table) throw new Error("未找到所选表，请刷新目录后重选");
      latestChange.current({
        dialect: connection.kind,
        table_name: table.name,
        columns: table.columns.map((column) => ({ name: column.name, physical_type: column.type, comment: column.comment ?? "" })),
        ...(dataset.table_name !== name ? { snapshot_date_column: null } : {}),
      });
    } catch (error) {
      if (request === selection.current) setFieldError(error instanceof Error ? error.message : "读取字段失败");
    } finally {
      if (request === selection.current) setLoadingFields(false);
    }
  };
  const schemaOptions = [...new Set([...(dataset.schema_name ? [dataset.schema_name] : []), ...schemas])];
  const tableOptions = [...new Set([...(dataset.table_name ? [dataset.table_name] : []), ...tables.map((table) => table.name)])];
  const error = connectionError || schemaError || tableError || fieldError;
  return <>
    <FormRow>
      {nameField}
      <Form.Item label="数据库连接" extra={!loadingConnections && !connections.length && !connectionError ? "暂无数据连接，请先在数据连接页配置。" : undefined}>
      <Select aria-label="数据库连接" showSearch optionFilterProp="label" loading={loadingConnections}
        placeholder="选择数据连接" value={connection?.id} options={connections.map((item) => ({ value: item.id, label: item.name }))}
        onChange={(id: string) => {
          selection.current += 1;
          setConnectionId(id);
          onChange({ dialect: connections.find((item) => item.id === id)?.kind ?? null, schema_name: null, table_name: "", columns: null, snapshot_date_column: null });
        }} />
      </Form.Item>
    </FormRow>
    <FormRow>
      <Form.Item label="库 / Schema">
        <Select aria-label="库或 schema" showSearch optionFilterProp="label" allowClear loading={loadingSchemas}
          disabled={!connection || loadingSchemas} placeholder={connection ? "默认库 / Schema" : "请先选择数据连接"}
          value={dataset.schema_name ?? undefined} options={schemaOptions.map((name) => ({ value: name, label: name, disabled: !schemas.includes(name) }))}
          onChange={(schema?: string) => {
            selection.current += 1;
            onChange({ schema_name: schema ?? null, table_name: "", columns: null, snapshot_date_column: null });
          }} />
      </Form.Item>
      <Form.Item label="表或视图" required>
        <Select aria-label="表或视图" showSearch optionFilterProp="label" loading={loadingTables || loadingFields}
          disabled={!connection || loadingTables || loadingFields || !!tableError} placeholder={connection ? "选择表或视图" : "请先选择数据连接"}
          value={dataset.table_name || undefined} options={tableOptions.map((name) => ({ value: name, label: name, disabled: !tables.some((table) => table.name === name) }))}
          notFoundContent="当前库没有可选的表或视图" onChange={(name: string) => void chooseTable(name)} />
      </Form.Item>
    </FormRow>
    {error && <Alert className="mb-4" type="error" showIcon message={error} action={<Button size="small" onClick={() => setReload((value) => value + 1)}>重试</Button>} />}
  </>;
}
