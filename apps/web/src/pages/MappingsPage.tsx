import { Database, Plus, X, PlugZap, ExternalLink } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { modelingApi, workspaceRequest } from "../api/client";
import type { DataConnection } from "../api/types";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { useSnapshot } from "../hooks/useSnapshot";
import { DatasetPicker } from "../components/DatasetPicker";
import { usePageTab } from "../hooks/usePageTab";

export function MappingsPage() {
  const { workspace } = useWorkspaceContext();
  const snapshot = useSnapshot(workspace);
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("postgresql");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  usePageTab({ dirty, busy });
  const [picker, setPicker] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    modelingApi
      .connections(workspace.id)
      .then((r) => setConnections(r.items))
      .catch((e: Error) => setError(e.message));
  }, [workspace.id]);
  return (
    <div className="ref-catalog">
      <header className="catalog-toolbar">
        <h1>数据映射</h1>
        <div className="toolbar-spacer" />
        <button
          className="button button--secondary"
          onClick={() => setPicker(true)}
        >
          <Database size={14} />
          浏览数据目录
        </button>
        {workspace.role === "admin" && (
          <button
            className="button button--primary"
            onClick={() => dialog.current?.showModal()}
          >
            <Plus size={14} />
            添加连接
          </button>
        )}
      </header>
      <div className="management-content">
        {(error || snapshot.error) && (
          <div className="inline-error">{error || snapshot.error}</div>
        )}
        <h2>数据连接</h2>
        <p className="muted">
          使用只读数据库账号。实例按需查询，不全量同步源数据。
        </p>
        <div className="connection-grid">
          {connections.map((c) => (
            <article className="connection-card" key={c.id}>
              <Database size={23} />
              <div>
                <h3>{c.name}</h3>
                <p>
                  {c.kind} · {c.database}
                </p>
                <small>
                  {c.host}:{c.port}
                </small>
              </div>
              <button
                className="button button--text"
                onClick={() => {
                  setStatus("");
                  workspaceRequest(
                    workspace.id,
                    "/connections/" + c.id + "/test",
                    {},
                  )
                    .then(() => setStatus(c.name + "：连接正常"))
                    .catch((e: Error) => setError(e.message));
                }}
              >
                <PlugZap size={14} />
                测试
              </button>
            </article>
          ))}
        </div>
        {!connections.length && (
          <div className="empty-data">
            <Database size={26} />
            <strong>尚未添加数据连接</strong>
            <p>添加 MySQL、PostgreSQL 或 Doris 连接后，即可选择表和字段。</p>
          </div>
        )}
        {status && (
          <p className="muted" role="status">
            {status}
          </p>
        )}
        <h2>本体与数据集</h2>
        <table className="ref-table">
          <thead>
            <tr>
              <th>业务对象</th>
              <th>数据集</th>
              <th>标识字段</th>
              <th>已映射属性</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {snapshot.draft?.object_types.map((t) => {
              const m = snapshot.draft?.mappings.find(
                (m) => m.type_id === t.id,
              );
              return (
                <tr key={t.id}>
                  <td>
                    {t.name}
                    <small>{t.technical_name}</small>
                  </td>
                  <td>{m?.table_name ?? "未映射"}</td>
                  <td>{m?.key_column ?? "—"}</td>
                  <td>
                    {Object.keys(m?.fields ?? {}).length}/{t.attributes.length}
                  </td>
                  <td>
                    <Link
                      className="button button--text"
                      to={"../objects/" + t.id + snapshot.suffix}
                    >
                      查看与编辑
                      <ExternalLink size={13} />
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <DatasetPicker
        workspaceId={workspace.id}
        open={picker}
        onClose={() => setPicker(false)}
        onSelect={(c, t) =>
          setStatus(
            c.name + " / " + t.name + " 已选择。进入对应本体的编辑页配置映射。",
          )
        }
      />
      <dialog
        ref={dialog}
        className="ref-dialog connection-dialog"
        aria-label="添加数据连接"
      >
        <form
          onChange={() => setDirty(true)}
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            setError("");
            const f = new FormData(e.currentTarget);
            try {
              const c = await workspaceRequest<DataConnection>(
                workspace.id,
                "/connections",
                {
                  name: f.get("name"),
                  kind,
                  host: f.get("host"),
                  port: Number(f.get("port")),
                  database: f.get("database"),
                  username: f.get("username"),
                  password: f.get("password"),
                },
              );
              setConnections((cs) => [...cs, c]);
              setDirty(false);
              dialog.current?.close();
            } catch (e) {
              setError(e instanceof Error ? e.message : "连接失败");
            } finally {
              setBusy(false);
            }
          }}
        >
          <header>
            <h2>添加只读数据连接</h2>
            <button
              type="button"
              className="icon-button"
              onClick={() => dialog.current?.close()}
              aria-label="关闭添加连接"
            >
              <X size={18} />
            </button>
          </header>
          <label className="section-field">
            <span>连接名称</span>
            <input name="name" required />
          </label>
          <label className="section-field">
            <span>数据库类型</span>
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="postgresql">PostgreSQL</option>
              <option value="mysql">MySQL</option>
              <option value="doris">Apache Doris</option>
            </select>
          </label>
          <div className="form-columns">
            <label className="section-field">
              <span>主机</span>
              <input name="host" required />
            </label>
            <label className="section-field">
              <span>端口</span>
              <input
                name="port"
                type="number"
                key={kind}
                defaultValue={
                  kind === "postgresql" ? 5432 : kind === "doris" ? 9030 : 3306
                }
                required
                min="1"
                max="65535"
              />
            </label>
          </div>
          <label className="section-field">
            <span>数据库名称</span>
            <input name="database" required />
          </label>
          <div className="form-columns">
            <label className="section-field">
              <span>只读用户名</span>
              <input name="username" required autoComplete="off" />
            </label>
            <label className="section-field">
              <span>密码</span>
              <input
                name="password"
                type="password"
                autoComplete="new-password"
              />
            </label>
          </div>
          {error && <p className="inline-error">{error}</p>}
          <footer>
            <button className="button button--primary" disabled={busy}>
              {busy ? "测试连接中…" : "测试并保存"}
            </button>
          </footer>
        </form>
      </dialog>
    </div>
  );
}
