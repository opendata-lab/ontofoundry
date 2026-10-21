import { Alert, Button, Empty, Input, Table, Tabs, Tooltip, Typography } from "antd";
import { Box, Braces, Database, FileText, GitBranch, Rocket, ShieldCheck, Sigma, TableProperties, Workflow, type LucideIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { Draft, ElementChange, ModelingSession, TargetKind, TypeGraph } from "../api/types";
import type { ElementRequest } from "../lib/elementInspector";
import type { ProposalsState } from "../hooks/useProposals";
import { VALUE_KINDS, byId } from "../lib/coreModel";
import { documentDisplayText } from "../lib/instanceDisplay";
import { METRIC_KINDS } from "../lib/metricEditing";
import { BINDING_MODES } from "../lib/objectMapping";
import { draftGraph } from "../lib/semanticExplorer";
import { Panel as ResultPanel, PanelToolbar, StatusMark, type StatusState } from "./layout";
import { ElementModal } from "./elements/ElementInspector";
import { OntologyGraph } from "./OntologyGraph";
import { ProposalPanel } from "./proposals/ProposalPanel";

const { Text } = Typography;


type Row = { id: string; kind: TargetKind; name: string; technical: string; description: string; deleted?: boolean };

const CHANGE: Record<ElementChange["change"], { text: string; state: StatusState }> = {
  created: { text: "新增", state: "mapped" },
  updated: { text: "已修改", state: "info" },
  deleted: { text: "待删除", state: "error" },
};

const CATEGORIES: { key: TargetKind; text: string; icon: LucideIcon; tone: string; background: string }[] = [
  { key: "object_type", text: "实体", icon: Box, tone: "text-object", background: "bg-object-soft" },
  { key: "link_type", text: "关系", icon: GitBranch, tone: "text-relation", background: "bg-relation-soft" },
  { key: "property", text: "属性", icon: Braces, tone: "text-attribute", background: "bg-attribute-soft" },
  { key: "rule", text: "规则", icon: ShieldCheck, tone: "text-ink-2", background: "bg-canvas" },
  { key: "metric", text: "指标", icon: Sigma, tone: "text-ink-2", background: "bg-canvas" },
  { key: "dataset", text: "数据集", icon: Database, tone: "text-ink-2", background: "bg-canvas" },
  { key: "mapping", text: "映射", icon: TableProperties, tone: "text-ink-2", background: "bg-canvas" },
  { key: "material_object", text: "文档实例", icon: FileText, tone: "text-ink-2", background: "bg-canvas" },
  { key: "material_link", text: "关系实例", icon: Workflow, tone: "text-ink-2", background: "bg-canvas" },
];

function rowsOf(draft: Draft, kind: TargetKind): Row[] {
  const row = (id: string, name: string, technical: string, description: string): Row => ({ id, kind, name, technical, description });
  switch (kind) {
    case "object_type":
      return draft.object_types.map((o) => row(o.id, (o.display_name || o.name), o.name, o.description));
    case "link_type":
      return draft.link_types.map((l) =>
        row(l.id, (l.display_name || l.name), "", `${(byId(draft.object_types, l.source_type_id)?.display_name || byId(draft.object_types, l.source_type_id)?.name) ?? "?"} → ${(byId(draft.object_types, l.target_type_id)?.display_name || byId(draft.object_types, l.target_type_id)?.name) ?? "?"}`),
      );
    case "property":
      return draft.properties.map((p) =>
        row(p.id, (p.display_name || p.name), p.name, `${(byId(draft.object_types, p.owner_type_id)?.display_name || byId(draft.object_types, p.owner_type_id)?.name) ?? "?"} · ${VALUE_KINDS[p.value_kind]}`),
      );
    case "rule":
      return draft.rules.map((r) => row(r.id, (r.display_name || r.name), r.name, r.expression));
    case "metric":
      return draft.metrics.map((m) => row(m.id, (m.display_name || m.name), m.name, `${METRIC_KINDS[m.kind]}${m.description ? " · " + m.description : ""}`));
    case "dataset":
      return draft.datasets.map((d) => row(d.id, d.name, [d.schema_name, d.table_name].filter(Boolean).join("."), d.description));
    case "mapping":
      return draft.mappings.map((m) =>
        row(
          m.id,
          (byId(draft.object_types, m.type_id)?.display_name || byId(draft.object_types, m.type_id)?.name) ?? "?",
          BINDING_MODES[m.binding_mode] ?? m.binding_mode,
          m.sources.map((s) => byId(draft.datasets, s.dataset_id)?.name ?? "?").join("、"),
        ),
      );
    case "material_object":
      return draft.material_objects.map((o) => row(o.id, documentDisplayText(draft, o), "", (byId(draft.object_types, o.type_id)?.display_name || byId(draft.object_types, o.type_id)?.name) ?? ""));
    case "material_link":
      return draft.material_links.map((l) => {
        const source = byId(draft.material_objects, l.source_id);
        const target = byId(draft.material_objects, l.target_id);
        return row(
          l.id,
          `${source ? documentDisplayText(draft, source) : "?"} → ${target ? documentDisplayText(draft, target) : "?"}`,
          "",
          (byId(draft.link_types, l.type_id)?.display_name || byId(draft.link_types, l.type_id)?.name) ?? "",
        );
      });
    default:
      return [];
  }
}

type Panel = "proposals" | "draft" | "graph";

export function ModelResults({
  session,
  proposals,
  running = false,
  busy = false,
  onRemodel = () => undefined,
}: {
  session: ModelingSession | null;
  proposals?: ProposalsState;
  running?: boolean;
  busy?: boolean;
  onRemodel?: (text: string) => void;
}) {
  const [params, setParams] = useSearchParams();
  // Draft rows and graph nodes open in place, like the semantic view.
  const [inspected, setInspected] = useState<ElementRequest | null>(null);
  const navigate = useNavigate();
  const pending = session?.pending_proposal_count ?? 0;
  const requested = params.get("panel") as Panel | null;
  const [tab, setTabState] = useState<Panel>(requested ?? (proposals && pending > 0 ? "proposals" : "draft"));
  const [fresh, setFresh] = useState(0);
  const lastRevision = useRef(session?.revision);
  const setTab = (next: Panel) => {
    setTabState(next);
    if (next === "draft") setFresh(0);
    setParams(
      (p) => {
        const value = new URLSearchParams(p);
        value.set("panel", next);
        return value;
      },
      { replace: true },
    );
  };
  // A newly arrived batch opens the proposals tab.
  const latest = session?.latest_batch_id;
  const seenLatest = useRef(latest);
  useEffect(() => {
    if (proposals && latest && latest !== seenLatest.current) setTabState("proposals");
    seenLatest.current = latest;
  }, [latest, proposals]);
  // Accepted proposals land in the draft; badge the draft tab until viewed.
  useEffect(() => {
    const previous = lastRevision.current;
    lastRevision.current = session?.revision;
    if (previous !== undefined && session && session.revision > previous && tab === "proposals") setFresh((n) => n + 1);
  }, [session, tab]);
  const [kind, setKind] = useState<TargetKind>("object_type");
  const [query, setQuery] = useState("");
  const draft = session?.draft ?? null;
  const diff = useMemo(() => new Map((session?.base_diff ?? []).map((c) => [c.element_id, c])), [session?.base_diff]);
  const rows = useMemo(() => {
    if (!draft) return [];
    const deleted: Row[] = (session?.base_diff ?? [])
      .filter((c) => c.change === "deleted" && c.element_kind === kind)
      .map((c) => ({
        id: c.element_id,
        kind,
        name: c.label,
        technical: String((c.before as { name?: string } | null)?.name ?? ""),
        description: "",
        deleted: true,
      }));
    return [...rowsOf(draft, kind), ...deleted];
  }, [draft, kind, session?.base_diff]);
  const normalized = query.trim().toLowerCase();
  const visible = rows.filter((r) => !normalized || [r.name, r.technical, r.description].join(" ").toLowerCase().includes(normalized));
  const count = (k: TargetKind) => (draft ? rowsOf(draft, k).length : 0);
  const warnings = session?.result_warnings ?? [];
  const graph = draft ? (session?.graph?.nodes.length ? (session.graph as TypeGraph) : draftGraph(draft)) : null;
  const canPublish = !!session && !!session.latest_batch_id && session.base_diff.length > 0 && !running && !busy;
  const publish = <Tooltip title={canPublish ? undefined : running || busy ? "建模完成后再发布" : "接受提案并形成草稿修改后可发布"}>
    <Button size="small" type="primary" className="shrink-0" icon={<Rocket size={14} />} disabled={!canPublish}
      onClick={() => { if (session) navigate("../delivery?session=" + session.id); }}>发布本体</Button>
  </Tooltip>;
  return (
    <aside className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden">
      {warnings.map((text) => (
        <Alert key={text} type="warning" showIcon message={text} />
      ))}
      <ResultPanel fill>
        <Tabs
          renderTabBar={(props, DefaultTabBar) => <PanelToolbar tabBar={<DefaultTabBar {...props} />} />}
          activeKey={tab}
          onChange={(key) => setTab(key as Panel)}
          className="review-tabs min-h-0 flex-1"
          items={[
            ...(proposals
              ? [
                  {
                    key: "proposals",
                    label: (
                      <span className="inline-flex items-center gap-2">提案 {pending > 0 && <StatusMark state="pending" label={pending} />}</span>
                    ),
                    children: <ProposalPanel session={session} proposals={proposals} running={running} onRemodel={onRemodel} />,
                  },
                ]
              : []),
            {
              key: "draft",
              label: (
                <span className="inline-flex items-center gap-2">本体草稿 {fresh > 0 && <StatusMark state="mapped" label={`+${fresh}`} />}</span>
              ),
              children: (
                <div className="flex h-full min-h-0 flex-col">
                  <div className="flex shrink-0 flex-col gap-3 border-b border-rule p-4">
                    <div className="model-result-categories" aria-label="模型分类">
                      {CATEGORIES.map((category) => {
                        const Icon = category.icon;
                        const selected = kind === category.key;
                        const total = count(category.key);
                        return <Button key={category.key} aria-pressed={selected} aria-label={`${category.text} ${total}`}
                          className={`h-auto min-w-0 justify-start gap-2 rounded-md px-2 py-2 text-xs ${selected ? "border-accent text-accent" : category.tone}`}
                          onClick={() => setKind(category.key)}>
                          <span className={`inline-flex size-5 flex-none items-center justify-center rounded-xs ${category.background} ${category.tone}`}><Icon size={14} /></span>
                          <span className="min-w-0 truncate">{category.text}</span>
                          <span className="ml-auto flex-none font-semibold tabular-nums">{total}</span>
                        </Button>;
                      })}
                    </div>
                    <div className="flex min-w-0 items-center gap-2">
                      <Input.Search allowClear size="small" aria-label="搜索模型" placeholder="搜索名称、英文标识、描述"
                        className="min-w-0 flex-1" value={query} onChange={(event) => setQuery(event.target.value)} />
                      {publish}
                    </div>
                  </div>
                  <div className="min-h-0 flex-1 overflow-auto">
                    <Table
                      size="small"
                      rowKey="id"
                      pagination={visible.length > 50 ? { pageSize: 50, size: "small" } : false}
                      dataSource={visible}
                      locale={{ emptyText: <Empty description={query ? "没有匹配的模型" : draft ? "暂无此类模型" : "暂无构建结果"} /> }}
                      columns={[
                        {
                          title: "名称",
                          key: "name",
                          render: (_, r) => (
                            <div className={`flex flex-col ${r.deleted ? "line-through opacity-60" : ""}`}>
                              {session && !r.deleted ? (
                                <Button
                                  type="link"
                                  size="small"
                                  className="h-auto self-start p-0"
                                  onClick={() => setInspected({ kind: r.kind, id: r.id, sessionId: session.id })}
                                >
                                  {r.name || "未命名"}
                                </Button>
                              ) : (
                                <span>{r.name}</span>
                              )}
                              {r.technical && <code className="text-xs text-muted">{r.technical}</code>}
                            </div>
                          ),
                        },
                        {
                          title: "说明",
                          key: "description",
                          // Two lines keep rows compact in the narrow results column; hover shows the rest.
                          render: (_, r) =>
                            r.description ? (
                              <Typography.Paragraph type="secondary" className="m-0 text-xs" ellipsis={{ rows: 2, tooltip: r.description }}>
                                {r.description}
                              </Typography.Paragraph>
                            ) : (
                              <Text type="secondary" className="text-xs">—</Text>
                            ),
                        },
                        {
                          title: "",
                          key: "change",
                          width: 72,
                          render: (_, r) => {
                            const change = r.deleted ? "deleted" : diff.get(r.id)?.change;
                            return change ? (
                              <StatusMark state={CHANGE[change].state} label={CHANGE[change].text} />
                            ) : null;
                          },
                        },
                      ]}
                    />
                  </div>
                  {session && (
                    <Text type="secondary" className="border-t border-rule bg-surface-raised px-4 py-2 text-xs">
                      本会话的修改 · 基于{session.base_version_id ? "已发布版本" : "空白模型"} · 发布前在发布页预览合并结果
                    </Text>
                  )}
                </div>
              ),
            },
            {
              key: "graph",
              label: "语义图谱",
              children: (
                <div className="relative h-full min-h-review-graph overflow-hidden">
                  {graph?.nodes.length ? (
                    <OntologyGraph
                      graph={graph}
                      query=""
                      onSelect={(selected) => {
                        if (!selected || !session) return;
                        if (selected.category === "node")
                          setInspected({ kind: "object_type", id: selected.item.id, sessionId: session.id, tab: "properties" });
                        else if (selected.item.kind === "link_type")
                          setInspected({ kind: "link_type", id: selected.item.link_type_id ?? selected.item.id, sessionId: session.id });
                      }}
                    />
                  ) : (
                    <Empty className="m-0 p-6" description="暂无构建结果" />
                  )}
                </div>
              ),
            },
          ]}
        />
      </ResultPanel>
      {inspected && <ElementModal request={inspected} onChange={setInspected} onClose={() => setInspected(null)} />}
    </aside>
  );
}
