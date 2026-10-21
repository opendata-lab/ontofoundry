import { Alert, Button, Collapse, Descriptions, Drawer, Empty, Form, Input, List, Modal, Segmented, Spin, Tabs, Tag, Tooltip, Typography } from "antd";
import { ArrowRight } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError, publishApi } from "../../api/client";
import type { ElementChange, MergeConflict, ModelingSession, PublishPreview, TargetKind, VersionSummary } from "../../api/types";
import type { ElementRequest } from "../../lib/elementInspector";
import { documentDisplayText } from "../../lib/instanceDisplay";
import { lineDiff } from "../../lib/lineDiff";
import { fieldLabel, KIND } from "../proposals/elementMeta";
import { FieldDiff } from "../proposals/FieldDiff";
import { PanelToolbar, SectionTitle, StatusMark, type StatusState } from "../layout";
import { ElementModal } from "../elements/ElementInspector";
import { ConflictResolver } from "./ConflictResolver";

const { Text } = Typography;

const CHANGE: Record<ElementChange["change"], { text: string; state: StatusState }> = {
  created: { text: "新增", state: "mapped" },
  updated: { text: "修改", state: "info" },
  deleted: { text: "删除", state: "error" },
};
const KIND_ORDER: TargetKind[] = [
  "object_type",
  "property",
  "link_type",
  "rule",
  "metric",
  "dataset",
  "mapping",
  "material_object",
  "material_link",
];
/** Past this many changes, cards start collapsed. */
const COLLAPSE_AFTER = 20;
/** Fields that point at another element; the object view shows its name. */
const REFERENCE_FIELDS = new Set([
  "owner_type_id",
  "source_type_id",
  "target_type_id",
  "source_id",
  "target_id",
  "owner_id",
  "type_id",
  "extends",
  "dataset_id",
  "numerator_id",
  "denominator_id",
  "title_property_id",
]);

type Filter = "all" | ElementChange["change"];

function show(value: unknown) {
  if (value === null || value === undefined) return "（无）";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

/** A field value as a reader would want it, not as stored. */
function readable(key: string, value: unknown): string {
  if (typeof value === "boolean") return value ? "是" : "否";
  if (key === "evidence" && Array.isArray(value)) {
    const quotes = value
      .map((e) => (e as { quote?: string }).quote)
      .filter(Boolean)
      .map((q) => `「${q}」`);
    return `${value.length} 条证据` + (quotes.length ? "：" + quotes.join(" ") : "");
  }
  if (Array.isArray(value) && value.every((v) => typeof v === "string")) return value.join("、");
  return show(value);
}

function JsonSplit({ before, after }: { before: unknown; after: unknown }) {
  const left = JSON.stringify(before, null, 2).split("\n");
  const right = JSON.stringify(after, null, 2).split("\n");
  const { removed, added } = lineDiff(left, right);
  const side = (lines: string[], marks: boolean[], cls: string) => (
    <pre className="m-0 max-h-review-code overflow-auto rounded-sm bg-surface-soft p-2 font-mono text-xs leading-base">
      {lines.map((line, i) => (
        <span key={i} className={`block ${marks[i] ? cls : ""}`}>
          {line || " "}
        </span>
      ))}
    </pre>
  );
  return (
    <div className="grid grid-cols-2 gap-2">
      <div className="flex min-w-0 flex-col gap-1">
        <Text type="secondary" className="text-xs">
          当前发布版本
        </Text>
        {side(left, removed, "bg-danger-soft")}
      </div>
      <div className="flex min-w-0 flex-col gap-1">
        <Text type="secondary" className="text-xs">
          发布后
        </Text>
        {side(right, added, "bg-success-soft")}
      </div>
    </div>
  );
}

/** The fields of a created or deleted element, minus identity and empty values. */
function FieldList({ value, names, kind }: { value: Record<string, unknown>; names: Map<string, string>; kind: ElementChange["element_kind"] }) {
  const named = (key: string, v: unknown) =>
    !REFERENCE_FIELDS.has(key) ? v : Array.isArray(v) ? v.map((id) => names.get(String(id)) ?? id) : (names.get(String(v)) ?? v);
  const rows = Object.entries(value).filter(
    ([key, v]) => key !== "id" && v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0),
  );
  if (!rows.length) return <Text type="secondary">无字段内容</Text>;
  return (
    <Descriptions
      size="small"
      column={1}
      items={rows.map(([key, v]) => ({
        key,
        label: fieldLabel(key, kind),
        children: <span className="text-xs whitespace-pre-wrap break-all">{readable(key, named(key, v))}</span>,
      }))}
    />
  );
}

