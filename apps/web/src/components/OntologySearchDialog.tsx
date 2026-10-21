import { Button, Empty, Input, Modal, Spin, Typography } from "antd";
import { Box, Database, GitBranch, ListTree, Search, Shapes, ShieldCheck, Sigma } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { OntologySearchHit, OntologySearchKind, OntologySearchResult } from "../api/types";
import { elementHref } from "../lib/elementInspector";

const ICONS: Record<OntologySearchKind, typeof Box> = {
  object_type: Box,
  property: ListTree,
  link_type: GitBranch,
  rule: ShieldCheck,
  metric: Sigma,
  dataset: Database,
  value_type: Shapes,
};
const KIND_LABELS: Record<OntologySearchKind, string> = {
  object_type: "实体",
  property: "属性",
  link_type: "关系",
  rule: "规则",
  metric: "指标",
  dataset: "数据集",
  value_type: "值类型",
};
const RELATION_LABELS: Record<string, string> = {
  metric_dataset_bound_type: "指标数据集绑定的实体",
  metric_numerator: "比率指标的分子",
  metric_denominator: "比率指标的分母",
  object_title_property: "标题属性",
  object_link_type: "实体的关系",
  property_owner: "所属实体",
  link_source_type: "关系起点",
  link_target_type: "关系终点",
};
// Value types have no detail page of their own yet.
const NAVIGABLE = new Set<OntologySearchKind>(["object_type", "property", "link_type", "rule", "metric", "dataset"]);
const label = (hit: Pick<OntologySearchHit, "display_name" | "name">) => hit.display_name || hit.name;

function matchText(hit: OntologySearchHit, names: Map<string, string>) {
  const { match } = hit;
  if (match.via) {
    const from = names.get(match.via.id);
    const relation = RELATION_LABELS[match.via.relation] ?? match.via.relation;
    return from ? `由「${from}」扩展：${relation}` : `关系扩展：${relation}`;
  }
  if (match.by === "description") return "描述命中";
  return match.text ? `命中「${match.text}」` : "名称命中";
}

/** Global search over the published ontology, ranked by the platform search service. */
export function OntologySearchDialog({ workspaceId, open, onClose }: { workspaceId: string; open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<OntologySearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const latest = useRef(0);

  useEffect(() => {
    if (!open) { setQuery(""); setResult(null); setError(""); }
  }, [open]);
  useEffect(() => {
    const text = query.trim();
    const ticket = ++latest.current;
    if (!open || !text) { setResult(null); setLoading(false); return; }
    setLoading(true);
    // Wait for typing to pause; only the newest query may update the list.
    const timer = window.setTimeout(() => {
      api.searchOntology(workspaceId, { query: text, limit: 20 })
        .then((value) => { if (ticket === latest.current) { setResult(value); setError(""); } })
        .catch((e: Error) => { if (ticket === latest.current) setError(e.message); })
        .finally(() => { if (ticket === latest.current) setLoading(false); });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [open, query, workspaceId]);

  const more = () => {
    if (!result?.next_cursor) return;
    const ticket = latest.current;
    setLoading(true);
    api.searchOntology(workspaceId, { query: query.trim(), limit: 20, cursor: result.next_cursor })
      .then((value) => { if (ticket === latest.current) setResult({ ...value, items: [...result.items, ...value.items] }); })
      .catch((e: Error) => { if (ticket === latest.current) setError(e.message); })
      .finally(() => { if (ticket === latest.current) setLoading(false); });
  };
  const names = new Map((result?.items ?? []).map((hit) => [hit.id, label(hit)]));
  const go = (hit: OntologySearchHit) => {
    onClose();
    navigate(elementHref(workspaceId, { kind: hit.kind, id: hit.id, sessionId: null }));
  };

  return (
    <Modal open={open} onCancel={onClose} title="搜索已发布本体" footer={null} destroyOnHidden>
      <Input
        autoFocus
        allowClear
        prefix={<Search className="size-icon" />}
        aria-label="搜索关键词"
        placeholder="输入业务问题或名称，如：近三个月的采购金额"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {!!result?.unmatched_terms.length && (
        <Typography.Text type="secondary" className="mt-2 block text-xs">
          未匹配到定义：{result.unmatched_terms.join("、")}
        </Typography.Text>
      )}
      {error && <Typography.Text type="danger" className="mt-2 block text-xs">{error}</Typography.Text>}
      <div className="mt-3 flex max-h-app-search flex-col overflow-auto" role="list" aria-label="搜索结果">
        {result?.items.map((hit) => {
          const Icon = ICONS[hit.kind] ?? Box;
          const navigable = NAVIGABLE.has(hit.kind);
          return (
            <Button
              key={`${hit.kind}:${hit.id}`}
              role="listitem"
              type="text"
              disabled={!navigable}
              className="h-auto justify-start gap-2 py-2 text-left whitespace-normal"
              onClick={() => go(hit)}
            >
              <Icon className="size-icon shrink-0" />
              <span className="flex min-w-0 flex-col">
                <span className="flex flex-wrap items-center gap-2">
                  <span>{label(hit)}</span>
                  <code className="text-xs text-muted">{hit.name}</code>
                  <Typography.Text type="secondary" className="text-xs">
                    {KIND_LABELS[hit.kind] ?? hit.kind}
                    {hit.owner ? ` · ${label(hit.owner)}` : ""}
                    {hit.source && hit.target ? ` · ${label(hit.source)} → ${label(hit.target)}` : ""}
                  </Typography.Text>
                </span>
                <Typography.Text type="secondary" className="text-xs">{matchText(hit, names)}</Typography.Text>
              </span>
            </Button>
          );
        })}
        {loading && <Spin className="py-3" size="small" />}
        {!loading && result && !result.items.length && <Empty description="没有匹配的定义" />}
        {!loading && !result && !query.trim() && <Empty description="输入名称、同义词或一句业务问题" />}
        {!loading && result?.next_cursor && <Button type="link" onClick={more}>加载更多</Button>}
      </div>
    </Modal>
  );
}
