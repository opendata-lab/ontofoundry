import { Alert, Button, Form, Input, Modal } from "antd";
import { useState } from "react";
import type { Dataset, ProposalItem } from "../../api/types";
import { DatasetLocationFields } from "../elements/DatasetLocationFields";
import { SectionTitle } from "../layout";
import { TableSyncPanel } from "../TableSyncPanel";

const TITLE: Record<string, string> = {
  SOURCE_NOT_REGISTERED: "表未同步",
  SOURCE_REMOVED: "表已不可见",
  CONNECTION_UNBOUND: "未绑定连接",
  DATASET_SOURCE_BLOCKED: "依赖的数据集未就绪",
  COLUMN_NOT_FOUND: "列不存在",
};

/** Derived source problems on a proposal, with the two fixes a reviewer can apply. */
export function ProposalSourceIssues({ item, workspaceId, busy, onReviseDataset }: {
  item: ProposalItem;
  workspaceId: string;
  busy: boolean;
  onReviseDataset: (dataset: Dataset) => Promise<boolean>;
}) {
  const issues = (item.source_diagnostics ?? []).filter((d) => d.severity === "error");
  const [syncing, setSyncing] = useState<{ connection?: string; schema?: string; table?: string } | null>(null);
  const [editing, setEditing] = useState<Dataset | null>(null);
  if (!issues.length || item.status !== "pending") return null;
  const dataset = item.target_kind === "dataset" && item.operation !== "delete" ? (item.after as Dataset | null) : null;
  return (
    <section className="flex flex-col gap-2 border-b border-rule pb-4">
      <SectionTitle title="数据来源" note="处理后会自动重新校验，未处理时不能接受" />
      {issues.map((issue) => (
        <Alert
          key={`${issue.code}:${issue.path}:${issue.details?.table_name ?? ""}`}
          type="error"
          showIcon
          message={`${TITLE[issue.code] ?? "来源未就绪"}：${issue.message}`}
          action={
            issue.code === "SOURCE_NOT_REGISTERED" && issue.details?.connection_id ? (
              <Button size="small" disabled={busy} onClick={() => setSyncing({
                connection: issue.details?.connection_id, schema: issue.details?.schema_name, table: issue.details?.table_name,
              })}>
                去同步
              </Button>
            ) : undefined
          }
        />
      ))}
      {dataset && (
        <div>
          <Button size="small" disabled={busy} onClick={() => setEditing({ ...dataset })}>修改连接和表</Button>
        </div>
      )}
      {syncing && (
        <Modal open title="同步数据表" width="var(--review-dialog-width)" footer={null} onCancel={() => setSyncing(null)}>
          <TableSyncPanel workspaceId={workspaceId} initialConnection={syncing.connection} initialSchema={syncing.schema ?? ""} initialTable={syncing.table} />
        </Modal>
      )}
      {editing && (
        <Modal
          open
          title="修改数据集来源"
          okText="保存并重新校验"
          cancelText="取消"
          okButtonProps={{ loading: busy, disabled: !editing.connection_id || (editing.source_kind !== "query" && !editing.table_name) }}
          onCancel={() => setEditing(null)}
          onOk={() => void onReviseDataset(editing).then((ok) => { if (ok) setEditing(null); })}
        >
          <Form layout="vertical" component="div">
            <DatasetLocationFields
              workspaceId={workspaceId}
              dataset={editing}
              nameField={<Form.Item label="名称"><Input aria-label="数据集名称" value={editing.display_name || editing.name} disabled /></Form.Item>}
              onChange={(patch) => setEditing((current) => (current ? { ...current, ...patch } : current))}
            />
          </Form>
        </Modal>
      )}
    </section>
  );
}
