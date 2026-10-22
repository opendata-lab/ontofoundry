import { Alert, Descriptions, Modal, Table, Tabs, Typography } from "antd";
import { useEffect, useState } from "react";
import { catalogApi } from "../api/client";
import type { AssetTable, TableRows } from "../api/types";
import { syncTime } from "../lib/metadataSync";
import { StatusMark } from "./layout";

// NULL keeps the cell's own size; only the color sets it apart from a value.
const cell = (value: unknown) => value === null || value === undefined ? <span className="text-muted">NULL</span>
  : typeof value === "object" ? JSON.stringify(value) : String(value);

/** One synced table: catalog facts, columns and the first rows from the source. */
export function TableDetailDialog({ workspaceId, connectionId, schema, table, onClose }: {
  workspaceId: string; connectionId: string; schema: string; table: AssetTable; onClose: () => void;
}) {
  const [tab, setTab] = useState("info");
  const [rows, setRows] = useState<TableRows | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // Rows come from the business source, so they load only when asked for.
  useEffect(() => {
    if (tab !== "rows" || rows || table.missing) return;
    let live = true;
    setLoading(true); setError("");
    catalogApi.tableRows(workspaceId, connectionId, { table_name: table.name, schema_name: schema || undefined })
      .then((value) => { if (live) setRows(value); })
      .catch((e: Error) => { if (live) setError(e.message); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [tab, rows, table, workspaceId, connectionId, schema]);
  return <Modal open title={`表详情 · ${table.name}`} width="var(--data-tables-dialog-width)" footer={null} onCancel={onClose}>
    {/* A fixed body keeps the dialog from resizing as tabs change; long content scrolls inside. */}
    <Tabs className="table-detail" activeKey={tab} onChange={setTab} items={[
      { key: "info", label: "基本信息", children: <Descriptions className="table-detail-info" size="small" column={2} items={[
        { key: "name", label: "表名", children: table.name },
        { key: "schema", label: "库", children: schema },
        { key: "kind", label: "类型", children: table.kind === "view" ? "视图" : "表" },
        { key: "state", label: "状态", children: <StatusMark state={table.missing ? "error" : "mapped"} label={table.missing ? "当前不可见或不存在" : "已登记"} /> },
        { key: "columns", label: "字段数", children: table.columns.length },
        { key: "time", label: "最近同步时间", children: syncTime(table.observed_at) },
        { key: "pk", label: "主键", children: table.primary_key?.length ? table.primary_key.join("、") : "无" },
        { key: "datasets", label: "引用的数据集", children: table.datasets.length ? table.datasets.map((d) => d.display_name || d.name).join("、") : "无" },
        { key: "comment", label: "说明", span: 2, children: table.comment || "无" },
      ]} /> },
      { key: "columns", label: `字段（${table.columns.length}）`, children: <Table size="small" rowKey="name" dataSource={table.columns} pagination={table.columns.length > 20 ? { pageSize: 20, showSizeChanger: false } : false} columns={[
        { title: "字段名", dataIndex: "name" },
        { title: "类型", dataIndex: "type" },
        { title: "主键", key: "pk", render: (_, c) => c.primary_key ? "是" : "" },
        { title: "可空", key: "nullable", render: (_, c) => c.nullable === false ? "否" : c.nullable ? "是" : "" },
        { title: "说明", dataIndex: "comment" },
      ]} /> },
      { key: "rows", label: "数据", children: <div className="flex flex-col gap-3">
        {table.missing ? <Alert type="warning" showIcon message="表当前不可见或不存在，无法读取数据" />
          : <Typography.Text type="secondary" className="text-xs">只读查询，最多显示前 {rows?.limit ?? 100} 行</Typography.Text>}
        {error && <Alert type="error" showIcon message={error} />}
        {!table.missing && <Table size="small" loading={loading} scroll={{ x: "max-content" }} rowKey={(_, i) => String(i)}
          dataSource={rows?.items ?? []} pagination={(rows?.items.length ?? 0) > 20 ? { pageSize: 20, showSizeChanger: false } : false}
          columns={(rows?.columns ?? table.columns.map((c) => c.name)).map((name) => ({ title: name, key: name, render: (_: unknown, row: Record<string, unknown>) => cell(row[name]) }))} />}
      </div> },
    ]} />
  </Modal>;
}
