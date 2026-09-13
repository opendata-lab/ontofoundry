import { useEffect, useRef, useState } from "react";
import { Database } from "lucide-react";
import { modelingApi, workspaceRequest } from "../api/client";
import type {
  DataConnection,
  DataMapping,
  DataTable,
  ObjectDefinition,
} from "../api/types";
import { DatasetPicker } from "./DatasetPicker";

export function MappingForm({
  workspaceId,
  type,
  mapping,
  onChange,
  fieldsOnly = false,
  suggestedSource,
}: {
  workspaceId: string;
  type: ObjectDefinition;
  mapping: DataMapping | undefined;
  onChange: (m: DataMapping) => void;
  fieldsOnly?: boolean;
  suggestedSource?: {
    connection_alias: string;
    table_name: string;
    schema_name: string | null;
  };
}) {
  const [picker, setPicker] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const previewRequest = useRef(0);
  const [sourceApplied, setSourceApplied] = useState(false);
  const [columns, setColumns] = useState<DataTable["columns"]>([]);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<Record<string, unknown>[] | null>(
    null,
  );
  // The model names a data source; the connection that serves that name is
  // workspace configuration, resolved here only to read columns and preview.
  const [connections, setConnections] = useState<DataConnection[]>([]);
  useEffect(() => {
    let active = true;
    setConnections([]);
    modelingApi
      .connections(workspaceId)
      .then((r) => {
        if (active) setConnections(r.items);
      })
      .catch(() => {
        if (active) setConnections([]);
      });
    return () => {
      active = false;
    };
  }, [workspaceId]);
  const alias = mapping?.connection_alias;
  const connectionId = connections.find((c) => c.name === alias)?.id;
  const tableName = mapping?.table_name;
  useEffect(() => {
    let active = true;
    setColumns([]);
    setPreview(null);
    setError("");
    if (!connectionId || !tableName) return;
    workspaceRequest<{ items: DataTable[] }>(
      workspaceId,
      "/connections/" +
        connectionId +
        "/tables?table=" +
        encodeURIComponent(tableName) +
        (mapping?.schema_name
          ? "&schema_name=" + encodeURIComponent(mapping.schema_name)
          : ""),
    )
      .then((r) => {
        if (active) setColumns(r.items[0]?.columns ?? []);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [connectionId, tableName, workspaceId, mapping?.schema_name]);
  useEffect(() => {
    const request = previewRequest;
    request.current++;
    setPreview(null);
    setPreviewing(false);
    return () => {
      request.current++;
    };
  }, [workspaceId, mapping]);
  return (
    <div className="mapping-form">
      {!fieldsOnly && suggestedSource && !sourceApplied && (
        <div className="mapping-source-choice">
          <p>
            来自数据资产：{suggestedSource.connection_alias} /{" "}
            {suggestedSource.schema_name
              ? suggestedSource.schema_name + "."
              : ""}
            {suggestedSource.table_name}
          </p>
          <p className="muted">
            {mapping
              ? "应用后将替换下方映射，请重新选择唯一且非空的标识字段和属性。保存草稿后才会写入。"
              : "应用后选择唯一且非空的标识字段和属性，再保存草稿。"}
          </p>
          <button
            type="button"
            className="button button--secondary"
            onClick={() => {
              onChange({
                id: mapping?.id ?? crypto.randomUUID(),
                type_id: type.id,
                ...suggestedSource,
                key_column: "",
                fields: {},
              });
              setSourceApplied(true);
            }}
          >
            使用此数据表{mapping ? "替换映射" : "配置映射"}
          </button>
          <button
            type="button"
            className="button button--text"
            onClick={() => setSourceApplied(true)}
          >
            保留当前配置
          </button>
        </div>
      )}
      {!fieldsOnly && (
        <>
          <h2>数据映射</h2>
          <p className="muted">
            选择表或视图，实例按需查询，原始数据保留在源系统。
          </p>
          <button
            className="dataset-target"
            onClick={() => setPicker(true)}
            type="button"
          >
            <Database size={22} />
            <span>
              <strong>
                {mapping
                  ? (mapping.schema_name ? mapping.schema_name + "." : "") +
                    mapping.table_name
                  : "选择数据表"}
              </strong>
              <small>
                {mapping
                  ? "数据源 " + mapping.connection_alias + " · 点击更换数据集"
                  : "MySQL / PostgreSQL / Doris"}
              </small>
            </span>
          </button>
        </>
      )}
      {mapping && alias && !connectionId && (
        <p className="inline-error">
          模型引用的数据源「{alias}
          」在本空间还没有配置连接，字段与预览暂不可用。
        </p>
      )}
      {mapping ? (
        <>
          <label className="section-field">
            <span>实例标识字段</span>
            <select
              value={mapping.key_column}
              onChange={(e) =>
                onChange({ ...mapping, key_column: e.target.value })
              }
            >
              <option value="">请选择唯一且非空的字段</option>
              {columns.map((c) => (
                <option key={c.name} value={c.name}>
                  {c.name}
                  {c.primary_key ? " · 主键" : ""}
                </option>
              ))}
            </select>
          </label>
          <div className="mapping-heading">
            <h3>属性映射</h3>
            <button
              type="button"
              className="button button--text"
              onClick={() =>
                onChange({
                  ...mapping,
                  fields: {
                    ...mapping.fields,
                    ...Object.fromEntries(
                      type.attributes
                        .filter((a) =>
                          columns.some((c) => c.name === a.technical_name),
                        )
                        .map((a) => [a.technical_name, a.technical_name]),
                    ),
                  },
                })
              }
            >
              匹配同名字段
            </button>
          </div>
          <table className="ref-table">
            <thead>
              <tr>
                <th>本体属性</th>
                <th>数据字段</th>
              </tr>
            </thead>
            <tbody>
              {type.attributes.map((a) => (
                <tr key={a.id}>
                  <td>
                    {a.name}
                    <small>{a.technical_name}</small>
                  </td>
                  <td>
                    <select
                      aria-label={a.name + "映射字段"}
                      value={mapping.fields[a.technical_name] ?? ""}
                      onChange={(e) => {
                        const fields = { ...mapping.fields };
                        if (e.target.value)
                          fields[a.technical_name] = e.target.value;
                        else delete fields[a.technical_name];
                        onChange({ ...mapping, fields });
                      }}
                    >
                      <option value="">暂不映射</option>
                      {columns.map((c) => (
                        <option key={c.name}>{c.name}</option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <button
            type="button"
            className="button button--secondary"
            disabled={!mapping.key_column || !connectionId || previewing}
            onClick={() => {
              const current = ++previewRequest.current;
              setError("");
              setPreviewing(true);
              workspaceRequest<{ items: Record<string, unknown>[] }>(
                workspaceId,
                "/mapping-preview",
                { mapping, limit: 5 },
              )
                .then((r) => {
                  if (current === previewRequest.current) setPreview(r.items);
                })
                .catch((e: Error) => {
                  if (current === previewRequest.current) setError(e.message);
                })
                .finally(() => {
                  if (current === previewRequest.current) setPreviewing(false);
                });
            }}
          >
            {previewing ? "正在读取…" : "预览 5 条数据"}
          </button>
          {preview && (
            <div className="preview-scroll">
              <table className="ref-table">
                <thead>
                  <tr>
                    {Object.keys(preview[0] ?? {}).map((k) => (
                      <th key={k}>{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview.map((r, i) => (
                    <tr key={i}>
                      {Object.entries(r).map(([k, v]) => (
                        <td key={k}>{String(v ?? "—")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {!preview.length && <p className="muted">没有查询到实例</p>}
            </div>
          )}
        </>
      ) : fieldsOnly ? (
        <p className="muted">请先在数据映射步骤选择数据表。</p>
      ) : null}
      {error && <p className="inline-error">{error}</p>}
      <DatasetPicker
        workspaceId={workspaceId}
        open={picker}
        onClose={() => setPicker(false)}
        onSelect={(c, t) =>
          onChange({
            id: mapping?.id ?? crypto.randomUUID(),
            type_id: type.id,
            connection_alias: c.name,
            table_name: t.name,
            schema_name: t.schema,
            key_column: "",
            fields: {},
          })
        }
      />
    </div>
  );
}
