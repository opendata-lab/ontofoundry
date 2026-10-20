import { ArrowUp, FileText, Upload as UploadIcon, Plus, PanelLeftClose, PanelLeftOpen, Search, Sparkles } from "lucide-react";
import { Alert, Button, Checkbox, Dropdown, Input, Segmented, Tag, Tooltip, Typography, Upload } from "antd";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { modelingApi } from "../api/client";
import type { Capabilities, Material } from "../api/types";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import type { AgentConversationElement, CompleteDetail, ErrorDetail, RunChangeDetail } from "../types/agent-conversation";
import { PageBody, PageHeader, Panel, PanelToolbar, SectionTitle } from "../components/layout";
import { ModelResults } from "../components/ModelResults";
import { BuilderConversationEmpty } from "../components/BuilderConversationEmpty";
import { TableMaterialPicker } from "../components/TableMaterialPicker";
import { SessionPicker } from "../components/SessionPicker";
import { TagList } from "../components/TagList";
import { useModeling } from "../hooks/useModeling";
import { useProposals } from "../hooks/useProposals";
import { usePageTab } from "../hooks/usePageTab";
import { useErrorMessage } from "../hooks/useErrorMessage";
import { createOntoFoundryConversationTransport } from "../lib/agentConversation";

// Bridge the SDK's public custom properties to existing design tokens.
const CONVERSATION = [
  "block h-full min-h-0 w-full flex-1 overflow-hidden",
  "[--dac-font-family:var(--font-body)] [--dac-font-size:var(--text-sm)] [--dac-text-color:var(--color-ink)] [--dac-text-muted:var(--color-muted)]",
  "[--dac-content-max-width:var(--review-dialog-width)] [--dac-content-padding-inline:var(--space-md)] [--dac-content-padding-block:var(--space-xl)] [--dac-message-gap:var(--space-lg)]",
  "[--dac-primary:var(--color-accent)] [--dac-primary-dark:var(--color-accent-hover)] [--dac-primary-hover:var(--color-accent-hover)] [--dac-primary-color:var(--color-accent)] [--dac-accent:var(--color-accent)] [--dac-user-bubble-bg:var(--color-accent-soft)]",
  "[--dac-user-bubble-color:var(--color-ink-2)] [--dac-bubble-radius:var(--radius-md)] [--dac-input-radius:var(--radius-sm)] [--dac-button-radius:var(--radius-sm)]",
  "[&::part(run-detail)]:hidden [&::part(root)]:justify-start [&::part(messages)]:flex-1 [&::part(messages)]:overflow-auto",
  "[&::part(actions)]:flex-1 [&::part(send-button)]:hidden",
].join(" ");

