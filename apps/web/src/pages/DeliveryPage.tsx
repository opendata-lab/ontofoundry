import { HistoryComparison, WorkspaceConstraints } from "../components/ReleaseReview";
import { PublishPanel } from "../components/publish/PublishPanel";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Download, KeyRound, Trash2 } from "lucide-react";
import { api, workspaceRequest } from "../api/client";
import type { VersionSummary } from "../api/types";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { useModeling } from "../hooks/useModeling";
import { usePageTab } from "../hooks/usePageTab";

type PageTab = "publish" | "history" | "service";

export function DeliveryPage() {
  const { workspace, refresh } = useWorkspaceContext();
  const model = useModeling(workspace.id, !!workspace.role, true);
  const [params, setParams] = useSearchParams();
  const tab: PageTab =
    (params.get("tab") as PageTab | null) ?? (workspace.role ? "publish" : "history");
  const setTab = (next: PageTab) =>
    setParams(
      (p) => {
        const value = new URLSearchParams(p);
        value.set("tab", next);
        return value;
      },
      { replace: true },
    );
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [reviewDirty, setReviewDirty] = useState(false);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [result, setResult] = useState("");
  const [tokens, setTokens] = useState<
    { id: string; name: string; scopes?: string[] }[]
  >([]);
  const [token, setToken] = useState("");
  const { setError } = model;
  usePageTab({
    title: model.session ? `发布 · ${model.session.title}` : undefined,
    dirty: reviewDirty,
    busy: reviewBusy,
  });
  const loadVersions = useCallback(
    () =>
      workspaceRequest<{ items: VersionSummary[] }>(
        workspace.id,
        "/versions",
      ).then((r) => setVersions(r.items)),
    [workspace.id],
  );
  useEffect(() => {
    loadVersions().catch((e: Error) => setError(e.message));
    if (workspace.role === "admin")
      workspaceRequest<{ items: typeof tokens }>(
        workspace.id,
        "/service-tokens",
      )
        .then((r) => setTokens(r.items))
        .catch((e: Error) => setError(e.message));
  }, [workspace.id, workspace.role, loadVersions, setError]);
  const serviceRoot =
    window.location.origin + "/api/v1/ontology/workspaces/" + workspace.id;
  const session = model.session;
  const base = versions.find((v) => v.version_id === session?.base_version_id);
  const latest = versions[0];
  return (
    <div className="ref-catalog">
      <nav className="breadcrumb" aria-label="面包屑">
        <Link to={"../builder" + (session ? "?session=" + session.id : "")}>本体自动构建</Link>
        <span aria-hidden> / </span>
        <span>发布与服务</span>
      </nav>
      <header className="catalog-toolbar">
        <h1>发布与服务</h1>
        <div className="toolbar-spacer" />
        {workspace.current_version && (
          <span className="available">
            <CheckCircle2 size={13} />
            当前 v{workspace.current_version}
          </span>
        )}
      </header>
      <div className="ref-tabs page-tabs" role="tablist" aria-label="发布与服务">
        {workspace.role && (
          <button role="tab" aria-selected={tab === "publish"} onClick={() => setTab("publish")}>
            发布
          </button>
        )}
        <button role="tab" aria-selected={tab === "history"} onClick={() => setTab("history")}>
          版本历史
        </button>
        <button role="tab" aria-selected={tab === "service"} onClick={() => setTab("service")}>
          服务接入
        </button>
      </div>
      <div className="management-content delivery-content">
        {tab === "publish" && workspace.role && (
          <section className="publish-tab">
            <div className="publish-context">
              <select
                aria-label="选择发布草稿"
                disabled={reviewBusy || reviewDirty}
                value={session?.id ?? ""}
                onChange={(e) => model.select(e.target.value)}
              >
                <option value="">选择一个建模会话</option>
                {model.sessions.map((s) => (
                  <option value={s.id} key={s.id}>
                    {s.title}
                  </option>
                ))}
              </select>
              {session && (
                <span className="version-chips" aria-label="版本">
                  <span className="chip">基线 {base ? `v${base.version}` : "空白"}</span>→
                  <span className="chip">最新 {latest ? `v${latest.version}` : "无"}</span>→
                  <span className="chip">草稿 r{session.revision}</span>
                </span>
              )}
              {session && (
                <Link className="button button--text" to={"../builder?session=" + session.id}>
                  返回建模
                </Link>
              )}
            </div>
            {result && (
              <p className="validation-pass" role="status">
                {result}
              </p>
            )}
            {session ? (
              <>
                <PublishPanel
                  key={session.id}
                  session={session}
                  disabled={reviewBusy || reviewDirty}
                  onSession={model.setSession}
                  onStale={() => {
                    // The workspace moved on: versions and header too.
                    model.reload();
                    void loadVersions();
                    refresh();
                  }}
                  onPublished={(version, next) => {
                    model.setSession(next);
                    setResult("已发布 v" + version.version);
                    void loadVersions();
                    refresh();
                  }}
                />
                <WorkspaceConstraints
                  key={session.id + "-constraints"}
                  session={session}
                  onSaved={model.setSession}
                  onDirtyChange={setReviewDirty}
                  onBusyChange={setReviewBusy}
                />
              </>
            ) : (
              <p className="muted">选择一个建模会话以预览并发布。</p>
            )}
            {model.error && <p className="inline-error">{model.error}</p>}
          </section>
        )}
        {tab === "history" && (
        <section className="detail-section">
          <h2>已发布版本</h2>
          {workspace.role && versions.length > 0 && (
            <HistoryComparison workspaceId={workspace.id} versions={versions} />
          )}
          <table className="ref-table">
            <thead>
              <tr>
                <th>版本</th>
                <th>说明</th>
                <th>对象 / 关系</th>
                <th>发布时间</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.version_id}>
                  <td>v{v.version}</td>
                  <td>{v.message || "—"}</td>
                  <td>
                    {v.counts.object_types} / {v.counts.link_types}
                  </td>
                  <td>{new Date(v.published_at).toLocaleString("zh-CN")}</td>
                  <td>
                    <a
                      className="button button--text"
                      href={api.exportUrl(workspace.id, v.version_id)}
                      download
                    >
                      <Download size={14} />
                      Ossie JSON
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!versions.length && <p className="muted">还没有已发布版本。</p>}
        </section>
        )}
        {tab === "service" && (
        <section className="detail-section">
          <h2>本体服务</h2>
          <div className="service-columns">
            <div>
              <h3>REST API</h3>
              <p className="muted">
                指定版本读取模型与语义图谱；获准的调用方可读取文档或数据库实例。
              </p>
              <code>{serviceRoot}/types</code>
              <a
                className="button button--text"
                target="_blank"
                rel="noreferrer"
                href="/docs"
              >
                查看接口文档
              </a>
            </div>
            <div>
              <h3>MCP</h3>
              <p className="muted">
                MCP 2026-07-28 ·
                八个本体工具（含按元素读取的清单、分页与按 id 查询）、三个实例工具（按权限开放）；按请求携带协议元数据，不使用旧
                initialize 握手。
              </p>
              <code>{serviceRoot}/mcp</code>
            </div>
          </div>
          {workspace.role === "admin" && (
            <>
              <h3>只读访问令牌</h3>
              <form
                className="row-actions"
                onSubmit={(e) => {
                  e.preventDefault();
                  const data = new FormData(e.currentTarget);
                  workspaceRequest<{ id: string; name: string; token: string }>(
                    workspace.id,
                    "/service-tokens",
                    {
                      name: data.get("name"),
                      scopes: data.get("instances")
                        ? ["ontology:read", "instances:read"]
                        : ["ontology:read"],
                    },
                  )
                    .then((t) => {
                      setToken(t.token);
                      setTokens((ts) => [...ts, t]);
                    })
                    .catch((e: Error) => model.setError(e.message));
                }}
              >
                <input
                  aria-label="令牌名称"
                  name="name"
                  placeholder="调用方名称"
                  required
                />
                <label>
                  <input type="checkbox" name="instances" />
                  允许读取业务实例与证据
                </label>
                <button className="button button--secondary">
                  <KeyRound size={14} />
                  创建令牌
                </button>
              </form>
              {token && (
                <div className="token-result">
                  <strong>请保存令牌，仅此时显示</strong>
                  <code>{token}</code>
                  <button
                    className="button button--text"
                    onClick={() => setToken("")}
                  >
                    已保存，隐藏
                  </button>
                </div>
              )}
              {tokens.map((t) => (
                <div className="token-row" key={t.id}>
                  {t.name}{" "}
                  {t.scopes?.includes("instances:read")
                    ? " · 本体与实例"
                    : " · 仅本体"}
                  <button
                    className="button button--text"
                    onClick={() =>
                      workspaceRequest(
                        workspace.id,
                        "/service-tokens/" + t.id,
                        undefined,
                        "DELETE",
                      )
                        .then(() =>
                          setTokens((ts) => ts.filter((x) => x.id !== t.id)),
                        )
                        .catch((e: Error) => model.setError(e.message))
                    }
                  >
                    <Trash2 size={13} />
                    撤销
                  </button>
                </div>
              ))}
              <p className="muted">
                请求头：Authorization: Bearer
                &lt;令牌&gt;。令牌仅能读取本空间已发布本体。
              </p>
            </>
          )}
        </section>
        )}
      </div>
    </div>
  );
}
