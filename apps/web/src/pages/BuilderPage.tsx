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
  ChevronDown,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { modelingApi } from "../api/client";
import type { Capabilities, Material } from "../api/types";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { ModelResults } from "../components/ModelResults";
import { useModeling } from "../hooks/useModeling";
import { usePageActive, usePageTab } from "../hooks/usePageTab";

export function BuilderPage() {
  const { workspace } = useWorkspaceContext();
  const model = useModeling(workspace.id, true, true);
  const { session, setSession, error, setError } = model;
  const [materials, setMaterials] = useState<Material[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [prompt, setPrompt] = useState("");
  const [scenario, setScenario] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [materialMode, setMaterialMode] = useState("upload");
  const input = useRef<HTMLInputElement>(null);
  const chatEnd = useRef<HTMLDivElement>(null);
  const lastChatUpdate = useRef("");
  const navigate = useNavigate();
  const pageActive = usePageActive();
  usePageTab({
    title: session ? `构建 · ${session.title}` : undefined,
    dirty: !!prompt.trim() || !!scenario.trim(),
    busy: busy || uploading,
  });
  const running =
    !!session && ["queued", "running"].includes(session.task_status);
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
  useEffect(() => {
    if (!session) return;
    const stamp = `${session.id}/${session.messages.length}/${session.task_detail}`;
    if (pageActive && lastChatUpdate.current !== stamp)
      chatEnd.current?.scrollIntoView({ block: "nearest" });
    lastChatUpdate.current = stamp;
  }, [session, pageActive]);
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
  const send = (mode: string) =>
    act(async () => {
      const content =
        (mode === "model" && scenario.trim() && prompt.trim()
          ? `业务场景：${scenario.trim()}\n本次需求：${prompt.trim()}`
          : prompt.trim()) ||
        (mode === "model" ? scenario.trim() || "基于已选材料开始建模" : "");
      if (!content) return;
      const current = await model.ensure();
      setSession(await modelingApi.chat(current, content, mode));
      setPrompt("");
    });
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
          <span>
            LLM:{" "}
            <Link to="../settings">
              {capabilities?.model || "未配置"} <ChevronDown size={12} />
            </Link>
          </span>
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
          <div className="chat-scroll">
            {!session?.messages.length ? (
              <div className="agent-welcome">
                <h2>
                  你好，
                  <br />
                  我是本体自动构建助手，
                  <br />
                  很高兴为你服务！
                </h2>
                <p>
                  你可以直接用自然语言描述业务场景，或在左侧上传材料，补充业务知识后开始构建。
                </p>
                <div className="prompt-suggestions">
                  {[
                    "结合已上传文档生成本体模型",
                    "帮我澄清一个业务概念",
                    "解释实体、属性与关系的区别",
                  ].map((p) => (
                    <button key={p} onClick={() => setPrompt(p)}>
                      {p}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              session.messages.map((m, i) => (
                <div key={i} className={"chat-message chat-message--" + m.role}>
                  {m.content}
                </div>
              ))
            )}
            {session?.task_status !== "idle" && session && (
              <div
                className={
                  "task-progress task-progress--" + session.task_status
                }
              >
                <span
                  className={running ? "progress-spinner" : "progress-check"}
                />
                <strong>
                  {
                    (
                      {
                        queued: "排队中",
                        running: "构建进行中",
                        completed: "处理完成",
                        failed: "处理失败",
                        cancelled: "已取消",
                      } as Record<string, string>
                    )[session.task_status]
                  }
                </strong>
                <p>{session.task_detail}</p>
              </div>
            )}
            {session && !running && session.candidates.length > 0 && (
              <div className="build-summary">
                <h3>构建产出</h3>
                <p>
                  {
                    session.candidates.filter((c) => c.status === "pending")
                      .length
                  }{" "}
                  项待确认候选 · {session.draft.object_types.length} 个草稿实体
                  · {session.draft.link_types.length} 条草稿关系
                </p>
                <span>
                  在右侧展开模型查看属性与来源，接受后可继续人工编辑。
                </span>
              </div>
            )}
            <div ref={chatEnd} />
          </div>
          <form
            className="ref-composer"
            onSubmit={(e) => {
              e.preventDefault();
              void send("chat");
            }}
          >
            <textarea
              aria-label="Agent 对话"
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="向智能体提问以辅助本体构建…"
              disabled={running}
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                  e.preventDefault();
                  void send("chat");
                }
              }}
            />
            <footer>
              {session && <span>会话草稿 · 独立保存</span>}
              <div>
                {running ? (
                  <button
                    type="button"
                    className="button button--secondary"
                    onClick={() =>
                      act(async () => {
                        if (session)
                          setSession(await modelingApi.cancel(session));
                      })
                    }
                  >
                    <Square size={12} />
                    停止
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      className="button button--secondary"
                      disabled={busy}
                      onClick={() => void send("model")}
                    >
                      开始建模
                    </button>
                    <button
                      type="submit"
                      className="button button--primary send-button"
                      aria-label="发送对话"
                      disabled={busy || !prompt.trim()}
                    >
                      <Send size={16} />
                    </button>
                  </>
                )}
              </div>
            </footer>
          </form>
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
