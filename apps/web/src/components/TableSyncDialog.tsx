import { Alert, Button, Checkbox, Collapse, Empty, Form, Input, Modal, Select, Spin, Steps, Table, Typography } from "antd";
import { useEffect, useRef, useState } from "react";
import { catalogApi } from "../api/client";
import type { DataConnection, SyncJob } from "../api/types";
import { METADATA_SYNCED } from "../lib/metadataSync";
import { SectionTitle, StatusMark } from "./layout";

const activeJob = (job: SyncJob) => job.state === "queued" || job.state === "running";
const labels: Record<SyncJob["state"], string> = { queued: "等待同步", running: "同步中", succeeded: "同步完成", failed: "同步失败", partial_failed: "部分失败", interrupted: "已中断" };
const message = (e: unknown) => e instanceof Error ? e.message : "操作失败，请重试";

export function TableSyncDialog({ workspaceId, initialConnection, initialSchema = "", initialTable, onClose }: {
  workspaceId: string; initialConnection?: string; initialSchema?: string; initialTable?: string; onClose: () => void;
}) {
  const [step, setStep] = useState(0);
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [connection, setConnection] = useState(initialConnection ?? "");
  const [groups, setGroups] = useState<string[]>([]);
  const [schemas, setSchemas] = useState<string[]>(initialSchema ? [initialSchema] : []);
  const [inventory, setInventory] = useState<Record<string, string[]>>({});
  const [selected, setSelected] = useState<Record<string, string[]>>(initialSchema && initialTable ? { [initialSchema]: [initialTable] } : {});
  const [full, setFull] = useState<Record<string, boolean>>({});
  const [jobs, setJobs] = useState<Record<string, SyncJob>>({});
  const [creationErrors, setCreationErrors] = useState<Record<string, string>>({});
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const mounted = useRef(true);
  const running = Object.values(jobs).some(activeJob);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    let live = true;
    catalogApi.connections(workspaceId).then(({ items }) => { if (live) { setConnections(items); setConnection((id) => id || items[0]?.id || ""); } }).catch((e) => { if (live) setError(message(e)); });
    return () => { live = false; };
  }, [workspaceId]);
  useEffect(() => {
    if (!connection) return;
    let live = true;
    setLoading(true); setError("");
    // Choosing a connection and its schemas only needs the source's schema names;
    // tables are read per chosen schema in the next step.
    catalogApi.schemas(workspaceId, connection).then(async ({ items: value }) => {
      const histories = await Promise.all(value.map(async (schema) => ({ schema, job: (await catalogApi.syncJobs(workspaceId, connection, schema)).items[0] })));
      if (!live) return;
      setGroups(value);
      setSchemas((current) => current.filter((s) => value.includes(s)));
      const existing = histories.filter((h) => h.job);
      setJobs(Object.fromEntries(existing.map((h) => [h.schema, h.job])));
      if (existing.some((h) => activeJob(h.job))) setStep(3);
    }).catch((e) => { if (live) setError(message(e)); }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [workspaceId, connection, reload]);
  useEffect(() => {
    if (!running) return;
    let live = true;
    let fetching = false;
    const timer = window.setInterval(async () => {
      if (fetching) return;
      fetching = true;
      try {
        const updates = await Promise.all(Object.entries(jobs).filter(([, j]) => activeJob(j)).map(async ([s, j]) => [s, await catalogApi.syncJob(workspaceId, connection, j.id)] as const));
        if (!live) return;
        setJobs((current) => ({ ...current, ...Object.fromEntries(updates) }));
        if (updates.some(([, j]) => !activeJob(j))) window.dispatchEvent(new CustomEvent(METADATA_SYNCED, { detail: { workspaceId } }));
      } catch (e) { if (live) setError(message(e)); }
      finally { fetching = false; }
    }, 2000);
    return () => { live = false; window.clearInterval(timer); };
  }, [running, jobs, workspaceId, connection]);
  const loadTables = async () => {
    setBusy(true); setError("");
    try {
      const entries = await Promise.all(schemas.map(async (s) => [s, (await catalogApi.tables(workspaceId, connection, { schema_name: s })).items.map((t) => t.name)] as const));
      if (!mounted.current) return;
      const next = Object.fromEntries(entries);
      setInventory(next);
      setSelected((current) => Object.fromEntries(schemas.map((s) => [s, full[s] ? next[s] : (current[s] ?? []).filter((t) => next[s].includes(t))])));
      setStep(2);
    } catch (e) { if (mounted.current) setError(message(e)); }
    finally { if (mounted.current) setBusy(false); }
  };
  const start = async (only?: string[]) => {
    if (lock.current || running) return;
    lock.current = true; setBusy(true); setError(""); setStep(3);
    const targets = only ?? schemas;
    if (!only) { setJobs({}); setCreationErrors({}); }
    // Each schema keeps its own task, so a failed submission never repeats successful ones.
    for (const s of targets) {
      try {
        const tables = selected[s] ?? [];
        const all = full[s] || (inventory[s]?.length > 0 && tables.length === inventory[s].length);
        const job = await catalogApi.refreshAssets(workspaceId, connection, { schema_name: s }, all ? [] : tables);
        if (mounted.current) { setJobs((current) => ({ ...current, [s]: job })); setCreationErrors((current) => { const next = { ...current }; delete next[s]; return next; }); }
      } catch (e) { if (mounted.current) setCreationErrors((current) => ({ ...current, [s]: message(e) })); }
    }
    lock.current = false;
    if (mounted.current) setBusy(false);
  };
  const retry = async (schema: string, job: SyncJob) => {
    if (lock.current || running) return;
    lock.current = true; setBusy(true); setError("");
    try { const next = await catalogApi.retrySync(workspaceId, connection, job.id); if (mounted.current) setJobs((current) => ({ ...current, [schema]: next })); }
    catch (e) { if (mounted.current) setError(message(e)); }
    finally { lock.current = false; if (mounted.current) setBusy(false); }
  };
  const close = () => { window.dispatchEvent(new CustomEvent(METADATA_SYNCED, { detail: { workspaceId } })); onClose(); };
  const pickAll = (s: string, checked: boolean) => { setFull((v) => ({ ...v, [s]: checked })); setSelected((v) => ({ ...v, [s]: checked ? inventory[s] : [] })); };
  const canSubmit = schemas.length > 0 && schemas.every((s) => full[s] || selected[s]?.length > 0);
  return <Modal open title="同步数据表" width="var(--data-tables-dialog-width)" onCancel={close} footer={<div className="flex justify-end gap-2">
    <Button onClick={close}>{step === 3 ? "关闭" : "取消"}</Button>
    {step > 0 && <Button disabled={running || busy || loading} onClick={() => { setError(""); setStep(step - 1); }}>上一步</Button>}
    {step < 3 && <Button type="primary" loading={busy} disabled={loading || !!error || !connection || (step === 1 && !schemas.length) || (step === 2 && !canSubmit) || running} onClick={() => step === 1 ? void loadTables() : step === 2 ? void start() : setStep(1)}>{step === 2 ? "开始同步" : "下一步"}</Button>}
  </div>}>
    <div className="flex flex-col gap-4">
      <Steps size="small" current={step} items={[{ title: "连接" }, { title: "库" }, { title: "表" }, { title: "进度与结果" }]} />
      {error && <Alert type="error" showIcon message={error} action={<Button size="small" onClick={() => { setError(""); setReload((v) => v + 1); }}>重新加载</Button>} />}
      <div className="data-tables-step"><Spin spinning={loading}><div className="flex flex-col gap-4">
        {step === 0 && <Form layout="vertical" component="div"><Form.Item label="数据连接"><Select aria-label="同步连接" className="w-full" placeholder="选择数据连接" value={connection || undefined} options={connections.map((c) => ({ value: c.id, label: c.name }))} onChange={(id) => { setConnection(id); setGroups([]); setSchemas([]); setSelected({}); setFull({}); setInventory({}); setJobs({}); setCreationErrors({}); }} /></Form.Item><Typography.Text type="secondary">选择连接后，可一次同步多个库的数据表结构。</Typography.Text>{Object.keys(jobs).length > 0 && <div className="pt-4"><Button onClick={() => setStep(3)}>查看上次同步结果</Button></div>}</Form>}
        {step === 1 && <><SectionTitle title="选择库" note="可同时选择多个库" />{!groups.length && !loading && <Empty description="此连接没有可用库" />}{groups.map((g) => <Checkbox key={g} checked={schemas.includes(g)} onChange={(e) => setSchemas((v) => e.target.checked ? [...v, g] : v.filter((s) => s !== g))}>{g}</Checkbox>)}</>}
        {step === 2 && <>
          <div className="flex items-center gap-3"><Input.Search aria-label="搜索同步表" placeholder="搜索表名" allowClear value={search} onChange={(e) => setSearch(e.target.value)} /><Button onClick={() => schemas.forEach((s) => pickAll(s, true))}>全选全部</Button><Button onClick={() => schemas.forEach((s) => pickAll(s, false))}>清空选择</Button></div>
          <Alert type="info" showIcon message="全选库会同步整个库，并标记已消失的表；部分选择只更新所选表。" />
          {schemas.map((s) => <section key={s} className="flex flex-col gap-3 border-b border-rule pb-4"><SectionTitle title={s} note={`已选 ${selected[s]?.length ?? 0}/${inventory[s]?.length ?? 0}`} children={<Checkbox aria-label={`全选当前库 ${s}`} checked={full[s] || ((inventory[s]?.length ?? 0) > 0 && selected[s]?.length === inventory[s]?.length)} indeterminate={!full[s] && !!selected[s]?.length && selected[s].length !== inventory[s]?.length} onChange={(e) => pickAll(s, e.target.checked)}>全选当前库</Checkbox>} />
            <div className="flex flex-wrap gap-3">{(inventory[s] ?? []).filter((t) => t.toLowerCase().includes(search.toLowerCase())).map((t) => <Checkbox key={t} aria-label={`${s}.${t}`} checked={selected[s]?.includes(t) ?? false} onChange={(e) => { setFull((v) => ({ ...v, [s]: false })); setSelected((v) => ({ ...v, [s]: e.target.checked ? [...(v[s] ?? []), t] : (v[s] ?? []).filter((n) => n !== t) })); }}>{t}</Checkbox>)}</div>
            {!inventory[s]?.length && <Typography.Text type="secondary">库中没有可见表，仍可全选同步以更新消失状态。</Typography.Text>}
          </section>)}
        </>}
        {step === 3 && <>
          {running && <Typography.Text type="secondary">任务进行中，关闭弹窗后仍会继续；再次打开可查看进度。</Typography.Text>}
          {Object.entries(creationErrors).map(([s, e]) => <Alert key={s} type="error" showIcon message={`${s}：${e}`} action={<Button disabled={running || busy} onClick={() => void start([s])}>重试创建任务</Button>} />)}
          {Object.entries(jobs).map(([s, job]) => <section key={s} className="flex flex-col gap-3 border-b border-rule pb-4">
            <SectionTitle title={s} children={!activeJob(job) && job.state !== "succeeded" ? <Button size="small" loading={busy} disabled={running} onClick={() => void retry(s, job)}>重试失败批次</Button> : undefined} />
            <div className="flex flex-wrap items-center gap-3"><StatusMark state={job.state === "succeeded" ? "mapped" : activeJob(job) ? "partial" : "error"} label={labels[job.state]} /><Typography.Text type="secondary">{job.total === null ? "正在发现数据表" : `已处理 ${job.processed}/${job.total}，成功 ${job.available}，失败 ${job.failed}`} · 累计 {job.duration_ms} ms</Typography.Text></div>
            {job.error && <Alert type="warning" showIcon message={job.error} />}
            <Table size="small" rowKey="id" pagination={false} dataSource={job.batches} columns={[{ title: "批次", dataIndex: "ordinal", render: (v: number) => v + 1 }, { title: "表数", key: "tables", render: (_, b) => b.tables.length }, { title: "耗时（ms）", dataIndex: "duration_ms" }, { title: "尝试次数", dataIndex: "attempt" }, { title: "结果", key: "result", render: (_, b) => b.error || (b.state === "succeeded" ? "已完成" : b.state === "interrupted" ? "已中断" : b.state === "failed" ? "失败" : b.state === "queued" ? "等待同步" : "处理中") }]} />
            {!activeJob(job) && <Collapse items={[{ key: "tables", label: "查看每张表结果", children: <Table size="small" rowKey="table_name" pagination={{ pageSize: 20, showSizeChanger: false }} dataSource={job.batches.flatMap((b) => b.results)} columns={[{ title: "表名", dataIndex: "table_name" }, { title: "结果", key: "state", render: (_, r) => r.error || (r.state === "succeeded" ? "已登记" : r.state === "missing" ? "当前不可见或不存在" : "同步失败") }]} /> }]} />}
          </section>)}
        </>}
      </div></Spin></div>
    </div>
  </Modal>;
}
