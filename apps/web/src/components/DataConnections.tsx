import { Database, Plus, X, PlugZap } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { modelingApi, workspaceRequest } from "../api/client";
import type { DataConnection } from "../api/types";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";

/**
 * 数据连接管理。
 *
 * 只负责内容，不含标题——标题归页面。这样组件被嵌到别处时不会带出一个重复的
 * 二级标题。新建弹窗由组件持有（表单状态在这里），触发按钮通过 onReady 交给
 * 页面工具栏，和其他页的主操作位置保持一致。
 */
export function DataConnections({
  onReady,
}: {
  /** 把"打开新建弹窗"交给调用方，让按钮能放进页面工具栏。 */
  onReady?: (open: () => void) => void;
}) {
  const { workspace } = useWorkspaceContext();
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("postgresql");
  const [busy, setBusy] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    onReady?.(() => dialog.current?.showModal());
  }, [onReady]);

  useEffect(() => {
    modelingApi
      .connections(workspace.id)
      .then((r) => setConnections(r.items))
      .catch((e: Error) => setError(e.message));
  }, [workspace.id]);

  return (
    <section className="detail-section">
      <p className="muted">
        使用只读数据库账号。实例按需查询，不全量同步源数据。
      </p>

      {error && <div className="inline-error">{error}</div>}

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
                workspaceRequest(workspace.id, "/connections/" + c.id + "/test", {})
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
          <p>添加 MySQL、PostgreSQL 或 Doris 连接后，即可在数据映射里选择表和字段。</p>
        </div>
      )}

      {status && (
        <p className="muted" role="status">
          {status}
        </p>
      )}

      <dialog ref={dialog} className="ref-dialog connection-dialog" aria-label="添加数据连接">
        <form
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
                defaultValue={kind === "postgresql" ? 5432 : kind === "doris" ? 9030 : 3306}
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
              <input name="password" type="password" autoComplete="new-password" />
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
    </section>
  );
}
