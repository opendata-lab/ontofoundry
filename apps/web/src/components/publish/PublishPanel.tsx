import { ArrowRight, Check, ChevronDown, ChevronRight, CircleAlert, X } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, publishApi } from "../../api/client";
import type {
  ElementChange,
  MergeConflict,
  ModelingSession,
  PublishPreview,
  Resolution,
  TargetKind,
  VersionSummary,
} from "../../api/types";
import { FieldDiff } from "../proposals/FieldDiff";
import { FIELD_LABELS, KIND } from "../proposals/elementMeta";

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

function show(value: unknown) {
  if (value === null || value === undefined) return "（无）";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

type ViewMode = "object" | "json";
/** Fields that point at another element; the object view shows its name. */
const REFERENCE_FIELDS = new Set(["owner_type_id", "source_type_id", "target_type_id", "owner_id", "type_id", "extends"]);

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

/** Element names by id, from the draft, so references read as names. */
function elementNames(draft: ModelingSession["draft"]): Map<string, string> {
  const names = new Map<string, string>();
  for (const key of ["object_types", "properties", "link_types", "rules", "actions"] as const)
    for (const item of (draft[key] ?? []) as { id: string; name?: string }[])
      if (item.name) names.set(item.id, item.name);
  return names;
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
    <dl className={"field-list" + (removed ? " field-list--removed" : "")}>
      {rows.map(([key, v]) => (
        <div key={key}>
          <dt>{FIELD_LABELS[key] ?? key}</dt>
          <dd>{readable(key, named(key, v))}</dd>
        </div>
      ))}
    </dl>
  );
}

function JsonView({ change }: { change: ElementChange }) {
  const json = (value: unknown) => JSON.stringify(value, null, 2);
  if (change.change === "updated")
    return (
      <div className="json-split">
        <div>
          <small>当前最新</small>
          <pre className="definition-preview">{json(change.before)}</pre>
        </div>
        <div>
          <small>发布后</small>
          <pre className="definition-preview">{json(change.after)}</pre>
        </div>
      </div>
    );
  return (
    <pre className="definition-preview">{json(change.change === "created" ? change.after : change.before)}</pre>
  );
}

/** One changed element, like a file in a pull request: object or JSON view. */
function ChangeCard({ change, names }: { change: ElementChange; names: Map<string, string> }) {
  const [open, setOpen] = useState(true);
  const [mode, setMode] = useState<ViewMode>("object");
  const Icon = KIND[change.element_kind].icon;
  const name =
    (change.owner_label && change.element_kind === "property" ? `${change.owner_label}.` : "") + change.label;
  return (
    <article className="change-card" aria-label={`${KIND[change.element_kind].label} ${name}`}>
      <header>
        <button
          type="button"
          className="change-card-toggle"
          aria-expanded={open}
          aria-label={(open ? "收起 " : "展开 ") + name}
          onClick={() => setOpen(!open)}
        >
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        <span className={`tag tag--change-${change.change}`}>{CHANGE_LABEL[change.change]}</span>
        <span className="change-card-kind">
          <Icon size={14} aria-hidden /> {KIND[change.element_kind].label}
        </span>
        <strong>{name}</strong>
        {change.element_kind === "action" && <span className="tag">仅定义</span>}
        {change.change === "updated" && change.field_changes.length > 0 && (
          <small className="muted">{change.field_changes.length} 个字段</small>
        )}
        <span className="view-switch" role="group" aria-label={`${name} 展示方式`}>
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
      {open &&
        (mode === "json" ? (
          <JsonView change={change} />
        ) : change.change === "updated" ? (
          change.field_changes.length ? (
            <FieldDiff changes={change.field_changes} beforeLabel="当前最新" afterLabel="发布后" />
          ) : (
            <p className="muted">无字段级变化</p>
          )
        ) : (
          <FieldList
            value={(change.change === "created" ? change.after : change.before) ?? {}}
            names={names}
            removed={change.change === "deleted"}
          />
        ))}
    </article>
  );
}

function sortChanges(changes: ElementChange[]) {
  return [...changes].sort(
    (a, b) => KIND_ORDER.indexOf(a.element_kind) - KIND_ORDER.indexOf(b.element_kind),
  );
}

