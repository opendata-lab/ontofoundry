import { useErrorMessage } from "../hooks/useErrorMessage";
import { Button, Empty, Input, Select, Table, Tabs, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Box, GitBranch, Plus, RefreshCw, Rocket, Search, Sigma } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, modelingApi } from "../api/client";
import type { LinkType, Metric, ObjectType, VersionSummary } from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { ExportDialog } from "../components/ExportDialog";
import { ImportDialog } from "../components/ImportDialog";
import { PageBody, PageHeader, Panel, PanelToolbar } from "../components/layout";
import { useElementInspector } from "../hooks/useElementInspector";
import { usePageActive, usePageTab } from "../hooks/usePageTab";
import { useSnapshot } from "../hooks/useSnapshot";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { MULTIPLICITY, byId, effectiveLinks, effectiveProperties, isA, mappingFor, metricDatasetId } from "../lib/coreModel";
import { METRIC_KINDS } from "../lib/metricEditing";

const { Text } = Typography;
type CatalogTab = "entities" | "relations" | "metrics";
type CatalogItem = ObjectType | LinkType | Metric;
const LABELS: Record<CatalogTab, string> = { entities: "实体", relations: "关系", metrics: "指标" };

/** One catalog owns entities, relationships and metrics, including session drafts. */
export function TypeCatalogPage({ kind: initialKind = "object_type" }: { kind?: "object_type" | "link_type" }) {
  const { workspace } = useWorkspaceContext();
  const { draft, error, load, sessionId, suffix } = useSnapshot(workspace);
  const [params, setParams] = useSearchParams();
  const requested = params.get("catalogTab");
  const tab: CatalogTab = requested === "metrics" || requested === "relations" ? requested : initialKind === "link_type" ? "relations" : "entities";
  const kind = tab === "entities" ? "object_type" : tab === "relations" ? "link_type" : "metric";
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState<string>();
  const [importOpen, setImportOpen] = useState(false);
  const [maxFileMb, setMaxFileMb] = useState<number>();
  const [exportOpen, setExportOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [actionError, setActionError] = useState("");
  useErrorMessage(actionError);
  const inspector = useElementInspector();
  const navigate = useNavigate();
  const active = usePageActive();
  usePageTab({ title: "本体对象" });
  useEffect(() => {
    if (!importOpen || !workspace.role) return;
    let live = true;
    modelingApi.capabilities(workspace.id)
      .then((result) => { if (live) setMaxFileMb(result.max_file_mb); })
      .catch(() => undefined);
    return () => { live = false; };
  }, [importOpen, workspace.id, workspace.role]);
  const openExport = async () => {
    setExporting(true);
    setActionError("");
    try {
      const result = await api.versions(workspace.id);
      setVersions(result.items);
      setExportOpen(true);
    } catch (problem) {
      setActionError(problem instanceof Error ? problem.message : "读取发布版本失败");
    } finally { setExporting(false); }
  };
  if (error) return <ErrorSurface message={error} retry={load} />;
  if (!draft) return <LoadingSurface label="正在读取本体目录…" />;
  const objects = tab === "entities";
  const metrics = tab === "metrics";
  const items: CatalogItem[] = objects ? draft.object_types : metrics ? draft.metrics : draft.link_types;
  const tags = [...new Set(items.flatMap((item) => "tags" in item ? item.tags : []))];
  const normalized = query.trim().toLowerCase();
  const filtered = items.filter((item) =>
    (!tag || ("tags" in item && item.tags.includes(tag))) &&
    (!normalized || [item.name, "technical_name" in item ? item.technical_name : "", item.description, ...item.synonyms,
      ...("verbalizes" in item ? item.verbalizes : []), "source_role_name" in item ? item.source_role_name ?? "" : "", "target_role_name" in item ? item.target_role_name ?? "" : ""]
      .join(" ").toLowerCase().includes(normalized)));
  const Icon = objects ? Box : metrics ? Sigma : GitBranch;
  const columns: ColumnsType<CatalogItem> = [{
    title: LABELS[tab], key: "name", render: (_, item) => <div className="flex flex-col gap-1">
      <Link
        to={inspector.href({ kind, id: item.id, tab: objects ? "properties" : "basic", sessionId })}
        className="inline-flex items-center gap-2 self-start font-medium"
      >
        <Icon size={14} className={objects ? "flex-none text-object" : metrics ? "flex-none text-accent" : "flex-none text-relation"} />{item.name}
      </Link>
      {"technical_name" in item && <code className="text-xs text-muted">{item.technical_name}</code>}
      {item.description && <Text type="secondary" className="max-w-md truncate text-xs" title={item.description}>{item.description}</Text>}
    </div>,
  }];
  if (objects) columns.push(
    { title: "属性", key: "properties", render: (_, item) => effectiveProperties(draft, item.id).length },
    { title: "关系", key: "links", render: (_, item) => effectiveLinks(draft, item.id).length },
    { title: "映射", key: "mappings", render: (_, item) => mappingFor(draft, item.id) ? 1 : 0 },
    { title: "文档实例", key: "instances", render: (_, item) => draft.material_objects.filter((object) => isA(draft, object.type_id, item.id)).length },
  );
  else if (metrics) columns.push(
    { title: "类型", key: "kind", render: (_, item) => "kind" in item ? METRIC_KINDS[item.kind] : "—" },
    { title: "数据集", key: "dataset", render: (_, item) => "kind" in item ? byId(draft.datasets, metricDatasetId(draft, item))?.name ?? "未指定" : "—" },
  );
  else columns.push({ title: "关系端点", key: "endpoints", render: (_, item) => "source_type_id" in item ? <span className="flex flex-wrap items-center gap-1">
    <Tag className="m-0">{byId(draft.object_types, item.source_type_id)?.name ?? "未指定"}</Tag><Text type="secondary">→</Text>
    <Tag className="m-0">{byId(draft.object_types, item.target_type_id)?.name ?? "未指定"}</Tag><Text type="secondary" className="text-xs">{MULTIPLICITY[item.multiplicity]}</Text>
  </span> : null });
  if (!metrics) columns.push({ title: "标签", key: "tags", render: (_, item) => {
    const parent = "extends" in item ? byId(draft.object_types, item.extends) : undefined;
    const labels = "tags" in item ? item.tags : [];
    return parent || labels.length ? <div className="flex flex-wrap gap-1">
      {parent && <Tag className="m-0">继承 {parent.name}</Tag>}{labels.map((label) => <Tag key={label} className="m-0">{label}</Tag>)}
    </div> : <Text type="secondary">—</Text>;
  } });
  const table = <Table<CatalogItem> size="middle" rowKey="id" dataSource={filtered} columns={columns}
    onHeaderRow={() => ({ className: "text-xs" })} pagination={filtered.length > 20 ? { pageSize: 20 } : false}
    locale={{ emptyText: <Empty description={items.length ? "没有匹配的定义" : workspace.role ? `还没有${LABELS[tab]}定义` : "暂无已发布定义"} /> }} />;
  const counts = { entities: draft.object_types.length, relations: draft.link_types.length, metrics: draft.metrics.length };
  return <div className="flex h-full min-h-0 flex-col bg-canvas">
    <PageHeader title="本体对象" note={sessionId ? "建模会话草稿" : undefined}>
      <Button icon={<RefreshCw size={13} />} onClick={load}>刷新</Button>
      {workspace.role && <>
        <Button onClick={() => setImportOpen(true)}>导入</Button>
        <Button disabled={!workspace.version_id} loading={exporting} onClick={() => void openExport()}>导出</Button>
        <Link to={"../delivery" + suffix}><Button type="primary" icon={<Rocket size={14} />}>发布</Button></Link>
      </>}
    </PageHeader>
    {workspace.role && <>
      <ImportDialog open={active && importOpen} workspaceId={workspace.id} maxFileMb={maxFileMb} onClose={() => setImportOpen(false)}
        onConfirmed={(result) => { setImportOpen(false); navigate(`../builder?session=${result.session_id}&panel=proposals`); }} />
      <ExportDialog open={active && exportOpen} workspaceId={workspace.id} versions={versions} initialVersionId={workspace.version_id ?? undefined} onClose={() => setExportOpen(false)} />
    </>}
    <PageBody>
      <Panel>
        <Tabs activeKey={tab} onChange={(next) => {
          setQuery(""); setTag(undefined);
          setParams((current) => { const value = new URLSearchParams(current); value.set("catalogTab", next); return value; }, { replace: true });
        }} renderTabBar={(props, DefaultTabBar) => <PanelToolbar tabBar={<DefaultTabBar {...props} />} extra={<>
          {!metrics && <Select size="small" aria-label="标签筛选" allowClear placeholder="按标签筛选" className="w-40" value={tag}
            options={tags.map((label) => ({ value: label, label }))} onChange={setTag} />}
          <Input size="small" type="search" prefix={<Search size={14} />} allowClear aria-label="搜索目录" placeholder="名称、标识或描述" className="w-60" value={query} onChange={(event) => setQuery(event.target.value)} />
          {workspace.role && <Button size="small" icon={<Plus size={15} />} onClick={() => inspector.open({ kind, id: "new", mode: "edit", sessionId })}>新建{LABELS[tab]}</Button>}
        </>} />} items={(Object.keys(LABELS) as CatalogTab[]).map((key) => ({ key, label: `${LABELS[key]} ${counts[key]}`, children: key === tab ? table : null }))} />
      </Panel>
    </PageBody>
  </div>;
}
