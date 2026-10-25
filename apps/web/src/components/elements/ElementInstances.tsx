import { Alert, Button, Checkbox, DatePicker, Descriptions, Empty, Input, Popover, Select, Table, Tag, Typography } from "antd";
import { DetailWorkbench, PanelToolbar, SectionTitle } from "../layout";
import dayjs from "dayjs";
import { ArrowRight, Settings2 } from "lucide-react";
import { useLayoutEffect, useMemo, useState } from "react";
import { api, catalogApi, instancesApi } from "../../api/client";
import type { Draft, InstanceList, InstanceNeighborhood, LinkType, MaterialObject, ObjectType, Scalar, TypedKey } from "../../api/types";
import { bindingMode, byId, effectiveProperties, effectiveSources, isA, linkDisplayName, mappingFor, titleProperty } from "../../lib/coreModel";
import type { PanelProps } from "../../lib/elementModel";
import { documentDisplayText, documentSearchText } from "../../lib/instanceDisplay";
import { ensureMapping } from "../../lib/objectMappingEditing";
import { EvidenceSection } from "./ElementPanels";

const { Text } = Typography;
const PAGE_SIZE = 8;
type SourceFilter = "document" | "database";
type Row = {
  id: string;
  ref?: string;
  source: "document" | "database";
  type_id: string;
  display_text: string;
  values: Record<string, Scalar>;
  key?: TypedKey;
  fact?: MaterialObject;
};
type Related = { id: string; label: string; other: string; typeName: string };
type DatabasePage = {
  requestKey: string;
  rows: Row[];
  hasMore: boolean;
  nextCursor?: string | null;
  dates: InstanceList["snapshot_dates"];
  truncated: boolean;
};
const rowKey = (row: Row) => `${row.source}:${row.id}`;
const sourceName = (source: Row["source"]) => source === "document" ? "文档" : "数据库";
const shown = (value: Scalar | undefined) => value === null || value === undefined || value === ""
  ? <Text type="secondary">—</Text>
  : typeof value === "boolean" ? value ? "是" : "否" : String(value);

function InstanceDetail({ draft, row, related, busy, error, snapshotDate, onClose }: {
  draft: Draft;
  row: Row;
  related: Related[] | null;
  busy: boolean;
  error: string;
  snapshotDate: string | null;
  onClose: () => void;
}) {
  const type = byId(draft.object_types, row.type_id);
  const properties = effectiveProperties(draft, row.type_id).map((p) => p.definition);
  const groups = new Map<string, Related[]>();
  for (const item of related ?? []) groups.set(item.label, [...(groups.get(item.label) ?? []), item]);
  const datasets = [...new Set(effectiveSources(draft, row.type_id).map((s) => s.dataset?.name).filter(Boolean))];
  return (
    <section aria-label={`${row.display_text}的实例详情`} className="flex min-w-0 flex-col gap-4">
      <SectionTitle title={row.display_text || "未命名实例"}>
        <Button size="small" type="text" onClick={onClose}>收起</Button>
      </SectionTitle>
      {type && <Tag className="m-0 self-start">{(type.display_name || type.name)}</Tag>}
      <section className="flex flex-col gap-3">
        <SectionTitle title="基本属性" />
        <Descriptions size="small" column={1} items={properties.map((p) => ({ key: p.id, label: (p.display_name || p.name), children: shown(row.values[p.name]) }))} />
      </section>
      <section className="flex flex-col gap-3 border-t border-rule pt-4">
        <SectionTitle title="关联实例" />
        {busy && <Text type="secondary">正在读取关联实例…</Text>}
        {error && <Alert type="error" showIcon message={error} />}
        {!busy && !error && related && !related.length && <Text type="secondary">没有关联实例</Text>}
        {[...groups].map(([label, items]) => (
          <div key={label} className="flex min-w-0 flex-col gap-2">
            <SectionTitle title={label} note={`${items.length} 条`} />
            <Table<Related> size="small" rowKey="id" pagination={false} dataSource={items} columns={[
              { title: "关联实例", dataIndex: "other" },
              { title: "对象类型", dataIndex: "typeName" },
            ]} />
          </div>
        ))}
      </section>
      <section className="flex flex-col gap-3 border-t border-rule pt-4">
        <SectionTitle title="来源信息" />
        <Descriptions size="small" column={1} items={[
          { key: "source", label: "来源", children: sourceName(row.source) },
          ...(row.source === "database" ? [
            { key: "dataset", label: "数据集", children: datasets.join("、") || "未配置来源" },
            ...(snapshotDate ? [{ key: "date", label: "数据日期", children: snapshotDate }] : []),
          ] : []),
        ]} />
        {row.fact && <EvidenceSection workspaceId={draft.workspace_id} evidence={row.fact.evidence} />}
      </section>
    </section>
  );
}

