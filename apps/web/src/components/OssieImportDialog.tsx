import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Upload } from "lucide-react";
import { modelingApi, publishApi } from "../api/client";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import type { OssieImportResult } from "../api/types";

type Mode = "merge" | "replace";

// Import lands in a modeling session first, so the report can be read before
// anything goes live: what Ossie constructs the internal model could not take.
// A first import has nothing to compare with: confirming the report publishes
// it as the initial version. A re-import meets a published model, so it goes
// to the publish page's three-way merge to be compared and confirmed there.
export function OssieImportDialog({
  workspaceId,
  onClose,
}: {
  workspaceId: string;
  onClose: (imported: boolean) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [payload, setPayload] = useState<unknown>(null);
  const [fileName, setFileName] = useState("");
  const [mode, setMode] = useState<Mode>("merge");
  // The default follows the situation; first import has no history to keep.
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<OssieImportResult | null>(null);
  const [published, setPublished] = useState<number | null>(null);
  const [publishError, setPublishError] = useState("");
  const { workspace, refresh } = useWorkspaceContext();
  const firstImport = !workspace.current_version;
  useEffect(() => dialog.current?.showModal(), []);

  const read = (file: File | undefined) => {
    setError("");
    setResult(null);
    setPayload(null);
    setFileName(file?.name ?? "");
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      try {
        setPayload(JSON.parse(String(reader.result)));
      } catch {
        setError("文件不是有效的 JSON");
      }
    };
    reader.onerror = () => setError("文件读取失败");
    reader.readAsText(file);
  };

  const submit = () => {
    if (!payload) return;
    setBusy(true);
    setError("");
    modelingApi
      .importOssie(workspaceId, payload, firstImport ? "replace" : mode)
      .then(setResult)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const publish = async () => {
    if (!result) return;
    setBusy(true);
    setPublishError("");
    try {
      const preview = await publishApi.preview(result);
      if (!preview.validation.publishable) {
        const first = preview.validation.errors[0] as
          | { message?: string }
          | undefined;
        throw new Error(first?.message ?? "校验未通过，请到发布页查看");
      }
      const name =
        result.import_report.name || fileName.replace(/\.json$/i, "");
      const done = await publishApi.publish(result, preview, `导入 ${name}`);
      // Refreshing the workspace now would reload the page under the dialog
      // and lose this confirmation; it happens when the dialog closes.
      setPublished(done.version.version);
    } catch (e) {
      setPublishError(e instanceof Error ? e.message : "发布失败");
    } finally {
      setBusy(false);
    }
  };

  const close = () => {
    dialog.current?.close();
    if (published) refresh();
    onClose(!!result);
  };
  const report = result?.import_report;
  return (
    <dialog
      ref={dialog}
      className="ref-dialog import-dialog"
      aria-label="导入本体"
    >
      <header>
        <h2>导入 Apache Ossie 本体</h2>
        <button className="icon-button" onClick={close} aria-label="关闭导入">
          ×
        </button>
      </header>
      {report ? (
        <div className="import-report">
          <p className="validation-pass" role="status">
            {published
              ? `已发布为 v${published}，本体视图与 MCP 服务已切换到新版本。`
              : firstImport
                ? `已读取「${result.title}」，确认下方报告无误后发布为初始版本。`
                : `已读取「${result.title}」。空间已有 v${workspace.current_version}，请对比差异并合并后发布。`}
          </p>
          <div className="release-stats">
            <span>
              新增对象 <b>{report.counts.objects_added}</b>
            </span>
            <span>
              更新对象 <b>{report.counts.objects_updated}</b>
            </span>
            <span>
              新增关系 <b>{report.counts.links_added}</b>
            </span>
            <span>
              新增属性 <b>{report.counts.attributes_added}</b>
            </span>
            <span>
              新增映射 <b>{report.counts.mappings_added ?? 0}</b>
            </span>
          </div>
          {publishError && (
            <p className="inline-error" role="alert">
              {publishError}{" "}
              <Link to={"../delivery?session=" + result.id} onClick={close}>
                到发布页处理
              </Link>
            </p>
          )}
          <div className="row-actions">
            {published ? (
              <button className="button button--primary" onClick={close}>
                完成
              </button>
            ) : firstImport ? (
              <>
                <button
                  className="button button--primary"
                  disabled={busy}
                  onClick={() => void publish()}
                >
                  {busy ? "正在发布…" : "确认并发布为初始版本"}
                </button>
                <Link
                  className="button button--secondary"
                  to={"../builder?session=" + result.id}
                  onClick={close}
                >
                  先看草稿，稍后发布
                </Link>
              </>
            ) : (
              <>
                <Link
                  className="button button--primary"
                  to={"../delivery?session=" + result.id}
                  onClick={close}
                >
                  对比并合并
                </Link>
                <Link
                  className="button button--secondary"
                  to={"../builder?session=" + result.id}
                  onClick={close}
                >
                  先看草稿
                </Link>
              </>
            )}
          </div>
          {!!report.skipped.length && (
            <>
              <h3>未导入的内容（{report.skipped.length}）</h3>
              <table className="ref-table">
                <thead>
                  <tr>
                    <th>位置</th>
                    <th>原因</th>
                  </tr>
                </thead>
                <tbody>
                  {report.skipped.map((item) => (
                    <tr key={item.path + item.reason}>
                      <td>
                        <code>{item.path}</code>
                      </td>
                      <td>{item.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
          {report.notes.filter(note => note.startsWith("平台扩展碰撞")).map(note => <p className="element-note" role="status" key={note}>{note}</p>)}
          {!!report.notes.length && (
            <details className="import-notes">
              <summary>导入说明（{report.notes.length} 条）</summary>
              {report.notes.map((note) => (
                <p className="muted" key={note}>
                  {note}
                </p>
              ))}
            </details>
          )}
        </div>
      ) : (
        <>
          <p className="muted">
            {firstImport
              ? "读取 Apache Ossie 0.2.0.dev0 本体 JSON。空间还没有版本：确认导入报告后直接发布为初始版本。"
              : `读取 Apache Ossie 0.2.0.dev0 本体 JSON。空间已有 v${workspace.current_version}：导入后进入对比与合并，确认后发布新版本。`}
          </p>
          <label className="section-field">
            <span>本体文件</span>
            <input
              type="file"
              accept=".json,application/json"
              aria-label="选择 Ossie JSON 文件"
              onChange={(e) => read(e.target.files?.[0])}
            />
          </label>
          {!firstImport && (
            <fieldset className="import-modes">
              <legend>导入方式</legend>
              <label>
                <input
                  type="radio"
                  name="import-mode"
                  checked={mode === "merge"}
                  onChange={() => setMode("merge")}
                />
                合并：按技术名新增或更新，文件之外的对象、实例与数据映射保持不变
              </label>
              <label>
                <input
                  type="radio"
                  name="import-mode"
                  checked={mode === "replace"}
                  onChange={() => setMode("replace")}
                />
                替换：草稿只保留文件内容，发布后文件之外的对象会消失
              </label>
            </fieldset>
          )}
          {error && <p className="inline-error">{error}</p>}
          <div className="row-actions">
            <button
              className="button button--primary"
              disabled={!payload || busy}
              onClick={submit}
            >
              <Upload size={14} />
              {busy ? "导入中…" : "导入" + (fileName ? " " + fileName : "")}
            </button>
            <button className="button button--secondary" onClick={close}>
              取消
            </button>
          </div>
        </>
      )}
    </dialog>
  );
}