function ConflictResolver({
  conflicts,
  currentVersionId,
  session,
  onResolved,
  onOutdated,
}: {
  conflicts: MergeConflict[];
  currentVersionId: string | null;
  session: ModelingSession;
  onResolved: (session: ModelingSession) => void;
  /** The version moved again: these conflicts are no longer the right ones. */
  onOutdated: () => void;
}) {
  const [index, setIndex] = useState(0);
  const [choices, setChoices] = useState<Record<string, Resolution>>({});
  const [customText, setCustomText] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const conflict = conflicts[Math.min(index, conflicts.length - 1)];
  const resolved = conflicts.filter((c) => choices[c.key]).length;
  const choose = (choice: Resolution["choice"]) => {
    setChoices((all) => ({ ...all, [conflict.key]: { choice } }));
    if (choice === "custom" && customText[conflict.key] === undefined)
      setCustomText((t) => ({ ...t, [conflict.key]: show(conflict.draft) }));
  };
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      const resolutions: Record<string, Resolution> = {};
      for (const c of conflicts) {
        const r = choices[c.key];
        if (r.choice !== "custom") {
          resolutions[c.key] = r;
          continue;
        }
        const text = customText[c.key] ?? "";
        let value: unknown = text;
        if (typeof c.draft !== "string" && typeof c.latest !== "string") {
          try {
            value = JSON.parse(text);
          } catch {
            throw new Error(`「${c.element_label} / ${c.path}」的自定义值不是有效 JSON`);
          }
        }
        resolutions[c.key] = { choice: "custom", value };
      }
      onResolved(await publishApi.resolve(session, currentVersionId, resolutions));
    } catch (e) {
      if (
        e instanceof ApiError &&
        (e.code === "PREVIEW_OUTDATED" || e.code === "CONFLICTS_UNRESOLVED")
      ) {
        onOutdated();
        return;
      }
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };
  const labels: Record<Resolution["choice"], [string, string]> = {
    latest: ["采用最新版本", "使用最新版本的内容，放弃我的修改"],
    draft: ["采用我的草稿", "使用我的草稿内容，覆盖最新版本的修改"],
    custom: ["自定义", "手动编辑合并后的内容"],
    both: ["都保留", "保留两边新增的所有值"],
  };
  return (
    <div className="conflict-resolver">
      <aside className="conflict-list" aria-label="冲突列表">
        <h3>冲突</h3>
        {conflicts.map((c, i) => (
          <button
            key={c.key}
            type="button"
            className="conflict-item"
            aria-current={i === index ? "true" : undefined}
            onClick={() => setIndex(i)}
          >
            <span className="dot" aria-hidden />
            {c.element_kind ? `${KIND[c.element_kind].label} · ` : ""}
            {c.element_label} / {c.kind === "delete_modify" ? "删除与修改" : (FIELD_LABELS[c.path] ?? c.path)}
            <span className={`tag ${choices[c.key] ? "tag--accepted" : "tag--stale"}`}>
              {choices[c.key] ? "已选择" : "待处理"}
            </span>
          </button>
        ))}
      </aside>
      <section className="conflict-detail" aria-label="解决冲突">
        <h3>
          {conflict.element_kind ? `${KIND[conflict.element_kind].label} · ` : ""}
          {conflict.element_label} /{" "}
          {conflict.kind === "delete_modify" ? "删除与修改" : (FIELD_LABELS[conflict.path] ?? conflict.path)}
        </h3>
        <div className="three-way">
          {(
            [
              ["基线", conflict.base],
              ["最新版本", conflict.latest],
              ["我的草稿", conflict.draft],
            ] as [string, unknown][]
          ).map(([label, value]) => (
            <div key={label}>
              <small>{label}</small>
              <pre>{show(value)}</pre>
            </div>
          ))}
        </div>
        <div className="choice-cards" role="radiogroup" aria-label="处理方式">
          {conflict.allowed.map((choice) => (
            <button
              key={choice}
              type="button"
              role="radio"
              aria-checked={choices[conflict.key]?.choice === choice}
              className="choice-card"
              onClick={() => choose(choice)}
            >
              <strong>{labels[choice][0]}</strong>
              <small>{labels[choice][1]}</small>
            </button>
          ))}
        </div>
        {choices[conflict.key]?.choice === "custom" && (
          <label className="section-field">
            <span>合并后的内容</span>
            <textarea
              rows={4}
              value={customText[conflict.key] ?? ""}
              onChange={(e) => setCustomText((t) => ({ ...t, [conflict.key]: e.target.value }))}
            />
          </label>
        )}
        <div className="row-actions">
          <button type="button" className="button button--secondary" disabled={index === 0} onClick={() => setIndex(index - 1)}>
            上一个
          </button>
          <button
            type="button"
            className="button button--secondary"
            disabled={index >= conflicts.length - 1}
            onClick={() => setIndex(index + 1)}
          >
            下一个
          </button>
        </div>
      </section>
      <footer className="conflict-bar">
        <span>
          已解决 {resolved} / {conflicts.length}
        </span>
        <progress value={resolved} max={conflicts.length} />
        {error && (
          <span className="inline-error" role="alert">
            {error}
          </span>
        )}
        <button
          type="button"
          className="button button--primary"
          disabled={busy || resolved < conflicts.length}
          onClick={() => void submit()}
        >
          {busy ? "正在保存…" : "保存并重新预览"}
        </button>
      </footer>
    </div>
  );
}

