import { useErrorMessage } from "../hooks/useErrorMessage";
import { Alert, Breadcrumb, Button, DatePicker, Descriptions, Empty, Input, Select, Table, Tag, Typography } from "antd";
import dayjs from "dayjs";
import { FileText, Network } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { catalogApi, instancesApi } from "../api/client";
import type { Draft, InstanceList, InstanceNeighborhood, MappingPreview, Scalar, TypedKey } from "../api/types";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { PageBody, PageHeader, Panel, PanelToolbar, SectionTitle } from "../components/layout";
import { EvidenceSection } from "../components/elements/ElementPanels";
import { OntologyGraph } from "../components/OntologyGraph";
import { useElementDetail } from "../hooks/useElementDetail";
import { usePageTab } from "../hooks/usePageTab";
import { useSnapshot } from "../hooks/useSnapshot";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { bindingMode, byId, effectiveProperties, effectiveSources, isA, linkDisplayName, mappingFor } from "../lib/coreModel";
import { documentDisplayText, documentSearchText } from "../lib/instanceDisplay";
import { instanceCanvas, instanceNeighborhood, type InstanceEdge, type InstanceNode } from "../lib/instanceGraph";
import { ensureMapping } from "../lib/objectMappingEditing";

const { Text } = Typography;
const PAGE_SIZE = 20;

type Shown = InstanceNode & {
  ref?: string;
  values: Record<string, Scalar>;
  key?: TypedKey;
  source?: "document" | "database";
  evidence?: Draft["material_objects"][number]["evidence"];
};

const cell = (value: Scalar | undefined) =>
  value === null || value === undefined || value === "" ? (
    <Text type="secondary">—</Text>
  ) : typeof value === "boolean" ? (
    value ? (
      "是"
    ) : (
      "否"
    )
  ) : (
    String(value)
  );

