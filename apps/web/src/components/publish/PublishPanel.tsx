import { Check, ChevronDown, ChevronRight, CircleAlert, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
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

function Stepper({ step, conflicts }: { step: 1 | 2 | 3; conflicts: number }) {
  const items = [
    { n: 1, label: "合并预览", hint: "" },
    { n: 2, label: "解决冲突", hint: conflicts ? `${conflicts} 个冲突` : "无需处理" },
    { n: 3, label: "确认发布", hint: "" },
  ];
  return (
    <ol className="publish-stepper" aria-label="发布步骤">
      {items.map((item) => {
        const state = item.n < step || (item.n === 2 && !conflicts && step !== 2) ? "done" : item.n === step ? "current" : "todo";
        return (
          <li key={item.n} className={`step step--${state}`} aria-current={state === "current" ? "step" : undefined}>
            <span className="step-dot">{state === "done" ? <Check size={14} /> : item.n}</span>
            <span>
              {item.label}
              {item.hint && <small>{item.hint}</small>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

function ChangeGroups({ changes }: { changes: ElementChange[] }) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  return (
    <div className="change-groups">
      {KIND_ORDER.map((kind) => {
        const rows = changes.filter((c) => c.element_kind === kind);
        if (!rows.length) return null;
        const Icon = KIND[kind].icon;
        return (
          <section key={kind} className="change-group">
            <h3>
              <Icon size={15} aria-hidden /> {KIND[kind].label} <small>{rows.length}</small>
            </h3>
            {rows.map((c) => {
              const expandable = c.change === "updated" && c.field_changes.length > 0;
              return (
                <div key={c.element_id} className="change-row">
                  <button
                    type="button"
                    className="change-row-head"
                    aria-expanded={expandable ? !!open[c.element_id] : undefined}
                    onClick={() => expandable && setOpen((o) => ({ ...o, [c.element_id]: !o[c.element_id] }))}
                  >
                    <span>
                      {c.owner_label && kind === "property" ? `${c.owner_label}.` : ""}
                      {c.label}
                    </span>
                    {kind === "action" && <span className="tag">仅定义</span>}
                    <span className={`tag tag--change-${c.change}`}>{CHANGE_LABEL[c.change]}</span>
                    {expandable && (open[c.element_id] ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
                  </button>
                  {expandable && open[c.element_id] && (
                    <FieldDiff changes={c.field_changes} beforeLabel="当前版本" afterLabel="发布后" />
                  )}
                </div>
              );
            })}
          </section>
        );
      })}
    </div>
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

/**
 * Publish tab: always shows the server's B/L/D merge — the exact content that
 * will be published — and publishes only with the values it previewed.
 */
export function PublishPanel({
  session,
  onSession,
  onPublished,
  onStale,
  disabled = false,
}: {
  session: ModelingSession;
  onSession: (value: ModelingSession) => void;
  onPublished: (version: VersionSummary, session: ModelingSession) => void;
  onStale: () => void;
  disabled?: boolean;
}) {
  const [preview, setPreview] = useState<PublishPreview | null>(null);
  const [previewedAt, setPreviewedAt] = useState<Date | null>(null);
  const [conflicts, setConflicts] = useState<{ items: MergeConflict[]; current: string | null } | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [showOssie, setShowOssie] = useState(false);
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

  const publish = async () => {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const result = await publishApi.publish(session, preview, message);
      setMessage("");
      setNotice("");
      onPublished(result.version, result.session);
    } catch (e) {
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

  const step: 1 | 2 | 3 = conflicts ? 2 : preview ? 3 : 1;
  const counts = preview
    ? {
        created: preview.changes.filter((c) => c.change === "created").length,
        updated: preview.changes.filter((c) => c.change === "updated").length,
        deleted: preview.changes.filter((c) => c.change === "deleted").length,
      }
    : null;
  const errors = preview?.validation.errors ?? [];
  return (
    <div className="publish-panel">
      <Stepper step={step} conflicts={conflicts?.items.length ?? 0} />
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
        <div className="publish-columns">
          <section className="publish-summary">
            <header>
              <h2>变更摘要</h2>
              <p className="summary-counts">
                <span>
                  新增 <b className="count-created">{counts!.created}</b>
                </span>
                <span>
                  修改 <b className="count-updated">{counts!.updated}</b>
                </span>
                <span>
                  删除 <b className="count-deleted">{counts!.deleted}</b>
                </span>
                <span>
                  来自其他会话 <b>{preview.auto_merged.length}</b>
                </span>
              </p>
            </header>
            {preview.changes.length ? (
              <ChangeGroups changes={preview.changes} />
            ) : (
              <p className="muted">与当前最新版本相比没有变化。</p>
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
            {preview.auto_merged.length > 0 && (
              <details className="change-extra">
                <summary>自动合并了其他会话的 {preview.auto_merged.length} 项变更</summary>
                <ChangeGroups changes={preview.auto_merged} />
              </details>
            )}
          </section>
          <aside className="publish-confirm" aria-label="确认发布">
            <h2>确认发布</h2>
            <p className="next-version">
              将发布为 <b>v{preview.next_version_number}</b>
            </p>
            <small className="muted">
              当前最新 {preview.current_version_number ? `v${preview.current_version_number}` : "无（首次发布）"}
            </small>
            {errors.length ? (
              <div className="inline-error" role="alert">
                校验未通过 · {errors.length} 个错误
                {errors.map((issue, i) => (
                  <p key={i}>{(issue as { message: string }).message}</p>
                ))}
              </div>
            ) : (
              <p className="validation-pass">
                <Check size={14} /> 校验通过 · 0 错误 {preview.validation.warnings.length} 警告
              </p>
            )}
            <small className="muted">
              预览于 {previewedAt?.toLocaleTimeString("zh-CN", { hour12: false })} · 基于最新{" "}
              {preview.current_version_number ? `v${preview.current_version_number}` : "空白模型"}
            </small>
            <label className="section-field">
              <span>版本说明</span>
              <textarea
                rows={4}
                maxLength={240}
                placeholder="说明本次模型变化"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
              />
            </label>
            <button
              type="button"
              className="button button--primary publish-button"
              disabled={disabled || busy || errors.length > 0}
              onClick={() => void publish()}
            >
              {busy ? "发布中…" : `发布 v${preview.next_version_number}`}
            </button>
            <div className="row-actions">
              <button type="button" className="button button--text" disabled={!preview.ossie} onClick={() => setShowOssie(true)}>
                查看 Ossie JSON
              </button>
              <button type="button" className="button button--text" onClick={() => void load()}>
                重新预览
              </button>
            </div>
          </aside>
        </div>
      )}
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
