import { PublishedTypeCatalogPage } from "./PublishedTypeCatalogPage";
import { useErrorMessage } from "../hooks/useErrorMessage";
import { Button, Empty, Input, Select, Table, Tag, Tooltip, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Box, Download, GitBranch, Plus, RefreshCw, Rocket, Search, Sigma, Upload, Zap } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, modelingApi } from "../api/client";
import type { Action, Dataset, LinkType, Metric, ObjectType, VersionSummary } from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { ActionDefinitionTag } from "../components/elements/ActionPanel";
import { ExportDialog } from "../components/ExportDialog";
import { ValueTypeCatalog } from "../components/ValueTypeCatalog";
import { ImportDialog } from "../components/ImportDialog";
import { PageBody, PageTabs, PageToolbar, Panel, StatusMark } from "../components/layout";
import { useElementDetail } from "../hooks/useElementDetail";
import { usePageActive, usePageTab } from "../hooks/usePageTab";
import { usePersonalSession } from "../hooks/usePersonalSession";
import { useSnapshot } from "../hooks/useSnapshot";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { useWorkspacePermissions } from "../hooks/useWorkspacePermissions";
import { MULTIPLICITY, byId, effectiveLinks, effectiveProperties, isA, metricDatasetId } from "../lib/coreModel";
import {
  CATALOG_RESOURCE_KINDS,
  CATALOG_TAB_COLLECTIONS,
  CATALOG_TAB_LABELS,
  type CatalogTab,
} from "../lib/elementKinds";
import { isForwardReading, renderLinkReading } from "../lib/linkReadings";
import { METRIC_KINDS } from "../lib/metricEditing";
import { objectMapping } from "../lib/objectMapping";

const { Text } = Typography;
type CatalogItem = ObjectType | LinkType | Metric | Dataset | Action;
const LABELS = CATALOG_TAB_LABELS;

/** One catalog owns entities, relationships and metrics, including session drafts. */
export function TypeCatalogPage({ kind = "object_type" }: { kind?: "object_type" | "link_type" }) {
  const [params] = useSearchParams();
  return params.get("session") || params.get("catalogTab") === "values"
    ? <DraftTypeCatalogPage kind={kind} />
    : <PublishedTypeCatalogPage initialKind={kind} />;
}

