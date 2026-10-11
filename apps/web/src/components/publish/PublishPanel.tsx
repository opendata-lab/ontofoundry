import { ArrowRight, Check, ChevronDown, ChevronRight, CircleAlert, ShieldCheck, X } from "lucide-react";
import {
  type KeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { ApiError, publishApi } from "../../api/client";
import type {
  ElementChange,
  MergeConflict,
  ModelingSession,
  PublishPreview,
  TargetKind,
  VersionSummary,
} from "../../api/types";
import { FieldDiff } from "../proposals/FieldDiff";
import { FIELD_LABELS, KIND } from "../proposals/elementMeta";
import { lineDiff } from "../../lib/lineDiff";
import { ConflictResolver } from "./ConflictResolver";
import { useElementInspector } from "../../hooks/useElementInspector";

const CHANGE_LABEL: Record<ElementChange["change"], string> = {
  created: "新增",
  updated: "修改",
  deleted: "删除",
};
const KIND_ORDER: TargetKind[] = [
  "object_type",
  "property",
  "link_type",
  "rule",
  "action",
  "material_object",
  "material_link",
  "mapping",
];
/** Past this many changes, cards start collapsed. */
const COLLAPSE_AFTER = 20;
/** Fields that point at another element; the object view shows its name. */
const REFERENCE_FIELDS = new Set(["owner_type_id", "source_type_id", "target_type_id", "owner_id", "type_id", "extends"]);

type ViewMode = "object" | "json";
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
  const side = (lines: string[], marks: boolean[], mark: "removed" | "added") => (
    <pre className="definition-preview json-lines">
      {lines.map((line, i) => (
        <span key={i} className={marks[i] ? `json-line--${mark}` : undefined}>
          {line}
        </span>
      ))}
    </pre>
  );
  return (
    <div className="json-split">
      <div>
        <small>当前发布版本</small>
        {side(left, removed, "removed")}
      </div>
      <div>
        <small>发布后</small>
        {side(right, added, "added")}
      </div>
    </div>
  );
}

/** The fields of a created or deleted element, minus identity and empty values. */
function FieldList({
  value,
  names,
  removed = false,
}: {
  value: Record<string, unknown>;
  names: Map<string, string>;
  removed?: boolean;
}) {
  const named = (key: string, v: unknown) =>
    !REFERENCE_FIELDS.has(key)
      ? v
      : Array.isArray(v)
        ? v.map((id) => names.get(String(id)) ?? id)
        : (names.get(String(v)) ?? v);
  const rows = Object.entries(value).filter(
    ([key, v]) =>
      key !== "id" && v !== null && v !== undefined && v !== "" && !(Array.isArray(v) && v.length === 0),
  );
  if (!rows.length) return <p className="muted">无字段内容</p>;
  return (
    <dl className={"field-list " + (removed ? "field-list--removed" : "field-list--added")}>
      {rows.map(([key, v]) => (
        <div key={key}>
          <dt>{FIELD_LABELS[key] ?? key}</dt>
          <dd>{readable(key, named(key, v))}</dd>
        </div>
      ))}
    </dl>
  );
}

/** Expand or collapse every card at once; `n` changes on each request. */
type ExpandSignal = { open: boolean; n: number };

/** The shared card frame: header with name and the object/JSON switch. */
function CardFrame({
  label,
  change,
  kind,
  icon: Icon,
  extra,
  expand,
  children,
}: {
  label: string;
  change: ElementChange["change"];
  kind: string;
  icon: typeof ShieldCheck;
  extra?: ReactNode;
  expand: ExpandSignal;
  children: (mode: ViewMode) => ReactNode;
}) {
  const [open, setOpen] = useState(expand.open);
  const [mode, setMode] = useState<ViewMode>("object");
  useEffect(() => setOpen(expand.open), [expand]);
  return (
    <article className="change-card" aria-label={`${kind} ${label}`}>
      <header>
        <button
          type="button"
          className="change-card-toggle"
          aria-expanded={open}
          aria-label={(open ? "收起 " : "展开 ") + label}
          onClick={() => setOpen(!open)}
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <span className={`tag tag--change-${change}`}>{CHANGE_LABEL[change]}</span>
        <span className="change-card-kind">
          <Icon size={14} aria-hidden /> {kind}
        </span>
        <strong>{label}</strong>
        {extra}
        <span className="view-switch" role="group" aria-label={`${label} 展示方式`}>
          {(["object", "json"] as const).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={mode === m}
              onClick={() => {
                setMode(m);
                setOpen(true);
              }}
            >
              {m === "object" ? "对象" : "JSON"}
            </button>
          ))}
        </span>
      </header>
      {open && children(mode)}
    </article>
  );
}