function ChangeBody({ change, names }: { change: ElementChange; names: Map<string, string> }) {
  const [mode, setMode] = useState<"object" | "json">("object");
  return (
    <div className="flex flex-col gap-2">
      <Segmented
        size="small"
        className="self-end"
        value={mode}
        onChange={(v) => setMode(v as typeof mode)}
        options={[
          { value: "object", label: "对象" },
          { value: "json", label: "JSON" },
        ]}
      />
      {mode === "json" ? (
        change.change === "updated" ? (
          <JsonSplit before={change.before} after={change.after} />
        ) : (
          <pre className="m-0 max-h-review-code overflow-auto rounded-sm bg-surface-soft p-2 font-mono text-xs">
            {JSON.stringify(change.change === "created" ? change.after : change.before, null, 2)}
          </pre>
        )
      ) : change.change === "updated" ? (
        change.field_changes.length ? (
          <FieldDiff kind={change.element_kind} changes={change.field_changes} beforeLabel="当前发布版本" afterLabel="发布后" names={names} />
        ) : (
          <Text type="secondary">无字段级变化</Text>
        )
      ) : (
        <FieldList kind={change.element_kind} value={((change.change === "created" ? change.after : change.before) ?? {}) as Record<string, unknown>} names={names} />
      )}
    </div>
  );
}

function changeLabel(change: ElementChange) {
  return (change.owner_label && change.element_kind === "property" ? `${change.owner_label}.` : "") + change.label;
}

function ChangeList({
  changes,
  names,
  open,
  onInspect,
}: {
  changes: ElementChange[];
  names: Map<string, string>;
  open: string[];
  onInspect?: (change: ElementChange) => void;
}) {
  const [active, setActive] = useState(open);
  useEffect(() => setActive(open), [open]);
  return (
    <Collapse
      ghost
      size="small"
      activeKey={active}
      onChange={(keys) => setActive(keys as string[])}
      items={changes.map((c) => ({
        key: c.element_id,
        label: (
          <span className="flex flex-wrap items-center gap-2" aria-label={`${KIND[c.element_kind].label} ${changeLabel(c)}`}>
            <StatusMark state={CHANGE[c.change].state} label={CHANGE[c.change].text} />
            <Tag className="m-0">
              {KIND[c.element_kind].label}
            </Tag>
            <strong>{changeLabel(c)}</strong>
            {c.change === "updated" && c.field_changes.length > 0 && (
              <Text type="secondary" className="text-xs">
                {c.field_changes.length} 个字段
              </Text>
            )}
          </span>
        ),
        extra:
          onInspect && c.change !== "deleted" ? (
            <Button
              size="small"
              type="link"
              onClick={(e) => {
                e.stopPropagation();
                onInspect(c);
              }}
            >
              查看发布后的元素
            </Button>
          ) : undefined,
        children: <ChangeBody change={c} names={names} />,
      }))}
    />
  );
}

function sortChanges<T extends ElementChange>(changes: T[]) {
  return [...changes].sort((a, b) => KIND_ORDER.indexOf(a.element_kind) - KIND_ORDER.indexOf(b.element_kind));
}