function DraftTypeCatalogPage({ kind: initialKind = "object_type" }: { kind?: "object_type" | "link_type" }) {
  const { workspace, refresh } = useWorkspaceContext();
  const { canEdit } = useWorkspacePermissions();
  const { draft, error, load, sessionId, suffix, session, setDraft, setSession } = useSnapshot(workspace);
  const [createValueType, setCreateValueType] = useState(0);
  const [params, setParams] = useSearchParams();
  const requested = params.get("catalogTab");
  const tab: CatalogTab =
    requested && requested in LABELS
      ? (requested as CatalogTab)
      : initialKind === "link_type"
        ? "relations"
        : "entities";
  const kind = tab === "values" ? "metric" : CATALOG_RESOURCE_KINDS[tab];
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState<string>();
  const [importOpen, setImportOpen] = useState(false);
  const [maxFileMb, setMaxFileMb] = useState<number>();
  const [exportOpen, setExportOpen] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [versions, setVersions] = useState<VersionSummary[]>([]);
  const [actionError, setActionError] = useState("");
  useErrorMessage(actionError);
  const detail = useElementDetail();
  const navigate = useNavigate();
  const active = usePageActive();
  const [personalRefresh, setPersonalRefresh] = useState(0);
  const personalSession = usePersonalSession(workspace.id, canEdit && active && !sessionId, personalRefresh);
  usePageTab({ title: "本体对象" });
  useEffect(() => {
    if (!importOpen || !canEdit) return;
    let live = true;
    modelingApi.capabilities(workspace.id)
      .then((result) => { if (live) setMaxFileMb(result.max_file_mb); })
      .catch(() => undefined);
    return () => { live = false; };
  }, [importOpen, workspace.id, canEdit]);
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
  const datasets = tab === "datasets";
  const actions = tab === "actions";
  const items: CatalogItem[] = tab === "values" ? [] : ((draft[CATALOG_TAB_COLLECTIONS[tab]] ?? []) as CatalogItem[]);
  const tags = [...new Set(items.flatMap((item) => "tags" in item ? item.tags : []))];
  const normalized = query.trim().toLowerCase();
  const filtered = items.filter((item) =>
    (!tag || ("tags" in item && item.tags.includes(tag))) &&
    (!normalized || [(item.display_name || item.name), "name" in item ? item.name : "", item.description, ...("synonyms" in item ? item.synonyms : []),
      ...("verbalizes" in item ? item.verbalizes : []), "source_role_name" in item ? item.source_role_name ?? "" : "", "target_role_name" in item ? item.target_role_name ?? "" : ""]
      .join(" ").toLowerCase().includes(normalized)));
  const Icon = objects ? Box : metrics ? Sigma : actions ? Zap : GitBranch;
  const dash = <Text type="secondary">—</Text>;
  const tagCell = (item: CatalogItem) => "tags" in item && item.tags.length
    ? <span className="flex flex-wrap gap-1">{item.tags.map((label) => <Tag key={label} className="m-0">{label}</Tag>)}</span>
    : dash;
  // One flat row per definition, with separate labels and stable identifiers.
  const columns: ColumnsType<CatalogItem> = [{
    title: "名称", key: "name", render: (_, item) => <span className="inline-flex items-center gap-2 whitespace-nowrap"><Link
      to={detail.href({ kind, id: item.id, tab: objects ? "properties" : "basic", sessionId })}
      className="inline-flex items-center gap-2 font-medium whitespace-nowrap"
    >
      <Icon size={14} className={objects ? "flex-none text-object" : metrics || actions ? "flex-none text-accent" : "flex-none text-relation"} />{(item.display_name || item.name)}
    </Link>{actions && <ActionDefinitionTag />}</span>,
  }];
  columns.push({ title: "英文标识", key: "identifier", render: (_, item) => <code className="text-xs whitespace-nowrap">{item.name}</code> });
  if (!objects && !metrics && !datasets && !actions) columns.push(
    { title: "关系含义", key: "reading", render: (_, item) => {
      if (!("source_type_id" in item)) return dash;
      const reading = item.verbalizes.find(isForwardReading);
      return reading ? renderLinkReading(draft, item, reading)
        : `${(byId(draft.object_types, item.source_type_id)?.display_name || byId(draft.object_types, item.source_type_id)?.name) ?? "未指定"} → ${(byId(draft.object_types, item.target_type_id)?.display_name || byId(draft.object_types, item.target_type_id)?.name) ?? "未指定"}`;
    } },
    { title: "基数", key: "multiplicity", render: (_, item) => "multiplicity" in item ? MULTIPLICITY[item.multiplicity] : dash },
  );
  if (objects) columns.push(
    { title: "继承自", key: "extends", render: (_, item) => {
      const parent = "extends" in item ? byId(draft.object_types, item.extends) : undefined;
      return parent ? <span className="whitespace-nowrap">{(parent.display_name || parent.name)}</span> : dash;
    } },
    { title: "标签", key: "tags", render: (_, item) => tagCell(item) },
    { title: "属性", key: "properties", render: (_, item) => effectiveProperties(draft, item.id).length },
    { title: "关系", key: "links", render: (_, item) => effectiveLinks(draft, item.id).length },
    // Same derivation as the detail page header, so a gap is visible without opening each entity.
    { title: "数据映射", key: "mapping", render: (_, item) => {
      const record = objectMapping(draft, item as ObjectType);
      return <StatusMark state={record.state} label={record.label} className="whitespace-nowrap" />;
    } },
    { title: "文档实例", key: "instances", render: (_, item) => draft.material_objects.filter((object) => isA(draft, object.type_id, item.id)).length },
  );
  else if (metrics) columns.push(
    { title: "类型", key: "kind", render: (_, item) => "kind" in item ? METRIC_KINDS[item.kind] : dash },
    { title: "数据集", key: "dataset", render: (_, item) => "kind" in item ? byId(draft.datasets, metricDatasetId(draft, item))?.name ?? "未指定" : dash },
  );
  else if (datasets) columns.push({ title: "来源", key: "source", render: (_, item) => "source_kind" in item && item.source_kind === "query" ? "表达式" : "数据表" }, { title: "列", key: "columns", render: (_, item) => "columns" in item ? item.columns?.length ?? "未探测" : "—" });
  else if (actions) columns.push(
    {
      title: "作用对象",
      key: "target",
      render: (_, item) => {
        if (!("parameters" in item)) return dash;
        const target = item.target_type_id ? byId(draft.object_types, item.target_type_id) : undefined;
        return target ? (
          <Link to={detail.href({ kind: "object_type", id: target.id, sessionId })} className="whitespace-nowrap">
            {target.display_name || target.name}
          </Link>
        ) : (
          <Tag className="m-0">全局动作</Tag>
        );
      },
    },
    { title: "参数", key: "parameters", render: (_, item) => ("parameters" in item ? item.parameters.length : dash) },
    { title: "效果", key: "effects", render: (_, item) => ("effects" in item ? item.effects.length : dash) },
    { title: "标签", key: "tags", render: (_, item) => tagCell(item) },
  );
  else columns.push({ title: "标签", key: "tags", render: (_, item) => tagCell(item) });
  // Auto layout keeps counts narrow; the description truncates within its own bound.
  columns.push({ title: "描述", key: "description", render: (_, item) => item.description
    ? <Tooltip title={item.description} placement="topLeft"><Text type="secondary" className="block max-w-sm truncate text-xs">{item.description}</Text></Tooltip>
    : dash });
  // Short headers stay on one line when the description column takes the remaining width.
  const table = <Table<CatalogItem> size="middle" rowKey="id" dataSource={filtered} columns={columns}
    onHeaderRow={() => ({ className: "text-xs whitespace-nowrap" })} pagination={filtered.length > 20 ? { pageSize: 20 } : false}
    locale={{ emptyText: <Empty description={items.length ? "没有匹配的定义" : canEdit ? `还没有${LABELS[tab]}定义` : "暂无已发布定义"} /> }} />;
  const counts = Object.fromEntries(
    (Object.keys(CATALOG_TAB_COLLECTIONS) as CatalogTab[]).map((key) => [
      key,
      (draft[CATALOG_TAB_COLLECTIONS[key]] ?? []).length,
    ]),
  ) as Record<CatalogTab, number>;
  const publishSession = session ?? personalSession;
  const deliverySuffix = suffix || (publishSession && publishSession.unpublished_change_count > 0 ? `?session=${publishSession.id}` : "");
  return <div className="flex h-full min-h-0 flex-col bg-canvas">
    <PageTabs title="本体对象" note={sessionId ? "建模会话草稿" : undefined} actions={<>
      <Button icon={<RefreshCw className="size-icon-sm" />} onClick={() => { load(); setPersonalRefresh((n) => n + 1); }}>刷新</Button>
      {canEdit && <>
        <Button icon={<Upload className="size-icon-sm" />} onClick={() => setImportOpen(true)}>导入</Button>
        <Button icon={<Download className="size-icon-sm" />} disabled={!workspace.version_id} loading={exporting} onClick={() => void openExport()}>导出</Button>
        {publishSession && publishSession.unpublished_change_count > 0 && (
          <Text type="secondary" className="whitespace-nowrap text-xs">{publishSession.unpublished_change_count} 项待发布</Text>
        )}
        <Link to={"../delivery" + deliverySuffix}><Button type="primary" icon={<Rocket className="size-icon-sm" />}>发布</Button></Link>
      </>}
    </>} activeKey={tab} onChange={(next) => {
          setQuery(""); setTag(undefined);
          setParams((current) => { const value = new URLSearchParams(current); value.set("catalogTab", next); return value; }, { replace: true });
        }} items={(Object.keys(LABELS) as CatalogTab[]).map((key) => ({ key, label: `${LABELS[key]} ${counts[key]}`, children: key !== tab ? null : <PageBody>
          <PageToolbar extra={<>
          {!metrics && !datasets && tab !== "values" && <Select aria-label="标签筛选" allowClear placeholder="按标签筛选" className="w-40" value={tag}
            options={tags.map((label) => ({ value: label, label }))} onChange={setTag} />}
          <Input type="search" prefix={<Search size={14} />} allowClear aria-label="搜索目录" placeholder="名称、标识或描述" className="w-60" value={query} onChange={(event) => setQuery(event.target.value)} />
          </>}>
          {canEdit && tab !== "actions" && <Button type="primary" icon={<Plus size={15} />} onClick={() => tab === "values" ? setCreateValueType((n) => n + 1) : detail.open({ kind, id: "new", mode: "edit", sessionId })}>新建{LABELS[tab]}</Button>}
          </PageToolbar>
          <Panel>{key === "values"
          ? <ValueTypeCatalog workspace={workspace} draft={draft} sessionId={sessionId} query={query} createRequest={createValueType} onSaved={(saved) => {
            setDraft(saved.draft);
            setSession?.(saved);
            if (!sessionId) {
              setParams((current) => {
                const value = new URLSearchParams(current);
                value.set("session", saved.id);
                return value;
              }, { replace: true });
            }
            void refresh?.();
          }} />
          : table}</Panel>
        </PageBody> }))} />
    {canEdit && <>
      <ImportDialog open={active && importOpen} workspaceId={workspace.id} maxFileMb={maxFileMb} onClose={() => setImportOpen(false)}
        onConfirmed={(result) => { setImportOpen(false); navigate(`../builder?session=${result.session_id}&panel=proposals`); }} />
      <ExportDialog open={active && exportOpen} workspaceId={workspace.id} versions={versions} initialVersionId={workspace.version_id ?? undefined} onClose={() => setExportOpen(false)} />
    </>}
  </div>;
}