function linkLabel(link: LinkType | undefined, outgoing: boolean) {
  if (!link) return "关系";
  return linkDisplayName(link, outgoing);
}

function ObjectInstances({ draft, type, canEdit, sessionId, canBrowseDatabase, initialObjectId, versionId, active = true }: PanelProps<ObjectType> & {
  canBrowseDatabase: boolean;
  initialObjectId?: string;
  active?: boolean;
}) {
  const mode = bindingMode(draft, type.id);
  const databaseReady = canBrowseDatabase && (sessionId
    ? mode === "independent" || mode === "shared_parent"
    : !canEdit && !draft.mappings.length ? true : mode !== "unbound");
  const facts = draft.material_objects.filter((o) => isA(draft, o.type_id, type.id));
  const [sourceChoice, setSource] = useState<SourceFilter>(() => !initialObjectId && databaseReady && !facts.length ? "database" : "document");
  const source = databaseReady ? sourceChoice : "document";
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [databasePage, setDatabasePage] = useState<DatabasePage | null>(null);
  const [databaseError, setDatabaseError] = useState<{ requestKey: string; message: string } | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<Row | null>(() => {
    const fact = facts.find((o) => o.id === initialObjectId);
    return fact ? factRow(draft, fact) : null;
  });
  const [neighborhood, setNeighborhood] = useState<InstanceNeighborhood | null>(null);
  const [detailBusy, setDetailBusy] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [snapshotDate, setSnapshotDate] = useState<string | null>(null);
  const allProperties = effectiveProperties(draft, type.id).map((p) => p.definition).filter((p) => !p.identifier);
  const [visiblePropertyIds, setVisiblePropertyIds] = useState<string[]>(() => allProperties.filter((p) => p.id !== titleProperty(draft, type.id)?.id).slice(0, 4).map((p) => p.id));
  const properties = allProperties.filter((p) => visiblePropertyIds.includes(p.id));
  const mapping = useMemo(() => mappingFor(draft, type.id) ?? ensureMapping(draft, type.id), [draft, type.id]);
  const documentRows = facts
    .filter((o) => !query || documentSearchText(draft, o).includes(query.toLowerCase()))
    .map((o) => factRow(draft, o));
  const pageStart = page * PAGE_SIZE;
  const needDatabase = source === "database" && databaseReady;
  const cursor = cursors[page];
  const requestKey = JSON.stringify([type.id, source, query, page, snapshotDate, sessionId]);
  const result = databasePage?.requestKey === requestKey ? databasePage : null;
  const error = databaseError?.requestKey === requestKey ? databaseError.message : "";
  const busy = needDatabase && !result && !error;
  const snapshotDates = result?.dates ?? [];
  const snapshotted = draft.object_types.some((o) => isA(draft, o.id, type.id) &&
    effectiveSources(draft, o.id).some((s) => s.dataset?.snapshot_date_column)) || snapshotDates.some((s) => s.date);
  const clearSelection = () => {
    setSelected(null);
    setNeighborhood(null);
    setDetailError("");
    setDetailBusy(false);
  };
  const resetPage = () => {
    setPage(0);
    setCursors([undefined]);
    setDatabasePage(null);
    setDatabaseError(null);
    clearSelection();
  };
  // Invalidate at commit so hidden panels cannot accept a settled request.
  useLayoutEffect(() => {
    if (!active || !needDatabase) return;
    let live = true;
    setDatabasePage(null);
    setDatabaseError(null);
    const timer = window.setTimeout(async () => {
      try {
        let next: DatabasePage;
        if (sessionId) {
          const data = await catalogApi.mappingPreview(draft.workspace_id, {
            mapping, session_id: sessionId, q: query, offset: pageStart, limit: PAGE_SIZE,
            ...(snapshotDate ? { snapshot_date: snapshotDate } : {}),
          });
          next = {
            requestKey,
            rows: data.items.map((item) => ({ id: item.__ref, ref: item.__ref, source: "database", type_id: item.__type_id, display_text: item.display_text, values: item.values, key: item.__key })),
            hasMore: data.has_more, dates: data.snapshot_dates, truncated: false,
          };
        } else {
          const data = await instancesApi.list(draft.workspace_id, {
            type_id: type.id, source: "database", q: query, limit: PAGE_SIZE,
            ...(versionId ? { version_id: versionId } : {}),
            ...(cursor ? { cursor } : {}), ...(snapshotDate ? { snapshot_date: snapshotDate } : {}),
          });
          next = {
            requestKey,
            rows: data.items.map((item) => ({ id: item.ref, ref: item.ref, source: "database", type_id: item.type_id, display_text: item.display_text, values: item.values, key: item.source === "database" ? item.key : undefined })),
            hasMore: Boolean(data.next_cursor), nextCursor: data.next_cursor, dates: data.snapshot_dates, truncated: data.truncated,
          };
        }
        if (live) setDatabasePage(next);
      } catch (e) {
        if (live) setDatabaseError({ requestKey, message: e instanceof Error ? e.message : "读取数据库实例失败" });
      }
    }, 250);
    return () => { live = false; window.clearTimeout(timer); };
  }, [active, needDatabase, requestKey, mapping, draft.workspace_id, type.id, sessionId, query, pageStart, snapshotDate, cursor, refresh, versionId]);
  const rows = source === "document" ? documentRows.slice(pageStart, pageStart + PAGE_SIZE) : result?.rows ?? [];
  const hasNext = source === "document" ? documentRows.length > pageStart + PAGE_SIZE : Boolean(result?.hasMore);
  const movePage = (next: number) => {
    if (next > page && !sessionId && source === "database" && result?.nextCursor) {
      setCursors((prev) => {
        const updated = prev.slice(0, page + 1);
        updated[next] = result.nextCursor ?? undefined;
        return updated;
      });
    }
    clearSelection();
    setPage(next);
  };
  const select = (row: Row) => {
    if (!active) return;
    setSelected(row);
  };
  useLayoutEffect(() => {
    setNeighborhood(null);
    setDetailError("");
    setDetailBusy(false);
    if (!active || !selected || selected.fact) return;
    let live = true;
    setDetailBusy(true);
    const load = async () => {
      try {
        const data = sessionId
          ? selected.key ? await instancesApi.draftNeighborhood(draft.workspace_id, {
              type_id: selected.type_id, key: selected.key, session_id: sessionId, depth: 1,
              ...(snapshotDate ? { snapshot_date: snapshotDate } : {}),
            }) : null
          : await instancesApi.neighborhood(draft.workspace_id, selected.ref ?? selected.id, {
              depth: 1, ...(versionId ? { version_id: versionId } : {}), ...(snapshotDate ? { snapshot_date: snapshotDate } : {}),
            });
        if (live) setNeighborhood(data);
      } catch (e) {
        if (live) setDetailError(e instanceof Error ? e.message : "读取关联实例失败");
      } finally {
        if (live) setDetailBusy(false);
      }
    };
    void load();
    return () => { live = false; };
  }, [active, selected, draft.workspace_id, sessionId, snapshotDate, versionId]);
  const related: Related[] | null = selected?.fact
    ? draft.material_links.filter((l) => l.source_id === selected.id || l.target_id === selected.id).map((l) => {
        const outgoing = l.source_id === selected.id;
        const other = byId(draft.material_objects, outgoing ? l.target_id : l.source_id);
        return { id: l.id, label: linkLabel(byId(draft.link_types, l.type_id), outgoing), other: other ? documentDisplayText(draft, other) : "?", typeName: (byId(draft.object_types, other?.type_id)?.display_name || byId(draft.object_types, other?.type_id)?.name) ?? "" };
      })
    : selected && neighborhood
      ? neighborhood.links.filter((l) => l.source_id === neighborhood.center_id || l.target_id === neighborhood.center_id).map((l) => {
          const outgoing = l.source_id === neighborhood.center_id;
          const other = neighborhood.objects.find((o) => o.id === (outgoing ? l.target_id : l.source_id));
          return { id: l.id, label: linkLabel(byId(draft.link_types, l.type_id), outgoing), other: other?.display_text ?? "?", typeName: (byId(draft.object_types, other?.type_id)?.display_name || byId(draft.object_types, other?.type_id)?.name) ?? "" };
        }) : null;
  const showTypeColumn = facts.some((f) => f.type_id !== type.id) || rows.some((r) => r.type_id !== type.id) || mode === "virtual";
  const columns = [
    { title: "实例", key: "display", ellipsis: true, render: (_: unknown, row: Row) => (
      <Button type="link" size="small" className="h-auto p-0" onClick={(e) => { e.stopPropagation(); void select(row); }}>{row.display_text}</Button>
    ) },
    ...(showTypeColumn ? [{ title: "类型", key: "type", ellipsis: true, render: (_: unknown, row: Row) => (byId(draft.object_types, row.type_id)?.display_name || byId(draft.object_types, row.type_id)?.name) }] : []),
    ...properties.map((p) => ({ title: (p.display_name || p.name), key: p.id, ellipsis: true, render: (_: unknown, row: Row) => shown(row.values[p.name]) })),
  ];
  const dates = [...new Set(snapshotDates.map((s) => s.date).filter(Boolean))];
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <PanelToolbar inset={false} className="inspector-toolbar" extra={
        <Popover trigger="click" title="显示业务属性" content={
          <Checkbox.Group value={visiblePropertyIds} onChange={(ids) => setVisiblePropertyIds(ids as string[])}>
            <div className="flex flex-col gap-2">{allProperties.map((p) => <Checkbox key={p.id} value={p.id}>{(p.display_name || p.name)}</Checkbox>)}</div>
          </Checkbox.Group>
        }>
          <Button size="small" icon={<Settings2 size={14} />} disabled={!allProperties.length}>列设置</Button>
        </Popover>
      }>
        <div className="inspector-toolbar-controls">
          <Input.Search size="small" allowClear aria-label="搜索实例" placeholder="搜索显示名称或属性值" className="inspector-search w-inspector-search" value={query} onChange={(e) => { setQuery(e.target.value); resetPage(); }} />
          <Select size="small" aria-label="筛选实例来源" className="inspector-filter min-w-inspector-filter" value={source} onChange={(value: SourceFilter) => { setSource(value); resetPage(); }} options={[
            { value: "document", label: "来源：文档" }, { value: "database", label: "来源：数据库", disabled: !databaseReady },
          ]} />
          {needDatabase && snapshotted && <DatePicker size="small" aria-label="数据库数据日期" placeholder="数据库：最新日期" value={snapshotDate ? dayjs(snapshotDate) : null} onChange={(date) => { setSnapshotDate(date ? date.format("YYYY-MM-DD") : null); resetPage(); }} />}
        </div>
      </PanelToolbar>
      {needDatabase && snapshotted && <Text type="secondary" className="text-xs">日期仅筛选数据库实例{dates.length ? ` · 当前数据日期：${dates.join("、")}` : ""}</Text>}
      {error && <Alert type="error" showIcon message={`数据库实例读取失败：${error}`} action={<Button size="small" onClick={() => setRefresh((value) => value + 1)}>重试</Button>} />}
      {result?.truncated && <Alert type="warning" showIcon message="数据库结果已达到浏览上限，请缩小搜索范围。" />}
      <DetailWorkbench variant="preview" detailLabel="选中实例详情" primary={
        <>
          <Table<Row>
            className="inspector-instance-table"
            size="small"
            rowKey={rowKey}
            loading={busy}
            dataSource={rows}
            columns={columns}
            scroll={{ x: true }}
            pagination={false}
            onRow={(row) => ({ onClick: () => void select(row), className: selected && rowKey(row) === rowKey(selected) ? "inspector-selection-row cursor-pointer" : "cursor-pointer" })}
            locale={{ emptyText: <Empty description={busy ? "正在读取实例…" : error ? "数据库读取失败，请重试" : "没有匹配的实例"} /> }}
          />
          <div className="flex flex-wrap items-center justify-end gap-2">
            <Button size="small" disabled={page === 0 || busy} onClick={() => movePage(page - 1)}>上一页</Button>
            <Text type="secondary" className="text-xs">第 {page + 1} 页</Text>
            <Button size="small" disabled={!hasNext || busy} onClick={() => movePage(page + 1)}>下一页</Button>
          </div>
        </>
      } detail={selected ? <InstanceDetail draft={draft} row={selected} related={related} busy={detailBusy} error={detailError} snapshotDate={snapshotDate ?? (dates.join("、") || null)} onClose={clearSelection} /> : undefined} />
    </div>
  );
}

