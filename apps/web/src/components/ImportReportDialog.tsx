import { Alert, Modal, Spin, Tabs, Typography } from "antd";
import { useEffect, useState } from "react";
import { importApi, modelingApi } from "../api/client";
import type { ImportConfirmed, ImportPreview, ImportSource, ModelingSession } from "../api/types";
import { ImportCompletionList } from "./ImportCompletionList";
import { TranslationReport } from "./TranslationReport";

type ImportReportDialogProps = { open: boolean; source: ImportSource; session: ModelingSession; onClose: () => void; onChanged: (result: ImportConfirmed) => void };

export function ImportReportDialog(props: ImportReportDialogProps) {
  const { open, source, session } = props;
  return <ImportReportContent key={`${session.workspace_id}:${session.id}:${source.adapter}:${source.report_id}:${open}`} {...props} />;
}

function ImportReportContent({ open, source, session, onClose, onChanged }: ImportReportDialogProps) {
  const [report, setReport] = useState<ImportPreview | null>(null);
  const [current, setCurrent] = useState(session);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const { adapter, report_id: reportId } = source;
  const { workspace_id: workspaceId, id: sessionId, revision } = session;
  useEffect(() => {
    if (!open) return;
    let active = true;
    Promise.all([importApi.get(workspaceId, { adapter, report_id: reportId }), modelingApi.get(workspaceId, sessionId)]).then(([value, next]) => { if (active) { setReport(value); setCurrent(next); setError(""); } }).catch((e: Error) => { if (active) setError(e.message); });
    return () => { active = false; };
  }, [open, adapter, reportId, workspaceId, sessionId, revision, refresh]);
  return <Modal closable={{ "aria-label": "关闭导入弹窗" }} open={open} onCancel={onClose} title="导入报告" footer={null} width="var(--review-detail-width)" destroyOnHidden>
    {error && <Alert type="error" showIcon message={error} />}
    {report ? <div className="max-h-review-detail overflow-auto">
      {!!report.current_blocked.length && <Alert type="warning" showIcon message={`当前仍有 ${report.current_blocked.length} 项阻断`} description={[...new Set(report.current_blocked.map((b) => b.reason))].join("；")} />}
      <Typography.Paragraph type="secondary">{report.filename} · {report.adapter} · 历史转换报告保留导入时的结果</Typography.Paragraph>
      <Tabs items={[
        { key: "report", label: "转换报告", children: <TranslationReport report={report.report} idMap={report.id_map} /> },
        { key: "completion", label: `人工补全 ${report.completion.filter((c) => c.status !== "accepted").length}`, children: <ImportCompletionList items={report.completion} source={source} session={current} onChanged={(result) => { setRefresh((v) => v + 1); onChanged(result); }} /> },
      ]} />
    </div> : !error && <Spin tip="正在加载报告"><div className="h-32" /></Spin>}
  </Modal>;
}