type Filter = "all" | ElementChange["change"];

/**
 * Publish tab, laid out like a pull request: what merges into what and the
 * publish button on top, then the changes and the checks as two tabs. It
 * always shows the server's B/L/D merge — the exact content that will be
 * published — and publishes only with the values it previewed.
 */
export function PublishPanel({
  session,
  onSession,
  onPublished,
  onStale,
  disabled = false,
  blockedReason = "",
  picker,
  baseLabel,
  constraints,
}: {
  session: ModelingSession;
  onSession: (value: ModelingSession) => void;
  onPublished: (version: VersionSummary, session: ModelingSession) => void;
  onStale: () => void;
  disabled?: boolean;
  /** Why the page cannot publish right now, e.g. unsaved workspace constraints. */
  blockedReason?: string;
  /** The draft selector, shown where a pull request names its branch. */
  picker?: ReactNode;
  /** The version the draft was built on, e.g. "v3" or "空白模型". */
  baseLabel?: string;
  /** Workspace constraints, shown in their own box below the changes. */
  constraints?: ReactNode;
}) {
  const [preview, setPreview] = useState<PublishPreview | null>(null);
  const [previewedAt, setPreviewedAt] = useState<Date | null>(null);
  const [conflicts, setConflicts] = useState<{ items: MergeConflict[]; current: string | null } | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"changes" | "checks">("changes");
  const [filter, setFilter] = useState<Filter>("all");
  const [confirming, setConfirming] = useState(false);
  const [showOssie, setShowOssie] = useState(false);
  const confirmDialog = useRef<HTMLDialogElement>(null);
  const ossie = useRef<HTMLDialogElement>(null);
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
    } catch (e) {
      if (mine !== sequence.current) return;
      if (e instanceof ApiError && e.code === "MERGE_CONFLICTS") {
        setConflicts({ items: e.conflicts as MergeConflict[], current: e.currentVersionId });
        setNotice(`最新版本已变化，自动合并后仍有 ${e.conflicts.length} 处需要你决定`);
      } else if (e instanceof ApiError && e.code === "SESSION_REVISION_CHANGED") {
        onStale();
      } else setError(e instanceof Error ? e.message : "预览失败");
    }
    // Revision and id identify the saved draft being previewed.
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
        setNotice("当前最新版本在你预览后已变化，已重新合并");
        onStale();
        void load();
      } else setError(e instanceof Error ? e.message : "发布失败");
    } finally {
      setBusy(false);
    }
  };

  const changes = preview ? sortChanges(preview.changes) : [];
  const count = (kind: ElementChange["change"]) => changes.filter((c) => c.change === kind).length;
  const errors = preview?.validation.errors ?? [];
  const warnings = preview?.validation.warnings ?? [];
  const currentLabel = preview
    ? preview.current_version_number
      ? `v${preview.current_version_number}`
      : "空白模型"
    : "最新版本";
  // One reason, in the order a user would have to fix them.
  const blocker = conflicts
    ? `还有 ${conflicts.items.length} 处冲突需要处理`
    : !preview
      ? error
        ? "预览失败"
        : "正在计算合并结果…"
      : errors.length
        ? `校验未通过 · ${errors.length} 个错误`
        : !changes.length
          ? "与最新版本一致，没有可发布的变更"
          : blockedReason;
  const canPublish = !blocker && !disabled && !busy;
  const status = conflicts
    ? { cls: "warn", text: "有冲突" }
    : !preview
      ? { cls: "idle", text: error ? "预览失败" : "计算中" }
      : errors.length
        ? { cls: "error", text: "校验未通过" }
        : !changes.length
          ? { cls: "idle", text: "无变更" }
          : { cls: "ok", text: "可发布" };
  const shown = filter === "all" ? changes : changes.filter((c) => c.change === filter);
  const names = elementNames(session.draft);

  return (
    <div className="publish-panel">
      <header className="pr-header">
        <div className="pr-title">
          {picker}
          <span className="pr-flow">
            草稿 r{session.revision} <ArrowRight size={14} aria-hidden /> 合并到 <b>最新 {currentLabel}</b>
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
            {preview ? `发布为 v${preview.next_version_number}` : "发布"}
          </button>
        </div>
        <p className="pr-meta">
          <span className={`pr-status pr-status--${status.cls}`}>{status.text}</span>
          {baseLabel && <span>基于 {baseLabel}</span>}
          {preview && (
            <span className="pr-counts" aria-label="变更计数">
              <b className="count-created">+{count("created")}</b>
              <b className="count-updated">~{count("updated")}</b>
              <b className="count-deleted">−{count("deleted")}</b>
            </span>
          )}
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
      <div className="ref-tabs pr-tabs" role="tablist" aria-label="发布内容">
        <button role="tab" aria-selected={tab === "changes"} onClick={() => setTab("changes")}>
          变更 <small>{preview ? changes.length : conflicts ? conflicts.items.length : ""}</small>
        </button>
        <button role="tab" aria-selected={tab === "checks"} onClick={() => setTab("checks")}>
          检查{" "}
          {preview &&
            (errors.length ? (
              <X size={13} className="check-fail" aria-label="未通过" />
            ) : (
              <Check size={13} className="check-pass" aria-label="通过" />
            ))}
        </button>
      </div>
      {tab === "changes" ? (
        <section className="pr-changes" aria-label="变更">
          {conflicts ? (
            <ConflictResolver
              conflicts={conflicts.items}
              currentVersionId={conflicts.current}
              session={session}
              onResolved={(next) => {
                setConflicts(null);
                setNotice("冲突已保存，已重新预览");
                onSession(next);
              }}
              onOutdated={() => {
                // Same rule as an outdated publish: drop what was shown, re-merge.
                setConflicts(null);
                setNotice("当前最新版本在你预览后已变化，已重新合并");
                onStale();
                void load();
              }}
            />
          ) : !preview ? (
            !error && <p className="muted">正在计算合并结果…</p>
          ) : (
            <>
              {changes.length > 0 ? (
                <>
                  <div className="pr-filter" role="group" aria-label="筛选变更">
                    {(
                      [
                        ["all", "全部", changes.length],
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
                  {shown.map((c) => (
                    <ChangeCard key={c.element_id} change={c} names={names} />
                  ))}
                </>
              ) : (
                <p className="muted pr-empty">草稿与最新版本一致，没有可发布的变更。</p>
              )}
              {preview.auto_merged.length > 0 && (
                <details className="change-extra">
                  <summary>来自其他会话的变更 {preview.auto_merged.length}（已自动合并）</summary>
                  {sortChanges(preview.auto_merged).map((c) => (
                    <ChangeCard key={c.element_id} change={c} names={names} />
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
          )}
        </section>
      ) : (
        <section className="pr-checks" aria-label="检查">
          <ul className="check-list">
            <li>
              {conflicts ? <CircleAlert size={15} className="check-warn" /> : <Check size={15} className="check-pass" />}
              <span>合并冲突</span>
              <small>{conflicts ? `${conflicts.items.length} 处待处理` : preview ? "无冲突" : "—"}</small>
            </li>
            <li>
              {!preview ? (
                <CircleAlert size={15} className="check-idle" />
              ) : errors.length ? (
                <X size={15} className="check-fail" />
              ) : (
                <Check size={15} className="check-pass" />
              )}
              <span>本体校验</span>
              <small>
                {preview ? `${errors.length} 个错误 · ${warnings.length} 个警告` : "等待合并结果"}
              </small>
              {[...errors, ...warnings].length > 0 && (
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
              {blockedReason ? <CircleAlert size={15} className="check-warn" /> : <Check size={15} className="check-pass" />}
              <span>工作空间约束</span>
              <small>{blockedReason || "已保存"}</small>
            </li>
            <li>
              <Check size={15} className={preview ? "check-pass" : "check-idle"} />
              <span>合并基准</span>
              <small>
                {preview
                  ? `基于最新 ${currentLabel} · 预览于 ${previewedAt?.toLocaleTimeString("zh-CN", { hour12: false })}`
                  : "—"}
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
      )}
      {/* Kept mounted across tabs: unsaved constraint edits must survive a look at the checks. */}
      <div className="pr-constraints" hidden={tab !== "changes"}>
        {constraints}
      </div>
      <dialog
        ref={confirmDialog}
        className="ref-dialog publish-confirm-dialog"
        aria-labelledby="publish-confirm-title"
        onClose={() => setConfirming(false)}
      >
        {preview && (
          <>
            <header>
              <h2 id="publish-confirm-title">发布为 v{preview.next_version_number}</h2>
              <p className="muted">
                草稿 r{session.revision} 合并到最新 {currentLabel}：新增 {count("created")} · 修改 {count("updated")} · 删除{" "}
                {count("deleted")}
              </p>
            </header>
            <p className="validation-pass">
              <Check size={14} /> 校验通过 · 0 错误 {warnings.length} 警告
            </p>
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