export function BuilderPage() {
  const { workspace } = useWorkspaceContext();
  const model = useModeling(workspace.id, true, true);
  const { session, sessionId, setSession, error, setError } = model;
  useErrorMessage(error);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [scenario, setScenario] = useState("");
  const [collapsed, setCollapsed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [materialMode, setMaterialMode] = useState("upload");
  const [composerMode, setComposerMode] = useState<"model" | "chat">("model");
  const [composerDraft, setComposerDraft] = useState("");
  const scenarioId = useId();
  const conversation = useRef<AgentConversationElement>(null);
  usePageTab({
    title: session ? `构建 · ${session.title}` : undefined,
    dirty: !!scenario.trim(),
    busy: busy || uploading,
  });
  // Run state comes from the element, not from a status column the page
  // polls. It knows first, and it covers the parked states — waiting_input is
  // still a live run, and treating it as idle would unlock editing mid-run.
  const [running, setRunning] = useState(false);
  const wasRunning = useRef(false);
  const proposals = useProposals(session, setSession, model.reload);
  const reloadProposals = proposals.reload;
  const reloadModel = model.reload;
  // A stale proposal is re-modelled by the user, not automatically: fill the
  // composer and focus it, never send.
  const remodel = (text: string) => {
    const el = conversation.current;
    if (!el) return;
    el.value = text;
    el.focus();
  };
  useEffect(() => {
    Promise.all([modelingApi.materials(workspace.id), modelingApi.capabilities(workspace.id)])
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
  const send = () => {
    const el = conversation.current;
    if (!el) return;
    void el.sendMessage(el.value.trim() || (composerMode === "model" ? scenario.trim() || "基于已选材料开始建模" : ""), {
      metadata: { mode: composerMode },
    });
  };
  const blocked = !capabilities?.agent_configured || running || busy || uploading;
  const canSend = !blocked && (composerMode === "model"
    ? !!session?.material_ids.length || !!scenario.trim() || !!composerDraft.trim()
    : !!composerDraft.trim());
  const sendState = useRef({ mode: composerMode, scenario, blocked, hasMaterials: !!session?.material_ids.length });
  useLayoutEffect(() => {
    sendState.current = { mode: composerMode, scenario, blocked, hasMaterials: !!session?.material_ids.length };
  });
  const attach = async (material: Material) => {
    const current = await model.ensure();
    setMaterials((ms) => [material, ...ms.filter((m) => m.id !== material.id)]);
    const saved = await modelingApi.save(current, current.draft, {
      material_ids: [...new Set([...current.material_ids, material.id])],
    });
    setSession(saved);
    setMaterialMode("library");
  };
  const upload = async (files: FileList | File[]) => {
    setUploading(true);
    await act(async () => {
      for (const file of Array.from(files)) await attach(await modelingApi.upload(workspace.id, file));
    });
    setUploading(false);
  };

  // The element owns the network; the page only reacts to what it reports.
  useEffect(() => {
    const el = conversation.current;
    if (!el) return;

    const onDraft = (event: Event) => setComposerDraft((event as CustomEvent<{ value: string }>).detail.value);

    const onRun = (event: Event) => {
      const { status } = (event as CustomEvent<RunChangeDetail>).detail;
      const active = ["queued", "running", "waiting_input", "waiting_permission"].includes(status);
      setRunning(active);
      // The BFF bumps the session revision when it accepts a run. Without
      // resyncing, every later save and publish would carry a stale
      // revision and be rejected. Once per run start is enough: the element
      // reports run changes repeatedly while a run is live.
      if (active && !wasRunning.current) reloadModel();
      wasRunning.current = active;
    };

    const onComplete = (event: Event) => {
      setRunning(false);
      wasRunning.current = false;
      // Reload on any terminal state: a modeling result is stored (a new
      // proposal batch, or a replaced draft for a legacy run) before
      // completion is reported.
      reloadModel();
      reloadProposals();
      const { metadata } = (event as CustomEvent<CompleteDetail>).detail;
      if (metadata?.mode === "model") setError("");
    };

    const onError = (event: Event) => {
      const { message, hint } = (event as CustomEvent<ErrorDetail>).detail;
      setError(hint ? `${message}（${hint}）` : message);
      // POST /messages claims the run and advances the revision before any
      // remote call. Even a reported transport/configuration failure can
      // therefore leave this page's session snapshot one revision behind.
      reloadModel();
    };

    el.addEventListener("dataagent-run-change", onRun);
    el.addEventListener("dataagent-draft-change", onDraft);
    el.addEventListener("dataagent-complete", onComplete);
    el.addEventListener("dataagent-error", onError);
    return () => {
      el.removeEventListener("dataagent-run-change", onRun);
      el.removeEventListener("dataagent-draft-change", onDraft);
      el.removeEventListener("dataagent-complete", onComplete);
      el.removeEventListener("dataagent-error", onError);
    };
  }, [reloadModel, setError, reloadProposals]);

  // A session that does not exist yet is created on first send, so opening the
  // page never mints an empty conversation.
  // `model` is a new object on every render. Every property assigned to the
  // element makes it re-render its whole conversation, so assign each one only
  // when its value really changes and read the latest `ensure` through a ref.
  const ensure = useRef(model.ensure);
  useLayoutEffect(() => {
    ensure.current = model.ensure;
  });
  useLayoutEffect(() => {
    const el = conversation.current;
    if (!el) return;

    // Functions are custom-element DOM properties, never JSX attributes.
    // Install the factory before the conversation key: useEndpoint builds a
    // transport when endpoint changes and intentionally does not rebuild one
    // merely because a late factory assignment arrived.
    // Both the host button and the SDK submit path use the selected scene.
    el.transportFactory = (endpoint) => {
      const transport = createOntoFoundryConversationTransport(endpoint);
      return {
        ...transport,
        async sendMessage(input) {
          const current = sendState.current;
          const mode = input.metadata?.mode ?? current.mode;
          const context = current.scenario.trim();
          const content = mode === "model" && context && input.content.trim() !== context
            ? `业务场景：${context}\n本次需求：${input.content}` : input.content;
          const run = await transport.sendMessage({ ...input, content, metadata: { ...input.metadata, mode } });
          if (mode === "model") setScenario((value) => value === current.scenario ? "" : value);
          return run;
        },
      };
    };
    el.beforeSend = ({ content }) => {
      const current = sendState.current;
      return !current.blocked && (current.mode === "model"
        ? current.hasMaterials || !!current.scenario.trim() || !!content.trim()
        : !!content.trim());
    };
    // A modeling run's deliverable is the draft, which the results panel to the
    // right already renders. The raw JSON behind it is not something to hand
    // the user as a file.
    el.showAttachments = false;
    el.endpointResolver = async () => `/api/v1/workspaces/${workspace.id}/sessions/${(await ensure.current()).id}/agent-conversation`;
  }, [workspace.id]);
  useLayoutEffect(() => {
    const el = conversation.current;
    if (!el) return;
    el.endpoint = sessionId ? `/api/v1/workspaces/${workspace.id}/sessions/${sessionId}/agent-conversation` : "";
  }, [sessionId, workspace.id]);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col bg-canvas">
      <PageHeader
        title="本体构建"
        note={session ? "最近保存: " + new Date(session.updated_at).toLocaleString("zh-CN", { hour12: false }) : "尚未开始"}
      />
      <PageBody>
        {/* A modeling run that ended with questions instead of a result. The
          conversation's own run label only says the turn finished. */}
        {!running && session?.result_state === "awaiting_reply" && (
          <Alert type="info" showIcon role="status" message={session.task_detail} />
        )}
        <div className="flex min-h-0 flex-1 gap-4">
          <Panel fill className={collapsed ? "max-w-16" : "max-w-64 2xl:max-w-80"}>
            <PanelToolbar>
              {!collapsed && <SectionTitle title="构建配置" />}
              <Button
                type="text"
                size="small"
                onClick={() => setCollapsed(!collapsed)}
                aria-label={collapsed ? "展开构建配置" : "收起构建配置"}
                icon={collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
              />
            </PanelToolbar>
            {!collapsed && (
              <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-auto p-4">
                <section className="flex shrink-0 flex-col gap-3">
                  <SectionTitle title="业务场景标签" />
                  <TagList tags={[workspace.name]} />
                </section>
                <section className="flex shrink-0 flex-col gap-3">
                  <SectionTitle title="业务知识" />
                  <Segmented
                    size="small"
                    aria-label="建模材料来源"
                    className="max-w-full self-start overflow-x-auto"
                    value={materialMode}
                    onChange={(v) => setMaterialMode(String(v))}
                    options={[
                      { value: "upload", label: "上传业务知识" },
                      { value: "library", label: "选择已上传材料" },
                    ]}
                  />
                  {materialMode === "upload" && (
                    <Upload.Dragger
                      className="block w-full [&_.ant-upload-drag]:h-auto"
                      aria-label="上传业务知识材料"
                      accept=".md,.markdown,.txt,.json,.yaml,.yml,.csv"
                      multiple
                      showUploadList={false}
                      disabled={uploading || running}
                      beforeUpload={(file, fileList) => {
                        if (!fileList.length || file === fileList[0]) {
                          void upload(fileList.length ? fileList : [file]);
                        }
                        return false;
                      }}
                    >
                      <div className="flex flex-col items-center gap-2 px-2 py-2 text-center text-ink-2">
                        <UploadIcon size={23} className="text-accent" />
                        <strong className="text-sm">{uploading ? "正在上传…" : "点击或拖拽文件至此上传"}</strong>
                        <small className="text-xs leading-base text-muted">
                          支持 Markdown、TXT、JSON、YAML、CSV · UTF-8
                          <br />
                          单文件不超过 {capabilities?.max_file_mb ?? 256} MB
                        </small>
                      </div>
                    </Upload.Dragger>
                  )}
                  {materialMode === "library" && (
                    <div className="flex flex-col gap-1">
                      {!materials.length && (
                        <Typography.Text type="secondary" className="text-xs">
                          尚未上传材料，请先上传业务知识文件。
                        </Typography.Text>
                      )}
                      {materials.map((m) => (
                        <Checkbox
                          key={m.id}
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
                        >
                          <span className="inline-flex min-w-0 items-center gap-2 text-sm">
                            <FileText size={14} className="flex-none" />
                            <span className="truncate" title={m.name}>
                              {m.name}
                            </span>
                            <Typography.Text type="secondary" className="text-xs">
                              {m.chunk_count} 段
                            </Typography.Text>
                          </span>
                        </Checkbox>
                      ))}
                    </div>
                  )}
                </section>
                <section className="flex shrink-0 flex-col gap-3">
                  <SectionTitle title="业务数据" />
                  <TableMaterialPicker
                    workspaceId={workspace.id}
                    disabled={busy || running}
                    onMaterial={(material) => act(() => attach(material))}
                  />
                </section>
                <section className="flex shrink-0 flex-col gap-3">
                  <SectionTitle title={<label htmlFor={scenarioId}>业务场景描述</label>} />
                  <Input.TextArea
                    id={scenarioId}
                    aria-label="业务场景描述"
                    rows={6}
                    placeholder="描述你希望构建的业务本体，例如采购协同中的供应商、物料和供货关系。"
                    value={scenario}
                    onChange={(e) => setScenario(e.target.value)}
                  />
                </section>
              </div>
            )}
          </Panel>
          <Panel fill className="min-w-0">
            <PanelToolbar extra={<>
              <SessionPicker session={session} sessionId={sessionId} sessions={model.sessions} onSelect={model.select} presentation="dialog" disabled={busy || uploading} />
              <Tooltip title="新建会话">
                <Button size="small" type="text" aria-label="新建会话" icon={<Plus size={15} />} disabled={busy || uploading}
                  onClick={() => act(async () => { await model.create(); })} />
              </Tooltip>
            </>}>
              <SectionTitle title={<span className="block max-w-40 truncate" title={session?.title}>{session?.title ?? "建模对话"}</span>} />
            </PanelToolbar>
            {/* The endpoint is derived from sessionId, never from `session`.
              That object is null while a session loads, and an endpoint that
              momentarily goes empty reads as a conversation switch — the
              element would clear itself and reload for no reason. */}
            <dataagent-conversation ref={conversation} placeholder={composerMode === "model" ? "描述你希望构建或调整的本体…" : "输入你想了解的本体问题…"} className={CONVERSATION}>
              <BuilderConversationEmpty />
              <div slot="composer-actions" className="flex w-full min-w-0 items-center gap-2">
                <Dropdown trigger={["click"]} placement="topLeft" disabled={running || busy || uploading}
                  menu={{ selectable: true, selectedKeys: [composerMode], items: [{ type: "group", label: "场景", children: [
                    { key: "model", label: "本体建模", icon: <Sparkles size={15} /> },
                    { key: "chat", label: "本体查询", icon: <Search size={15} /> },
                  ] }], onClick: ({ key }) => setComposerMode(key as "model" | "chat") }}>
                  <Button size="small" type="text" aria-label="选择场景" icon={<Plus size={15} />} disabled={running || busy || uploading} />
                </Dropdown>
                <span className="min-w-0 flex-1" role="status"><Tag className="m-0 border-accent bg-accent-soft text-accent">{composerMode === "model" ? "本体建模" : "本体查询"}</Tag></span>
                {!running && <Tooltip title={!capabilities?.agent_configured ? "请先在空间设置中配置 DataAgent" : uploading ? "正在上传材料" : busy ? "操作处理中" : "发送"}>
                  <Button size="small" type="primary" aria-label="发送" icon={<ArrowUp size={15} />} disabled={!canSend} onClick={send} />
                </Tooltip>}
              </div>
            </dataagent-conversation>
          </Panel>
          <div className="flex min-h-0 w-builder-results flex-none flex-col overflow-hidden">
            <ModelResults session={session} proposals={proposals} running={running} busy={busy || uploading} onRemodel={remodel} />
          </div>
        </div>
      </PageBody>
    </div>
  );
}
