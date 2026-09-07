import { useEffect, useRef, useState } from "react";
import { Database, Search, X } from "lucide-react";
import { modelingApi } from "../api/client";
import type { DataConnection, DataTable } from "../api/types";

export function DatasetPicker({
  workspaceId,
  open,
  onClose,
  onSelect,
}: {
  workspaceId: string;
  open: boolean;
  onClose: () => void;
  onSelect: (connection: DataConnection, table: DataTable) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [connectionId, setConnectionId] = useState("");
  const [tables, setTables] = useState<DataTable[]>([]);
  const [selected, setSelected] = useState<DataTable | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (open) {
      dialog.current?.showModal();
      modelingApi
        .connections(workspaceId)
        .then((r) => {
          setConnections(r.items);
          if (r.items[0]) setConnectionId(r.items[0].id);
        })
        .catch((e: Error) => setError(e.message));
    } else dialog.current?.close();
  }, [open, workspaceId]);
  useEffect(() => {
    if (!connectionId) return;
    setLoading(true);
    setError("");
    setSelected(null);
    modelingApi
      .tables(workspaceId, connectionId)
      .then((r) => setTables(r.items))
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, [connectionId, workspaceId]);
  return (
    <dialog
      ref={dialog}
      className="ref-dialog dataset-dialog"
      onClose={onClose}
      aria-label="选择数据表"
    >
      <header>
        <h2>从数据连接中选择数据表</h2>
        <button
          className="icon-button"
          aria-label="关闭选择数据表"
          onClick={onClose}
        >
          <X size={18} />
        </button>
      </header>
      <div className="dataset-columns">
        <section>
          <h3>数据目录</h3>
          <select
            aria-label="数据连接"
            value={connectionId}
            onChange={(e) => setConnectionId(e.target.value)}
          >
            <option value="">选择连接</option>
            {connections.map((c) => (
              <option value={c.id} key={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <label className="ref-search">
            <Search size={14} />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索数据表"
              aria-label="搜索数据表"
            />
          </label>
          {loading ? (
            <p className="muted">正在读取数据目录…</p>
          ) : (
            tables
              .filter((t) => t.name.toLowerCase().includes(query.toLowerCase()))
              .map((t) => (
                <label className="dataset-option" key={t.name}>
                  <input
                    type="radio"
                    name="dataset"
                    checked={selected?.name === t.name}
                    onChange={() => setSelected(t)}
                  />
                  <Database size={14} />
                  {t.name}
                </label>
              ))
          )}
          {!connections.length && (
            <p className="muted">
              尚无数据连接，请先在数据映射页添加只读连接。
            </p>
          )}
        </section>
        <section>
          <h3>已选择数据表</h3>
          {selected ? (
            <div className="selected-table">
              <Database size={15} />
              {selected.name}
              <button
                className="icon-button"
                aria-label="取消选择"
                onClick={() => setSelected(null)}
              >
                <X size={14} />
              </button>
            </div>
          ) : (
            <p className="muted">从左侧选择一张表</p>
          )}
        </section>
      </div>
      {error && <p className="inline-error">{error}</p>}
      <footer>
        <button className="button button--secondary" onClick={onClose}>
          取消
        </button>
        <button
          className="button button--primary"
          disabled={!selected}
          onClick={() => {
            const c = connections.find((c) => c.id === connectionId);
            if (c && selected) {
              onSelect(c, selected);
              onClose();
            }
          }}
        >
          完成
        </button>
      </footer>
    </dialog>
  );
}
