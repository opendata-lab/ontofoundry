import { Fragment, useEffect, useRef, useState } from "react";
import { flushSync } from "react-dom";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { workspaceRequest, modelingApi } from "../api/client";
import type { DataConnection, Draft } from "../api/types";
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
  draft: Draft | null;
  sessionId: string | null;
  onBusyChange?: (busy: boolean) => void;
}) {
  const navigate = useNavigate();
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
      const session = sessionId
        ? await modelingApi.get(workspaceId, sessionId)
        : await modelingApi.create(workspaceId, `映射 ${table.name}`);
      if (current !== request.current) return;
      if (!session.draft.object_types.some((t) => t.id === targetType))
        throw new Error("对象不在当前草稿中，请重新选择");
      // Pass source context to the editor. A mapping is changed only after the
      // user selects its identity field and explicitly saves the draft there.
      const search = new URLSearchParams({
        session: session.id,
        step: "1",
        mapping_source: connection.name,
        mapping_table: table.name,
        mapping_schema: table.schema ?? "",
      });
      // Complete the guarded request before navigating; otherwise the workspace
      // tab blocker treats this successful transition as leaving an active write.
      flushSync(() => {
        setOpening(false);
        onBusyChange?.(false);
      });
      navigate(`../objects/${targetType}/edit?${search}`);
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
    `../objects/${id}${sessionId ? `?session=${encodeURIComponent(sessionId)}` : ""}`;

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
          <div>
            <h2>源表与本体映射</h2>
            <p className="muted">映射对照已发布定义；编辑会进入建模草稿。</p>
            <p className="muted">
              {data?.observed_at
                ? `结构读取于 ${new Date(data.observed_at).toLocaleString("zh-CN")}`
                : "尚未读取数据结构"}
            </p>
          </div>
          <button
            className="button button--secondary"
            disabled={!connectionId || busy}
            onClick={() => void refresh()}
          >
            {loading ? "正在读取…" : "刷新结构"}
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
          <p className="muted">
            添加只读数据连接后，即可读取表结构并关联本体。
          </p>
        ) : data?.status === "unobserved" ? (
          <p className="muted">
            点击“刷新结构”建立元数据基线，业务数据保留在源系统。
          </p>
        ) : loading && !data ? (
          <p role="status">正在读取资产…</p>
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
                                  {opening ? "正在打开…" : "在草稿中配置映射"}
                                </button>
                                <span className="muted">
                                  进入编辑页后确认数据表、标识字段与属性，保存并发布后生效。
                                </span>
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
                <p className="muted">没有匹配的表，调整筛选或刷新结构。</p>
              )}
            </>
          )
        )}
      </div>
    </section>
  );
}