/** Element names by id: the preview's labels first, the session's draft as fallback. */
function elementNames(preview: PublishPreview | null, draft: ModelingSession["draft"]): Map<string, string> {
  const names = new Map<string, string>();
  for (const key of ["object_types", "properties", "link_types", "rules", "metrics", "datasets"] as const)
    for (const item of draft[key] as { id: string; name?: string; display_name?: string | null }[]) if (item.name) names.set(item.id, item.display_name || item.name);
  for (const fact of draft.material_objects) names.set(fact.id, documentDisplayText(draft, fact));
  if (preview?.merged_model) {
    for (const fact of preview.merged_model.material_objects)
      names.set(fact.id, documentDisplayText(preview.merged_model, fact));
  }
  for (const [id, label] of Object.entries(preview?.labels ?? {})) names.set(id, label);
  return names;
}

const versionLabel = (n: number | null | undefined) => (n ? `v${n}` : "尚未发布");

const CHECK_STATE: Record<"pass" | "fail" | "warn" | "idle", StatusState> = {
  pass: "mapped",
  fail: "error",
  warn: "partial",
  idle: "pending",
};

/**
 * Publish tab, laid out like a pull request: which session merges into the
 * current published version and the publish button on top, then what
 * publishing changes and the checks as two tabs. It always shows the server's
 * merge — the exact content that will be published — and publishes only with
 * the values it previewed.
 */
