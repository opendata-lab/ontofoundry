import { Button, Card, Empty, Input, Select, Tag, Typography } from "antd";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Box, GitBranch, Plus, RefreshCw, Rocket } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { useElementInspector } from "../hooks/useElementInspector";
import { useSnapshot } from "../hooks/useSnapshot";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { MULTIPLICITY, byId, effectiveLinks, effectiveProperties, isA, mappingFor } from "../lib/coreModel";

const { Text, Paragraph } = Typography;

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <span className="flex flex-col">
      <Text type="secondary" className="text-[10px]">
        {label}
      </Text>
      <span className="text-xs tabular-nums">{value}</span>
    </span>
  );
}

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
          <Select
            aria-label="标签筛选"
            allowClear
            placeholder="按标签筛选"
            className="min-w-[160px]"
            value={tag}
            options={tags.map((t) => ({ value: t, label: t }))}
            onChange={setTag}
          />
          <Input.Search
            allowClear
            aria-label="搜索目录"
            placeholder="名称、英文名、同义词或描述"
            className="w-[280px]"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
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
      {filtered.length ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
          {filtered.map((item) => {
            const link = !objects ? draft.link_types.find((l) => l.id === item.id) : undefined;
            const parent = objects && "extends" in item ? byId(draft.object_types, item.extends) : undefined;
            return (
              <Link key={item.id} to={inspector.href({ kind, id: item.id, tab: objects ? "properties" : "basic", sessionId })}>
                <Card hoverable size="small" className="h-full">
                  <div className="flex items-start gap-3">
                    <span
                      className={`flex size-9 flex-none items-center justify-center rounded-sm ${objects ? "bg-object-soft text-object" : "bg-relation-soft text-relation"}`}
                    >
                      <Icon size={20} />
                    </span>
                    <div className="flex min-w-0 flex-col">
                      <Text strong className="truncate">
                        {item.name}
                      </Text>
                      <code className="truncate text-xs text-muted">{item.technical_name}</code>
                    </div>
                  </div>
                  {item.description && (
                    <Paragraph type="secondary" ellipsis={{ rows: 2 }} className="!mt-2 !mb-0 text-xs">
                      {item.description}
                    </Paragraph>
                  )}
                  <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
                    {objects ? (
                      <>
                        <Metric label="属性" value={effectiveProperties(draft, item.id).length} />
                        <Metric label="关系" value={effectiveLinks(draft, item.id).length} />
                        <Metric label="映射" value={mappingFor(draft, item.id) ? 1 : 0} />
                        <Metric
                          label="文档实例"
                          value={draft.material_objects.filter((o) => isA(draft, o.type_id, item.id)).length}
                        />
                      </>
                    ) : (
                      link && (
                        <span className="flex flex-wrap items-center gap-1 text-sm">
                          <Tag className="!m-0">{byId(draft.object_types, link.source_type_id)?.name ?? "未指定"}</Tag>
                          <Text type="secondary">→</Text>
                          <Tag className="!m-0">{byId(draft.object_types, link.target_type_id)?.name ?? "未指定"}</Tag>
                          <Text type="secondary" className="text-xs">
                            {MULTIPLICITY[link.multiplicity]}
                          </Text>
                        </span>
                      )
                    )}
                  </div>
                  {(parent || item.tags.length > 0) && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {parent && <Tag color="blue" className="!m-0">继承 {parent.name}</Tag>}
                      {item.tags.map((t) => (
                        <Tag key={t} className="!m-0">
                          {t}
                        </Tag>
                      ))}
                    </div>
                  )}
                </Card>
              </Link>
            );
          })}
        </div>
      ) : (
        <Empty description={items.length ? "没有匹配的本体模型" : workspace.role ? "还没有定义" : "暂无已发布本体"} />
      )}
      </PageBody>
    </div>
  );
}
