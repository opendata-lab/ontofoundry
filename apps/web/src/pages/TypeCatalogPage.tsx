import { Button, Empty, Input, Select, Table, Tag, Typography } from "antd";
import { PageBody, PageHeader, Panel, PanelToolbar, SectionTitle } from "../components/layout";
import { Box, GitBranch, Plus, RefreshCw, Rocket, Search } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { useElementInspector } from "../hooks/useElementInspector";
import { useSnapshot } from "../hooks/useSnapshot";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { MULTIPLICITY, byId, effectiveLinks, effectiveProperties, isA, mappingFor } from "../lib/coreModel";

const { Text } = Typography;

export function TypeCatalogPage({ kind }: { kind: "object_type" | "link_type" }) {
  const { workspace } = useWorkspaceContext();
  const { draft, error, load, sessionId, suffix } = useSnapshot(workspace);
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState<string>();
  const inspector = useElementInspector();
  if (error) return <ErrorSurface message={error} retry={load} />;
  if (!draft) return <LoadingSurface label="正在读取本体目录…" />;
  const objects = kind === "object_type";
  const items = objects ? draft.object_types : draft.link_types;
  const tags = [...new Set(items.flatMap((i) => i.tags))];
  const normalized = query.trim().toLowerCase();
  const filtered = items.filter(
    (i) =>
      (!tag || i.tags.includes(tag)) &&
      (!normalized ||
        [i.name, i.technical_name, i.description, ...i.synonyms, "inverse_name" in i ? (i.inverse_name ?? "") : ""]
          .join(" ")
          .toLowerCase()
          .includes(normalized)),
  );
  const Icon = objects ? Box : GitBranch;
  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <PageHeader title={objects ? "本体对象" : "本体关系"}>
        <Button icon={<RefreshCw size={13} />} onClick={load}>
          刷新
        </Button>
        {workspace.role && (
          <>
            <Button
              type="primary"
              icon={<Plus size={15} />}
              onClick={() => inspector.open({ kind, id: "new", mode: "edit", sessionId })}
            >
              新建{objects ? "对象" : "关系"}
            </Button>
            <Link to={"../delivery" + suffix}>
              <Button icon={<Rocket size={14} />}>发布</Button>
            </Link>
          </>
        )}
      </PageHeader>
      <PageBody>
        <Panel>
          <PanelToolbar
            extra={
              <>
                <Select
                  size="small"
                  aria-label="标签筛选"
                  allowClear
                  placeholder="按标签筛选"
                  className="w-40"
                  value={tag}
                  options={tags.map((t) => ({ value: t, label: t }))}
                  onChange={setTag}
                />
                <Input
                  size="small"
                  type="search"
                  prefix={<Search size={14} className="text-muted" />}
                  allowClear
                  aria-label="搜索目录"
                  placeholder="名称、英文名、同义词或描述"
                  className="w-72"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </>
            }
          >
            <SectionTitle title={objects ? "业务对象" : "本体关系"} note={`${filtered.length} / ${items.length}`} />
          </PanelToolbar>
          <Table<(typeof items)[number]>
            size="middle"
            onHeaderRow={() => ({ className: "text-xs" })}
            rowKey="id"
            dataSource={filtered}
            pagination={filtered.length > 20 ? { pageSize: 20 } : false}
            locale={{
              emptyText: (
                <Empty
                  description={items.length ? "没有匹配的本体模型" : workspace.role ? "还没有定义" : "暂无已发布本体"}
                />
              ),
            }}
            columns={[
              {
                title: objects ? "业务对象" : "本体关系",
                key: "name",
                render: (_, item) => (
                  <div className="flex flex-col gap-1">
                    <Link
                      to={inspector.href({ kind, id: item.id, tab: objects ? "properties" : "basic", sessionId })}
                      className="inline-flex items-center gap-2 font-medium"
                    >
                      <Icon size={14} className={objects ? "flex-none text-object" : "flex-none text-relation"} />
                      {item.name}
                    </Link>
                    <code className="text-xs text-muted">{item.technical_name}</code>
                    {item.description && (
                      <Text type="secondary" className="max-w-md truncate text-xs" title={item.description}>
                        {item.description}
                      </Text>
                    )}
                  </div>
                ),
              },
              ...(objects
                ? [
                    {
                      title: "属性",
                      key: "properties",
                      render: (_: unknown, item: (typeof items)[number]) => effectiveProperties(draft, item.id).length,
                    },
                    {
                      title: "关系",
                      key: "links",
                      render: (_: unknown, item: (typeof items)[number]) => effectiveLinks(draft, item.id).length,
                    },
                    {
                      title: "映射",
                      key: "mappings",
                      render: (_: unknown, item: (typeof items)[number]) => (mappingFor(draft, item.id) ? 1 : 0),
                    },
                    {
                      title: "文档实例",
                      key: "instances",
                      render: (_: unknown, item: (typeof items)[number]) =>
                        draft.material_objects.filter((o) => isA(draft, o.type_id, item.id)).length,
                    },
                  ]
                : [
                    {
                      title: "关系端点",
                      key: "endpoints",
                      render: (_: unknown, item: (typeof items)[number]) => {
                        const link = draft.link_types.find((l) => l.id === item.id);
                        return (
                          link && (
                            <span className="flex flex-wrap items-center gap-1">
                              <Tag className="m-0">
                                {byId(draft.object_types, link.source_type_id)?.name ?? "未指定"}
                              </Tag>
                              <Text type="secondary">→</Text>
                              <Tag className="m-0">
                                {byId(draft.object_types, link.target_type_id)?.name ?? "未指定"}
                              </Tag>
                              <Text type="secondary" className="text-xs">
                                {MULTIPLICITY[link.multiplicity]}
                              </Text>
                            </span>
                          )
                        );
                      },
                    },
                  ]),
              {
                title: "标签",
                key: "tags",
                render: (_, item) => {
                  const parent = objects && "extends" in item ? byId(draft.object_types, item.extends) : undefined;
                  return parent || item.tags.length ? (
                    <div className="flex flex-wrap gap-1">
                      {parent && <Tag className="m-0">继承 {parent.name}</Tag>}
                      {item.tags.map((t) => (
                        <Tag key={t} className="m-0">
                          {t}
                        </Tag>
                      ))}
                    </div>
                  ) : (
                    <Text type="secondary">—</Text>
                  );
                },
              },
            ]}
          />
        </Panel>
      </PageBody>
    </div>
  );
}
