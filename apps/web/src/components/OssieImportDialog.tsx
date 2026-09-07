import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Upload } from "lucide-react";
import { modelingApi } from "../api/client";
import type { OssieImportResult } from "../api/types";

type Mode = "merge" | "replace";

// Import lands in a modeling session, never straight into the published model:
// publishing stays the one explicit step, and the report says what Ossie
// constructs the internal model could not take.
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<OssieImportResult | null>(null);
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
      .importOssie(workspaceId, payload, mode)
      .then(setResult)
      .catch((e: Error) => setError(e.message))
      .finally(() => setBusy(false));
  };

  const close = () => {
    dialog.current?.close();
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
            已生成建模草稿「{result.title}」，检查无误后再发布。
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
          </div>
          {report.notes.map((note) => (
            <p className="muted" key={note}>
              {note}
            </p>
          ))}
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
          <div className="row-actions">
            <Link
              className="button button--primary"
              to={"../builder?session=" + result.id}
              onClick={close}
            >
              打开导入草稿
            </Link>
            <button className="button button--secondary" onClick={close}>
              稍后处理
            </button>
          </div>
        </div>
      ) : (
        <>
          <p className="muted">
            读取 Apache Ossie 0.2.0.dev0 本体
            JSON。导入只生成建模草稿，发布仍是单独的操作。
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