function factRow(draft: Draft, fact: MaterialObject): Row {
  return { id: fact.id, source: "document", type_id: fact.type_id, display_text: documentDisplayText(draft, fact), values: fact.values, fact };
}

function LinkInstances({ draft, type, open }: PanelProps<LinkType>) {
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const facts = draft.material_links.filter((l) => l.type_id === type.id);
  const name = (id: string) => {
    const fact = byId(draft.material_objects, id);
    return fact ? documentDisplayText(draft, fact) : "?";
  };
  const rows = facts.filter((fact) => `${name(fact.source_id)} ${name(fact.target_id)}`.toLowerCase().includes(query.trim().toLowerCase()));
  const selected = rows.find((fact) => fact.id === selectedId);
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <PanelToolbar inset={false} className="inspector-toolbar">
        <Input.Search className="inspector-search w-inspector-search" size="small" allowClear aria-label="搜索关系实例" placeholder="搜索来源或目标实例" value={query} onChange={(e) => { setQuery(e.target.value); setSelectedId(null); }} />
      </PanelToolbar>
      <DetailWorkbench variant="preview" detailLabel="选中关系实例详情" primary={
        <Table
          size="small"
          rowKey="id"
          dataSource={rows}
          pagination={rows.length > PAGE_SIZE ? { pageSize: PAGE_SIZE, size: "small", onChange: () => setSelectedId(null) } : false}
          onRow={(row) => ({ onClick: () => setSelectedId(row.id), className: row.id === selectedId ? "inspector-selection-row cursor-pointer" : "cursor-pointer" })}
          locale={{ emptyText: <Empty description={query ? "没有匹配的关系实例" : "没有文档中的关系实例"} /> }}
          columns={[
            { title: type.source_role_name || "来源实例", key: "source", render: (_, row) => name(row.source_id) },
            { title: type.target_role_name || "目标实例", key: "target", render: (_, row) => name(row.target_id) },
            { title: "来源", key: "origin", render: () => "文档" },
          ]}
        />
      } detail={selected ? (
        <>
          <SectionTitle title={(type.display_name || type.name)}><Button size="small" type="text" onClick={() => setSelectedId(null)}>收起</Button></SectionTitle>
          <SectionTitle title="关联实例" />
          <Descriptions size="small" column={1} items={[
            { key: "source", label: type.source_role_name || "来源实例", children: name(selected.source_id) },
            { key: "target", label: type.target_role_name || "目标实例", children: name(selected.target_id) },
            { key: "origin", label: "来源", children: "文档" },
          ]} />
          <EvidenceSection workspaceId={draft.workspace_id} evidence={selected.evidence} />
        </>
      ) : undefined} />
      <Button type="link" className="self-start" icon={<ArrowRight size={14} />} iconPosition="end" onClick={() => open({ kind: "object_type", id: type.source_type_id, tab: "instances" })}>
        查看来源对象的数据库实例
      </Button>
    </div>
  );
}

