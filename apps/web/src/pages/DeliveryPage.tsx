import { LoadingSurface } from "../components/AsyncState";
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
  Rocket,
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
  }, [loadVersions, setError]);
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
                  sessionId={model.sessionId}
                  sessions={model.sessions}
                  onSelect={model.select}
                />
              );
              // A session named in the address (?session=) is being loaded,
              // which takes a while on a large draft: say so instead of
              // offering the chooser as if none had been asked for.
              if (!session && model.sessionId && !model.error)
                return <LoadingSurface label="正在加载会话…" />;
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
              <code>{serviceRoot}/mcp</code>
              <div className="service-links">
                <CopyButton text={serviceRoot + "/mcp"} label="复制地址" />
              </div>
            </div>
          </div>
        </section>
        )}
      </div>
    </div>
  );
}
