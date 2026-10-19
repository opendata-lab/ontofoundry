import { Button, Dropdown, Empty, Input, Segmented, Table, Tag, Tooltip, Tree, Typography } from "antd";
import type { DataNode } from "antd/es/tree";
import { Box, Database, MoreHorizontal, PanelLeftClose, PanelLeftOpen, Plus, Sigma, Workflow } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Draft, TypeGraph } from "../api/types";
import { usePageActive } from "../hooks/usePageTab";
import type { ElementRequest } from "../lib/elementInspector";
import {
  RESOURCE_KIND_LABELS,
  semanticCanvas,
  semanticResources,
  type ResourceKind,
  type SemanticResource,
} from "../lib/semanticExplorer";
import { PanelToolbar, SectionTitle } from "./layout";
import { OntologyGraph, type SelectedGraphItem } from "./OntologyGraph";

const { Text } = Typography;
const STORAGE_KEY = "ontofoundry.semantic.explorer.collapsed";
const KINDS: ResourceKind[] = ["object", "relation", "metric", "dataset"];
const ICONS = { object: Box, relation: Workflow, metric: Sigma, dataset: Database };
type Filter = "all" | ResourceKind;

function storedCollapsed() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === null ? window.innerWidth < 700 : stored === "true";
  } catch {
    return window.innerWidth < 700;
  }
}

/**
 * Objects, relations, metrics and datasets. Objects and relations are drawn
 * on the graph; metrics and datasets are listed, since they are not ontology
 * nodes. Rules open inside their owner's popup.
 */
