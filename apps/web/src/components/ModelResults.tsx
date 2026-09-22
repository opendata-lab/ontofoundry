import { Box, Braces, Database, GitBranch } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { Draft, ModelingSession, TypeGraph } from "../api/types";
import { EmptyModel } from "./EmptyModel";
import { OntologyGraph } from "./OntologyGraph";

function draftGraph(draft: Draft): TypeGraph {
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

export function ModelResults({ session }: { session: ModelingSession | null }) {
  const [tab, setTab] = useState("models");
  const [kind, setKind] = useState("object_type");
  const [query, setQuery] = useState("");
  const model = session?.draft ?? null;
  const rows =
    kind === "object_type"
      ? (model?.object_types ?? [])
      : kind === "link_type"
        ? (model?.link_types ?? [])
        : kind === "mapping"
          ? (model?.mappings ?? []).map((m) => ({
              ...m,
              name: `${m.connection_alias} · ${m.schema_name ? m.schema_name + "." : ""}${m.table_name}`,
              description: `主键 ${m.key_column}`,
              technical_name: m.table_name,
            }))
          : (model?.object_types.flatMap((t) =>
              t.attributes.map((a) => ({
                ...a,
                description: t.name + " · " + a.value_kind,
              })),
            ) ?? []);
  const categories = [
    {
      key: "object_type",
      text: "实体",
      icon: Box,
      count: model?.object_types.length ?? 0,
      cls: "object",
    },
    {
      key: "link_type",
      text: "关系",
      icon: GitBranch,
      count: model?.link_types.length ?? 0,
      cls: "relation",
    },
    {
      key: "mapping",
      text: "映射",
      icon: Database,
      count: model?.mappings.length ?? 0,
      cls: "mapping",
    },
    {
      key: "attribute",
      text: "属性",
      icon: Braces,
      count:
        model?.object_types.reduce((n, t) => n + t.attributes.length, 0) ?? 0,
      cls: "attribute",
    },
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
        <button
          role="tab"
          aria-selected={tab === "models"}
          onClick={() => setTab("models")}
        >
          本体模型列表
        </button>
        <button
          role="tab"
          aria-selected={tab === "graph"}
          onClick={() => setTab("graph")}
        >
          语义图谱概览
        </button>
      </div>
      {tab === "models" ? (
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
            {visibleRows.map((r) => (
              <details className="result-row" key={r.id}>
                <summary>
                  <span
                    className={
                      "model-icon model-icon--" +
                      (kind === "object_type"
                        ? "object"
                        : kind === "link_type"
                          ? "relation"
                          : "attribute")
                    }
                  >
                    {kind === "object_type" ? (
                      <Box size={13} />
                    ) : kind === "link_type" ? (
                      <GitBranch size={13} />
                    ) : (
                      <Braces size={13} />
                    )}
                  </span>
                  <span className="result-row-title">
                    <strong>{r.name}</strong>
                    <small>{r.technical_name}</small>
                    <p>{r.description || "尚未填写定义"}</p>
                  </span>
                  <span className="result-count">
                    {"attributes" in r ? r.attributes.length + " 属性" : "新版本草稿"}
                  </span>
                </summary>
                <div className="result-expanded">
                  {"attributes" in r && (
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
                  {session && kind === "object_type" && (
                    <Link
                      className="button button--text"
                      to={"../objects/" + r.id + "/edit?session=" + session.id}
                    >
                      编辑本体
                    </Link>
                  )}
                </div>
              </details>
            ))}
            {!visibleRows.length && (
              <EmptyModel
                text={
                  query
                    ? "没有匹配的模型"
                    : model
                      ? "暂无此类模型"
                      : "暂无构建结果"
                }
              />
            )}
          </div>
          {session && (
            <footer className="result-footnote">
              完整的新版本草稿 · 请前往交付页预览差异并发布
            </footer>
          )}
        </>
      ) : (
        <div className="result-graph">
          {model?.object_types.length ? (
            <OntologyGraph
              graph={draftGraph(model)}
              query=""
              onSelect={() => undefined}
            />
          ) : (
            <EmptyModel />
          )}
        </div>
      )}
    </aside>
  );
}
