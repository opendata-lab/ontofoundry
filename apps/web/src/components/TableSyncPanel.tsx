import { Alert, Button, Empty, Select, Table, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { catalogApi } from "../api/client";
import type { Assets, DataConnection, SyncJob } from "../api/types";
import { usePageActive } from "../hooks/usePageTab";
import { PageToolbar, Panel, PanelToolbar, StatusMark } from "./layout";

const LABELS: Record<SyncJob["state"], string> = { queued: "等待同步", running: "同步中", succeeded: "同步完成", failed: "同步失败，可重试", partial_failed: "部分失败，可重试", interrupted: "已中断，可重试" };
export const METADATA_SYNCED = "ontofoundry:metadata-synced";

export function TableSyncPanel({ workspaceId, editable = true, initialConnection, initialSchema = "", initialTable, pageLayout = false }: {
  workspaceId: string; editable?: boolean; initialConnection?: string; initialSchema?: string; initialTable?: string; pageLayout?: boolean;
}) {
  const active = usePageActive();
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [connectionId, setConnectionId] = useState(initialConnection ?? "");
  const [schema, setSchema] = useState(initialSchema);
  const [schemas, setSchemas] = useState<string[]>([]);
  const [available, setAvailable] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>(initialTable ? [initialTable] : []);
  const [assets, setAssets] = useState<Assets | null>(null);
  const [job, setJob] = useState<SyncJob | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const running = job?.state === "queued" || job?.state === "running";
  const load = useCallback(async () => {
    if (!connectionId) return;
    const value = await catalogApi.assets(workspaceId, connectionId, { schema_name: schema });
    setAssets(value);
  }, [workspaceId, connectionId, schema]);
  useEffect(() => {
    let live = true;
    catalogApi.connections(workspaceId).then((r) => { if (live) { setConnections(r.items); setConnectionId((id) => id || r.items[0]?.id || ""); } }).catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [workspaceId]);
  useEffect(() => {
    if (!connectionId || !active) return;
    let live = true;
    setError(""); setAssets(null); setJob(null);
    void Promise.all([catalogApi.schemas(workspaceId, connectionId), catalogApi.tables(workspaceId, connectionId, { schema_name: schema || undefined }), catalogApi.assets(workspaceId, connectionId, { schema_name: schema }), catalogApi.syncJobs(workspaceId, connectionId, schema)]).then(([s, t, a, j]) => { if (live) { setSchemas(s.items); setAvailable(t.items.map((v) => v.name)); setAssets(a); setJob((current) => current ?? j.items[0] ?? null); } }).catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [workspaceId, connectionId, schema, active]);
  useEffect(() => {
    if (!running || !job || !active) return;
    let live = true;
    const timer = window.setInterval(() => { void catalogApi.syncJob(workspaceId, connectionId, job.id).then(async (value) => {
      if (!live) return;
      setJob(value);
      await load();
      if (value.state !== "queued" && value.state !== "running") window.dispatchEvent(new CustomEvent(METADATA_SYNCED, { detail: { workspaceId } }));
    }).catch((e: Error) => { if (live) setError(e.message); }); }, 2000);
    return () => { live = false; window.clearInterval(timer); };
  }, [workspaceId, connectionId, job, running, active, load]);
  const start = async (retry = false) => {
    if (!connectionId) return;
    setBusy(true); setError("");
    try { setJob(retry && job ? await catalogApi.retrySync(workspaceId, connectionId, job.id) : await catalogApi.refreshAssets(workspaceId, connectionId, { schema_name: schema }, selected)); }
    catch (problem) { setError(problem instanceof Error ? problem.message : "同步失败"); }
    finally { setBusy(false); }
  };
  const controls = <>
      <Select aria-label="数据连接" className="w-48" value={connectionId || undefined} options={connections.map((c) => ({ value: c.id, label: c.name }))} onChange={(id) => { setConnectionId(id); setSchema(""); setSelected([]); }} />
      <Select aria-label="Schema" className="w-44" allowClear placeholder="默认 Schema" value={schema || undefined} options={schemas.map((s) => ({ value: s, label: s }))} onChange={(v?: string) => { setSchema(v ?? ""); setSelected([]); }} />
      <Select mode="multiple" aria-label="选择同步表" className="min-w-56 flex-1" showSearch optionFilterProp="label" maxTagCount="responsive" placeholder="不选则全量同步" value={selected} options={[...new Set([...available, ...selected])].map((name) => ({ value: name, label: name }))} onChange={setSelected} />
  </>;
  const syncAction = editable && <Button type={pageLayout ? "primary" : "default"} size={pageLayout ? "middle" : "small"} loading={busy} disabled={!connectionId || running} onClick={() => void start()}>{selected.length ? `同步所选 ${selected.length} 张表` : "全量同步"}</Button>;
  const results = <div className="flex flex-col gap-3">
    {error && <Alert type="error" showIcon message={error} />}
    {job && <section className="flex flex-col gap-3">
      <div className="flex items-center gap-3"><StatusMark state={job.state === "succeeded" ? "mapped" : running ? "partial" : "error"} label={LABELS[job.state]} /><Typography.Text type="secondary">{job.total === null ? "正在发现数据表" : `已处理 ${job.processed}/${job.total}，可用 ${job.available}，失败 ${job.failed}`} · 累计 {job.duration_ms} ms</Typography.Text>{editable && !running && job.state !== "succeeded" && <Button size="small" loading={busy} onClick={() => void start(true)}>重试失败批次</Button>}</div>
      {job.error && <Alert type="warning" message={job.error} showIcon />}
      <Table size="small" rowKey="id" pagination={false} dataSource={job.batches} columns={[{ title: "批次", dataIndex: "ordinal", render: (v: number) => v + 1 }, { title: "表数", key: "tables", render: (_, b) => b.tables.length }, { title: "耗时（ms）", dataIndex: "duration_ms" }, { title: "尝试次数", dataIndex: "attempt" }, { title: "结果", key: "result", render: (_, b) => b.error || (b.state === "succeeded" ? "已完成" : b.state === "interrupted" ? "已中断" : "处理中") }]} expandable={{ expandedRowRender: (b) => <Table size="small" rowKey="table_name" pagination={false} dataSource={b.results} columns={[{ title: "表", dataIndex: "table_name" }, { title: "结果", key: "state", render: (_, r) => r.error || (r.state === "succeeded" ? "已登记" : "当前不可见或不存在") }]} /> }} />
    </section>}
    <Table size="middle" rowKey={(t) => `${t.schema}.${t.name}`} dataSource={assets?.items ?? []} loading={!assets && !error && !!connectionId} pagination={(assets?.items.length ?? 0) > 20 ? { pageSize: 20 } : false} locale={{ emptyText: <Empty description="还没有已登记数据表，请选择同步范围" /> }} columns={[{ title: "数据表", dataIndex: "name" }, { title: "库 / Schema", dataIndex: "schema" }, { title: "列", key: "columns", render: (_, t) => t.columns.length }, { title: "状态", key: "state", render: (_, t) => <StatusMark state={t.missing ? "error" : "mapped"} label={t.missing ? "当前不可见或不存在" : "已登记"} /> }, { title: "说明", dataIndex: "comment" }]} />
  </div>;
  return <div className="flex flex-col gap-4">
    {pageLayout
      ? <PageToolbar extra={controls}>{syncAction}</PageToolbar>
      : <PanelToolbar inset={false} extra={syncAction}>{controls}</PanelToolbar>}
    {pageLayout ? <Panel>{results}</Panel> : results}
  </div>;
}
