import { useEffect, useState } from "react";
import { Database } from "lucide-react";
import { workspaceRequest } from "../api/client";
import type { DataMapping, DataTable, ObjectDefinition } from "../api/types";
import { DatasetPicker } from "./DatasetPicker";

export function MappingForm({
  workspaceId,
  type,
  mapping,
  onChange,
  fieldsOnly = false,
}: {
  workspaceId: string;
  type: ObjectDefinition;
  mapping: DataMapping | undefined;
  onChange: (m: DataMapping) => void;
  fieldsOnly?: boolean;
}) {
  const [picker, setPicker] = useState(false);
  const [columns, setColumns] = useState<DataTable["columns"]>([]);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<Record<string, unknown>[] | null>(
    null,
  );
  const connectionId = mapping?.connection_id;
  const tableName = mapping?.table_name;
  useEffect(() => {
    setColumns([]);
    setPreview(null);
    setError("");
    if (!connectionId || !tableName) return;
    workspaceRequest<{ items: DataTable[] }>(
      workspaceId,
      "/connections/" +
        connectionId +
        "/tables?table=" +
        encodeURIComponent(tableName),
    )
      .then((r) => setColumns(r.items[0]?.columns ?? []))
      .catch((e: Error) => setError(e.message));
  }, [connectionId, tableName, workspaceId]);
  return (
    <div className="mapping-form">
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
              <strong>{mapping?.table_name || "选择数据表"}</strong>
              <small>
                {mapping ? "点击更换数据集" : "MySQL / PostgreSQL / Doris"}
              </small>
            </span>
          </button>
        </>
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
                  fields: Object.fromEntries(
                    type.attributes
                      .filter((a) =>
                        columns.some((c) => c.name === a.technical_name),
                      )
                      .map((a) => [a.technical_name, a.technical_name]),
                  ),
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
            disabled={!mapping.key_column}
            onClick={() => {
              setError("");
              workspaceRequest<{ items: Record<string, unknown>[] }>(
                workspaceId,
                "/mapping-preview",
                { mapping, limit: 5 },
              )
                .then((r) => setPreview(r.items))
                .catch((e: Error) => setError(e.message));
            }}
          >
            预览 5 条数据
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
            connection_id: c.id,
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
