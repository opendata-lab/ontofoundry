import { useEffect, useState } from "react";
import { workspaceRequest } from "../api/client";
import type { ModelingSession, VersionSummary } from "../api/types";
import { ExpressionsEditor } from "./ExpressionsEditor";
import { modelingApi } from "../api/client";
import "../styles/ontology-reading.css";

type Comparison = {
  changes: { path: string; kind: string; before: unknown; after: unknown }[];
  impacts: { id: string; kind: string; label: string }[];
};
type Preview = Comparison & {
  revision: number;
  ossie: unknown;
  validation: VersionSummary["validation"];
};

function Changes({ value }: { value: Comparison }) {
  return (
    <>
      <p className="muted">
        {value.changes.length} 项变化 · {value.impacts.length} 个模型内依赖
      </p>
      {value.impacts.length > 0 && (
        <p>影响：{value.impacts.map((i) => i.label).join("、")}</p>
      )}
      <div className="change-list">
        {value.changes.map((change) => (
          <article key={change.path}>
            <code>{change.path}</code>
            <span className="reading-badge">
              {" "}
              ·{" "}
              {{ added: "新增", removed: "删除", changed: "修改" }[change.kind]}
            </span>
            <div className="change-values">
              <div>
                <small>修改前</small>
                <pre>{JSON.stringify(change.before, null, 2) ?? "—"}</pre>
              </div>
              <div>
                <small>修改后</small>
                <pre>{JSON.stringify(change.after, null, 2) ?? "—"}</pre>
              </div>
            </div>
          </article>
        ))}
      </div>
      {!value.changes.length && <p className="muted">两个版本没有模型变化。</p>}
    </>
  );
}

export function ReleaseReview({
  session,
  onSaved,
  disabled = false,
  onDirtyChange,
  onBusyChange,
}: {
  session: ModelingSession;
  onSaved: (value: ModelingSession) => void;
  disabled?: boolean;
  onDirtyChange?: (dirty: boolean) => void;
  onBusyChange?: (busy: boolean) => void;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [rules, setRules] = useState(session.draft.requires ?? []);
  const [saving, setSaving] = useState(false);
  const dirty =
    JSON.stringify(rules) !== JSON.stringify(session.draft.requires ?? []);
  useEffect(() => {
    onDirtyChange?.(dirty);
    return () => onDirtyChange?.(false);
  }, [dirty, onDirtyChange]);
  useEffect(() => {
    onBusyChange?.(saving);
    return () => onBusyChange?.(false);
  }, [saving, onBusyChange]);
  useEffect(() => {
    setRules(session.draft.requires ?? []);
  }, [session.id, session.revision, session.draft.requires]);
  useEffect(() => {
    let active = true;
    setPreview(null);
    setError("");
    workspaceRequest<Preview>(
      session.workspace_id,
      `/sessions/${session.id}/preview`,
      { revision: session.revision },
    )
      .then((r) => {
        if (active) setPreview(r);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [session.workspace_id, session.id, session.revision, attempt]);
  return (
    <div className="release-review">
      <details className="expression-editor">
        <summary>发布预览与变化</summary>
        {error ? (
          <p className="inline-error" role="alert">
            {error}
            <button onClick={() => setAttempt(attempt + 1)}>重试</button>
          </p>
        ) : !preview ? (
          <p>正在编译草稿…</p>
        ) : (
          <>
            <p className="muted">
              草稿修订 {preview.revision} · 相对当前已发布版本
            </p>
            <Changes value={preview} />
            {preview.validation.errors.map((issue, i) => (
              <p className="inline-error" key={i}>
                {(issue as { path?: string }).path}{" "}
                {(issue as { message: string }).message}
              </p>
            ))}
            {preview.ossie ? (
              <details>
                <summary>Ossie JSON</summary>
                <pre className="definition-preview">
                  {JSON.stringify(preview.ossie, null, 2)}
                </pre>
              </details>
            ) : (
              <p className="muted">修正校验错误后可查看本次标准定义。</p>
            )}
          </>
        )}
      </details>
      <ExpressionsEditor
        disabled={disabled || saving}
        label="工作空间约束"
        value={{ requires: rules }}
        onChange={(next) => {
          if (next.requires) setRules(next.requires);
        }}
        onlyConstraints
      />
      {dirty && (
        <p className="muted" role="status">
          空间约束尚未保存。预览对应已保存的修订，请保存后再发布。
        </p>
      )}
      {dirty && (
        <button
          disabled={disabled || saving}
          className="button button--secondary"
          onClick={async () => {
            setSaving(true);
            setError("");
            try {
              onSaved(
                await modelingApi.save(session, {
                  ...session.draft,
                  requires: rules.map((r) => r.trim()).filter(Boolean),
                }),
              );
            } catch (e) {
              setError(e instanceof Error ? e.message : "保存失败");
            } finally {
              setSaving(false);
            }
          }}
        >
          {saving ? "正在保存…" : "保存空间约束"}
        </button>
      )}
    </div>
  );
}

export function HistoryComparison({
  workspaceId,
  versions,
}: {
  workspaceId: string;
  versions: VersionSummary[];
}) {
  const [left, setLeft] = useState("");
  const [chosen, setChosen] = useState("");
  const right = chosen || versions[0]?.version_id || "";
  const [value, setValue] = useState<Comparison | null>(null);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  useEffect(() => {
    let active = true;
    setValue(null);
    setError("");
    if (open && right && left !== right)
      workspaceRequest<Comparison>(
        workspaceId,
        `/version-comparison?${new URLSearchParams({ right_id: right, ...(left ? { left_id: left } : {}) })}`,
      )
        .then((r) => {
          if (active) setValue(r);
        })
        .catch((e: Error) => {
          if (active) setError(e.message);
        });
    return () => {
      active = false;
    };
  }, [workspaceId, left, right, open]);
  return (
    <details
      className="expression-editor"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>比较历史版本</summary>
      <div className="row-actions">
        <label>
          基线{" "}
          <select
            aria-label="比较基线"
            value={left}
            onChange={(e) => setLeft(e.target.value)}
          >
            <option value="">空基线</option>
            {versions.map((v) => (
              <option key={v.version_id} value={v.version_id}>
                v{v.version}
              </option>
            ))}
          </select>
        </label>
        <label>
          目标{" "}
          <select
            aria-label="比较目标"
            value={right}
            onChange={(e) => setChosen(e.target.value)}
          >
            {versions.map((v) => (
              <option key={v.version_id} value={v.version_id}>
                v{v.version}
              </option>
            ))}
          </select>
        </label>
      </div>
      {left === right ? (
        <p className="muted">请选择不同版本。</p>
      ) : error ? (
        <p className="inline-error" role="alert">
          {error}
        </p>
      ) : value ? (
        <Changes value={value} />
      ) : (
        open && <p>正在比较…</p>
      )}
    </details>
  );
}
