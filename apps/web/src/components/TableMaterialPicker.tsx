import { Database, Table2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { modelingApi } from "../api/client";
import type { DataConnection, Material } from "../api/types";

/**
 * Bottom-up modeling input. The chosen tables are described server-side
 * (columns, keys, samples, join hints) as a Markdown material, which the run
 * reads like any document and answers with objects, mappings and joins.
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
  const [connections, setConnections] = useState<DataConnection[] | null>(null);
  const [connectionId, setConnectionId] = useState("");
  const [tables, setTables] = useState<string[]>([]);
  const [chosen, setChosen] = useState<string[]>([]);
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
    setTables([]);
    setChosen([]);
    if (!connectionId) return;
    let active = true;
    modelingApi
      .tables(workspaceId, connectionId)
      .then((r) => active && setTables(r.items.map((t) => t.name)))
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
  const generate = async () => {
    setBusy(true);
    setError("");
    try {
      const material = await modelingApi.tableMaterial(workspaceId, connectionId, chosen);
      await onMaterial(material);
      setChosen([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取数据表失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="data-source-box table-material-picker">
      <select
        aria-label="数据连接"
        value={connectionId}
        disabled={busy || disabled}
        onChange={(e) => setConnectionId(e.target.value)}
      >
        <option value="">选择数据连接</option>
        {connections?.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
      {connectionId && (
        <div className="table-choice-list" role="group" aria-label="选择数据表">
          {!tables.length && <p className="muted">正在读取数据表…</p>}
          {tables.map((name) => (
            <label key={name}>
              <input
                type="checkbox"
                checked={chosen.includes(name)}
                disabled={busy || disabled}
                onChange={() =>
                  setChosen((c) =>
                    c.includes(name) ? c.filter((n) => n !== name) : [...c, name],
                  )
                }
              />
              <Table2 size={14} />
              <span>{name}</span>
            </label>
          ))}
        </div>
      )}
      {error && <p className="inline-error">{error}</p>}
      <button
        type="button"
        className="button button--secondary"
        disabled={!chosen.length || busy || disabled}
        onClick={() => void generate()}
      >
        <Database size={15} />
        {busy ? "正在读取表结构…" : `加入建模材料${chosen.length ? `（${chosen.length} 张表）` : ""}`}
      </button>
      <p className="muted">
        读取所选表的字段、主键、样例值和关联字段，生成一份结构说明加入材料；开始建模后由智能体提出业务对象、数据映射和关系。
      </p>
    </div>
  );
}
