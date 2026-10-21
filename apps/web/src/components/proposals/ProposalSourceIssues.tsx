import { Alert, Button, Form, Input, Modal } from "antd";
import { useState, type ReactNode } from "react";
import type { Dataset, ProposalItem } from "../../api/types";
import { DatasetLocationFields } from "../elements/DatasetLocationFields";
import { StatusMark } from "../layout";
import { TableSyncDialog } from "../TableSyncDialog";

const TITLE: Record<string, string> = {
  SOURCE_NOT_REGISTERED: "表未同步",
  SOURCE_REMOVED: "表已不可见",
  CONNECTION_UNBOUND: "未绑定连接",
  DATASET_SOURCE_BLOCKED: "依赖的数据集未就绪",
  COLUMN_NOT_FOUND: "列不存在",
};

/** "/table_name" or "/fields/amount/column" -> the top-level field the diff row shows. */
const fieldOf = (path: string) => path.replace(/^\//, "").split("/")[0] ?? "";

/**
 * Source problems placed next to the field they concern. After a sync or a
 * revision the proposals reload and the mark disappears where it was shown.
 */
export function useSourceIssues({ item, workspaceId, busy, fields, onReviseDataset }: {
  item: ProposalItem;
  workspaceId: string;
  busy: boolean;
  /** Fields the diff shows; problems elsewhere stay in a note above it. */
  fields: ReadonlySet<string>;
  onReviseDataset: (dataset: Dataset) => Promise<boolean>;
}): { marks: Record<string, ReactNode>; notes: ReactNode; dialogs: ReactNode } {
  const [syncing, setSyncing] = useState<{ connection?: string; schema?: string; table?: string } | null>(null);
  const [editing, setEditing] = useState<Dataset | null>(null);
  const issues = item.status === "pending" ? (item.source_diagnostics ?? []).filter((d) => d.severity === "error") : [];
  const dataset = item.target_kind === "dataset" && item.operation !== "delete" ? (item.after as Dataset | null) : null;

  const mark = (issue: (typeof issues)[number]) => (
    <span key={`${issue.code}:${issue.path}`} className="inline-flex flex-wrap items-center gap-2">
      <StatusMark state="error" label={TITLE[issue.code] ?? "来源未就绪"} title={issue.message} />
      {issue.code === "SOURCE_NOT_REGISTERED" && issue.details?.connection_id && (
        <Button
          type="link"
          size="small"
          className="h-auto p-0"
          disabled={busy}
          onClick={() => setSyncing({ connection: issue.details?.connection_id, schema: issue.details?.schema_name, table: issue.details?.table_name })}
        >
          去同步
        </Button>
      )}
      {dataset && (
        <Button type="link" size="small" className="h-auto p-0" disabled={busy} onClick={() => setEditing({ ...dataset })}>
          修改连接和表
        </Button>
      )}
    </span>
  );

  const marks: Record<string, ReactNode> = {};
  const unplaced: typeof issues = [];
  for (const issue of issues) {
    const field = fieldOf(issue.path);
    if (fields.has(field)) marks[field] = <>{marks[field]}{mark(issue)}</>;
    else unplaced.push(issue);
  }
  const notes = unplaced.length ? (
    <Alert
      type="error"
      showIcon
      message={<div className="flex flex-col gap-1">{unplaced.map((issue) => <span key={`${issue.code}:${issue.path}`}>{TITLE[issue.code] ?? "来源未就绪"}：{issue.message}</span>)}</div>}
      action={<div className="flex flex-col gap-1">{unplaced.map(mark)}</div>}
    />
  ) : null;

  const dialogs = (
    <>
      {syncing && (
        <TableSyncDialog
          workspaceId={workspaceId}
          initialConnection={syncing.connection}
          initialSchema={syncing.schema ?? ""}
          initialTable={syncing.table}
          onClose={() => setSyncing(null)}
        />
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
    </>
  );
  return { marks, notes, dialogs };
}
