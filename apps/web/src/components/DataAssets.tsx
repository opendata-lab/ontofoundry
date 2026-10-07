import { useElementInspector } from "../hooks/useElementInspector";
import { Database, Table2 } from "lucide-react";
import { Fragment, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { workspaceRequest } from "../api/client";
import type { DataConnection, DraftView } from "../api/types";
import "../styles/ontology-reading.css";

type AssetColumn = {
  name: string;
  type: string;
  primary_key: boolean;
  nullable: boolean | null;
  comment: string | null;
};
type AssetMapping = {
  id: string;
  type_id: string;
  name: string;
  fields: Record<string, string>;
  key_column: string;
  status: string;
  missing_columns: string[];
  changed_columns: unknown[];
};
type AssetTable = {
  name: string;
  schema: string | null;
  comment: string | null;
  missing: boolean;
  columns: AssetColumn[];
  mappings: AssetMapping[];
};
type Assets = {
  items: AssetTable[];
  observed_at: string | null;
  version_id: string | null;
  status: string;
  error: string | null;
  changes: { table: string; column: string | null; kind: string }[];
};
const statuses: Record<string, string> = {
  valid: "字段存在",
  review: "字段变化待核对",
  invalid: "映射失效",
  unverified: "未验证",
};
const changes: Record<string, string> = {
  added: "新增",
  removed: "删除",
  changed: "变更",
};

export function DataAssets({
  workspaceId,
  connections,
  draft,
  sessionId,
  onBusyChange,
}: {
  workspaceId: string;
  connections: DataConnection[];
  draft: DraftView | null;
  sessionId: string | null;
  onBusyChange?: (busy: boolean) => void;
}) {
  const navigate = useNavigate();
  const inspector = useElementInspector();
  const [params] = useSearchParams();
  const preferred = connections.find(
    (c) => c.name === params.get("source"),
  )?.id;
  const [chosen, setChosen] = useState("");
  const connectionId = connections.some((c) => c.id === chosen)
    ? chosen
    : preferred || connections[0]?.id || "";
  const connection = connections.find((c) => c.id === connectionId);
  const [schema, setSchema] = useState(params.get("schema") ?? "");
  const [selected, setSelected] = useState(params.get("table") ?? "");
  const [targetType, setTargetType] = useState("");
  const [query, setQuery] = useState("");
  const [data, setData] = useState<Assets | null>(null);
  const [loading, setLoading] = useState(false);
  const [opening, setOpening] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const request = useRef(0);
  const busy = loading || opening;
  const suffix = `/connections/${connectionId}/assets?${new URLSearchParams({ schema_name: schema })}`;

  useEffect(() => {
    onBusyChange?.(opening);
    return () => onBusyChange?.(false);
  }, [opening, onBusyChange]);
  useEffect(() => {
    let active = true;
    const current = ++request.current;
    setData(null);
    setError("");
    setLoading(!!connectionId);
    if (connectionId) {
      workspaceRequest<Assets>(workspaceId, suffix)
        .then((result) => {
          if (active && current === request.current) setData(result);
        })
        .catch((e: Error) => {
          if (active && current === request.current) setError(e.message);
        })
        .finally(() => {
          if (active && current === request.current) setLoading(false);
        });
    }
    return () => {
      active = false;
    };
  }, [workspaceId, connectionId, suffix, attempt]);
  useEffect(() => {
    const current = request;
    return () => {
      current.current++;
    };
  }, [workspaceId, sessionId]);

  const refresh = async () => {
    const current = ++request.current;
    setLoading(true);
    setError("");
    try {
      const result = await workspaceRequest<Assets>(
        workspaceId,
        `/connections/${connectionId}/assets/refresh?${new URLSearchParams({ schema_name: schema })}`,
        {},
      );
      if (current === request.current) setData(result);
    } catch (e) {
      if (current === request.current)
        setError(e instanceof Error ? e.message : "刷新失败");
    } finally {
      if (current === request.current) setLoading(false);
    }
  };
  const mapObject = async (table: AssetTable) => {
    if (!targetType || !connection || table.missing) return;
    const current = ++request.current;
    setOpening(true);
    setError("");
    try {
      if (!draft?.object_types.some((t) => t.id === targetType))
        throw new Error("对象已变化，请重新选择");
      const to = new URL(inspector.href({ kind: "object_type", id: targetType, tab: "mapping", mode: "edit", sessionId }), window.location.origin);
      to.searchParams.set("mapping_source", connection.name);
      to.searchParams.set("mapping_table", table.name);
      to.searchParams.set("mapping_schema", table.schema ?? "");
      // Complete the guarded request before navigating; otherwise the workspace
      // tab blocker treats this successful transition as leaving an active write.
      flushSync(() => {
        setOpening(false);
        onBusyChange?.(false);
      });
      navigate(to.pathname + to.search);
    } catch (e) {
      if (current === request.current)
        setError(e instanceof Error ? e.message : "打开映射失败");
    } finally {
      if (current === request.current) setOpening(false);
    }
  };
  const tables =
    data?.items.filter((table) =>
      `${table.name} ${table.comment ?? ""} ${table.mappings.map((m) => m.name).join(" ")}`
        .toLowerCase()
        .includes(query.toLowerCase()),
    ) ?? [];
  const objectHref = (id: string) =>
    inspector.href({ kind: "object_type", id, tab: "mapping", sessionId });

  return (
    <section className="asset-workspace" aria-label="数据资产目录">
      <aside className="asset-tree">
        <label>
          数据源
          <select
            aria-label="选择资产数据源"
            disabled={opening}
            value={connectionId}
            onChange={(e) => {
              setChosen(e.target.value);
              setSelected("");
              setSchema("");
            }}
          >
            <option value="">选择数据源</option>
            {connections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Schema
          <input
            aria-label="资产 Schema"
            disabled={opening}
            value={schema}
            placeholder="默认 schema"
            onChange={(e) => {
              setSchema(e.target.value);
              setSelected("");
            }}
          />
        </label>
        <label>
          搜索表或对象
          <input
            value={query}
            aria-label="搜索资产"
            onChange={(e) => setQuery(e.target.value)}
            placeholder="表名、注释或业务对象"
          />
        </label>
        {tables.map((table) => (
          <button
            key={table.name}
            aria-pressed={selected === table.name}
            onClick={() => {
              setSelected(selected === table.name ? "" : table.name);
              setTargetType("");
            }}
          >
            {table.name}
          </button>
        ))}
      </aside>
      <div className="asset-main">
        <div className="reading-heading">
          <h2>数据表映射</h2>
          <button
            className="button button--secondary"
            disabled={!connectionId || busy}
            onClick={() => void refresh()}
          >
            {loading ? "加载中…" : "刷新表结构"}
          </button>
        </div>
        {(error || data?.error) && (
          <p className="inline-error" role="alert">
            {error || data?.error}
            {data?.observed_at && " · 展示上次成功快照"}
            <button
              className="button button--text"
              disabled={busy}
              onClick={() => setAttempt((a) => a + 1)}
            >
              重新加载
            </button>
          </p>
        )}
        {!connections.length ? (
          <div className="asset-empty">
            <span className="workspace-empty-icon"><Database size={26} aria-hidden="true" /></span>
            <h3>暂无数据连接</h3>
            <Link className="button button--primary" to="../connections">
              添加数据连接
            </Link>
          </div>
        ) : data?.status === "unobserved" ? (
          <div className="asset-empty">
            <span className="workspace-empty-icon"><Table2 size={26} aria-hidden="true" /></span>
            <h3>表结构未加载</h3>
          </div>
        ) : loading && !data ? (
          <p role="status">加载中…</p>
        ) : (
          data && (
            <>
              {!!data.changes.length && (
                <details className="expression-editor">
                  <summary>本次结构变化 · {data.changes.length} 项</summary>
                  {data.changes.map((change, i) => (
                    <p key={i}>
                      {change.table}
                      {change.column ? `.${change.column}` : ""} ·{" "}
                      {changes[change.kind] ?? change.kind}
                    </p>
                  ))}
                </details>
              )}
              <table className="ref-table">
                <thead>
                  <tr>
                    <th>表名</th>
                    <th>字段</th>
                    <th>映射本体</th>
                    <th>结构验证</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {tables.map((table) => (
                    <Fragment key={table.name}>
                      <tr>
                        <td>
                          <button
                            className="button button--text"
                            aria-expanded={selected === table.name}
                            onClick={() => {
                              setSelected(
                                selected === table.name ? "" : table.name,
                              );
                              setTargetType("");
                            }}
                          >
                            {table.name}
                          </button>
                          <small>{table.comment}</small>
                        </td>
                        <td>
                          {table.missing ? "表已缺失" : table.columns.length}
                        </td>
                        <td>
                          {table.mappings.length
                            ? table.mappings.map((m) => (
                                <div key={m.id}>
                                  <Link to={objectHref(m.type_id)}>
                                    {m.name}
                                  </Link>
                                </div>
                              ))
                            : "未映射"}
                        </td>
                        <td>
                          {table.mappings.map((m) => (
                            <div key={m.id}>
                              <span
                                className={
                                  m.status === "invalid"
                                    ? "inline-error"
                                    : "muted"
                                }
                              >
                                {statuses[m.status] ?? m.status}
                              </span>
                              {!!m.missing_columns.length && (
                                <small>
                                  缺少：{m.missing_columns.join("、")}
                                </small>
                              )}
                            </div>
                          ))}
                        </td>
                        <td>
                          <button
                            className="button button--text"
                            onClick={() => {
                              setSelected(table.name);
                              setTargetType("");
                            }}
                          >
                            查看字段与映射
                          </button>
                        </td>
                      </tr>
                      {selected === table.name && (
                        <tr>
                          <td colSpan={5} className="asset-columns">
                            {!table.missing && !!draft?.object_types.length && (
                              <div className="row-actions">
                                <select
                                  aria-label={`映射 ${table.name} 到业务对象`}
                                  value={targetType}
                                  disabled={opening}
                                  onChange={(e) =>
                                    setTargetType(e.target.value)
                                  }
                                >
                                  <option value="">选择业务对象</option>
                                  {draft.object_types.map((t) => (
                                    <option key={t.id} value={t.id}>
                                      {t.name}
                                    </option>
                                  ))}
                                </select>
                                <button
                                  className="button button--secondary"
                                  disabled={
                                    busy || !targetType || !table.columns.length
                                  }
                                  onClick={() => void mapObject(table)}
                                >
                                  {opening ? "正在打开…" : "配置映射"}
                                </button>
                              </div>
                            )}
                            <table className="ref-table">
                              <thead>
                                <tr>
                                  <th>字段</th>
                                  <th>类型</th>
                                  <th>主键 / 可空</th>
                                  <th>注释</th>
                                  <th>本体属性</th>
                                </tr>
                              </thead>
                              <tbody>
                                {table.columns.map((column) => (
                                  <tr key={column.name}>
                                    <td>{column.name}</td>
                                    <td>{column.type}</td>
                                    <td>
                                      {column.primary_key
                                        ? "主键"
                                        : column.nullable === null
                                          ? "未提供可空信息"
                                          : column.nullable
                                            ? "可空"
                                            : "非空"}
                                    </td>
                                    <td>{column.comment || "—"}</td>
                                    <td>
                                      {table.mappings.flatMap((m) =>
                                        Object.entries(m.fields)
                                          .filter(
                                            ([, field]) =>
                                              field === column.name,
                                          )
                                          .map(([attr]) => (
                                            <div key={`${m.id}-${attr}`}>
                                              <Link to={objectHref(m.type_id)}>
                                                {m.name}.{attr}
                                              </Link>
                                            </div>
                                          )),
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  ))}
                </tbody>
              </table>
              {!tables.length && (
                <p>{query ? "未找到匹配的数据表" : "暂无数据表"}</p>
              )}
            </>
          )
        )}
      </div>
    </section>
  );
}
