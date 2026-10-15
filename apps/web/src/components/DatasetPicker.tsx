import { Database, Search } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { modelingApi } from "../api/client";
import type {
  DataConnection,
  DataTable,
  LegacyDraft,
  NativeDraft,
  SemanticDataset,
} from "../api/types";
import { objectMapping, sourceColumns } from "../lib/objectMapping";
import { useElementInspector } from "../hooks/useElementInspector";
import { InspectorDialog } from "./elements/InspectorDialog";
import { InfoButton, ReadonlyIcon } from "./elements/MappingWidgets";

export function DatasetPicker({
  workspaceId,
  open,
  onClose,
  onSelect,
  onSelectDataset,
  datasets = [],
  draft,
  nativeDraft,
  extraContent,
  selectionReason,
  onOpenObject,
}: {
  workspaceId: string;
  open: boolean;
  onClose: () => void;
  onSelect?: (connection: DataConnection, table: DataTable) => void;
  onSelectDataset?: (dataset: SemanticDataset) => void;
  datasets?: SemanticDataset[];
  draft?: LegacyDraft;
  nativeDraft?: NativeDraft;
  extraContent?: ReactNode;
  selectionReason?: string;
  onOpenObject?: (id: string) => void;
}) {
  if (!open) return null;
  return (
    <TableBrowser
      key={workspaceId}
      {...{
        workspaceId,
        onClose,
        onSelect,
        onSelectDataset,
        datasets,
        draft,
        nativeDraft,
        extraContent,
        selectionReason,
        onOpenObject,
      }}
    />
  );
}
function TableBrowser({
  workspaceId,
  onClose,
  onSelect,
  onSelectDataset,
  datasets,
  draft,
  nativeDraft,
  extraContent,
  selectionReason,
  onOpenObject,
}: Omit<Parameters<typeof DatasetPicker>[0], "open"> & {
  datasets: SemanticDataset[];
}) {
  const inspector = useElementInspector();
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [connectionId, setConnectionId] = useState("");
  const [tables, setTables] = useState<DataTable[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [fields, setFields] = useState<string[] | null>(null);
  const initialConnection = useState(!datasets.length || !!onSelect)[0];
  useEffect(() => {
    let live = true;
    modelingApi
      .connections(workspaceId)
      .then((result) => {
        if (!live) return;
        setConnections(result.items);
        if (initialConnection)
          setConnectionId(result.items[0]?.id ?? "");
      })
      .catch((e: Error) => {
        if (live) setError(e.message);
      });
    return () => {
      live = false;
    };
  }, [workspaceId, initialConnection]);
  useEffect(() => {
    if (!connectionId) return;
    let live = true;
    setLoading(true);
    setError("");
    setTables([]);
    modelingApi
      .tables(workspaceId, connectionId)
      .then((result) => {
        if (live) setTables(result.items);
      })
      .catch((e: Error) => {
        if (live) setError(e.message);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [workspaceId, connectionId]);
  const selecting = !!onSelect || !!onSelectDataset;
  const rows = [
    ...datasets.map((dataset) => ({
      id: dataset.id,
      source: dataset.source,
      dataset,
      table: undefined as DataTable | undefined,
      columns: sourceColumns(dataset),
    })),
    ...tables
      .filter(
        (table) =>
          !datasets.some(
            (d) =>
              d.source === [table.schema, table.name].filter(Boolean).join("."),
          ),
      )
      .map((table) => ({
        id: [connectionId, table.schema, table.name].join(":"),
        source: [table.schema, table.name].filter(Boolean).join("."),
        dataset: undefined as SemanticDataset | undefined,
        table,
        columns: table.columns.map((c) => c.name),
      })),
  ].filter((row) =>
    [row.source, ...row.columns]
      .join(" ")
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  return (
    <InspectorDialog
      title={selecting ? "选择表" : "浏览数据目录"}
      wide
      onClose={onClose}
    >
      <div className="om-toolbar">
        <label className="om-search">
          <Search size={16} />
          <input
            autoFocus
            placeholder="搜索表或字段"
            aria-label="搜索表或字段"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {(connections.length > 1 ||
          (datasets.length > 0 &&
            connections.length > 0 &&
            !onSelectDataset)) && (
          <select
            aria-label="数据连接"
            value={connectionId}
            onChange={(e) => setConnectionId(e.target.value)}
          >
            <option value="">语义模型中的表</option>
            {connections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        )}
        <span className="om-push muted">{rows.length} 张表</span>
      </div>
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      {loading && (
        <p role="status" className="muted">
          正在读取数据目录…
        </p>
      )}
      <table className="om-table om-assets">
        <thead>
          <tr>
            <th>表</th>
            <th>映射对象</th>
            <th>{selecting ? "选择" : "字段"}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const objects =
              draft?.object_types.filter((object) =>
                objectMapping(draft, object, nativeDraft).tables.some(
                  (d) => d.source === row.source,
                ),
              ) ?? [];
            return (
              <tr key={row.id}>
                <td data-label="表">
                  <code>{row.source}</code>
                  <small className="om-sub">
                    {connections.find((c) => c.id === connectionId)?.name}
                  </small>
                </td>
                <td data-label="映射对象">
                  {objects.map((object) => (
                    <div key={object.id}>
                      <button
                        type="button"
                        className="element-text-button"
                        onClick={() => {
                          onClose();
                          if (onOpenObject) onOpenObject(object.id);
                          else inspector.open({
                            kind: "object_type",
                            id: object.id,
                            tab: "properties",
                          });
                        }}
                      >
                        {object.name}
                      </button>
                    </div>
                  ))}
                  {!objects.length && <span className="muted">—</span>}
                </td>
                <td data-label={selecting ? "选择" : "字段"}>
                  {selecting && row.table && !onSelect && (
                    <ReadonlyIcon
                      reason={
                        selectionReason ??
                        "当前对象保存合同不能新增此数据集，请在「数据映射 › 语义模型」中添加数据集。"
                      }
                    />
                  )}
                  {selecting ? (
                    <button
                      type="button"
                      className="element-text-button"
                      disabled={
                        row.dataset
                          ? !onSelectDataset
                          : !onSelect || !connectionId
                      }
                      onClick={() => {
                        if (row.dataset) onSelectDataset?.(row.dataset);
                        else if (row.table) {
                          const connection = connections.find(
                            (c) => c.id === connectionId,
                          );
                          if (connection) onSelect?.(connection, row.table);
                        }
                      }}
                    >
                      选用
                    </button>
                  ) : (
                    <InfoButton
                      label="字段"
                      onClick={() => setFields(row.columns)}
                    />
                  )}
                </td>
              </tr>
            );
          })}
          {!rows.length && !loading && (
            <tr>
              <td colSpan={3} className="om-blank">
                <Database size={16} /> 没有匹配的表
              </td>
            </tr>
          )}
        </tbody>
      </table>
      {extraContent}
      {fields && (
        <InspectorDialog title="字段" onClose={() => setFields(null)}>
          {fields.map((field) => (
            <div className="om-entry" key={field}>
              <code>{field}</code>
            </div>
          ))}
        </InspectorDialog>
      )}
    </InspectorDialog>
  );
}
