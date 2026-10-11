import { useState } from "react";
import { ApiError, publishApi } from "../../api/client";
import type { MergeConflict, ModelingSession, Resolution } from "../../api/types";
import { FIELD_LABELS, KIND } from "../proposals/elementMeta";

function show(value: unknown) {
  if (value === null || value === undefined) return "（无）";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

/**
 * One conflict at a time: session start, current published version and this
 * session's change side by side. Applying the choices saves them to the
 * session, which moves its revision, so the page previews again.
 */
export function ConflictResolver({
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
    latest: ["采用当前发布版本", "保留当前发布版本的内容，放弃本会话的修改"],
    draft: ["采用本会话修改", "用本会话的修改覆盖当前发布版本"],
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
              ["会话起点", conflict.base],
              ["当前发布版本", conflict.latest],
              ["本会话修改", conflict.draft],
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
          {busy ? "正在应用…" : "应用到会话并重新预览"}
        </button>
      </footer>
    </div>
  );
}