export function PublishPanel({
  session,
  onSession,
  onPublished,
  onStale,
  disabled = false,
  picker,
}: {
  session: ModelingSession;
  onSession: (value: ModelingSession) => void;
  onPublished: (version: VersionSummary, session: ModelingSession) => void;
  onStale: () => void;
  disabled?: boolean;
  /** The session selector, shown where a pull request names its branch. */
  picker?: ReactNode;
}) {
  // The release page shows changed elements in place; the popup leads on to their pages.
  const [inspected, setInspected] = useState<ElementRequest | null>(null);
  const [preview, setPreview] = useState<PublishPreview | null>(null);
  const [previewedAt, setPreviewedAt] = useState<Date | null>(null);
  const [conflicts, setConflicts] = useState<{ items: MergeConflict[]; current: string | null } | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"changes" | "checks">("changes");
  const [filter, setFilter] = useState<Filter>("all");
  const [open, setOpen] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [showModel, setShowModel] = useState(false);
  // Only the newest request may land: a slow preview of an older revision
  // must never replace the preview of the current one.
  const sequence = useRef(0);
  const load = useCallback(async () => {
    const mine = ++sequence.current;
    setError("");
    setPreview(null);
    try {
      const value = await publishApi.preview(session);
      if (mine !== sequence.current) return;
      setPreview(value);
      setConflicts(null);
      setPreviewedAt(new Date());
      setFilter("all");
      // A long list starts collapsed, as a large pull request does.
      setOpen(value.changes.length <= COLLAPSE_AFTER ? value.changes.map((c) => c.element_id) : []);
    } catch (e) {
      if (mine !== sequence.current) return;
      if (e instanceof ApiError && e.code === "MERGE_CONFLICTS") {
        setConflicts({ items: e.conflicts, current: e.currentVersionId });
        setNotice(`当前发布版本已变化，自动合并后仍有 ${e.conflicts.length} 处需要你决定`);
      } else if (e instanceof ApiError && e.code === "SESSION_REVISION_CHANGED") {
        onStale();
      } else setError(e instanceof Error ? e.message : "预览失败");
    }
    // Revision and id identify the saved session state being previewed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id, session.revision]);
  useEffect(() => {
    void load();
  }, [load]);
  const publish = async () => {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const result = await publishApi.publish(session, preview, message);
      setMessage("");
      setNotice("");
      setConfirming(false);
      onPublished(result.version, result.session);
    } catch (e) {
      setConfirming(false);
      if (e instanceof ApiError && (e.code === "PREVIEW_OUTDATED" || e.code === "MERGE_CONFLICTS")) {
        // Never reuse a preview the server says is outdated.
        setPreview(null);
        setNotice("当前发布版本在你预览后已变化，已重新合并");
        onStale();
        void load();
      } else setError(e instanceof Error ? e.message : "发布失败");
    } finally {
      setBusy(false);
    }
  };
  const changes = preview ? sortChanges(preview.changes) : [];
  const count = (kind: ElementChange["change"]) => changes.filter((c) => c.change === kind).length;
  const total = changes.length;
  // Changed datasets whose source is not ready block publishing like validation errors.
  const sourceErrors = (preview?.dataset_checks ?? []).flatMap((c) =>
    c.diagnostics.map((d) => ({ message: `数据集 ${c.display_name || c.name}：${d.message}` })),
  );
  const errors = [...(preview?.validation.errors ?? []), ...sourceErrors];
  const publishable = !!preview?.validation.publishable && !sourceErrors.length;
  const warnings = preview?.validation.warnings ?? [];
  const current = preview ? versionLabel(preview.current_version_number) : "…";
  // The session is behind when versions were published after it started.
  const behind =
    preview?.current_version_number && preview.base_version_number !== preview.current_version_number
      ? preview.base_version_number
        ? preview.current_version_number - preview.base_version_number > 1
          ? `会话开始于 v${preview.base_version_number}，之后发布的 v${preview.base_version_number + 1}–v${preview.current_version_number} 已纳入合并`
          : `会话开始于 v${preview.base_version_number}，之后发布的 v${preview.current_version_number} 已纳入合并`
        : `会话从空白模型开始，已发布的 v1–v${preview.current_version_number} 已纳入合并`
      : "";
  // One reason, in the order a user would have to fix them.
  const blocker = conflicts
    ? `还有 ${conflicts.items.length} 处冲突需要处理`
    : !preview
      ? error
        ? "预览失败"
        : "正在计算合并结果…"
      : !publishable
        ? errors.length
          ? `校验未通过 · ${errors.length} 个错误`
          : "校验未通过"
        : !total
          ? "本会话不会改变当前发布版本"
          : "";
  const canPublish = !blocker && !disabled && !busy;
  const status: { state: StatusState; text: string } = conflicts
    ? { state: "partial", text: "有冲突" }
    : !preview
      ? { state: "unmapped", text: error ? "预览失败" : "计算中" }
      : !publishable
        ? { state: "error", text: "校验未通过" }
        : !total
          ? { state: "unmapped", text: "无变更" }
          : { state: "mapped", text: "可发布" };
  const shown = filter === "all" ? changes : changes.filter((c) => c.change === filter);
  const names = elementNames(preview, session.draft);
  return (
    <div className="flex flex-col gap-3">
      <section className="border-b border-rule pb-4">
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-3">
            {picker}
            <span className="inline-flex items-center gap-1 text-sm">
              <ArrowRight size={14} aria-hidden /> 当前发布版本 <b>{current}</b>
            </span>
            <Tooltip title={blocker || undefined}>
              <span className="ml-auto inline-flex">
                <Button type="primary" disabled={!canPublish} onClick={() => setConfirming(true)}>
                  {preview ? `发布 v${preview.next_version_number}` : "发布"}
                </Button>
              </span>
            </Tooltip>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <StatusMark state={status.state} label={status.text} />
            {preview && (
              <span className="inline-flex gap-2 font-mono" aria-label="变更计数">
                <b className="text-success">+{count("created")}</b>
                <b className="text-accent">~{count("updated")}</b>
                <b className="text-danger">−{count("deleted")}</b>
              </span>
            )}
            {behind && <Text type="secondary">{behind}</Text>}
            {blocker && preview !== null && <Text type="secondary">{blocker}</Text>}
          </div>
        </div>
      </section>
      {notice && <Alert type="info" showIcon message={notice} role="status" />}
      {error && (
        <Alert
          type="error"
          showIcon
          message={error}
          action={
            <Button size="small" onClick={() => void load()}>
              重试
            </Button>
          }
        />
      )}
      <Tabs
        renderTabBar={(props, DefaultTabBar) => <PanelToolbar className="px-0" tabBar={<DefaultTabBar {...props} />} />}
        activeKey={tab}
        onChange={(key) => setTab(key as typeof tab)}
        items={[
          {
            key: "changes",
            label: `变更 ${preview ? total : conflicts ? conflicts.items.length : ""}`,
            children: conflicts ? (
              <ConflictResolver
                conflicts={conflicts.items}
                currentVersionId={conflicts.current}
                session={session}
                onResolved={(next) => {
                  setConflicts(null);
                  setNotice("冲突处理已应用到会话，已重新预览");
                  onSession(next);
                }}
                onOutdated={() => {
                  // Same rule as an outdated publish: drop what was shown, re-merge.
                  setConflicts(null);
                  setNotice("当前发布版本在你预览后已变化，已重新合并");
                  onStale();
                  void load();
                }}
              />
            ) : !preview ? (
              !error && <Spin tip="正在计算合并结果…"><div className="p-6" /></Spin>
            ) : total ? (
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center gap-3">
                  <SectionTitle title="本次发布将改变的内容" />
                  <Segmented
                    size="small"
                    value={filter}
                    onChange={(v) => setFilter(v as Filter)}
                    options={(
                      [
                        ["all", "全部", total],
                        ["created", "新增", count("created")],
                        ["updated", "修改", count("updated")],
                        ["deleted", "删除", count("deleted")],
                      ] as [Filter, string, number][]
                    ).map(([value, label, n]) => ({ value, label: `${label} ${n}` }))}
                  />
                  <Button
                    size="small"
                    type="link"
                    onClick={() => setOpen(open.length ? [] : shown.map((c) => c.element_id))}
                  >
                    {open.length ? "全部收起" : "全部展开"}
                  </Button>
                </div>
                {shown.length ? (
                  <ChangeList
                    changes={shown}
                    names={names}
                    open={open}
                    onInspect={(c) =>
                      setInspected({
                        kind: c.element_kind,
                        id: c.element_id,
                        sessionId: session.id,
                        previewHash: preview.merged_snapshot_sha256,
                      })
                    }
                  />
                ) : (
                  <Text type="secondary">此筛选下没有变更。</Text>
                )}
                {(preview.auto_merged.length > 0 || preview.impacts.length > 0) && (
                  <Collapse
                    size="small"
                    ghost
                    items={[
                      ...(preview.auto_merged.length
                        ? [
                            {
                              key: "auto",
                              label: `会话开始后已发布的变化 ${preview.auto_merged.length} · 已在线，仅用于解释合并结果`,
                              children: <ChangeList changes={sortChanges(preview.auto_merged)} names={names} open={[]} />,
                            },
                          ]
                        : []),
                      ...(preview.impacts.length
                        ? [
                            {
                              key: "impacts",
                              label: `受影响但未修改的元素 ${preview.impacts.length}`,
                              children: (
                                <ul className="m-0 flex flex-col gap-1 pl-5 text-sm">
                                  {preview.impacts.map((i) => (
                                    <li key={i.element_id}>
                                      {KIND[i.element_kind].label} · {i.label}：{i.reason}
                                    </li>
                                  ))}
                                </ul>
                              ),
                            },
                          ]
                        : []),
                    ]}
                  />
                )}
              </div>
            ) : (
              <Empty description="本会话不会改变当前发布版本" />
            ),
          },
          {
            key: "checks",
            label: (
              <span className="inline-flex items-center gap-1">
                检查
                {preview ? (
                  <StatusMark
                    state={publishable ? "mapped" : "error"}
                    label={publishable ? "通过" : "未通过"}
                  />
                ) : conflicts ? <StatusMark state="partial" label="待处理" /> : null}
              </span>
            ),
            children: (
              <div className="flex flex-col gap-3">
                <List
                  size="small"
                  dataSource={[
                    {
                      key: "conflicts",
                      state: (conflicts ? "warn" : preview ? "pass" : "idle") as "pass" | "fail" | "warn" | "idle",
                      title: "合并冲突",
                      detail: conflicts ? `${conflicts.items.length} 处待处理` : preview ? "无冲突" : "等待预览",
                    },
                    {
                      key: "validation",
                      state: (!preview ? "idle" : publishable ? "pass" : "fail") as "pass" | "fail" | "warn" | "idle",
                      title: "本体校验",
                      detail: preview ? `${errors.length} 个错误 · ${warnings.length} 个警告` : "等待合并结果",
                      extra:
                        errors.length + warnings.length > 0 ? (
                          <List
                            size="small"
                            split={false}
                            className="pl-6"
                            dataSource={[
                              ...errors.map((issue, i) => ({ key: "e" + i, message: issue.message, kind: "error" as const })),
                              ...warnings.map((issue, i) => ({ key: "w" + i, message: issue.message, kind: "warning" as const })),
                            ]}
                            renderItem={(issue) => (
                              <List.Item
                                key={issue.key}
                                role={issue.kind === "error" ? "alert" : undefined}
                                className="py-1 text-sm"
                              >
                                <Text type={issue.kind === "error" ? "danger" : "secondary"}>{issue.message}</Text>
                              </List.Item>
                            )}
                          />
                        ) : undefined,
                    },
                    {
                      key: "base",
                      state: (preview ? "pass" : "idle") as "pass" | "fail" | "warn" | "idle",
                      title: "合并基准",
                      detail: preview
                        ? `会话开始于 ${versionLabel(preview.base_version_number)} · 合并到当前发布版本 ${current} · 预览于 ${previewedAt?.toLocaleTimeString("zh-CN", { hour12: false })}`
                        : "等待预览",
                      extra: (
                        <Button size="small" type="link" className="self-start p-0" onClick={() => void load()}>
                          重新预览
                        </Button>
                      ),
                    },
                  ]}
                  renderItem={(item) => (
                    <List.Item key={item.key} className="block">
                      <span className="flex flex-wrap items-center gap-2">
                        <StatusMark state={CHECK_STATE[item.state]} label={item.title} />
                        <Text type="secondary" className="text-xs">
                          {item.detail}
                        </Text>
                      </span>
                      {item.extra}
                    </List.Item>
                  )}
                />
                <Button className="self-start" disabled={!preview} onClick={() => setShowModel(true)}>
                  查看本次将发布的模型 JSON
                </Button>
              </div>
            ),
          },
        ]}
      />
      <Modal
        open={confirming && !!preview}
        title={preview ? `发布 v${preview.next_version_number}` : "发布"}
        onCancel={() => setConfirming(false)}
        okText="确认发布"
        cancelText="取消"
        okButtonProps={{ disabled: !canPublish, loading: busy }}
        onOk={() => void publish()}
      >
        {preview && (
          <div className="flex flex-col gap-3">
            <Text type="secondary">
              当前发布版本 {current} → 新版本 v{preview.next_version_number} · 新增 {count("created")} · 修改 {count("updated")} · 删除{" "}
              {count("deleted")}
            </Text>
            {warnings.length ? (
              <Alert
                type="warning"
                showIcon
                message={`校验通过，但有 ${warnings.length} 个警告`}
                description={
                  <ul className="m-0 pl-5">
                    {warnings.map((issue, i) => (
                      <li key={i}>{issue.message}</li>
                    ))}
                  </ul>
                }
              />
            ) : (
              <Alert type="success" showIcon message="校验通过 · 0 错误 0 警告" />
            )}
            <Form layout="vertical" component="div">
              <Form.Item label="版本说明" className="mb-0">
                <Input.TextArea
                  aria-label="版本说明"
                  rows={3}
                  maxLength={240}
                  showCount
                  placeholder="说明本次模型变化"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                />
              </Form.Item>
            </Form>
          </div>
        )}
      </Modal>
      <Drawer open={showModel} width="var(--review-dialog-width)" title="本次将发布的模型" onClose={() => setShowModel(false)} destroyOnHidden>
        <pre className="m-0 font-mono text-xs leading-base whitespace-pre-wrap">{JSON.stringify(preview?.merged_model, null, 2)}</pre>
      </Drawer>
      {inspected && <ElementModal request={inspected} onChange={setInspected} onClose={() => setInspected(null)} />}
    </div>
  );
}