export function InstancesPage() {
  const { workspace } = useWorkspaceContext();
  const { typeId = "", objectId } = useParams();
  const navigate = useNavigate();
  const detail = useElementDetail();
  const [params, setParams] = useSearchParams();
  const sessionId = params.get("session");
  const keyParam = params.get("key");
  const refParam =
    params.get("ref") ??
    (objectId && objectId !== "database" && (params.get("source") === "database" || objectId.startsWith("db.")) ? objectId : null);
  const databaseDetail = (objectId === "database" && (keyParam !== null || refParam !== null)) || Boolean(refParam);
  const snapshotDate = params.get("date");
  const { draft, error, load, suffix } = useSnapshot(workspace);
  const [source, setSource] = useState<"document" | "database">(params.get("source") === "database" ? "database" : "document");
  const [depth, setDepth] = useState(1);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [preview, setPreview] = useState<MappingPreview | null>(null);
  const [list, setList] = useState<InstanceList | null>(null);
  const [neighborhood, setNeighborhood] = useState<InstanceNeighborhood | null>(null);
  const [dbError, setDbError] = useState("");
  useErrorMessage(dbError);
  const [loading, setLoading] = useState(false);
  const [graphOpen, setGraphOpen] = useState(false);
  const key = useMemo(() => {
    try {
      return keyParam ? (JSON.parse(keyParam) as TypedKey) : null;
    } catch {
      return null;
    }
  }, [keyParam]);
  const mode = draft ? bindingMode(draft, typeId) : "unbound";
  const databaseReady =
    Boolean(draft) &&
    (sessionId
      ? mode === "independent" || mode === "shared_parent"
      : !workspace.role && !draft!.mappings.length
        ? true
        : mode !== "unbound");
  const mapping = useMemo(
    () => (draft && sessionId && databaseReady ? (mappingFor(draft, typeId) ?? ensureMapping(draft, typeId)) : null),
    [draft, sessionId, typeId, databaseReady],
  );
  const cursor = cursors[page];
  const resetPage = () => {
    setPage(0);
    setCursors([undefined]);
  };
  useEffect(() => {
    setDepth(1);
    setGraphOpen(false);
  }, [typeId, objectId, keyParam, refParam]);
  useEffect(() => {
    setNeighborhood(null);
    if (!databaseDetail) return;
    if (sessionId ? !key : !refParam && !key) return;
    let active = true;
    setLoading(true);
    setDbError("");
    const request =
      !sessionId && refParam
        ? instancesApi.neighborhood(workspace.id, refParam, {
            depth,
            ...(snapshotDate ? { snapshot_date: snapshotDate } : {}),
          })
        : instancesApi.draftNeighborhood(workspace.id, {
            type_id: typeId,
            key: key!,
            ...(sessionId ? { session_id: sessionId } : {}),
            depth,
            ...(snapshotDate ? { snapshot_date: snapshotDate } : {}),
          });
    request
      .then((r) => active && setNeighborhood(r))
      .catch((e: Error) => active && setDbError(e.message))
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [workspace.id, typeId, databaseDetail, key, refParam, sessionId, depth, snapshotDate]);
  useEffect(() => {
    if (objectId || source !== "database" || !databaseReady) return;
    if (sessionId && !mapping) return;
    let active = true;
    setLoading(true);
    setDbError("");
    const timer = setTimeout(() => {
      if (sessionId && mapping) {
        catalogApi
          .mappingPreview(workspace.id, {
            mapping,
            session_id: sessionId,
            q: query,
            offset: page * PAGE_SIZE,
            limit: PAGE_SIZE,
            ...(snapshotDate ? { snapshot_date: snapshotDate } : {}),
          })
          .then((r) => active && setPreview(r))
          .catch((e: Error) => active && setDbError(e.message))
          .finally(() => active && setLoading(false));
      } else {
        instancesApi
          .list(workspace.id, {
            type_id: typeId,
            source: "database",
            q: query,
            ...(cursor ? { cursor } : {}),
            limit: PAGE_SIZE,
            ...(snapshotDate ? { snapshot_date: snapshotDate } : {}),
          })
          .then((r) => active && setList(r))
          .catch((e: Error) => active && setDbError(e.message))
          .finally(() => active && setLoading(false));
      }
    }, 250);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [mapping, databaseReady, source, query, page, cursor, workspace.id, typeId, objectId, sessionId, snapshotDate]);
  const type = draft ? byId(draft.object_types, typeId) : undefined;
  const facts: Shown[] = useMemo(
    () =>
      draft
        ? draft.material_objects.map((o) => ({
            id: o.id,
            type_id: o.type_id,
            display_text: documentDisplayText(draft, o),
            values: o.values,
            evidence: o.evidence,
          }))
        : [],
    [draft],
  );
  const object: Shown | undefined = databaseDetail
    ? (() => {
        const center = neighborhood?.objects.find((o) => o.id === neighborhood.center_id);
        return center && { ...center, ref: center.ref ?? center.id, key: center.source === "database" ? center.key : undefined };
      })()
    : facts.find((o) => o.id === objectId);
  usePageTab({
    title: object ? `实例 · ${object.display_text}` : type ? `${type.name} · ${objectId ? "实例详情" : "实例列表"}` : undefined,
  });
  if (error) return <ErrorSurface message={error} retry={load} />;
  if (!draft) return <LoadingSurface label="正在读取实例…" />;
  if (!type) return <Empty className="mt-16" description="没有找到业务对象" />;
  const properties = effectiveProperties(draft, typeId).map((p) => p.definition);
  const columnsShown = properties.filter((p) => !p.identifier).slice(0, 4);
  const snapshotDates = (sessionId ? preview?.snapshot_dates : list?.snapshot_dates) ?? [];
  const snapshotted =
    draft.object_types.some(
      (o) => isA(draft, o.id, typeId) && effectiveSources(draft, o.id).some((s) => s.dataset?.snapshot_date_column),
    ) || snapshotDates.some((s) => s.date);
  const documentRows = facts.filter(
    (f) =>
      isA(draft, f.type_id, typeId) &&
      (!query || documentSearchText(draft, byId(draft.material_objects, f.id)!).includes(query.toLowerCase())),
  );
  const databaseRows: Shown[] = sessionId
    ? (preview?.items ?? []).map((i) => ({
        id: i.__ref,
        ref: i.__ref,
        type_id: i.__type_id,
        display_text: i.display_text,
        values: i.values,
        key: i.__key,
        source: "database",
      }))
    : (list?.items ?? []).map((i) => ({
        id: i.ref,
        ref: i.ref,
        type_id: i.type_id,
        display_text: i.display_text,
        values: i.values,
        key: i.source === "database" ? i.key : undefined,
        source: "database",
      }));
  const withSession = (search: URLSearchParams) => {
    if (sessionId) search.set("session", sessionId);
    return search;
  };
  const linkTo = (o: Shown) => {
    if (sessionId && o.key) {
      return `/workspaces/${workspace.id}/objects/${o.type_id}/instances/database?${withSession(
        new URLSearchParams({ source: "database", key: JSON.stringify(o.key), ...(snapshotDate ? { date: snapshotDate } : {}) }),
      )}`;
    }
    if (o.source === "database" || o.ref?.startsWith("db.") || o.key) {
      const ref = o.ref ?? o.id;
      const search = new URLSearchParams({ source: "database", ...(snapshotDate ? { date: snapshotDate } : {}) });
      return `/workspaces/${workspace.id}/objects/${o.type_id}/instances/${encodeURIComponent(ref)}?${search}`;
    }
    return `/workspaces/${workspace.id}/objects/${o.type_id}/instances/${o.id}${suffix}`;
  };
  const availableObjects: Shown[] = databaseDetail
    ? (neighborhood?.objects ?? []).map((o) => ({
        ...o,
        ref: o.ref ?? o.id,
        key: o.source === "database" ? o.key : undefined,
      }))
    : facts;
  const availableLinks: InstanceEdge[] = databaseDetail ? (neighborhood?.links ?? []) : draft.material_links;
  const related = object
    ? availableLinks
        .filter((l) => l.source_id === object.id || l.target_id === object.id)
        .map((l) => {
          const outgoing = l.source_id === object.id;
          const link = byId(draft.link_types, l.type_id);
          return {
            id: l.id,
            label: link ? linkDisplayName(link, outgoing) : "关系",
            other: availableObjects.find((o) => o.id === (outgoing ? l.target_id : l.source_id)),
          };
        })
        .filter((r) => r.other)
    : [];
  const neighborhoodGraph = object ? instanceNeighborhood(availableObjects, availableLinks, object.id, depth) : { objects: [], links: [] };
  const showTypeColumn =
    mode === "shared_parent" ||
    mode === "virtual" ||
    documentRows.some((f) => f.type_id !== typeId) ||
    databaseRows.some((r) => r.type_id !== typeId);
  const columns = [
    {
      title: "实例",
      key: "display",
      render: (_: unknown, o: Shown) => <Link to={linkTo(o)}>{o.display_text}</Link>,
    },
    ...(showTypeColumn
      ? [{ title: "类型", key: "type", render: (_: unknown, o: Shown) => byId(draft.object_types, o.type_id)?.name }]
      : []),
    ...columnsShown.map((p) => ({ title: p.name, key: p.id, render: (_: unknown, o: Shown) => cell(o.values[p.technical_name]) })),
  ];
  const hasNext = sessionId ? Boolean(preview?.has_more) : Boolean(list?.next_cursor);
  const setDate = (date: string | null) =>
    setParams(
      (p) => {
        const next = new URLSearchParams(p);
        if (date) next.set("date", date);
        else next.delete("date");
        return next;
      },
      { replace: true },
    );
  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <div className="px-6 pt-4">
        <Breadcrumb
          items={[
            { title: <Link to={"../objects" + suffix}>本体对象</Link> },
            { title: <Link to={detail.href({ kind: "object_type", id: type.id })}>{type.name}</Link> },
            { title: <Link to={`../objects/${type.id}/instances${suffix}`}>实例列表</Link> },
            ...(object ? [{ title: object.display_text }] : []),
          ]}
        />
      </div>
      <PageHeader
        title={object?.display_text ?? type.name}
        note={`${byId(draft.object_types, object?.type_id ?? typeId)?.name} / ${type.technical_name}`}
      >
        {object && (
          <Button type="primary" className="ml-auto" icon={<Network size={14} />} onClick={() => setGraphOpen(!graphOpen)}>
            {graphOpen ? "返回详情" : "实例图谱"}
          </Button>
        )}
      </PageHeader>
      <PageBody>
        <Panel>
          {databaseDetail && neighborhood?.warnings.map((w) => <Alert key={w} type="info" showIcon message={w} />)}
          {neighborhood?.truncated && (
            <Alert type="warning" showIcon message="已达到查询范围上限，当前结果仅为部分关系。请缩小范围或选择新的中心实例。" />
          )}
          {databaseDetail && neighborhood?.snapshot_dates.some((s) => s.date) && (
            <Text type="secondary" className="text-xs">
              数据日期：{[...new Set(neighborhood.snapshot_dates.map((s) => s.date).filter(Boolean))].join("、")}
            </Text>
          )}
          {!objectId ? (
            <>
              <PanelToolbar>
                <Select
                  size="small"
                  aria-label="实例来源"
                  value={source}
                  className="w-44"
                  onChange={(value: typeof source) => {
                    setSource(value);
                    resetPage();
                  }}
                  options={[
                    { value: "document", label: "文档实例" },
                    { value: "database", label: databaseReady ? "数据库实例" : "数据库实例（未映射）", disabled: !databaseReady },
                  ]}
                />
                <Input.Search
                  size="small"
                  allowClear
                  aria-label="搜索实例"
                  placeholder="显示名称或属性值"
                  className="w-72"
                  value={query}
                  onChange={(e) => {
                    setQuery(e.target.value);
                    resetPage();
                  }}
                />
                {source === "database" && snapshotted && (
                  <DatePicker
                    size="small"
                    aria-label="数据日期"
                    placeholder="最新日期"
                    value={snapshotDate ? dayjs(snapshotDate) : null}
                    onChange={(d) => {
                      setDate(d ? d.format("YYYY-MM-DD") : null);
                      resetPage();
                    }}
                  />
                )}
                {source === "database" && snapshotDates.some((s) => s.date) && (
                  <Text type="secondary" className="text-xs">
                    数据日期：{[...new Set(snapshotDates.map((s) => s.date).filter(Boolean))].join("、")}
                  </Text>
                )}
              </PanelToolbar>
              {source === "document" ? (
                <Table
                  size="middle"
                  rowKey="id"
                  dataSource={documentRows}
                  columns={columns}
                  pagination={{ pageSize: PAGE_SIZE, showTotal: (total) => `共 ${total} 条`, hideOnSinglePage: true }}
                  locale={{ emptyText: <Empty description="暂无文档实例，可从建模材料中抽取" /> }}
                />
              ) : (
                <>
                  <Table
                    size="middle"
                    rowKey="id"
                    loading={loading}
                    dataSource={databaseRows}
                    columns={columns}
                    pagination={false}
                    locale={{ emptyText: <Empty description="没有匹配的实例" /> }}
                  />
                  <div className="flex items-center justify-end gap-2 border-t border-rule px-4 py-2">
                    <Text type="secondary" className="text-xs">
                      按需查询 · 每页 {PAGE_SIZE} 条
                    </Text>
                    <Button size="small" disabled={page === 0 || loading} onClick={() => setPage(page - 1)}>
                      上一页
                    </Button>
                    <span className="tabular-nums">{page + 1}</span>
                    <Button
                      size="small"
                      disabled={!hasNext || loading}
                      onClick={() => {
                        if (!sessionId && list?.next_cursor) {
                          setCursors((prev) => {
                            const next = prev.slice(0, page + 1);
                            next[page + 1] = list.next_cursor ?? undefined;
                            return next;
                          });
                        }
                        setPage(page + 1);
                      }}
                    >
                      下一页
                    </Button>
                  </div>
                </>
              )}
            </>
          ) : loading ? (
            <LoadingSurface label="正在查询实例及关联关系…" />
          ) : !object ? (
            <Empty description="此实例不存在" />
          ) : graphOpen ? (
            <div className="relative h-review-graph overflow-hidden">
              <OntologyGraph
                query=""
                graph={{
                  workspace_id: workspace.id,
                  version_id: "instances",
                  version_sha256: "",
                  version_content_sha256: "",
                  normalized_snapshot_sha256: "",
                  ...instanceCanvas(neighborhoodGraph.objects, neighborhoodGraph.links, draft.object_types, draft.link_types),
                }}
                onSelect={(selected) => {
                  if (selected?.category !== "node") return;
                  const next = availableObjects.find((o) => o.id === selected.item.id);
                  if (next && next.id !== object.id) navigate(linkTo(next));
                }}
              />
              <div className="absolute top-3 left-3 flex items-center gap-2 rounded-md border border-rule bg-surface px-3 py-1 text-xs text-muted">
                {databaseDetail ? "数据库关联" : "文档实例"} · 展开范围
                <Select
                  size="small"
                  aria-label="实例图谱深度"
                  value={depth}
                  onChange={setDepth}
                  options={[1, 2, 3].map((d) => ({ value: d, label: `${d} 跳` }))}
                />
                · 点击其他节点设为中心
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-4 p-4">
              <SectionTitle title="全部属性" />
              <Descriptions
                size="small"
                column={2}
                items={effectiveProperties(draft, object.type_id).map((p) => ({
                  key: p.definition.id,
                  label: p.definition.name,
                  children: cell(object.values[p.definition.technical_name]),
                }))}
              />
              <div className="grid grid-cols-1 gap-4 border-t border-rule pt-4 lg:grid-cols-2">
                <section className="flex flex-col gap-2">
                  <SectionTitle title="关联关系" />
                  {related.length ? (
                    related.map((r) => (
                      <Link key={r.id} to={linkTo(r.other!)} className="inline-flex items-center gap-2">
                        <Network size={15} />
                        <Text type="secondary">{r.label}</Text>
                        {r.other!.display_text}
                        <Tag className="m-0">{byId(draft.object_types, r.other!.type_id)?.name}</Tag>
                      </Link>
                    ))
                  ) : (
                    <Text type="secondary">暂无关联关系</Text>
                  )}
                </section>
                <section className="flex flex-col gap-2">
                  {databaseDetail ? (
                    <>
                      <SectionTitle title="来源" />
                      <span className="inline-flex items-center gap-2 text-sm">
                        <FileText size={14} />
                        数据库实时查询，没有全量同步或写回源系统。
                      </span>
                    </>
                  ) : object.evidence?.length ? (
                    <EvidenceSection workspaceId={workspace.id} evidence={object.evidence} />
                  ) : (
                    <>
                      <SectionTitle title="来源证据" />
                      <Text type="secondary">暂无文档证据</Text>
                    </>
                  )}
                </section>
              </div>
            </div>
          )}
        </Panel>
      </PageBody>
    </div>
  );
}
