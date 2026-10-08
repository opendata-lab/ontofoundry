import { HistoryComparison } from "../components/ReleaseReview";
import { SessionPicker } from "../components/SessionPicker";
import { PublishPanel } from "../components/publish/PublishPanel";
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Check,
  CheckCircle2,
  Copy,
  Download,
  KeyRound,
  Rocket,
  Trash2,
} from "lucide-react";
import { api, workspaceRequest } from "../api/client";
import type { VersionSummary } from "../api/types";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { useModeling } from "../hooks/useModeling";
import { usePageTab } from "../hooks/usePageTab";

type PageTab = "publish" | "history" | "service";

function CopyButton({ text, label }: { text: string; label: string }) {
  const [state, setState] = useState<"idle" | "done" | "failed">("idle");
  return (
    <button
      type="button"
      className="button button--text"
      onClick={() =>
        navigator.clipboard
          .writeText(text)
          .then(() => setState("done"))
          .catch(() => setState("failed"))
      }
    >
      {state === "done" ? <Check size={14} /> : <Copy size={14} />}
      {state === "done" ? "已复制" : state === "failed" ? "复制失败，请手动选择" : label}
    </button>
  );
}

// The `mcpServers` shape DataAgent (and most MCP clients) import as is.
function mcpConfig(url: string, token: string) {
  return JSON.stringify(
    {
      mcpServers: {
        ontofoundry: {
          type: "http",
          url,
          headers: { Authorization: "Bearer " + token },
        },
      },
    },
    null,
    2,
  );
}

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
  const [result, setResult] = useState("");
  const [tokens, setTokens] = useState<
    { id: string; name: string; scopes?: string[] }[]
  >([]);
  const [token, setToken] = useState("");
  const { setError } = model;
  usePageTab({
    title: model.session ? `发布 · ${model.session.title}` : undefined,
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
  return (
    <div className="ref-catalog">
      <header className="catalog-toolbar">
        <h1>本体发布</h1>
        <div className="toolbar-spacer" />
        {workspace.current_version && (
          <span className="available">
            <CheckCircle2 size={13} />
            当前 v{workspace.current_version}
          </span>
        )}
      </header>
      <div className="ref-tabs page-tabs management-tabs" role="tablist" aria-label="本体发布">
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
            {result && (
              <p className="validation-pass" role="status">
                {result}
              </p>
            )}
            {(() => {
              const picker = (
                <SessionPicker
                  session={session}
                  sessionId={session?.id ?? null}
                  sessions={model.sessions}
                  onSelect={model.select}
                />
              );
              if (!session)
                return (
                  <div className="publish-context publish-context--empty">
                    <span className="workspace-empty-icon"><Rocket size={26} aria-hidden="true" /></span>
                    <h2>选择待发布的本体</h2>
                    {picker}
                  </div>
                );
              return (
                <PublishPanel
                  key={session.id}
                  session={session}
                  picker={picker}
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
              );
            })()}
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
              <div className="service-links">
                <CopyButton text={serviceRoot + "/types"} label="复制地址" />
                <a
                  className="button button--text"
                  target="_blank"
                  rel="noreferrer"
                  href="/docs"
                >
                  查看接口文档
                </a>
              </div>
            </div>
            <div>
              <h3>MCP</h3>
              <p className="muted">
                供智能体调用：8 个本体查询工具、3 个业务数据查询工具（令牌需允许查询业务数据）。兼容
                MCP 2026-07-28 与 2025 系列客户端。
              </p>
              <code>{serviceRoot}/mcp</code>
              <div className="service-links">
                <CopyButton text={serviceRoot + "/mcp"} label="复制地址" />
              </div>
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
                  允许查询业务数据（问数需要）
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
                  <CopyButton text={token} label="复制令牌" />
                  <strong>智能体 MCP 配置</strong>
                  <p className="muted">
                    在 DataAgent「MCP 服务 → 导入」中粘贴，即可让智能体通过本体查询数据。
                  </p>
                  <pre className="token-config">
                    {mcpConfig(serviceRoot + "/mcp", token)}
                  </pre>
                  <CopyButton
                    text={mcpConfig(serviceRoot + "/mcp", token)}
                    label="复制 MCP 配置"
                  />
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