export function SemanticView({
  graph,
  model,
  onOpen,
  resourceError,
  canCreate = false,
}: {
  graph: TypeGraph;
  model?: Draft | null;
  onOpen: (request: ElementRequest) => void;
  resourceError?: string;
  canCreate?: boolean;
}) {
  const active = usePageActive();
  const [collapsed, setCollapsed] = useState(storedCollapsed);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string[]>(KINDS);
  const resources = useMemo(() => semanticResources(graph, model), [graph, model]);
  const canvas = useMemo(() => semanticCanvas(graph, resources), [graph, resources]);
  const selection = resources.find((r) => r.id === selected);
  const graphSelection: SelectedGraphItem | undefined =
    selection?.kind === "relation"
      ? { category: "edge", item: canvas.edges.find((e) => (e.link_type_id ?? e.id) === selection.id)! }
      : (selection?.selection ?? null);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (!active || event.key !== "Escape" || document.querySelector(".ant-modal-wrap")) return;
      if (selected) setSelected(null);
      else setQuery("");
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [active, selected]);
  const collapse = (value: boolean) => {
    setCollapsed(value);
    try {
      localStorage.setItem(STORAGE_KEY, String(value));
    } catch {
      /* Browsing remains available when storage is blocked. */
    }
  };
  const normalized = query.trim().toLocaleLowerCase();
  const visible = resources.filter(
    (r) =>
      (filter === "all" || r.kind === filter) &&
      (!normalized || [r.name, r.technical, r.subtitle].join(" ").toLocaleLowerCase().includes(normalized)),
  );
  const count = (kind: ResourceKind) => resources.filter((r) => r.kind === kind).length;
  const select = (resource: SemanticResource) => {
    setSelected(resource.id);
    if (!expanded.includes(resource.kind)) setExpanded([...expanded, resource.kind]);
  };
  const graphSelect = (item: SelectedGraphItem) => {
    if (!item) return setSelected(null);
    const id = item.category === "edge" ? (item.item.link_type_id ?? item.item.id) : item.item.id;
    const resource = resources.find((r) => r.id === id);
    if (resource) {
      if (filter !== "all" && filter !== resource.kind) setFilter("all");
      select(resource);
    }
  };
  const menu = (resource: SemanticResource) => ({
    items: [
      { key: "open", label: "打开详情" },
      ...(resource.selection ? [{ key: "locate", label: "在图中定位" }] : []),
    ],
    onClick: ({ key, domEvent }: { key: string; domEvent: { stopPropagation: () => void } }) => {
      domEvent.stopPropagation();
      if (key === "open") onOpen(resource.detail);
      else {
        setFilter("all");
        select(resource);
      }
    },
  });
  const treeData: DataNode[] = KINDS.filter((kind) => filter === "all" || filter === kind).map((kind) => {
    const items = visible.filter((r) => r.kind === kind);
    const Icon = ICONS[kind];
    return {
      key: kind,
      selectable: false,
      title: (
        <span className="inline-flex items-center gap-2 font-medium">
          {RESOURCE_KIND_LABELS[kind]}
          <Text type="secondary" className="text-xs">
            {normalized ? `${items.length} / ` : ""}
            {count(kind)}
          </Text>
        </span>
      ),
      children: items.map((resource) => ({
        key: resource.id,
        isLeaf: true,
        title: (
          <span
            className="group flex min-w-0 items-center gap-2"
            data-resource={resource.id}
            title={[resource.technical, resource.subtitle].filter(Boolean).join(" · ")}
            onDoubleClick={() => onOpen(resource.detail)}
          >
            <Icon size={14} className="flex-none text-muted" />
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate">{resource.name}</span>
              {resource.subtitle && <span className="truncate text-xs text-muted">{resource.subtitle}</span>}
            </span>
            <Dropdown menu={menu(resource)} trigger={["click"]}>
              <Button
                size="small"
                type="text"
                aria-label={`${resource.name}的操作`}
                className="opacity-0 group-hover:opacity-100 focus:opacity-100"
                icon={<MoreHorizontal size={15} />}
                onClick={(e) => e.stopPropagation()}
              />
            </Dropdown>
          </span>
        ),
      })),
    };
  });
  const listing = filter === "metric" || filter === "dataset" ? filter : null;
  const objects = resources.filter((r) => r.kind === "object").length;
  const relations = resources.filter((r) => r.kind === "relation").length;
  const expandExplorer = (
    <Tooltip title="展开资源管理器">
      <Button size="small" aria-label="展开资源管理器" aria-expanded={false}
        icon={<PanelLeftOpen size={16} />} onClick={() => collapse(false)} />
    </Tooltip>
  );
  return (
    <div className="flex h-full min-h-0 bg-surface">
      {!collapsed && <aside
        aria-label="资源管理器"
        className="flex min-h-0 w-80 flex-none flex-col border-r border-rule bg-surface"
      >
        <PanelToolbar>
          <SectionTitle title="资源管理器" />
          <Tooltip title="收起资源管理器">
            <Button
              size="small"
              type="text"
              aria-label="收起资源管理器"
              aria-expanded={true}
              icon={<PanelLeftClose size={16} />}
              onClick={() => collapse(true)}
            />
          </Tooltip>
        </PanelToolbar>
        <div className="flex flex-col gap-2 px-4 py-2">
          <Segmented
            size="small"
            block
            className="max-w-full overflow-x-auto"
            value={filter}
            onChange={(value) => setFilter(value as Filter)}
            options={[
              { value: "all", label: "全部" },
              ...KINDS.map((kind) => ({ value: kind, label: RESOURCE_KIND_LABELS[kind] })),
            ]}
          />
          <Input.Search
            allowClear
            size="small"
            aria-label="名称筛选"
            placeholder="名称筛选"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <div className="min-h-0 flex-1 overflow-auto px-4 pb-2" aria-label="本体资源">
          <Tree
            blockNode
            showLine={false}
            treeData={treeData}
            expandedKeys={expanded}
            onExpand={(keys) => setExpanded(keys.map(String))}
            selectedKeys={selected ? [selected] : []}
            onSelect={(keys) => {
              const resource = resources.find((r) => r.id === keys[0]);
              if (resource) select(resource);
              else setSelected(null);
            }}
          />
          {resourceError && (
            <Text type="secondary" role="status" className="block px-4 py-2 text-xs">
              {resourceError}
            </Text>
          )}
        </div>
        <footer className="flex justify-between border-t border-rule-soft px-4 py-2 text-xs text-muted">
          <span>
            {objects} 个对象 · {relations} 个关系
          </span>
        </footer>
      </aside>}
      <section className="relative min-w-0 flex-1" aria-label={listing ? `${RESOURCE_KIND_LABELS[listing]}列表` : "语义关系画布"}>
        {listing ? (
          <div className="flex h-full flex-col overflow-auto">
            <PanelToolbar>
              {collapsed && expandExplorer}
              <SectionTitle title={RESOURCE_KIND_LABELS[listing]} note={listing === "metric" ? "指标只挂在一个数据集上，只使用该数据集的列" : "登记后供对象映射、关系映射表和指标使用"} />
              {canCreate && (
                <Button
                  type="primary"
                  size="small"
                  className="ml-auto"
                  icon={<Plus size={15} />}
                  onClick={() => onOpen({ kind: listing, id: "new", mode: "edit", sessionId: null })}
                >
                  新建{RESOURCE_KIND_LABELS[listing]}
                </Button>
              )}
            </PanelToolbar>
            <Table
              size="middle"
              rowKey="id"
              pagination={false}
              dataSource={visible}
              locale={{ emptyText: <Empty description={`还没有${RESOURCE_KIND_LABELS[listing]}`} /> }}
              onRow={(resource) => ({ onDoubleClick: () => onOpen(resource.detail) })}
              columns={[
                {
                  title: RESOURCE_KIND_LABELS[listing],
                  key: "name",
                  render: (_, r) => (
                    <Button type="link" className="h-auto p-0" onClick={() => onOpen(r.detail)}>
                      {r.name}
                    </Button>
                  ),
                },
                { title: listing === "metric" ? "技术名" : "物理位置", key: "technical", render: (_, r) => <code>{r.technical}</code> },
                {
                  title: listing === "metric" ? "数据集 · 计算方式" : "快照",
                  key: "subtitle",
                  render: (_, r) => (r.subtitle ? <Tag className="m-0">{r.subtitle}</Tag> : <Text type="secondary">—</Text>),
                },
              ]}
            />
          </div>
        ) : (
          <>
            <OntologyGraph
              graph={canvas}
              query=""
              selection={graphSelection}
              viewportKey={collapsed}
              semantic
              onSelect={graphSelect}
              onOpen={(item) => {
                if (!item) return;
                const id = item.category === "edge" ? (item.item.link_type_id ?? item.item.id) : item.item.id;
                const resource = resources.find((r) => r.id === id);
                if (resource) onOpen(resource.detail);
              }}
            />
            {collapsed && <div className="absolute top-4 left-4 z-10">{expandExplorer}</div>}
            <div
              role="status"
              className="pointer-events-none absolute top-4 left-1/2 -translate-x-1/2 rounded-sm border border-rule bg-surface px-3 py-1 text-xs text-muted"
            >
              {objects} 个对象 · {relations} 个关系
            </div>
          </>
        )}
      </section>
    </div>
  );
}
