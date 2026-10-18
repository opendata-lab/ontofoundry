import { Alert, Button, Descriptions, Form, Modal, Select, Steps, Typography, Upload } from "antd";
import { FileUp } from "lucide-react";
import { useRef, useState } from "react";
import { ApiError, importApi } from "../api/client";
import type { ImportConfirmed, ImportPreview } from "../api/types";
import { newId } from "../lib/id";
import { TranslationReport } from "./TranslationReport";

export function ImportDialog({ open, workspaceId, maxFileMb = 20, onClose, onConfirmed }: { open: boolean; workspaceId: string; maxFileMb?: number; onClose: () => void; onConfirmed: (result: ImportConfirmed) => void }) {
  return <Modal closable={{ "aria-label": "关闭导入弹窗" }} open={open} onCancel={onClose} title="导入本体文件" footer={null} width="var(--review-dialog-width)" destroyOnHidden><ImportFlow key={`${workspaceId}:${open}`} workspaceId={workspaceId} maxFileMb={maxFileMb} onClose={onClose} onConfirmed={onConfirmed} /></Modal>;
}

function ImportFlow({ workspaceId, maxFileMb, onClose, onConfirmed }: { workspaceId: string; maxFileMb: number; onClose: () => void; onConfirmed: (result: ImportConfirmed) => void }) {
  const [adapter, setAdapter] = useState("ossie-0.2");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [expired, setExpired] = useState(false);
  const submitting = useRef(false);
  const sequence = useRef(0);
  const confirmKey = useRef(newId());
  const reset = () => {
    sequence.current += 1;
    setPreview(null); setStep(0); setError(""); setExpired(false);
    confirmKey.current = newId();
  };
  const load = async () => {
    if (!file || submitting.current) return;
    submitting.current = true; setBusy(true); setError("");
    const current = ++sequence.current;
    try {
      const result = await importApi.preview(workspaceId, adapter, file);
      if (current !== sequence.current) return;
      setPreview(result); setStep(1); setExpired(false); confirmKey.current = newId();
    } catch (e) { if (current === sequence.current) setError(e instanceof Error ? e.message : "预览失败"); }
    finally { submitting.current = false; setBusy(false); }
  };
  const confirm = async () => {
    if (!preview || submitting.current || expired || preview.document_error) return;
    submitting.current = true; setBusy(true); setError("");
    try {
      const result = await importApi.confirm(workspaceId, adapter, preview.import_id, { content_sha256: preview.content_sha256, expected_current_version_id: preview.base_version_id, idempotency_key: confirmKey.current });
      onConfirmed(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "确认失败");
      if (e instanceof ApiError && ["IMPORT_BASE_CHANGED", "IMPORT_IDENTITIES_CHANGED", "IMPORT_ARTIFACT_CHANGED", "IMPORT_CONTENT_CHANGED"].includes(e.code)) setExpired(true);
      if (e instanceof ApiError && e.code === "IMPORT_ALREADY_CONFIRMED") setExpired(true);
    } finally { submitting.current = false; setBusy(false); }
  };
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <Steps size="small" current={step} items={[{ title: "选择文件" }, { title: "预览报告" }, { title: "生成提案" }]} />
      {error && <Alert type="error" showIcon message={error} />}
      {step === 0 && <Form layout="vertical">
        <Form.Item label="文件格式">
          <Select aria-label="文件格式" value={adapter} disabled={busy} onChange={(value) => { reset(); setAdapter(value); setFile(null); }} options={[{ value: "ossie-0.2", label: "Apache Ossie 0.2" }, { value: "ontofoundry-core-1", label: "OntoFoundry core-1 原生单文件" }]} />
        </Form.Item>
        <Form.Item label="本体文件" extra={`支持 UTF-8 JSON，最大 ${maxFileMb} MB。`}>
          <Upload accept=".json" maxCount={1} disabled={busy} fileList={file ? [{ uid: "import-file", name: file.name, status: "done" }] : []} beforeUpload={(next) => {
            reset();
            if (next.size > maxFileMb * 1024 * 1024) { setFile(null); setError("文件超过上传限制"); }
            else setFile(next);
            return false;
          }} onRemove={() => { reset(); setFile(null); }}>
            <Button icon={<FileUp size={15} />}>选择 JSON 文件</Button>
          </Upload>
        </Form.Item>
        <Typography.Paragraph type="secondary">先查看转换结果，再生成待审提案。接受提案后仍需正常发布。</Typography.Paragraph>
      </Form>}
      {preview && step > 0 && <>
        <Descriptions size="small" column={2} items={[
          { key: "file", label: "文件", children: preview.filename, span: 2 },
          { key: "create", label: "新增", children: preview.proposal_summary.create },
          { key: "update", label: "更新", children: preview.proposal_summary.update },
          { key: "same", label: "不变", children: preview.proposal_summary.unchanged },
          { key: "blocked", label: "阻断", children: preview.proposal_summary.blocked.length },
        ]} />
        {preview.document_error && <Alert type="error" showIcon message="文件未通过校验，请修正后重新选择文件。" />}
        {!!preview.proposal_summary.blocked.length && <Alert type="warning" showIcon message="部分内容与当前模型冲突，其他合法内容仍可生成提案。" description={preview.proposal_summary.blocked.map((b) => b.reason).filter((value, i, all) => all.indexOf(value) === i).join("；")} />}
        {step === 1 && <div className="max-h-review-code overflow-auto"><TranslationReport report={preview.report} idMap={preview.id_map} /></div>}
        {step === 2 && <Alert type="info" showIcon message="确认后将创建独立会话和待审提案" description={`已发布内容保持原样。${preview.completion.length ? `另有 ${preview.completion.length} 项可在会话中人工补全。` : "可在提案页逐项接受或拒绝。"}`} />}
      </>}
      <div className="flex justify-end gap-2 border-t border-rule pt-4">
        <Button disabled={busy} onClick={onClose}>取消</Button>
        {step > 0 && <Button disabled={busy} onClick={() => { if (step === 2 && !expired) setStep(1); else reset(); }}>上一步</Button>}
        {step === 0 ? <Button type="primary" disabled={!file} loading={busy} onClick={() => void load()}>预览转换</Button> : expired ? <Button type="primary" loading={busy} onClick={() => void load()}>重新预览</Button> : step === 1 ? <Button type="primary" disabled={preview?.document_error} onClick={() => setStep(2)}>下一步</Button> : <Button type="primary" loading={busy} onClick={() => void confirm()}>生成待审提案</Button>}
      </div>
    </div>
  );
}
