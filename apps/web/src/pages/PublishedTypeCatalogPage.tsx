import { Button, Empty, Input, Select, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Box, Download, GitBranch, Plus, RefreshCw, Rocket, Search, Sigma, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, modelingApi } from "../api/client";
import type { CatalogItem, CatalogPage, ResourceKind, VersionSummary } from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { ExportDialog } from "../components/ExportDialog";
import { ImportDialog } from "../components/ImportDialog";
import { PageBody, PageTabs, PageToolbar, Panel, StatusMark } from "../components/layout";
import { useElementDetail } from "../hooks/useElementDetail";
import { useErrorMessage } from "../hooks/useErrorMessage";
import { usePageActive, usePageTab } from "../hooks/usePageTab";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { MULTIPLICITY } from "../lib/coreModel";
import { isForwardReading } from "../lib/linkReadings";
import { METRIC_KINDS } from "../lib/metricEditing";

type Tab = "entities" | "values" | "relations" | "metrics" | "datasets";
const LABELS: Record<Tab, string> = { entities: "实体类型", values: "值类型", relations: "关系", metrics: "指标", datasets: "数据集" };
const KINDS: Record<Exclude<Tab, "values">, ResourceKind> = { entities: "object_type", relations: "link_type", metrics: "metric", datasets: "dataset" };
const COUNT = { entities: "object_types", values: "value_types", relations: "link_types", metrics: "metrics", datasets: "datasets" } as const;
const { Text } = Typography;

