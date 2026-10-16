import { Alert, Button, DatePicker, Descriptions, Empty, Input, Segmented, Table, Tag, Typography } from "antd";
import dayjs from "dayjs";
import { ArrowRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { catalogApi, instancesApi } from "../../api/client";
import type {
  Draft,
  InstanceList,
  InstanceNeighborhood,
  LinkType,
  MappingPreview,
  MaterialObject,
  ObjectType,
  Scalar,
  TypedKey,
} from "../../api/types";
import { bindingMode, byId, effectiveProperties, effectiveSources, isA, mappingFor } from "../../lib/coreModel";
import type { PanelProps } from "../../lib/elementModel";
import { documentDisplayText, documentSearchText } from "../../lib/instanceDisplay";
import { ensureMapping } from "../../lib/objectMappingEditing";
import { EvidenceSection } from "./ElementPanels";

const { Text } = Typography;
const PAGE_SIZE = 8;

type Row = {
  id: string;
  ref?: string;
  type_id: string;
  display_text: string;
  values: Record<string, Scalar>;
  key?: TypedKey;
  fact?: MaterialObject;
};

const shown = (value: Scalar | undefined) =>
  value === null || value === undefined || value === "" ? (
    <Text type="secondary">—</Text>
  ) : typeof value === "boolean" ? (
    value ? "是" : "否"
  ) : (
    String(value)
  );

function InstanceDetail({
  draft,
  row,
  related,
  onClose,
}: {
  draft: Draft;
  row: Row;
  related: { id: string; label: string; other: string; typeName: string }[] | null;
  onClose: () => void;
}) {
  const type = byId(draft.object_types, row.type_id);
  const properties = effectiveProperties(draft, row.type_id).map((p) => p.definition);
  return (
    <section className="flex flex-col gap-3 rounded-md border border-rule p-4">
      <div className="flex items-center gap-2">
        <Text strong className="flex-1">
          {row.display_text}
        </Text>
        {type && <Tag className="!m-0">{type.name}</Tag>}
        <Button size="small" type="text" onClick={onClose}>
          收起
        </Button>
      </div>
      <Descriptions
        size="small"
        bordered
        column={2}
        items={properties.map((p) => ({ key: p.id, label: p.name, children: shown(row.values[p.technical_name]) }))}
      />
      {related && (
        <div className="flex flex-col gap-1">
          <Text strong>关联实例</Text>
          {related.length ? (
            related.map((r) => (
              <span key={r.id} className="text-sm">
                <Text type="secondary">{r.label}</Text> {r.other} <Text type="secondary">（{r.typeName}）</Text>
              </span>
            ))
          ) : (
            <Text type="secondary">没有关联实例</Text>
          )}
        </div>
      )}
      {row.fact && <EvidenceSection workspaceId={draft.workspace_id} evidence={row.fact.evidence} />}
    </section>
  );
}

function linkLabel(link: LinkType | undefined, outgoing: boolean) {
  if (!link) return "关系";
  return outgoing ? link.name : (link.inverse_name ?? `${link.name}（反向）`);
}

function ObjectInstances({
  draft,
  type,
  canEdit,
  sessionId,
  canBrowseDatabase,
  initialObjectId,
}: PanelProps<ObjectType> & { canBrowseDatabase: boolean; initialObjectId?: string }) {
  const mode = bindingMode(draft, type.id);
  const databaseReady =
    canBrowseDatabase &&
    (sessionId
      ? mode === "independent" || mode === "shared_parent"
      : !canEdit && !draft.mappings.length
        ? true
        : mode !== "unbound");
  const facts = draft.material_objects.filter((o) => isA(draft, o.type_id, type.id));
  const [source, setSource] = useState<"document" | "database">(
    !initialObjectId && databaseReady && !facts.length ? "database" : "document",
  );
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [selected, setSelected] = useState<Row | null>(() => {
    const fact = facts.find((o) => o.id === initialObjectId);
    return fact ? factRow(draft, fact) : null;
  });
  const [preview, setPreview] = useState<MappingPreview | null>(null);
  const [list, setList] = useState<InstanceList | null>(null);
  const [neighborhood, setNeighborhood] = useState<InstanceNeighborhood | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [snapshotDate, setSnapshotDate] = useState<string | null>(null);
  const snapshotDates = (sessionId ? preview?.snapshot_dates : list?.snapshot_dates) ?? [];
  const snapshotted =
    draft.object_types.some(
      (o) => isA(draft, o.id, type.id) && effectiveSources(draft, o.id).some((s) => s.dataset?.snapshot_date_column),
    ) || snapshotDates.some((s) => s.date);
  const mapping = useMemo(() => mappingFor(draft, type.id) ?? ensureMapping(draft, type.id), [draft, type.id]);
  const cursor = cursors[page];
  const resetPage = () => {
    setPage(0);
    setCursors([undefined]);
  };
  useEffect(() => {
    if (source !== "database" || !databaseReady) return;
    let live = true;
    const timer = window.setTimeout(() => {
      setBusy(true);
      setError("");
      if (sessionId) {
        catalogApi
          .mappingPreview(draft.workspace_id, {
            mapping,
            session_id: sessionId,
            q: query,
            offset: page * PAGE_SIZE,
            limit: PAGE_SIZE,
            ...(snapshotDate ? { snapshot_date: snapshotDate } : {}),
          })
          .then((result) => live && setPreview(result))
          .catch((e: Error) => live && setError(e.message))
          .finally(() => live && setBusy(false));
      } else {
        instancesApi
          .list(draft.workspace_id, {
            type_id: type.id,
            source: "database",
            q: query,
            ...(cursor ? { cursor } : {}),
            limit: PAGE_SIZE,
            ...(snapshotDate ? { snapshot_date: snapshotDate } : {}),
          })
          .then((result) => live && setList(result))
          .catch((e: Error) => live && setError(e.message))
          .finally(() => live && setBusy(false));
      }
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [source, databaseReady, mapping, sessionId, query, page, cursor, snapshotDate, draft.workspace_id, type.id]);
  const properties = effectiveProperties(draft, type.id)
    .map((p) => p.definition)
    .filter((p) => !p.identifier)
    .slice(0, 4);
  const documentRows = facts
    .filter((o) => !query || documentSearchText(draft, o).includes(query.toLowerCase()))
    .map((o) => factRow(draft, o));
  const databaseRows: Row[] = sessionId
    ? (preview?.items ?? []).map((item) => ({
        id: item.__ref,
        ref: item.__ref,
        type_id: item.__type_id,
        display_text: item.display_text,
        values: item.values,
        key: item.__key,
      }))
    : (list?.items ?? []).map((item) => ({
        id: item.ref,
        ref: item.ref,
        type_id: item.type_id,
        display_text: item.display_text,
        values: item.values,
        key: item.source === "database" ? item.key : undefined,
      }));
  const select = async (row: Row) => {
    setSelected(row);
    setNeighborhood(null);
    if (row.fact) return;
    try {
      if (sessionId) {
        if (!row.key) return;
        setNeighborhood(
          await instancesApi.draftNeighborhood(draft.workspace_id, {
            type_id: row.type_id,
            key: row.key,
            session_id: sessionId,
            depth: 1,
            ...(snapshotDate ? { snapshot_date: snapshotDate } : {}),
          }),
        );
      } else {
        const ref = row.ref ?? row.id;
        if (!ref) return;
        setNeighborhood(
          await instancesApi.neighborhood(draft.workspace_id, ref, {
            depth: 1,
            ...(snapshotDate ? { snapshot_date: snapshotDate } : {}),
          }),
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取关联实例失败");
    }
  };
  const related = selected
    ? selected.fact
      ? draft.material_links
          .filter((l) => l.source_id === selected.id || l.target_id === selected.id)
          .map((l) => {
            const outgoing = l.source_id === selected.id;
            const other = byId(draft.material_objects, outgoing ? l.target_id : l.source_id);
            return {
              id: l.id,
              label: linkLabel(byId(draft.link_types, l.type_id), outgoing),
              other: other ? documentDisplayText(draft, other) : "?",
              typeName: byId(draft.object_types, other?.type_id)?.name ?? "",
            };
          })
      : neighborhood
        ? neighborhood.links
            .filter((l) => l.source_id === neighborhood.center_id || l.target_id === neighborhood.center_id)
            .map((l) => {
              const outgoing = l.source_id === neighborhood.center_id;
              const other = neighborhood.objects.find((o) => o.id === (outgoing ? l.target_id : l.source_id));
              return {
                id: l.id,
                label: linkLabel(byId(draft.link_types, l.type_id), outgoing),
                other: other?.display_text ?? "?",
                typeName: byId(draft.object_types, other?.type_id)?.name ?? "",
              };
            })
        : null
    : null;
  const showTypeColumn =
    facts.some((f) => f.type_id !== type.id) ||
    databaseRows.some((r) => r.type_id !== type.id) ||
    mode === "shared_parent" ||
    mode === "virtual";
  const columns = [
    {
      title: "实例",
      key: "display",
      render: (_: unknown, row: Row) => (
        <Button type="link" size="small" className="!h-auto !p-0" onClick={() => void select(row)}>
          {row.display_text}
        </Button>
      ),
    },
    ...(showTypeColumn
      ? [{ title: "类型", key: "type", render: (_: unknown, row: Row) => byId(draft.object_types, row.type_id)?.name }]
      : []),
    ...properties.map((p) => ({
      title: p.name,
      key: p.id,
      render: (_: unknown, row: Row) => shown(row.values[p.technical_name]),
    })),
  ];
  const hasNext = sessionId ? Boolean(preview?.has_more) : Boolean(list?.next_cursor);
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented
          value={source}
          onChange={(v) => {
            setSource(v as typeof source);
            resetPage();
            setSelected(null);
          }}
          options={[
            { value: "document", label: `文档事实 ${facts.length}` },
            { value: "database", label: "数据库", disabled: !databaseReady },
          ]}
        />
        <Input.Search
          allowClear
          aria-label="搜索实例"
          placeholder="搜索显示名称或属性值"
          className="max-w-[320px]"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            resetPage();
          }}
        />
        {source === "database" && snapshotted && (
          <DatePicker
            aria-label="数据日期"
            placeholder="最新日期"
            value={snapshotDate ? dayjs(snapshotDate) : null}
            onChange={(d) => {
              setSnapshotDate(d ? d.format("YYYY-MM-DD") : null);
              resetPage();
            }}
          />
        )}
        {source === "database" && snapshotDates.some((s) => s.date) && (
          <Text type="secondary" className="text-xs">
            数据日期：{[...new Set(snapshotDates.map((s) => s.date).filter(Boolean))].join("、")}
          </Text>
        )}
      </div>
      {Boolean(sessionId) && mode === "virtual" && source === "document" && !facts.length && (
        <Alert type="info" showIcon message="虚拟父对象的实例来自子对象，请打开子对象查看数据库实例。" />
      )}
      {error && <Alert type="error" showIcon message={error} />}
      {source === "document" ? (
        <Table
          size="small"
          rowKey="id"
          dataSource={documentRows}
          columns={columns}
          pagination={documentRows.length > PAGE_SIZE ? { pageSize: PAGE_SIZE, size: "small" } : false}
          locale={{ emptyText: <Empty description="没有文档事实" /> }}
        />
      ) : (
        <>
          <Table
            size="small"
            rowKey="id"
            loading={busy}
            dataSource={databaseRows}
            columns={columns}
            pagination={false}
            locale={{ emptyText: <Empty description="没有匹配的实例" /> }}
          />
          <div className="flex justify-end gap-2">
            <Button size="small" disabled={page === 0 || busy} onClick={() => setPage(page - 1)}>
              上一页
            </Button>
            <Button
              size="small"
              disabled={!hasNext || busy}
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
      {selected && <InstanceDetail draft={draft} row={selected} related={related} onClose={() => setSelected(null)} />}
    </div>
  );
}

function factRow(draft: Draft, fact: MaterialObject): Row {
  return { id: fact.id, type_id: fact.type_id, display_text: documentDisplayText(draft, fact), values: fact.values, fact };
}

function LinkInstances({ draft, type, open }: PanelProps<LinkType>) {
  const facts = draft.material_links.filter((l) => l.type_id === type.id);
  const name = (id: string) => {
    const fact = byId(draft.material_objects, id);
    return fact ? documentDisplayText(draft, fact) : "?";
  };
  return (
    <div className="flex flex-col gap-3">
      <Table
        size="small"
        rowKey="id"
        dataSource={facts}
        pagination={facts.length > PAGE_SIZE ? { pageSize: PAGE_SIZE, size: "small" } : false}
        locale={{ emptyText: <Empty description="没有文档中的关系事实" /> }}
        columns={[
          { title: "来源实例", key: "source", render: (_, l) => name(l.source_id) },
          { title: "目标实例", key: "target", render: (_, l) => name(l.target_id) },
        ]}
      />
      <Button
        type="link"
        className="self-start"
        icon={<ArrowRight size={14} />}
        iconPosition="end"
        onClick={() => open({ kind: "object_type", id: type.source_type_id, tab: "instances" })}
      >
        查看来源对象的数据库实例
      </Button>
    </div>
  );
}

export function ElementInstances(
  props: PanelProps & { canBrowseDatabase: boolean; initialObjectId?: string },
) {
  const { type } = props;
  return "derived_by" in type ? (
    <ObjectInstances {...(props as PanelProps<ObjectType> & typeof props)} />
  ) : (
    <LinkInstances {...(props as PanelProps<LinkType>)} />
  );
}
