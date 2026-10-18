import {
  FileText,
  Upload as UploadIcon,
  Plus,
  PanelLeftClose,
  PanelLeftOpen,
  Rocket,
  Sparkles,
} from "lucide-react";
import { Alert, Button, Checkbox, Form, Input, Segmented, Tooltip, Typography, Upload } from "antd";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
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
import { BuilderConversationEmpty } from "../components/BuilderConversationEmpty";
import { TableMaterialPicker } from "../components/TableMaterialPicker";
import { SessionPicker } from "../components/SessionPicker";
import { TagList } from "../components/TagList";
import { useModeling } from "../hooks/useModeling";
import { useProposals } from "../hooks/useProposals";
import { usePageTab } from "../hooks/usePageTab";
import { createOntoFoundryConversationTransport } from "../lib/agentConversation";

// The SDK reads its theme from these properties; unset, it would be the one
// green thing on a blue page.
const CONVERSATION = [
  "block h-full min-h-0 w-full flex-[1_1_0] overflow-hidden",
  "[--dac-font-family:var(--font-body)] [--dac-text-color:var(--color-ink)] [--dac-text-muted:var(--color-muted)]",
  "[--dac-content-max-width:760px] [--dac-content-padding-inline:clamp(16px,2vw,24px)] [--dac-content-padding-block:24px] [--dac-message-gap:20px]",
  "[--dac-primary:var(--color-accent)] [--dac-primary-dark:var(--color-accent-hover)] [--dac-primary-color:var(--color-accent)] [--dac-accent:var(--color-accent)] [--dac-user-bubble-bg:var(--color-accent-soft)]",
  "[&::part(run-detail)]:hidden [&::part(root)]:justify-start [&::part(messages)]:flex-[1_1_0] [&::part(messages)]:overflow-auto",
].join(" ");

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
  const conversation = useRef<AgentConversationElement>(null);
  const navigate = useNavigate();
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
  // Ordinary composer messages are chat. Only this action asks DataAgent for a
  // proposals batch: metadata.mode is what the BFF reads to pin the run and
  // expect a result file, and it comes back on completion.
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
    void el.sendMessage(content, { metadata: { mode: "model" } });
    setScenario("");
  };
  const canModel =
    !!capabilities?.agent_configured &&
    !running &&
    !busy &&
    !uploading &&
    (!!session?.material_ids.length || !!scenario.trim());
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
      for (const file of Array.from(files))
        await attach(await modelingApi.upload(workspace.id, file));
    });
    setUploading(false);
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
    el.addEventListener("dataagent-complete", onComplete);
    el.addEventListener("dataagent-error", onError);
    return () => {
      el.removeEventListener("dataagent-run-change", onRun);
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
    el.transportFactory = createOntoFoundryConversationTransport;
    // A modeling run's deliverable is the draft, which the results panel to the
    // right already renders. The raw JSON behind it is not something to hand
    // the user as a file.
    el.showAttachments = false;
    el.endpointResolver = async () =>
      `/api/v1/workspaces/${workspace.id}/sessions/${(await ensure.current()).id}/agent-conversation`;
  }, [workspace.id]);
  useLayoutEffect(() => {
    const el = conversation.current;
    if (!el) return;
    el.endpoint = sessionId
      ? `/api/v1/workspaces/${workspace.id}/sessions/${sessionId}/agent-conversation`
      : "";
  }, [sessionId, workspace.id]);

  const heading = (text: string) => (
    <h3 className="m-0 mb-3 flex items-center text-xs font-semibold before:mr-2 before:block before:h-3 before:w-0.5 before:bg-accent before:content-['']">
      {text}
    </h3>
  );
  return (
    <div className="flex h-full min-w-0 flex-col">
      <header className="flex min-h-14 flex-none flex-wrap items-center gap-3 border-b border-rule-soft bg-surface px-5">
        <h1 className="m-0 text-sm font-semibold whitespace-nowrap text-ink">本体构建</h1>
        <SessionPicker session={session} sessionId={sessionId} sessions={model.sessions} onSelect={model.select} />
        <Tooltip title="新建会话">
          <Button
            aria-label="新建会话"
            icon={<Plus size={15} />}
            disabled={busy}
            onClick={() =>
              act(async () => {
                await model.create();
              })
            }
          />
        </Tooltip>
        <Typography.Text type="secondary" className="text-xs">
          {session ? "最近保存: " + new Date(session.updated_at).toLocaleString("zh-CN", { hour12: false }) : "尚未开始"}
        </Typography.Text>
        <div className="ml-auto flex items-center gap-3 text-xs">
          {/* 只在没配的时候提示——那才是用户需要做事的时候。 */}
          {capabilities && !capabilities.agent_configured && <Link to="../settings">DataAgent 未配置，查看连通性</Link>}
          <Button
            type="primary"
            icon={<Rocket size={14} />}
            disabled={!session || running || busy}
            onClick={() => navigate("../delivery?session=" + session?.id)}
          >
            发布本体
          </Button>
        </div>
      </header>
      {error && (
        <Alert
          type="error"
          showIcon
          banner
          closable={{ closeIcon: true, "aria-label": "关闭错误" }}
          message={error}
          onClose={() => setError("")}
        />
      )}
      {/* A modeling run that ended with questions instead of a result. The
          conversation's own run label only says the turn finished. */}
      {!running && session?.result_state === "awaiting_reply" && (
        <Alert type="info" showIcon banner role="status" message={session.task_detail} />
      )}
      <div
        className={`grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)] ${collapsed ? "grid-cols-[36px_minmax(0,1fr)_minmax(0,1fr)]" : "grid-cols-[minmax(240px,0.95fr)_minmax(280px,1fr)_minmax(310px,1.05fr)] max-[1100px]:grid-cols-[260px_minmax(260px,1fr)_minmax(290px,1fr)]"}`}
      >
        <aside className="flex min-h-0 flex-col overflow-hidden border-r border-rule">
          <header className="flex h-10 flex-none items-center justify-between border-b border-rule-soft px-4">
            {!collapsed && <h2 className="m-0 text-[13px] font-semibold">构建配置</h2>}
            <Button
              type="text"
              size="small"
              onClick={() => setCollapsed(!collapsed)}
              aria-label={collapsed ? "展开构建配置" : "收起构建配置"}
              icon={collapsed ? <PanelLeftOpen size={15} /> : <PanelLeftClose size={15} />}
            />
          </header>
          {!collapsed && (
            <div className="flex flex-1 flex-col gap-6 overflow-auto px-[18px] py-5">
              <section>
                {heading("业务场景标签")}
                <TagList tags={[workspace.name]} />
              </section>
              <section>
                {heading("业务知识")}
                <Segmented
                  size="small"
                  aria-label="建模材料来源"
                  className="!mb-3"
                  value={materialMode}
                  onChange={(v) => setMaterialMode(String(v))}
                  options={[
                    { value: "upload", label: "上传业务知识" },
                    { value: "library", label: "选择已上传材料" },
                  ]}
                />
                {materialMode === "upload" && (
                  <Upload.Dragger
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
                      <strong className="text-[13px]">{uploading ? "正在上传…" : "点击或拖拽文件至此上传"}</strong>
                      <small className="text-xs leading-5 text-muted">
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
                        <span className="inline-flex min-w-0 items-center gap-1.5 text-[13px]">
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
              <section>
                {heading("业务数据")}
                <TableMaterialPicker
                  workspaceId={workspace.id}
                  disabled={busy || running}
                  onMaterial={(material) => act(() => attach(material))}
                />
              </section>
              <section className="flex flex-col gap-3">
                <Form layout="vertical" component="div">
                  <Form.Item label="业务场景描述" className="!mb-0">
                    <Input.TextArea
                      aria-label="业务场景描述"
                      rows={6}
                      placeholder="描述你希望构建的业务本体，例如采购协同中的供应商、物料和供货关系。"
                      value={scenario}
                      onChange={(e) => setScenario(e.target.value)}
                    />
                  </Form.Item>
                </Form>
                <Tooltip title={canModel ? undefined : "先上传或选择业务材料，或填写业务场景描述"}>
                  <Button type="primary" block icon={<Sparkles size={15} />} disabled={!canModel} onClick={startModeling}>
                    {running ? "建模中…" : "开始建模"}
                  </Button>
                </Tooltip>
              </section>
            </div>
          )}
        </aside>
        <section className="flex min-h-0 min-w-0 flex-col overflow-hidden border-r border-rule bg-surface">
          {/* The endpoint is derived from sessionId, never from `session`.
              That object is null while a session loads, and an endpoint that
              momentarily goes empty reads as a conversation switch — the
              element would clear itself and reload for no reason. */}
          <dataagent-conversation
            ref={conversation}
            placeholder="向智能体提问以辅助本体构建…"
            className={CONVERSATION}
          >
            <BuilderConversationEmpty />
          </dataagent-conversation>
        </section>
        <div className="flex min-h-0 min-w-0 flex-col overflow-hidden bg-surface px-3 pt-1 pb-3">
        <ModelResults
          session={session}
          proposals={proposals}
          running={running}
          onRemodel={remodel}
        />
        </div>
      </div>
    </div>
  );
}