/** Published directories never acquire a complete editable definition baseline. */
export function PublishedTypeCatalogPage({ initialKind }: { initialKind: "object_type" | "link_type" }) {
  const { workspace, refresh } = useWorkspaceContext();
  const [params, setParams] = useSearchParams();
  const key = params.get("catalogTab");
  const tab: Exclude<Tab, "values"> = key === "relations" || key === "metrics" || key === "datasets" ? key : initialKind === "link_type" ? "relations" : "entities";
  const kind = KINDS[tab];
  const [versionId, setVersionId] = useState(workspace.version_id);
  const [result, setResult] = useState<CatalogPage | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState<string>();
  const [page, setPage] = useState(1);
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [attempt, setAttempt] = useState(0);
  const [importOpen, setImportOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [exporting, setExporting] = useState(false);
  const [maxFileMb, setMaxFileMb] = useState<number>();
  const [actionError, setActionError] = useState("");
  useErrorMessage(actionError);
  const detail = useElementDetail();
  const navigate = useNavigate();
  const active = usePageActive();
  usePageTab({ title: "本体对象" });
  useEffect(() => {
    if (!active || !versionId) return;
    let live = true;
    const timer = window.setTimeout(() => {
      api.catalog(workspace.id, { version_id: versionId, kind, q: query, tag, limit: 20, cursor: cursors[page - 1] })
        .then(value => { if (live) { setResult(value); setError(""); } })
        .catch((problem: Error) => { if (live) setError(problem.message); });
    }, query ? 200 : 0);
    return () => { live = false; window.clearTimeout(timer); };
  }, [active, workspace.id, versionId, kind, query, tag, page, cursors, attempt]);
  useEffect(() => {
    if (!active || !importOpen || !workspace.role) return;
    let live = true;
    modelingApi.capabilities(workspace.id).then(value => { if (live) setMaxFileMb(value.max_file_mb); }).catch(() => undefined);
    return () => { live = false; };
  }, [active, importOpen, workspace.id, workspace.role]);
  const reset = () => { setPage(1); setCursors([undefined]); };
  const reload = async () => {
    try { const current = await api.workspace(workspace.id); setVersionId(current.version_id); reset(); setAttempt(n => n + 1); refresh(); }
    catch (problem) { setActionError(problem instanceof Error ? problem.message : "读取版本失败"); }
  };
  const openExport = async () => {
    setExporting(true);
    try { const value = await api.versions(workspace.id); setVersions(value.items); setExportOpen(true); }
    catch (problem) { setActionError(problem instanceof Error ? problem.message : "读取发布版本失败"); }
    finally { setExporting(false); }
  };
  if (error) return <ErrorSurface message={error} retry={() => setAttempt(n => n + 1)} />;
  if (versionId && !result) return <LoadingSurface label="正在读取本体目录…" />;
  const items = result?.items ?? [];
  const Icon = tab === "entities" ? Box : tab === "metrics" ? Sigma : GitBranch;
  const dash = <Text type="secondary">—</Text>;
  const columns: ColumnsType<CatalogItem> = [
    { title: "名称", key: "name", render: (_, item) => <Link to={detail.href({ kind, id: item.id, tab: tab === "entities" ? "properties" : "basic", sessionId: null, versionId: versionId ?? undefined })} className="inline-flex items-center gap-2 font-medium whitespace-nowrap"><Icon size={14} className={tab === "entities" ? "flex-none text-object" : tab === "metrics" ? "flex-none text-accent" : "flex-none text-relation"} />{item.display_name || item.name}</Link> },
    { title: "英文标识", key: "identifier", render: (_, item) => <code className="text-xs whitespace-nowrap">{item.name}</code> },
  ];
  const tagCell = (item: CatalogItem) => item.tags.length ? <span className="flex flex-wrap gap-1">{item.tags.map(label => <Tag key={label} className="m-0">{label}</Tag>)}</span> : dash;
  if (tab === "entities") columns.push(
    { title: "继承自", key: "extends", render: (_, item) => item.parent ? <span className="whitespace-nowrap">{item.parent.display_name || item.parent.name}</span> : dash },
    { title: "标签", key: "tags", render: (_, item) => tagCell(item) },
    { title: "属性", key: "properties", dataIndex: "property_count" },
    { title: "关系", key: "links", dataIndex: "link_count" },
    { title: "数据映射", key: "mapping", render: (_, item) => <StatusMark state={item.mapping_state ?? "unmapped"} label={item.mapping_label ?? "未绑定数据集"} className="whitespace-nowrap" /> },
    { title: "文档实例", key: "instances", render: (_, item) => item.document_instance_count ?? dash },
  );
  else if (tab === "relations") columns.push(
    { title: "关系含义", key: "reading", render: (_, item) => {
      const source = item.source_role_name || item.source?.display_name || item.source?.name || "未指定";
      const target = item.target_role_name || item.target?.display_name || item.target?.name || "未指定";
      const reading = item.verbalizes?.find(isForwardReading);
      return reading ? reading.replaceAll("{source}", source).replaceAll("{target}", target) : `${source} → ${target}`;
    } },
    { title: "基数", key: "multiplicity", render: (_, item) => item.multiplicity ? MULTIPLICITY[item.multiplicity] : dash },
    { title: "标签", key: "tags", render: (_, item) => tagCell(item) },
  );
  else if (tab === "metrics") columns.push({ title: "类型", key: "kind", render: (_, item) => item.metric_kind ? METRIC_KINDS[item.metric_kind] : dash }, { title: "数据集", key: "dataset", render: (_, item) => item.dataset_name ?? "未指定" });
  else columns.push({ title: "来源", key: "source", render: (_, item) => item.source_kind === "query" ? "表达式" : "数据表" }, { title: "列", key: "columns", render: (_, item) => item.column_count ?? "未探测" });
  columns.push({ title: "描述", key: "description", render: (_, item) => item.description ? <Tooltip title={item.description} placement="topLeft"><Text type="secondary" className="block max-w-sm truncate text-xs">{item.description}</Text></Tooltip> : dash });
  return <div className="flex h-full min-h-0 flex-col bg-canvas">
    <PageTabs title="本体对象" actions={<>
      <Button icon={<RefreshCw className="size-icon-sm" />} onClick={() => void reload()}>刷新</Button>
      {workspace.role && <><Button icon={<Upload className="size-icon-sm" />} onClick={() => setImportOpen(true)}>导入</Button><Button icon={<Download className="size-icon-sm" />} disabled={!versionId} loading={exporting} onClick={() => void openExport()}>导出</Button><Link to="../delivery"><Button type="primary" icon={<Rocket className="size-icon-sm" />}>发布</Button></Link></>}
    </>} activeKey={tab} onChange={next => { setQuery(""); setTag(undefined); reset(); setParams(current => { const value = new URLSearchParams(current); value.set("catalogTab", next); return value; }, { replace: true }); }} items={(Object.keys(LABELS) as Tab[]).map(key => ({ key, label: `${LABELS[key]} ${result?.counts[COUNT[key]] ?? 0}`, children: key !== tab ? null : <PageBody>
      <PageToolbar extra={<>{(tab === "entities" || tab === "relations") && <Select aria-label="标签筛选" allowClear placeholder="按标签筛选" className="w-40" value={tag} options={(result?.tags ?? []).map(label => ({ value: label, label }))} onChange={value => { setTag(value); reset(); }} />}<Input type="search" prefix={<Search size={14} />} allowClear aria-label="搜索目录" placeholder="名称、标识或描述" className="w-60" value={query} onChange={event => { setQuery(event.target.value); reset(); }} /></>}>
        {workspace.role && <Button type="primary" icon={<Plus size={15} />} onClick={() => detail.open({ kind, id: "new", mode: "edit", sessionId: null })}>新建{LABELS[tab]}</Button>}
      </PageToolbar>
      <Panel><Table<CatalogItem> size="middle" rowKey="id" columns={columns} dataSource={items} onHeaderRow={() => ({ className: "text-xs whitespace-nowrap" })} pagination={(result?.total ?? 0) > 20 ? { simple: { readOnly: true }, current: page, pageSize: 20, total: result?.total, showSizeChanger: false, showQuickJumper: false, onChange: next => { if (next === page + 1 && result?.next_cursor) { setCursors(value => [...value.slice(0, page), result.next_cursor!]); setPage(next); } else if (cursors[next - 1] !== undefined || next === 1) setPage(next); } } : false} locale={{ emptyText: <Empty description={query || tag ? "没有匹配的定义" : workspace.role ? `还没有${LABELS[tab]}定义` : "暂无已发布定义"} /> }} /></Panel>
    </PageBody> }))} />
    {workspace.role && <><ImportDialog open={active && importOpen} workspaceId={workspace.id} maxFileMb={maxFileMb} onClose={() => setImportOpen(false)} onConfirmed={value => { setImportOpen(false); navigate(`../builder?session=${value.session_id}&panel=proposals`); }} /><ExportDialog open={active && exportOpen} workspaceId={workspace.id} versions={versions} initialVersionId={versionId ?? undefined} onClose={() => setExportOpen(false)} /></>}
  </div>;
}