/** One changed element, like a file in a pull request. */
function ChangeCard({
  change,
  names,
  expand,
  onInspect,
}: {
  change: ElementChange;
  names: Map<string, string>;
  expand: ExpandSignal;
  onInspect?: () => void;
}) {
  const label =
    (change.owner_label && change.element_kind === "property" ? `${change.owner_label}.` : "") + change.label;
  return (
    <CardFrame
      label={label}
      change={change.change}
      kind={KIND[change.element_kind].label}
      icon={KIND[change.element_kind].icon}
      expand={expand}
      extra={
        <>
          {onInspect && <button type="button" className="button button--text" onClick={onInspect}>查看发布后的元素</button>}
          {change.element_kind === "action" && <span className="tag">仅定义</span>}
          {change.change === "updated" && change.field_changes.length > 0 && (
            <small className="muted">{change.field_changes.length} 个字段</small>
          )}
        </>
      }
    >
      {(mode) =>
        mode === "json" ? (
          change.change === "updated" ? (
            <JsonSplit before={change.before} after={change.after} />
          ) : (
            <pre className="definition-preview">
              {JSON.stringify(change.change === "created" ? change.after : change.before, null, 2)}
            </pre>
          )
        ) : change.change === "updated" ? (
          change.field_changes.length ? (
            <FieldDiff changes={change.field_changes} beforeLabel="当前发布版本" afterLabel="发布后" />
          ) : (
            <p className="muted">无字段级变化</p>
          )
        ) : (
          <FieldList
            value={(change.change === "created" ? change.after : change.before) ?? {}}
            names={names}
            removed={change.change === "deleted"}
          />
        )
      }
    </CardFrame>
  );
}

/** Workspace constraints as one more changed item, read-only here. */
function RequiresCard({
  change,
  expand,
}: {
  change: NonNullable<PublishPreview["requires_change"]>;
  expand: ExpandSignal;
}) {
  const kept = new Set(change.after);
  const before = new Set(change.before);
  return (
    <CardFrame label="工作空间约束" change="updated" kind="空间" icon={ShieldCheck} expand={expand}>
      {(mode) =>
        mode === "json" ? (
          <JsonSplit before={{ requires: change.before }} after={{ requires: change.after }} />
        ) : (
          <ul className="requires-diff">
            {change.before
              .filter((rule) => !kept.has(rule))
              .map((rule) => (
                <li key={"-" + rule} className="requires-diff--removed">
                  <del>{rule}</del>
                </li>
              ))}
            {change.after.map((rule) => (
              <li key={"+" + rule} className={before.has(rule) ? undefined : "requires-diff--added"}>
                {before.has(rule) ? rule : <ins>{rule}</ins>}
              </li>
            ))}
          </ul>
        )
      }
    </CardFrame>
  );
}

function sortChanges(changes: ElementChange[]) {
  return [...changes].sort(
    (a, b) => KIND_ORDER.indexOf(a.element_kind) - KIND_ORDER.indexOf(b.element_kind),
  );
}

/** Element names by id: the preview's labels first, the session's draft as fallback. */
function elementNames(preview: PublishPreview | null, draft: ModelingSession["draft"]): Map<string, string> {
  const names = new Map<string, string>();
  for (const key of ["object_types", "properties", "link_types", "rules", "actions"] as const)
    for (const item of (draft[key] ?? []) as { id: string; name?: string }[])
      if (item.name) names.set(item.id, item.name);
  for (const [id, label] of Object.entries(preview?.labels ?? {})) names.set(id, label);
  return names;
}

