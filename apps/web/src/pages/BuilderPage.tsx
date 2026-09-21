import {
  FileText,
  Upload,
  Send,
  Plus,
  PanelLeftClose,
  PanelLeftOpen,
  Rocket,
  Square,
  Database,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { modelingApi } from "../api/client";
import type { Capabilities, Material } from "../api/types";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import type {
  AgentConversationElement,
  CompleteDetail,
  ErrorDetail,
  RunChangeDetail,
} from "../types/agent-conversation";
import { ModelResults } from "../components/ModelResults";
import { useModeling } from "../hooks/useModeling";
import { usePageActive, usePageTab } from "../hooks/usePageTab";

export function BuilderPage() {
  const { workspace } = useWorkspaceContext();
  const model = useModeling(workspace.id, true, true);
  const { session, sessionId, setSession, error, setError } = model;
  const [materials, setMaterials] = useState<Material[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [scenario, setScenario] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [materialMode, setMaterialMode] = useState("upload");
  const input = useRef<HTMLInputElement>(null);
  const conversation = useRef<AgentConversationElement>(null);
  const navigate = useNavigate();
  const pageActive = usePageActive();
  usePageTab({
    title: session ? `构建 · ${session.title}` : undefined,
    dirty: !!scenario.trim(),
    busy: busy || uploading,
  });
  // Run state comes from the element, not from a status column the page
  // polls. It knows first, and it covers the parked states — waiting_input is
  // still a live run, and treating it as idle would unlock editing mid-run.
  const [running, setRunning] = useState(false);
  useEffect(() => {
    Promise.all([
      modelingApi.materials(workspace.id),
      modelingApi.capabilities(workspace.id),
    ])
      .then(([m, c]) => {
        setMaterials(m.items);
        setCapabilities(c);
      })
      .catch((e: Error) => setError(e.message));
  }, [workspace.id, setError]);
  const act = async (fn: () => Promise<void>) => {
    setError("");
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "操作失败");
    } finally {
      setBusy(false);
    }
  };
  const upload = async (files: FileList | File[]) => {
    setUploading(true);
    await act(async () => {
      let current = await model.ensure();
      for (const file of Array.from(files)) {
        const material = await modelingApi.upload(workspace.id, file);
        setMaterials((ms) => [
          material,
          ...ms.filter((m) => m.id !== material.id),
        ]);
        current = await modelingApi.save(current, current.draft, {
          material_ids: [...new Set([...current.material_ids, material.id])],
        });
      }
      setSession(current);
      setMaterialMode("library");
    });
    setUploading(false);
    if (input.current) input.current.value = "";
  };
  const startModeling = () => {
    const el = conversation.current;
    if (!el) return;
    const text = el.value.trim();
    const content =
      (scenario.trim() && text
        ? `业务场景：${scenario.trim()}\n本次需求：${text}`
        : text) ||
      scenario.trim() ||
      "基于已选材料开始建模";
    // metadata is opaque to the SDK and comes back on completion; it is how we
    // tell a modeling run apart from ordinary chat when deciding what to refresh.
    void el.sendMessage(content, { metadata: { mode: "model" } });
  };

  // The element owns the network; the page only reacts to what it reports.
  useEffect(() => {
    const el = conversation.current;
    if (!el) return;

    const onRun = (event: Event) => {
      const { status } = (event as CustomEvent<RunChangeDetail>).detail;
      const active = [
        "queued",
        "running",
        "waiting_input",
        "waiting_permission",
      ].includes(status);
      setRunning(active);
      // The BFF bumps the session revision when it accepts a run. Without
      // resyncing, every later save, accept and publish would carry a stale
      // revision and be rejected.
      if (active) model.reload();
    };

    const onComplete = (event: Event) => {
      setRunning(false);
      // Reload on any terminal state: the revision moved regardless of how the
      // run ended. Only whether to draw attention to the candidates depends on
      // the mode.
      model.reload();
      const { metadata } = (event as CustomEvent<CompleteDetail>).detail;
      if (metadata?.mode === "model") setError("");
    };

    const onError = (event: Event) => {
      const { message, hint } = (event as CustomEvent<ErrorDetail>).detail;
      setError(hint ? `${message}（${hint}）` : message);
    };

    el.addEventListener("dataagent-run-change", onRun);
    el.addEventListener("dataagent-complete", onComplete);
    el.addEventListener("dataagent-error", onError);
    return () => {
      el.removeEventListener("dataagent-run-change", onRun);
      el.removeEventListener("dataagent-complete", onComplete);
      el.removeEventListener("dataagent-error", onError);
    };
  }, [model, setError]);

  // A session that does not exist yet is created on first send, so opening the
  // page never mints an empty conversation.
  useEffect(() => {
    const el = conversation.current;
    if (el) el.endpointResolver = async () =>
      `/api/v1/workspaces/${workspace.id}/sessions/${(await model.ensure()).id}/agent-conversation`;
  }, [model, workspace.id]);

  return (
    <div className="ref-builder">
      <header className="context-bar">
        <h1>本体自动构建</h1>
        <select
          aria-label="选择建模会话"
          value={session?.id ?? ""}
          onChange={(e) => e.target.value && model.select(e.target.value)}
        >
          <option value="">新的建模会话</option>
          {model.sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {s.title}
            </option>
          ))}
        </select>
        <button
          className="icon-button"
          aria-label="新建会话"
          onClick={() =>
            act(async () => {
              await model.create();
            })
          }
          disabled={busy}
        >
          <Plus size={15} />
        </button>
        <small className="saved-at">
          {session
            ? "最近保存: " +
              new Date(session.updated_at).toLocaleString("zh-CN", {
                hour12: false,
              })
            : "尚未开始"}
        </small>
        <div className="context-right">
          {/* 配好之后这里恒等于同一个运行时名，既不是模型名也点不动，下拉箭头
              还让它看着像个选择器。只在没配的时候提示——那才是用户需要做事的时候，
              「空间设置」本来就在主导航里。 */}
          {capabilities && !capabilities.agent_configured && (
            <span>
              <Link to="../settings">大模型尚未配置</Link>
            </span>
          )}
          <button
            className="button button--primary"
            disabled={!session || running || busy}
            onClick={() => navigate("../delivery?session=" + session?.id)}
          >
            <Rocket size={14} />
            发布本体
          </button>
        </div>
      </header>
      {error && (
        <div className="inline-error" role="alert">
          {error}
          <button onClick={() => setError("")} aria-label="关闭错误">
            ×
          </button>
        </div>
      )}
      <div
        className={
          "ref-builder-columns" + (collapsed ? " config-collapsed" : "")
        }
      >
        <aside className="ref-build-config">
          <header>
            <h2>构建配置</h2>
            <button
              className="icon-button"
              onClick={() => setCollapsed(!collapsed)}
              aria-label={collapsed ? "展开构建配置" : "收起构建配置"}
            >
              {collapsed ? (
                <PanelLeftOpen size={15} />
              ) : (
                <PanelLeftClose size={15} />
              )}
            </button>
          </header>
          {!collapsed && (
            <div className="build-config-scroll">
              <section>
                <h3>业务场景标签</h3>
                <div className="context-tag">{workspace.name}</div>
              </section>
              <section>
                <h3>业务知识</h3>
                <div
                  className="ref-tabs"
                  role="tablist"
                  aria-label="建模材料来源"
                >
                  <button
                    role="tab"
                    aria-selected={materialMode === "upload"}
                    onClick={() => setMaterialMode("upload")}
                  >
                    上传业务知识
                  </button>
                  <button
                    role="tab"
                    aria-selected={materialMode === "library"}
                    onClick={() => setMaterialMode("library")}
                  >
                    选择已上传材料
                  </button>
                </div>
                {materialMode === "upload" && (
                  <button
                    className="ref-upload"
                    aria-label="上传 Markdown 材料"
                    disabled={uploading || running}
                    onClick={() => input.current?.click()}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault();
                      if (!running) void upload(e.dataTransfer.files);
                    }}
                  >
                    <Upload size={23} />
                    <strong>
                      {uploading ? "正在上传…" : "点击或拖拽文件至此上传"}
                    </strong>
                    <small>
                      支持 Markdown · UTF-8
                      <br />
                      单文件不超过 {capabilities?.max_file_mb ?? 256} MB
                    </small>
                  </button>
                )}
                <input
                  ref={input}
                  type="file"
                  accept=".md,.markdown"
                  multiple
                  hidden
                  onChange={(e) =>
                    e.target.files && void upload(e.target.files)
                  }
                />
                {materialMode === "library" && (
                  <div className="material-list">
                    {!materials.length && (
                      <p className="muted">
                        尚未上传材料，请先上传 Markdown 文件。
                      </p>
                    )}
                    {materials.map((m) => (
                      <label key={m.id}>
                        <input
                          type="checkbox"
                          checked={!!session?.material_ids.includes(m.id)}
                          disabled={busy || running}
                          onChange={() =>
                            act(async () => {
                              const s = await model.ensure();
                              setSession(
                                await modelingApi.save(s, s.draft, {
                                  material_ids: s.material_ids.includes(m.id)
                                    ? s.material_ids.filter((id) => id !== m.id)
                                    : [...s.material_ids, m.id],
                                }),
                              );
                            })
                          }
                        />
                        <FileText size={14} />
                        <span title={m.name}>{m.name}</span>
                        <small>{m.chunk_count} 段</small>
                      </label>
                    ))}
                  </div>
                )}
              </section>
              <section>
                <label className="section-field">
                  <span>业务场景描述</span>
                  <textarea
                    rows={6}
                    placeholder="描述你希望构建的业务本体，例如采购协同中的供应商、物料和供货关系。"
                    value={scenario}
                    onChange={(e) => setScenario(e.target.value)}
                  />
                </label>
              </section>
              <section>
                <h3>业务数据</h3>
                <div className="data-source-box">
                  <strong>从数据库选择数据表</strong>
                  <Link className="button button--text" to="../mappings">
                    <Database size={15} />
                    配置数据表
                  </Link>
                </div>
              </section>
            </div>
          )}
        </aside>
        <section className="ref-chat">
          {/* The endpoint is derived from sessionId, never from `session`.
              That object is null while a session loads, and an endpoint that
              momentarily goes empty reads as a conversation switch — the
              element would clear itself and reload for no reason. */}
          <dataagent-conversation
            ref={conversation}
            endpoint={
              sessionId
                ? `/api/v1/workspaces/${workspace.id}/sessions/${sessionId}/agent-conversation`
                : ""
            }
            placeholder="向智能体提问以辅助本体构建…"
          >
            <button
              slot="composer-actions"
              type="button"
              className="button button--secondary"
              disabled={busy}
              onClick={startModeling}
            >
              开始建模
            </button>
          </dataagent-conversation>
        </section>
        <ModelResults
          session={session}
          busy={busy || running}
          onCandidate={(ids, action) =>
            act(async () => {
              if (session)
                setSession(await modelingApi.candidates(session, ids, action));
            })
          }
        />
      </div>
    </div>
  );
}
