import {
  Box,
  Braces,
  Database,
  FileText,
  GitBranch,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import type {
  DraftView,
  ElementChange,
  ModelingSession,
  TypeGraph,
} from "../api/types";
import type { ProposalsState } from "../hooks/useProposals";
import { toView } from "../lib/draftView";
import { EmptyModel } from "./EmptyModel";
import { OntologyGraph } from "./OntologyGraph";
import { ProposalPanel } from "./proposals/ProposalPanel";

function draftGraph(draft: DraftView): TypeGraph {
  return {
    workspace_id: draft.workspace_id,
    version_id: "draft",
    version_sha256: "",
    nodes: draft.object_types.map((t) => ({
      id: t.id,
      kind: "object_type",
      label: t.name,
      technical_name: t.technical_name,
      description: t.description,
      tags: t.tags,
      attribute_count: t.attributes.length,
    })),
    edges: draft.link_types.map((r) => ({
      id: r.id,
      kind: "link_type",
      label: r.name,
      technical_name: r.technical_name,
      source: r.source_type_id,
      target: r.target_type_id,
      description: r.description,
      multiplicity: r.multiplicity,
    })),
  };
}

type Row = {
  id: string;
  name: string;
  technical_name: string;
  description: string;
  attributes?: DraftView["object_types"][number]["attributes"];
  deleted?: boolean;
};

const CHANGE_LABEL: Record<ElementChange["change"], string> = {
  created: "新增",
  updated: "已修改",
  deleted: "待删除",
};

type Panel = "proposals" | "draft" | "graph";

export function ModelResults({
  session,
  proposals,
  running = false,
  onRemodel = () => undefined,
}: {
  session: ModelingSession | null;
  proposals?: ProposalsState;
  running?: boolean;
  onRemodel?: (text: string) => void;
}) {
  const [params, setParams] = useSearchParams();
  const pending = session?.pending_proposal_count ?? 0;
  const requested = params.get("panel") as Panel | null;
  const [tab, setTabState] = useState<Panel>(
    requested ?? (proposals && pending > 0 ? "proposals" : "draft"),
  );
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
    if (previous !== undefined && session && session.revision > previous && tab === "proposals")
      setFresh((n) => n + 1);
  }, [session, tab]);

  const [kind, setKind] = useState("object_type");
  const [query, setQuery] = useState("");
  const model = session ? toView(session.draft) : null;
  const diff = new Map((session?.base_diff ?? []).map((c) => [c.element_id, c]));
  const deleted = (session?.base_diff ?? []).filter((c) => c.change === "deleted");
  const deletedRows = (target: string): Row[] =>
    deleted
      .filter((c) => c.element_kind === target)
      .map((c) => ({
        id: c.element_id,
        name: c.label,
        technical_name: String(c.before?.technical_name ?? ""),
        description: String(c.before?.description ?? ""),
        deleted: true,
      }));
  const rules = session?.draft.rules ?? [];
  const actions = session?.draft.actions ?? [];
  const rows: Row[] =
    kind === "object_type"
      ? [...(model?.object_types ?? []), ...deletedRows("object_type")]
      : kind === "link_type"
        ? [...(model?.link_types ?? []), ...deletedRows("link_type")]
        : kind === "mapping"
          ? (model?.mappings ?? []).map((m) => ({
              ...m,
              name: `${m.connection_alias} · ${m.schema_name ? m.schema_name + "." : ""}${m.table_name}`,
              description: `主键 ${m.key_column}`,
              technical_name: m.table_name,
            }))
          : kind === "rule"
            ? [
                ...rules.map((r) => ({
                  id: r.id,
                  name: r.name,
                  technical_name: r.technical_name,
                  description: r.expression,
                })),
                ...deletedRows("rule"),
              ]
            : kind === "action"
              ? [
                  ...actions.map((a) => ({
                    id: a.id,
                    name: a.name,
                    technical_name: a.technical_name,
                    description: a.description || "仅定义 · 不可执行",
                  })),
                  ...deletedRows("action"),
                ]
              : kind === "instance"
                ? (model?.objects ?? []).map((o) => ({
                    id: o.id,
                    name: o.name,
                    technical_name: "",
                    description:
                      model?.object_types.find((t) => t.id === o.type_id)?.name ?? "",
                  }))
                : (model?.object_types.flatMap((t) =>
                    t.attributes.map((a) => ({
                      ...a,
                      description: t.name + " · " + a.value_kind,
                    })),
                  ) ?? []);
  const categories = [
    { key: "object_type", text: "实体", icon: Box, count: model?.object_types.length ?? 0, cls: "object" },
    { key: "link_type", text: "关系", icon: GitBranch, count: model?.link_types.length ?? 0, cls: "relation" },
    { key: "attribute", text: "属性", icon: Braces, count: model?.object_types.reduce((n, t) => n + t.attributes.length, 0) ?? 0, cls: "attribute" },
    { key: "rule", text: "规则", icon: ShieldCheck, count: rules.length, cls: "rule" },
    { key: "action", text: "Action", icon: Zap, count: actions.length, cls: "action" },
    { key: "instance", text: "材料实例", icon: FileText, count: model?.objects.length ?? 0, cls: "instance" },
    { key: "mapping", text: "映射", icon: Database, count: model?.mappings.length ?? 0, cls: "mapping" },
  ];
  const warnings = session?.result_warnings ?? [];
  const visibleRows = rows.filter((r) =>
    (r.name + r.technical_name + r.description)
      .toLowerCase()
      .includes(query.toLowerCase()),
  );

  return (
    <aside className="ref-results">
      {warnings.length > 0 && (
        <div className="result-warnings" role="status">
          {warnings.map((text) => (
            <p key={text}>{text}</p>
          ))}
        </div>
      )}
      <div className="ref-tabs" role="tablist" aria-label="构建结果">
        {proposals && (
          <button role="tab" aria-selected={tab === "proposals"} onClick={() => setTab("proposals")}>
            提案 {pending > 0 && <span className="tab-badge">{pending}</span>}
          </button>
        )}
        <button role="tab" aria-selected={tab === "draft"} onClick={() => setTab("draft")}>
          本体草稿 {fresh > 0 && <span className="tab-badge tab-badge--fresh">+{fresh}</span>}
        </button>
        <button role="tab" aria-selected={tab === "graph"} onClick={() => setTab("graph")}>
          语义图谱
        </button>
      </div>
      {tab === "proposals" && proposals ? (
        <ProposalPanel session={session} proposals={proposals} running={running} onRemodel={onRemodel} />
      ) : tab === "draft" ? (
        <>
          <div className="category-grid">
            {categories.map((c) => (
              <button
                key={c.key}
                className={"category category--" + c.cls}
                aria-pressed={kind === c.key}
                onClick={() => setKind(c.key)}
              >
                <c.icon size={15} />
                <span>{c.text}</span>
                <b>{c.count}</b>
              </button>
            ))}
          </div>
          <label className="ref-search results-search">
            <input
              aria-label="搜索模型"
              placeholder="搜索名称、API 标识、描述等"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="result-list">
            {visibleRows.map((r) => {
              const change = r.deleted ? "deleted" : diff.get(r.id)?.change;
              return (
                <details className={"result-row" + (r.deleted ? " result-row--deleted" : "")} key={r.id}>
                  <summary>
                    <span className="result-row-title">
                      <strong>{r.name}</strong>
                      <small>{r.technical_name}</small>
                      <p>{r.description || "尚未填写定义"}</p>
                    </span>
                    {change && <span className={`tag tag--change-${change}`}>{CHANGE_LABEL[change]}</span>}
                    {r.attributes && <span className="result-count">{r.attributes.length} 属性</span>}
                  </summary>
                  <div className="result-expanded">
                    {r.attributes && (
                      <table>
                        <tbody>
                          {r.attributes.map((a) => (
                            <tr key={a.id}>
                              <td>
                                <Braces size={12} />
                                {a.name}
                              </td>
                              <td>{a.technical_name}</td>
                              <td>{a.value_kind}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                    {session && kind === "object_type" && !r.deleted && (
                      <Link className="button button--text" to={"../objects/" + r.id + "/edit?session=" + session.id}>
                        编辑本体
                      </Link>
                    )}
                  </div>
                </details>
              );
            })}
            {!visibleRows.length && (
              <EmptyModel text={query ? "没有匹配的模型" : model ? "暂无此类模型" : "暂无构建结果"} />
            )}
          </div>
          {session && (
            <footer className="result-footnote">
              会话草稿 · 基于 {session.base_version_id ? "已发布版本" : "空白模型"} · r{session.revision} ·
              发布前需预览合并结果
            </footer>
          )}
        </>
      ) : (
        <div className="result-graph">
          {model?.object_types.length ? (
            <OntologyGraph graph={draftGraph(model)} query="" onSelect={() => undefined} />
          ) : (
            <EmptyModel />
          )}
        </div>
      )}
    </aside>
  );
}
