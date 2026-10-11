import { Database, Search, Table2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { modelingApi } from "../api/client";
import type { DataConnection, DataTable, Material } from "../api/types";
import { HintIcon } from "./HintIcon";

const HINT =
  "读取所选表的字段、主键、样例值和关联字段，生成一份结构说明加入材料；开始建模后由智能体提出业务对象、数据映射和关系。";

/**
 * Bottom-up modeling input. The chosen tables are described server-side
 * (columns, keys, samples, join hints) as a Markdown material, which the run
 * reads like any document and answers with objects, mappings and joins.
 * Tables are picked in a dialog: a real database has far more tables than the
 * side panel can list.
 */
export function TableMaterialPicker({
  workspaceId,
  disabled,
  onMaterial,
}: {
  workspaceId: string;
  disabled: boolean;
  onMaterial: (material: Material) => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [connections, setConnections] = useState<DataConnection[] | null>(null);
  const [connectionId, setConnectionId] = useState("");
  const [tables, setTables] = useState<DataTable[] | null>(null);
  const [chosen, setChosen] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    modelingApi
      .connections(workspaceId)
      .then((r) => {
        setConnections(r.items);
        if (r.items.length === 1) setConnectionId(r.items[0].id);
      })
      .catch((e: Error) => setError(e.message));
  }, [workspaceId]);
  useEffect(() => {
    setTables(null);
    setChosen([]);
    if (!connectionId) return;
    let active = true;
    modelingApi
      .tables(workspaceId, connectionId)
      .then((r) => active && setTables(r.items))
      .catch((e: Error) => active && setError(e.message));
    return () => {
      active = false;
    };
  }, [workspaceId, connectionId]);

  if (connections && !connections.length)
    return (
      <div className="data-source-box">
        <strong>还没有数据连接</strong>
        <Link className="button button--text" to="../connections">
          <Database size={15} />
          新增数据连接
        </Link>
      </div>
    );

  const needle = query.trim().toLowerCase();
  const visible = (tables ?? []).filter(
    (t) => !needle || `${t.schema ?? ""}.${t.name}`.toLowerCase().includes(needle),
  );
  const toggle = (name: string) =>
    setChosen((c) => (c.includes(name) ? c.filter((n) => n !== name) : [...c, name]));
  const close = () => {
    dialog.current?.close();
    setQuery("");
  };
  const generate = async () => {
    setBusy(true);
    setError("");
    try {
      const material = await modelingApi.tableMaterial(workspaceId, connectionId, chosen);
      await onMaterial(material);
      setChosen([]);
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取数据表失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="data-source-box table-material-picker">
      <div className="table-material-trigger">
        <button
          type="button"
          className="button button--secondary"
          disabled={disabled || !connections}
          onClick={() => dialog.current?.showModal()}
        >
          <Database size={15} />
          选择数据表…
        </button>
        <HintIcon text={HINT} />
      </div>

      <dialog ref={dialog} className="ref-dialog table-material-dialog" aria-label="选择业务数据表" onClose={() => setQuery("")}>
        <header>
          <h2>选择业务数据表</h2>
          <button type="button" className="icon-button" onClick={close} aria-label="关闭选择数据表">
            <X size={18} />
          </button>
        </header>
        <div className="table-material-toolbar">
          <select
            aria-label="数据连接"
            value={connectionId}
            disabled={busy}
            onChange={(e) => setConnectionId(e.target.value)}
          >
            <option value="">选择数据连接</option>
            {connections?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <label className="table-material-search">
            <Search size={14} aria-hidden="true" />
            <input
              type="search"
              aria-label="搜索数据表"
              placeholder="搜索表名"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
        </div>
        {connectionId && (
          <div className="table-material-summary">
            <span className="muted">
              已选 {chosen.length} / 共 {tables?.length ?? 0} 张表
            </span>
            <button
              type="button"
              className="button button--text"
              disabled={!visible.length || busy}
              onClick={() => setChosen((c) => [...new Set([...c, ...visible.map((t) => t.name)])])}
            >
              全选筛选结果
            </button>
            <button
              type="button"
              className="button button--text"
              disabled={!chosen.length || busy}
              onClick={() => setChosen([])}
            >
              清空
            </button>
          </div>
        )}
        <div className="table-choice-list" role="group" aria-label="选择数据表">
          {!connectionId && <p className="muted">先选择数据连接</p>}
          {connectionId && !tables && <p className="muted">正在读取数据表…</p>}
          {tables && !visible.length && <p className="muted">没有匹配的数据表</p>}
          {visible.map((t) => {
            const keys = t.columns.filter((c) => c.primary_key).map((c) => c.name);
            return (
              <label key={`${t.schema ?? ""}.${t.name}`}>
                <input
                  type="checkbox"
                  aria-label={t.name}
                  checked={chosen.includes(t.name)}
                  disabled={busy}
                  onChange={() => toggle(t.name)}
                />
                <Table2 size={14} aria-hidden="true" />
                <span className="table-choice-name">{t.name}</span>
                {/* The list endpoint may omit columns; never show a misleading "0 列". */}
                {(t.schema || t.columns.length > 0) && (
                  <small className="muted">
                    {[
                      t.schema,
                      t.columns.length ? `${t.columns.length} 列` : "",
                      keys.length ? `主键 ${keys.join(", ")}` : "",
                    ].filter(Boolean).join(" · ")}
                  </small>
                )}
              </label>
            );
          })}
        </div>
        {error && <p className="inline-error">{error}</p>}
        <footer>
          <button type="button" className="button button--secondary" onClick={close} disabled={busy}>
            取消
          </button>
          <button
            type="button"
            className="button button--primary"
            disabled={!chosen.length || busy}
            onClick={() => void generate()}
          >
            {busy ? "正在读取表结构…" : `加入建模材料${chosen.length ? `（${chosen.length} 张表）` : ""}`}
          </button>
        </footer>
      </dialog>
    </div>
  );
}
