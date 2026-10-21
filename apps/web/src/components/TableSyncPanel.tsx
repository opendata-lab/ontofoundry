import { Alert, Empty, Form, Input, Menu, Select, Table, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import { catalogApi } from "../api/client";
import type { DataConnection } from "../api/types";
import { usePageActive } from "../hooks/usePageTab";
import { loadSchemaAssets, syncTime, type SchemaAssets } from "../lib/metadataSync";
import { DataTablesLayout, StatusMark } from "./layout";


export function TableSyncPanel({ workspaceId, initialConnection, initialSchema = "", refreshKey = 0, onConnectionChange }: {
  workspaceId: string; initialConnection?: string; initialSchema?: string; refreshKey?: number; onConnectionChange?: (id: string) => void;
}) {
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
  }, [workspaceId, connectionId, refreshKey, active]);
  const rows = useMemo(() => groups.filter((g) => !schema || g.schema === schema).flatMap((g) => g.assets.items.map((t) => ({ ...t, schema: g.schema }))).filter((t) => `${t.name} ${t.comment ?? ""}`.toLowerCase().includes(search.toLowerCase())).sort((a, b) => {
    const difference = sort === "columns" ? a.columns.length - b.columns.length : sort === "time" ? (Date.parse(a.observed_at ?? "") || 0) - (Date.parse(b.observed_at ?? "") || 0) : a.name.localeCompare(b.name);
    return (difference || a.schema.localeCompare(b.schema) || a.name.localeCompare(b.name)) * (direction === "asc" ? 1 : -1);
  }), [groups, schema, search, sort, direction]);
  const latest = groups.map((g) => g.assets.observed_at).filter((t): t is string => !!t).sort().at(-1);
  const controls = <>
    <Form layout="vertical" component="div"><Form.Item label="数据连接" className="mb-0"><Select aria-label="数据连接" placeholder="选择数据连接" value={connectionId || undefined} options={connections.map((c) => ({ value: c.id, label: `${c.name} · ${c.kind}` }))} onChange={(id) => { setConnectionId(id); setSchema(""); }} /></Form.Item></Form>
    <div><Typography.Text strong>库</Typography.Text><Menu aria-label="库列表" className="border-0" selectedKeys={[schema]} onClick={({ key }) => setSchema(key)} items={[{ key: "", label: <div><div>全部库 · {groups.reduce((n, g) => n + g.assets.items.length, 0)} 张</div><Typography.Text type="secondary" className="text-xs">{syncTime(latest)}</Typography.Text></div> }, ...groups.map((g) => ({ key: g.schema, label: <div><div>{g.schema} · {g.assets.items.length} 张</div><Typography.Text type="secondary" className="text-xs">{syncTime(g.assets.observed_at)}</Typography.Text></div> }))]} /></div>
    <Form layout="vertical" component="div"><Form.Item label="搜索" ><Input.Search aria-label="搜索表名或注释" placeholder="表名或注释" allowClear value={search} onChange={(e) => setSearch(e.target.value)} /></Form.Item><Form.Item label="排序字段"><Select aria-label="排序字段" value={sort} onChange={setSort} options={[{ value: "name", label: "表名" }, { value: "time", label: "最近同步时间" }, { value: "columns", label: "列数" }]} /></Form.Item><Form.Item label="排序方向" className="mb-0"><Select aria-label="排序方向" value={direction} onChange={setDirection} options={[{ value: "asc", label: "升序" }, { value: "desc", label: "降序" }]} /></Form.Item></Form>
  </>;
  return <DataTablesLayout controls={controls}><div className="flex flex-col gap-3">
    {error && <Alert type="error" showIcon message={error} />}
    <Table size="middle" rowKey={(t) => JSON.stringify([t.schema, t.name])} dataSource={rows} loading={loading} pagination={rows.length > 20 ? { pageSize: 20, showSizeChanger: false } : false} locale={{ emptyText: <Empty description={search ? "没有匹配的数据表" : "还没有已登记数据表，请点击同步数据表"} /> }} columns={[{ title: "表名", dataIndex: "name" }, { title: "库", dataIndex: "schema" }, { title: "列数", key: "columns", render: (_, t) => t.columns.length }, { title: "状态", key: "state", render: (_, t) => <StatusMark state={t.missing ? "error" : "mapped"} label={t.missing ? "当前不可见或不存在" : "已登记"} /> }, { title: "最近同步时间", key: "time", render: (_, t) => syncTime(t.observed_at) }, { title: "说明", dataIndex: "comment" }]} />
  </div></DataTablesLayout>;
}
