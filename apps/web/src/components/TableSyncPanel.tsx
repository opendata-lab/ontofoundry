import { Alert, App, Button, Empty, Input, Popconfirm, Select, Table, Tooltip, Typography } from "antd";
import { ArrowDownWideNarrow, ArrowUpNarrowWide, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { catalogApi } from "../api/client";
import type { AssetTable, DataConnection } from "../api/types";
import { usePageActive } from "../hooks/usePageTab";
import { loadSchemaAssets, syncTime, type SchemaAssets } from "../lib/metadataSync";
import { PageToolbar, Panel, StatusMark } from "./layout";
import { TableDetailDialog } from "./TableDetailDialog";


export function TableSyncPanel({ workspaceId, initialConnection, initialSchema = "", refreshKey = 0, onConnectionChange, actions, canManage = false }: {
  workspaceId: string; initialConnection?: string; initialSchema?: string; refreshKey?: number; onConnectionChange?: (id: string) => void;
  /** Primary page actions, placed where the documents tab puts its upload button. */
  actions?: ReactNode;
  /** Members who may sync may also remove a table from the registered catalog. */
  canManage?: boolean;
}) {
  const { message } = App.useApp();
  const [reload, setReload] = useState(0);
  const active = usePageActive();
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [connectionId, setConnectionId] = useState(initialConnection ?? "");
  const [schema, setSchema] = useState(initialSchema);
  const [groups, setGroups] = useState<SchemaAssets[]>([]);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("name");
  const [direction, setDirection] = useState("asc");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<AssetTable & { schema: string } | null>(null);
  useEffect(() => {
    let live = true;
    catalogApi.connections(workspaceId).then(({ items }) => { if (live) { setConnections(items); setConnectionId((id) => id || items[0]?.id || ""); } }).catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [workspaceId]);
  useEffect(() => { onConnectionChange?.(connectionId); }, [connectionId, onConnectionChange]);
  useEffect(() => {
    if (!connectionId || !active) return;
    let live = true;
    setLoading(true); setError(""); setGroups([]);
    loadSchemaAssets(workspaceId, connectionId).then((value) => { if (live) { setGroups(value); setSchema((current) => value.some((g) => g.schema === current) ? current : ""); } }).catch((e: Error) => { if (live) setError(e.message); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [workspaceId, connectionId, refreshKey, active, reload]);
  const remove = async (table: AssetTable & { schema: string }) => {
    try {
      await catalogApi.deleteTable(workspaceId, connectionId, table.schema, table.name);
      void message.success(`已移除 ${table.schema}.${table.name} 的登记`);
      setReload((n) => n + 1);
    } catch (e) {
      void message.error(e instanceof Error ? e.message : "删除失败");
    }
  };
  const rows = useMemo(() => groups.filter((g) => !schema || g.schema === schema).flatMap((g) => g.assets.items.map((t) => ({ ...t, schema: g.schema }))).filter((t) => `${t.name} ${t.comment ?? ""}`.toLowerCase().includes(search.toLowerCase())).sort((a, b) => {
    const difference = sort === "columns" ? a.columns.length - b.columns.length : sort === "time" ? (Date.parse(a.observed_at ?? "") || 0) - (Date.parse(b.observed_at ?? "") || 0) : a.name.localeCompare(b.name);
    return (difference || a.schema.localeCompare(b.schema) || a.name.localeCompare(b.name)) * (direction === "asc" ? 1 : -1);
  }), [groups, schema, search, sort, direction]);
  const latest = groups.map((g) => g.assets.observed_at).filter((t): t is string => !!t).sort().at(-1);
  return <>
    <PageToolbar extra={<>
      <Typography.Text type="secondary" className="text-xs">{rows.length} 张表 · 最近同步 {syncTime(latest)}</Typography.Text>
      <Input type="search" allowClear prefix={<Search size={14} />} className="w-60" aria-label="搜索表名或注释" placeholder="搜索表名或注释" value={search} onChange={(e) => setSearch(e.target.value)} />
    </>}>
      {actions}
      <Select aria-label="数据连接" className="w-48" placeholder="选择数据连接" value={connectionId || undefined} options={connections.map((c) => ({ value: c.id, label: c.name }))} onChange={(id) => { setConnectionId(id); setSchema(""); }} />
      <Select aria-label="库" className="w-48" value={schema} onChange={setSchema} options={[
        { value: "", label: `全部库 · ${groups.reduce((n, g) => n + g.assets.items.length, 0)} 张` },
        ...groups.map((g) => ({ value: g.schema, label: `${g.schema} · ${g.assets.items.length} 张` })),
      ]} />
      <Select aria-label="排序字段" className="w-36" value={sort} onChange={setSort} options={[{ value: "name", label: "按表名" }, { value: "time", label: "按同步时间" }, { value: "columns", label: "按列数" }]} />
      <Tooltip title={direction === "asc" ? "升序" : "降序"}>
        <Button aria-label={direction === "asc" ? "升序" : "降序"} icon={direction === "asc" ? <ArrowUpNarrowWide size={14} /> : <ArrowDownWideNarrow size={14} />} onClick={() => setDirection((d) => (d === "asc" ? "desc" : "asc"))} />
      </Tooltip>
    </PageToolbar>
    <Panel><div className="flex flex-col gap-3">
    {error && <Alert type="error" showIcon message={error} />}
    <Table size="middle" rowKey={(t) => JSON.stringify([t.schema, t.name])} dataSource={rows} loading={loading} pagination={rows.length > 20 ? { pageSize: 20, showSizeChanger: false } : false} locale={{ emptyText: <Empty description={search ? "没有匹配的数据表" : "还没有已登记数据表，请点击同步数据表"} /> }} columns={[{ title: "表名", key: "name", render: (_, t) => <Button type="link" size="small" className="h-auto p-0" onClick={() => setDetail(t)}>{t.name}</Button> }, { title: "库", dataIndex: "schema" }, { title: "列数", key: "columns", render: (_, t) => t.columns.length }, { title: "状态", key: "state", render: (_, t) => <StatusMark state={t.missing ? "error" : "mapped"} label={t.missing ? "当前不可见或不存在" : "已登记"} /> }, { title: "最近同步时间", key: "time", render: (_, t) => syncTime(t.observed_at) }, { title: "说明", dataIndex: "comment" },
      ...(canManage ? [{ title: "", key: "actions", width: 64, render: (_: unknown, t: AssetTable & { schema: string }) => (
        <Popconfirm
          title={`移除 ${t.schema}.${t.name} 的登记？`}
          description={`${t.datasets.length ? `${t.datasets.length} 个数据集引用这张表，移除后它们会显示“表未同步”。` : ""}只移除平台中的登记，业务库中的表不受影响；需要时可重新同步。`}
          okText="移除"
          okButtonProps={{ danger: true }}
          cancelText="取消"
          onConfirm={() => remove(t)}
        >
          <Button type="text" size="small" aria-label={`移除 ${t.name}`} icon={<Trash2 size={14} />} />
        </Popconfirm>
      ) }] : [])]} />
  </div></Panel>
    {detail && <TableDetailDialog workspaceId={workspaceId} connectionId={connectionId} schema={detail.schema} table={detail} onClose={() => setDetail(null)} />}
  </>;
}