function ScopedElementInstances(
  props: PanelProps & { canBrowseDatabase: boolean; initialObjectId?: string; active?: boolean; readScope?: string },
) {
  const { type, draft, versionId, partialRead, active = true } = props;
  const [documents, setDocuments] = useState<Pick<Draft, "material_objects" | "material_links"> | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useLayoutEffect(() => {
    if (!active || !partialRead || !versionId || documents) return;
    let live = true;
    api.elementDocuments(draft.workspace_id, "derived_by" in type ? "object_type" : "link_type", type.id, versionId)
      .then(value => { if (live) { setDocuments({ material_objects: value.material_objects, material_links: value.material_links }); setError(""); } })
      .catch((problem: Error) => { if (live) setError(problem.message); });
    return () => { live = false; };
  }, [active, partialRead, versionId, type, draft.workspace_id, documents, attempt]);
  if (partialRead && !documents) return error
    ? <Alert type="error" showIcon message={error} action={<Button size="small" onClick={() => setAttempt(n => n + 1)}>重试</Button>} />
    : <Text type="secondary">正在读取实例…</Text>;
  const scoped = documents ? { ...props, draft: { ...draft, ...documents } } : props;
  return "derived_by" in type ? (
    <ObjectInstances key={JSON.stringify([draft.workspace_id, type.id, props.readScope])} {...(scoped as PanelProps<ObjectType> & typeof props)} />
  ) : (
    <LinkInstances key={JSON.stringify([draft.workspace_id, type.id, props.readScope])} {...(scoped as PanelProps<LinkType>)} />
  );
}


export function ElementInstances(props: PanelProps & { canBrowseDatabase: boolean; initialObjectId?: string; active?: boolean; readScope?: string }) {
  return <ScopedElementInstances key={JSON.stringify([props.draft.workspace_id, props.type.id, props.versionId, props.partialRead, props.readScope])} {...props} />;
}
