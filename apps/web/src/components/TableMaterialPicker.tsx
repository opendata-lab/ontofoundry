import { Alert, Button, Checkbox, Empty, Input, Modal, Typography } from "antd";
import { Database } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { datasetApi } from "../api/client";
import type { LinkedTable, RegisteredTable } from "../api/types";
import { tableKey, tableLabel } from "../lib/linkedTables";


/** Links registered tables to a modeling session; only synced tables can be used. */
export function TableMaterialPicker({ workspaceId, sessionId, linked, disabled, onLink }: {
  workspaceId: string;
  sessionId?: string;
  linked: LinkedTable[];
  disabled: boolean;
  onLink: (tables: LinkedTable[]) => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [tables, setTables] = useState<RegisteredTable[]>();
  const [selected, setSelected] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  // A string key keeps a fresh `linked` array from resetting the user's choice.
  const linkedKeys = linked.map(tableKey).join("\n");
  useEffect(() => {
    if (!open) return;
    let live = true;
    setTables(undefined);
    setError("");
    setSelected(linkedKeys ? linkedKeys.split("\n") : []);
    datasetApi.registeredTables(workspaceId, sessionId)
      .then((result) => { if (live) setTables(result.items); })
      .catch((e: Error) => { if (live) { setTables([]); setError(e.message); } });
    return () => { live = false; };
  }, [open, workspaceId, sessionId, linkedKeys]);
  const words = query.trim().toLowerCase();
  const visible = (tables ?? []).filter((t) => `${t.connection_name} ${tableLabel(t)} ${t.comment}`.toLowerCase().includes(words));
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      const byKey = new Map((tables ?? []).map((t) => [tableKey(t), t]));
      await onLink(selected.flatMap((key) => {
        const t = byKey.get(key);
        return t ? [{ connection_id: t.connection_id, schema_name: t.schema_name, table_name: t.table_name }] : [];
      }));
      setOpen(false);
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : "关联数据表失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button icon={<Database size={15} />} disabled={disabled} onClick={() => setOpen(true)}>选择数据表…</Button>
      <Modal
        open={open}
        title="关联数据表"
        onCancel={() => !busy && setOpen(false)}
        okText="关联到会话"
        cancelText="取消"
        okButtonProps={{ loading: busy, disabled: tables === undefined }}
        onOk={() => void save()}
      >
        <div className="flex flex-col gap-3">
          <Typography.Text type="secondary">只能使用已在数据管理中同步的表和视图；建模助手会在这些表上提议数据集。</Typography.Text>
          <Input.Search aria-label="搜索数据表" placeholder="连接、表名或注释" value={query} onChange={(e) => setQuery(e.target.value)} />
          {tables !== undefined && !tables.length && !error && (
            <Empty description={<span>还没有已同步的数据表，请先到 <Link to={`/workspaces/${workspaceId}/mappings`}>数据管理</Link> 同步</span>} />
          )}
          {!!tables?.length && !visible.length && <Empty description="没有匹配的数据表" />}
          {!!visible.length && (
            <Checkbox.Group
              className="flex max-h-review-code flex-col gap-2 overflow-auto"
              value={selected}
              onChange={(keys) => setSelected(keys as string[])}
              options={visible.map((t) => ({
                value: tableKey(t),
                label: (
                  <span className="inline-flex min-w-0 items-center gap-2 text-sm">
                    <span className="truncate" title={tableLabel(t)}>{tableLabel(t)}</span>
                    <Typography.Text type="secondary" className="text-xs">
                      {t.connection_name} · {t.column_count} 列{t.kind === "view" ? " · 视图" : ""}
                      {t.datasets.length ? ` · 已有数据集 ${t.datasets.map((d) => d.display_name || d.name).join("、")}` : ""}
                    </Typography.Text>
                  </span>
                ),
              }))}
            />
          )}
          {error && <Alert type="error" showIcon message={error} />}
        </div>
      </Modal>
    </>
  );
}