const versionLabel = (n: number | null | undefined) => (n ? `v${n}` : "尚未发布");

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
  const inspector = useElementInspector();
  const [preview, setPreview] = useState<PublishPreview | null>(null);
  const [previewedAt, setPreviewedAt] = useState<Date | null>(null);
  const [conflicts, setConflicts] = useState<{ items: MergeConflict[]; current: string | null } | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"changes" | "checks">("changes");
  const [filter, setFilter] = useState<Filter>("all");
  const [expand, setExpand] = useState<ExpandSignal>({ open: true, n: 0 });
  const [confirming, setConfirming] = useState(false);
  const [showOssie, setShowOssie] = useState(false);
  const confirmDialog = useRef<HTMLDialogElement>(null);
  const ossie = useRef<HTMLDialogElement>(null);
  const tabs = useRef<Record<"changes" | "checks", HTMLButtonElement | null>>({ changes: null, checks: null });
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
      setExpand((e) => ({ open: value.changes.length <= COLLAPSE_AFTER, n: e.n + 1 }));
    } catch (e) {
      if (mine !== sequence.current) return;
      if (e instanceof ApiError && e.code === "MERGE_CONFLICTS") {
        setConflicts({ items: e.conflicts as MergeConflict[], current: e.currentVersionId });
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
  useEffect(() => {
    const el = ossie.current;
    if (!el) return;
    if (showOssie && !el.open) el.showModal?.();
    if (!showOssie && el.open) el.close?.();
  }, [showOssie]);
  useEffect(() => {
    const el = confirmDialog.current;
    if (!el) return;
    if (confirming && !el.open) el.showModal?.();
    if (!confirming && el.open) el.close?.();
  }, [confirming]);

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
  const requires = preview?.requires_change ?? null;
  const count = (kind: ElementChange["change"]) =>
    changes.filter((c) => c.change === kind).length + (kind === "updated" && requires ? 1 : 0);
  const total = changes.length + (requires ? 1 : 0);
  const errors = preview?.validation.errors ?? [];
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
      : !preview.validation.publishable
        ? errors.length
          ? `校验未通过 · ${errors.length} 个错误`
          : "校验未通过"
        : !total
          ? "本会话不会改变当前发布版本"
          : "";
  const canPublish = !blocker && !disabled && !busy;
  const status = conflicts
    ? { cls: "warn", text: "有冲突" }
    : !preview
      ? { cls: "idle", text: error ? "预览失败" : "计算中" }
      : !preview.validation.publishable
        ? { cls: "error", text: "校验未通过" }
        : !total
          ? { cls: "idle", text: "无变更" }
          : { cls: "ok", text: "可发布" };
  const shown = filter === "all" ? changes : changes.filter((c) => c.change === filter);
  const showRequires = requires && (filter === "all" || filter === "updated");
  const names = elementNames(preview, session.draft);
  const switchTab = (next: "changes" | "checks") => {
    setTab(next);
    tabs.current[next]?.focus();
  };
  const onTabKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowLeft" || e.key === "ArrowRight" || e.key === "Home" || e.key === "End") {
      e.preventDefault();
      switchTab(tab === "changes" ? "checks" : "changes");
    }
  };

  return (
    <div className="publish-panel">
      <header className="pr-header">
        <div className="pr-title">
          {picker}
          <span className="pr-flow">
            <ArrowRight size={14} aria-hidden /> 当前发布版本 <b>{current}</b>
          </span>
        </div>
        <div className="pr-actions">
          <button
            type="button"
            className="button button--primary"
            disabled={!canPublish}
            title={blocker || undefined}
            onClick={() => setConfirming(true)}
          >
            {preview ? `发布 v${preview.next_version_number}` : "发布"}
          </button>
        </div>
        <p className="pr-meta">
          <span className={`pr-status pr-status--${status.cls}`}>{status.text}</span>
          {preview && (
            <span className="pr-counts" aria-label="变更计数">
              <b className="count-created">+{count("created")}</b>
              <b className="count-updated">~{count("updated")}</b>
              <b className="count-deleted">−{count("deleted")}</b>
            </span>
          )}
          {behind && <span>{behind}</span>}
          {blocker && preview !== null && <span className="muted">{blocker}</span>}
        </p>
      </header>
      {notice && (
        <p className="publish-notice" role="status">
          <CircleAlert size={15} aria-hidden /> {notice}
        </p>
      )}
      {error && (
        <p className="inline-error" role="alert">
          {error}{" "}
          <button type="button" className="button button--text" onClick={() => void load()}>
            重试
          </button>
        </p>
      )}
      <div className="ref-tabs pr-tabs" role="tablist" aria-label="发布内容" onKeyDown={onTabKey}>
        <button
          ref={(el) => {
            tabs.current.changes = el;
          }}
          id="pr-tab-changes"
          role="tab"
          aria-selected={tab === "changes"}
          aria-controls="pr-panel-changes"
          tabIndex={tab === "changes" ? 0 : -1}
          onClick={() => setTab("changes")}
        >
          变更 <small>{preview ? total : conflicts ? conflicts.items.length : ""}</small>
        </button>
        <button
          ref={(el) => {
            tabs.current.checks = el;
          }}
          id="pr-tab-checks"
          role="tab"
          aria-selected={tab === "checks"}
          aria-controls="pr-panel-checks"
          tabIndex={tab === "checks" ? 0 : -1}
          onClick={() => setTab("checks")}
        >
          检查{" "}
          {preview ? (
            preview.validation.publishable ? (
              <Check size={13} className="check-pass" aria-label="通过" />
            ) : (
              <X size={13} className="check-fail" aria-label="未通过" />
            )
          ) : conflicts ? (
            <CircleAlert size={13} className="check-warn" aria-label="待处理" />
          ) : null}
        </button>
      </div>
      <section
        id="pr-panel-changes"
        role="tabpanel"
        aria-labelledby="pr-tab-changes"
        className="pr-changes"
        hidden={tab !== "changes"}
      >
        {conflicts ? (
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
          !error && <p className="muted">正在计算合并结果…</p>
        ) : total ? (
          <>
            <div className="pr-toolbar">
              <h2>本次发布将改变的内容</h2>
              <div className="pr-filter" role="group" aria-label="筛选变更">
                {(
                  [
                    ["all", "全部", total],
                    ["created", "新增", count("created")],
                    ["updated", "修改", count("updated")],
                    ["deleted", "删除", count("deleted")],
                  ] as [Filter, string, number][]
                ).map(([key, label, n]) => (
                  <button key={key} type="button" aria-pressed={filter === key} onClick={() => setFilter(key)}>
                    {label} {n}
                  </button>
                ))}
              </div>
              <button
                type="button"
                className="button button--text"
                onClick={() => setExpand((e) => ({ open: !e.open, n: e.n + 1 }))}
              >
                {expand.open ? "全部收起" : "全部展开"}
              </button>
            </div>
            {shown.map((c) => (
              <ChangeCard key={c.element_id} change={c} names={names} expand={expand} onInspect={c.change !== "deleted" ? () => inspector.open({ kind: c.element_kind, id: c.element_id, sessionId: session.id, previewHash: preview.merged_snapshot_sha256 }) : undefined} />
            ))}
            {showRequires && <RequiresCard change={requires} expand={expand} />}
            {!shown.length && !showRequires && <p className="muted pr-empty">此筛选下没有变更。</p>}
            {preview.auto_merged.length > 0 && (
              <details className="change-extra">
                <summary>
                  会话开始后已发布的变化 {preview.auto_merged.length}
                  <small className="muted"> · 已在线，仅用于解释合并结果</small>
                </summary>
                {sortChanges(preview.auto_merged).map((c) => (
                  <ChangeCard key={c.element_id} change={c} names={names} expand={COLLAPSED} />
                ))}
              </details>
            )}
            {preview.impacts.length > 0 && (
              <details className="change-extra">
                <summary>受影响但未修改的元素 {preview.impacts.length}</summary>
                <ul>
                  {preview.impacts.map((i) => (
                    <li key={i.element_id}>
                      {KIND[i.element_kind].label} · {i.label}：{i.reason}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        ) : (
          <p className="muted pr-empty">本会话不会改变当前发布版本。</p>
        )}
      </section>
      <section
        id="pr-panel-checks"
        role="tabpanel"
        aria-labelledby="pr-tab-checks"
        className="pr-checks"
        hidden={tab !== "checks"}
      >
        <ul className="check-list">
          <li>
            {conflicts ? (
              <CircleAlert size={15} className="check-warn" />
            ) : preview ? (
              <Check size={15} className="check-pass" />
            ) : (
              <CircleAlert size={15} className="check-idle" />
            )}
            <span>合并冲突</span>
            <small>{conflicts ? `${conflicts.items.length} 处待处理` : preview ? "无冲突" : "等待预览"}</small>
          </li>
          <li>
            {!preview ? (
              <CircleAlert size={15} className="check-idle" />
            ) : preview.validation.publishable ? (
              <Check size={15} className="check-pass" />
            ) : (
              <X size={15} className="check-fail" />
            )}
            <span>本体校验</span>
            <small>{preview ? `${errors.length} 个错误 · ${warnings.length} 个警告` : "等待合并结果"}</small>
            {errors.length + warnings.length > 0 && (
              <ul className="check-issues">
                {errors.map((issue, i) => (
                  <li key={"e" + i} className="inline-error" role="alert">
                    {(issue as { message: string }).message}
                  </li>
                ))}
                {warnings.map((issue, i) => (
                  <li key={"w" + i} className="muted">
                    {(issue as { message: string }).message}
                  </li>
                ))}
              </ul>
            )}
          </li>
          <li>
            {preview ? <Check size={15} className="check-pass" /> : <CircleAlert size={15} className="check-idle" />}
            <span>合并基准</span>
            <small>
              {preview
                ? `会话开始于 ${versionLabel(preview.base_version_number)} · 合并到当前发布版本 ${current} · 预览于 ${previewedAt?.toLocaleTimeString("zh-CN", { hour12: false })}`
                : "等待预览"}
            </small>
            <button type="button" className="button button--text" onClick={() => void load()}>
              重新预览
            </button>
          </li>
        </ul>
        <button
          type="button"
          className="button button--text"
          disabled={!preview?.ossie}
          onClick={() => setShowOssie(true)}
        >
          查看本次将发布的 Ossie JSON
        </button>
      </section>
      <dialog
        ref={confirmDialog}
        className="ref-dialog publish-confirm-dialog"
        aria-labelledby="publish-confirm-title"
        onClose={() => setConfirming(false)}
      >
        {preview && (
          <>
            <header>
              <h2 id="publish-confirm-title">发布 v{preview.next_version_number}</h2>
              <p className="muted">
                当前发布版本 {current} → 新版本 v{preview.next_version_number} · 新增 {count("created")} · 修改{" "}
                {count("updated")} · 删除 {count("deleted")}
              </p>
            </header>
            {warnings.length ? (
              <div className="confirm-warnings">
                <p>
                  <CircleAlert size={14} className="check-warn" /> 校验通过，但有 {warnings.length} 个警告：
                </p>
                <ul>
                  {warnings.map((issue, i) => (
                    <li key={i}>{(issue as { message: string }).message}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="validation-pass">
                <Check size={14} /> 校验通过 · 0 错误 0 警告
              </p>
            )}
            <label className="section-field">
              <span>版本说明</span>
              <textarea
                rows={3}
                maxLength={240}
                placeholder="说明本次模型变化"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </label>
            <footer className="row-actions">
              <button type="button" className="button button--secondary" onClick={() => setConfirming(false)}>
                取消
              </button>
              <button
                type="button"
                className="button button--primary"
                disabled={!canPublish}
                onClick={() => void publish()}
              >
                {busy ? "发布中…" : "确认发布"}
              </button>
            </footer>
          </>
        )}
      </dialog>
      <dialog ref={ossie} className="proposal-drawer" aria-label="Ossie JSON" onClose={() => setShowOssie(false)}>
        <header>
          <div>
            <h2>Ossie JSON</h2>
            <small>本次将发布的标准定义</small>
          </div>
          <button type="button" className="icon-button" aria-label="关闭" onClick={() => setShowOssie(false)}>
            <X size={16} />
          </button>
        </header>
        <div className="proposal-drawer-body">
          <pre className="definition-preview">{JSON.stringify(preview?.ossie, null, 2)}</pre>
        </div>
      </dialog>
    </div>
  );
}

/** Already-live changes stay folded; a stable value keeps them from re-opening. */
const COLLAPSED: ExpandSignal = { open: false, n: 0 };
