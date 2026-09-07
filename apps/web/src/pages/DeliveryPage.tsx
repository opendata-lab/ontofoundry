import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { CheckCircle2, Download, Rocket, KeyRound, Trash2 } from "lucide-react";
import { api, ApiError, modelingApi, workspaceRequest } from "../api/client";
import type { ModelingSession, VersionSummary } from "../api/types";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { useModeling } from "../hooks/useModeling";
import { usePageTab } from "../hooks/usePageTab";

type MergeConflict = {
  path: string;
  base: unknown;
  current: unknown;
  draft: unknown;
};
export function DeliveryPage() {
  const { workspace, refresh } = useWorkspaceContext();
  const model = useModeling(workspace.id, !!workspace.role, true);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [report, setReport] = useState<VersionSummary["validation"] | null>(
    null,
  );
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState("");
  const [conflict, setConflict] = useState<{
    current_version_id: string;
    conflicts: MergeConflict[];
  } | null>(null);
  const [choices, setChoices] = useState<Record<string, string>>({});
  const [tokens, setTokens] = useState<{ id: string; name: string }[]>([]);
  const [token, setToken] = useState("");
  const { setError } = model;
  usePageTab({
    title: model.session ? `发布 · ${model.session.title}` : undefined,
    dirty: !!message.trim() || Object.keys(choices).length > 0,
    busy,
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
  const publish = async () => {
    if (!model.session) return;
    setBusy(true);
    model.setError("");
    setConflict(null);
    try {
      const validation = await modelingApi.validate(model.session);
      setReport(validation);
      if (!validation.publishable) return;
      const r = await modelingApi.publish(model.session, message);
      model.setSession(r.session);
      setResult("已整体发布 v" + r.version.version);
      setMessage("");
      setChoices({});
      await loadVersions();
      refresh();
    } catch (e) {
      if (
        e instanceof ApiError &&
        e.status === 409 &&
        typeof e.detail === "object" &&
        e.detail &&
        "conflicts" in e.detail
      )
        setConflict(e.detail as typeof conflict);
      else model.setError(e instanceof Error ? e.message : "发布失败");
    } finally {
      setBusy(false);
    }
  };
  const serviceRoot =
    window.location.origin + "/api/v1/ontology/workspaces/" + workspace.id;
  return (
    <div className="ref-catalog">
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
      <div className="management-content delivery-content">
        {workspace.role && (
          <section className="detail-section">
            <h2>整体发布本体</h2>
            <p className="muted">
              发布当前会话的完整草稿。本体视图、REST API 与 MCP
              同时使用这个版本。
            </p>
            <select
              aria-label="选择发布草稿"
              value={model.session?.id ?? ""}
              onChange={(e) => model.select(e.target.value)}
            >
              <option value="">选择一个建模会话</option>
              {model.sessions.map((s) => (
                <option value={s.id} key={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
            {model.session && (
              <>
                <div className="release-stats">
                  <span>
                    实体 <b>{model.session.draft.object_types.length}</b>
                  </span>
                  <span>
                    关系 <b>{model.session.draft.link_types.length}</b>
                  </span>
                  <span>
                    文档实例 <b>{model.session.draft.objects.length}</b>
                  </span>
                  <span>
                    映射 <b>{model.session.draft.mappings.length}</b>
                  </span>
                  <span>
                    待确认候选{" "}
                    <b>
                      {
                        model.session.candidates.filter(
                          (c) => c.status === "pending",
                        ).length
                      }
                    </b>
                  </span>
                </div>
                <label className="section-field">
                  <span>版本说明</span>
                  <input
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    maxLength={240}
                    placeholder="说明本次模型变化"
                  />
                </label>
                <div className="row-actions">
                  <Link
                    className="button button--secondary"
                    to={"../builder?session=" + model.session.id}
                  >
                    返回草稿
                  </Link>
                  <button
                    className="button button--secondary"
                    disabled={busy}
                    onClick={() =>
                      modelingApi
                        .validate(model.session!)
                        .then(setReport)
                        .catch((e: Error) => model.setError(e.message))
                    }
                  >
                    校验 JSON
                  </button>
                  <button
                    className="button button--primary"
                    disabled={busy}
                    onClick={publish}
                  >
                    <Rocket size={14} />
                    {busy ? "校验与发布中…" : "发布整个空间"}
                  </button>
                </div>
              </>
            )}
            {report && (
              <div
                className={
                  report.publishable ? "validation-pass" : "inline-error"
                }
              >
                {report.publishable
                  ? "JSON Schema 与语义引用校验通过"
                  : "校验未通过"}
                {report.errors.map((e, i) => (
                  <p key={i}>{(e as { message: string }).message}</p>
                ))}
              </div>
            )}
            {result && (
              <p className="validation-pass" role="status">
                {result}
              </p>
            )}
            {conflict && (
              <div className="merge-conflicts">
                <h3>合并冲突</h3>
                {conflict.conflicts.map((c) => (
                  <div key={c.path}>
                    <strong>{c.path}</strong>
                    <div className="merge-columns">
                      <section>
                        <small>基线</small>
                        <pre>{JSON.stringify(c.base, null, 2)}</pre>
                      </section>
                      <section>
                        <label>
                          <input
                            type="radio"
                            name={c.path}
                            checked={choices[c.path] === "current"}
                            onChange={() =>
                              setChoices({ ...choices, [c.path]: "current" })
                            }
                          />
                          使用最新版本
                        </label>
                        <pre>{JSON.stringify(c.current, null, 2)}</pre>
                      </section>
                      <section>
                        <label>
                          <input
                            type="radio"
                            name={c.path}
                            checked={choices[c.path] === "draft"}
                            onChange={() =>
                              setChoices({ ...choices, [c.path]: "draft" })
                            }
                          />
                          使用当前草稿
                        </label>
                        <pre>{JSON.stringify(c.draft, null, 2)}</pre>
                      </section>
                    </div>
                  </div>
                ))}
                <button
                  className="button button--primary"
                  disabled={conflict.conflicts.some((c) => !choices[c.path])}
                  onClick={() =>
                    workspaceRequest<ModelingSession>(
                      workspace.id,
                      "/sessions/" + model.session!.id + "/resolve-merge",
                      {
                        revision: model.session!.revision,
                        current_version_id: conflict.current_version_id,
                        resolutions: choices,
                      },
                    )
                      .then((s) => {
                        model.setSession(s);
                        setConflict(null);
                        setResult("冲突已合并，请重新校验后发布");
                      })
                      .catch((e: Error) => model.setError(e.message))
                  }
                >
                  保存合并结果
                </button>
              </div>
            )}
          </section>
        )}
        {model.error && <p className="inline-error">{model.error}</p>}
        <section className="detail-section">
          <h2>已发布版本</h2>
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
        <section className="detail-section">
          <h2>本体服务</h2>
          <div className="service-columns">
            <div>
              <h3>REST API</h3>
              <p className="muted">读取当前发布的模型、关系与语义图谱。</p>
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
                MCP 2026-07-28 · 五个只读工具；按请求携带协议元数据，不使用旧
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
                    { name: data.get("name") },
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
                  {t.name}
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
      </div>
    </div>
  );
}
