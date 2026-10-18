import { Alert, Button, Descriptions, Form, Modal, Select, Typography } from "antd";
import { useRef, useState } from "react";
import { exportApi } from "../api/client";
import type { ExportPreview, VersionSummary } from "../api/types";
import { TranslationReport } from "./TranslationReport";

export function ExportDialog({ open, workspaceId, versions, initialVersionId, onClose }: { open: boolean; workspaceId: string; versions: VersionSummary[]; initialVersionId?: string; onClose: () => void }) {
  return <Modal open={open} onCancel={onClose} closable={{ "aria-label": "关闭导出弹窗" }} title="导出本体文件" footer={null} width="var(--review-detail-width)" destroyOnHidden><ExportFlow key={`${workspaceId}:${open}:${initialVersionId ?? ""}`} workspaceId={workspaceId} versions={versions} initialVersionId={initialVersionId} onClose={onClose} /></Modal>;
}

function ExportFlow({ workspaceId, versions, initialVersionId, onClose }: { workspaceId: string; versions: VersionSummary[]; initialVersionId?: string; onClose: () => void }) {
  const [versionId, setVersionId] = useState(initialVersionId ?? versions[0]?.version_id ?? "");
  const [adapter, setAdapter] = useState("ontofoundry-core-1");
  const [preview, setPreview] = useState<ExportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const sequence = useRef(0);
  const submitting = useRef(false);
  const reset = () => { sequence.current += 1; setPreview(null); setError(""); };
  const load = async () => {
    if (!versionId || submitting.current) return;
    submitting.current = true; setBusy(true); setError(""); setPreview(null);
    const current = ++sequence.current;
    try {
      const value = await exportApi.preview(workspaceId, adapter, versionId);
      if (current === sequence.current) setPreview(value);
    } catch (e) { if (current === sequence.current) setError(e instanceof Error ? e.message : "导出失败"); }
    finally { submitting.current = false; setBusy(false); }
  };
  const hasErrors = !!preview?.report.issues.some((issue) => issue.outcome === "error");
  return <div className="flex min-w-0 flex-col gap-4">
    <Form layout="vertical" className="grid grid-cols-2 gap-x-4">
      <Form.Item label="已发布版本"><Select showSearch optionFilterProp="label" aria-label="导出版本" value={versionId || undefined} options={versions.map((v) => ({ value: v.version_id, label: `v${v.version}${v.message ? " · " + v.message : ""}` }))} onChange={(id) => { reset(); setVersionId(id); }} /></Form.Item>
      <Form.Item label="文件格式"><Select aria-label="导出格式" value={adapter} options={[{ value: "ontofoundry-core-1", label: "OntoFoundry core-1 原生单文件" }, { value: "ossie-0.2", label: "Apache Ossie 0.2" }]} onChange={(id) => { reset(); setAdapter(id); }} /></Form.Item>
    </Form>
    <Typography.Paragraph type="secondary" className="m-0">只导出所选已发布版本。原生单文件不包含材料原文；Ossie 的转换损失和逐指标约定见报告。</Typography.Paragraph>
    {error && <Alert type="error" showIcon message={error} />}
    {hasErrors && <Alert type="error" showIcon message="当前格式无法完整交付，未生成可下载文件" description="请按报告修正定义，或明确选择原生单文件后重新生成报告。" />}
    {preview && <>
      <Descriptions size="small" column={1} items={[
        { key: "file", label: "文件名", children: preview.filename },
        { key: "sha", label: "文件 SHA-256", children: preview.content_sha256 ? <Typography.Text code copyable className="break-all">{preview.content_sha256}</Typography.Text> : "未生成文件" },
      ]} />
      <div className="max-h-review-code overflow-auto"><TranslationReport key={`${preview.version_id}:${preview.adapter}:${preview.report.id}`} report={preview.report} /></div>
    </>}
    <div className="flex justify-end gap-2 border-t border-rule pt-4">
      <Button onClick={onClose}>关闭</Button>
      <Button disabled={!versionId} loading={busy} onClick={() => void load()}>{preview ? "重新生成报告" : "生成导出报告"}</Button>
      {preview?.download_url && !hasErrors && <Button type="primary" href={preview.download_url} download={preview.filename}>下载文件</Button>}
    </div>
  </div>;
}
