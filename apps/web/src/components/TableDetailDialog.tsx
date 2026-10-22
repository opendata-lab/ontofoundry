import { Alert, Button, Descriptions, Empty, Modal, Table, Tabs, Typography } from "antd";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { catalogApi, modelingApi } from "../api/client";
import type { AssetTable, SchemaImpactItem, TableRows } from "../api/types";
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
  const navigate = useNavigate();
  const [impact, setImpact] = useState<SchemaImpactItem[] | null>(null);
  const [impactError, setImpactError] = useState("");
  const [starting, setStarting] = useState(false);
  useEffect(() => {
    if (tab !== "changes" || impact) return;
    let live = true;
    catalogApi.schemaImpact(workspaceId, connectionId, schema || undefined)
      .then((value) => { if (live) setImpact(value.items.filter((i) => i.table === table.name)); })
      .catch((e: Error) => { if (live) setImpactError(e.message); });
    return () => { live = false; };
  }, [tab, impact, workspaceId, connectionId, schema, table.name]);
  // Opens a new modeling session with this table linked; the user says what to adjust (SC-02).
  const startModeling = async () => {
    setStarting(true);
    try {
      const session = await modelingApi.create(workspaceId, `结构变化：${table.name}`);
      await modelingApi.save(session, session.draft, { linked_tables: [{ connection_id: connectionId, schema_name: schema, table_name: table.name }] });
      onClose();
      navigate(`/workspaces/${workspaceId}/builder?session=${session.id}`);
    } catch (e) {
      setImpactError(e instanceof Error ? e.message : "无法发起建模");
    } finally {
      setStarting(false);
    }
  };
  const CHANGE = { added: "新增", removed: "消失", changed: "修改" } as const;
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
      { key: "changes", label: "结构变化", children: <div className="flex flex-col gap-3">
        {impactError && <Alert type="error" showIcon message={impactError} />}
        {impact && !impact.length && <Empty description="最近一次同步没有记录到这张表的结构变化" />}
        {impact?.map((item, n) => (
          <section key={n} className="flex flex-col gap-1 border-b border-rule pb-3">
            <Typography.Text strong>{item.column ? `列 ${item.column}` : "整张表"}{CHANGE[item.kind]}</Typography.Text>
            {item.affected.length
              ? item.affected.map((a) => (
                <Typography.Text key={`${a.kind}:${a.id}`} type="secondary" className="text-xs">
                  {a.display_name || a.name}（{a.name}）· {a.via === "column" ? "引用该列" : "引用该表"}
                </Typography.Text>
              ))
              : <Typography.Text type="secondary" className="text-xs">已发布本体中没有定义引用它</Typography.Text>}
          </section>
        ))}
        {!!impact?.some((i) => i.affected.length) && (
          <div><Button type="primary" loading={starting} onClick={() => void startModeling()}>发起局部建模</Button></div>
        )}
      </div> },
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
