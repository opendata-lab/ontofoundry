import { Box, GitBranch, Braces, Check, X, FileText } from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import type {
  Candidate,
  Draft,
  ModelingSession,
  TypeGraph,
} from "../api/types";
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

export function ModelResults({
  session,
  busy,
  onCandidate,
}: {
  session: ModelingSession | null;
  busy: boolean;
  onCandidate: (ids: string[], action: string) => void;
}) {
  const [tab, setTab] = useState("models");
  const [kind, setKind] = useState("object_type");
  const [query, setQuery] = useState("");
  const pending =
    session?.candidates.filter((c) => c.status === "pending") ?? [];
  const model = useMemo(() => {
    if (!session) return null;
    const d = structuredClone(session.draft);
    for (const c of session.candidates.filter((c) => c.status === "pending")) {
      if (c.kind === "object_type")
        d.object_types = [
          ...d.object_types.filter((t) => t.id !== c.value.id),
          c.value,
        ];
      if (c.kind === "link_type")
        d.link_types = [
          ...d.link_types.filter((t) => t.id !== c.value.id),
          c.value,
        ];
    }
    return d;
  }, [session]);
  const rows =
    kind === "object_type"
      ? (model?.object_types ?? [])
      : kind === "link_type"
        ? (model?.link_types ?? [])
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
      key: "attribute",
      text: "属性",
      icon: Braces,
      count:
        model?.object_types.reduce((n, t) => n + t.attributes.length, 0) ?? 0,
      cls: "attribute",
    },
  ];
  const candidateFor = (id: string): Candidate | undefined =>
    pending.find((c) => "id" in c.value && c.value.id === id);
  return (
    <aside className="ref-results">
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
          {pending.some((c) => c.kind !== "clarification") && (
            <div className="candidate-actions">
              <span>{pending.length} 项候选</span>
              <button
                className="button button--text"
                disabled={busy}
                onClick={() =>
                  onCandidate(
                    pending
                      .filter((c) => !c.conflict && c.kind !== "clarification")
                      .map((c) => c.id),
                    "accept",
                  )
                }
              >
                接受全部无冲突项
              </button>
            </div>
          )}
          <div className="result-list">
            {rows
              .filter((r) =>
                (r.name + r.technical_name + r.description)
                  .toLowerCase()
                  .includes(query.toLowerCase()),
              )
              .map((r) => {
                const candidate = candidateFor(r.id);
                return (
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
                      <span
                        className={
                          candidate ? "candidate-badge" : "result-count"
                        }
                      >
                        {candidate
                          ? "候选"
                          : "attributes" in r
                            ? r.attributes.length + " 属性"
                            : "草稿"}
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
                      {candidate && (
                        <>
                          <p>{candidate.reason}</p>
                          {candidate.evidence?.map((ev, i) => (
                            <a
                              key={i}
                              className="evidence-link"
                              target="_blank"
                              rel="noreferrer"
                              href={
                                "/api/v1/workspaces/" +
                                session?.workspace_id +
                                "/materials/" +
                                ev.material_id
                              }
                            >
                              <FileText size={13} />
                              原文 {ev.line_start}–{ev.line_end} 行
                            </a>
                          ))}
                          {candidate.conflict && (
                            <p className="inline-error">{candidate.conflict}</p>
                          )}
                          <div className="result-actions">
                            <button
                              className="button button--primary"
                              disabled={busy}
                              onClick={() =>
                                onCandidate([candidate.id], "accept")
                              }
                            >
                              <Check size={13} />
                              接受
                            </button>
                            <button
                              className="button button--text"
                              disabled={busy}
                              onClick={() =>
                                onCandidate([candidate.id], "ignore")
                              }
                            >
                              <X size={13} />
                              忽略
                            </button>
                          </div>
                        </>
                      )}
                      {!candidate && session && kind === "object_type" && (
                        <Link
                          className="button button--text"
                          to={
                            "../objects/" + r.id + "/edit?session=" + session.id
                          }
                        >
                          编辑本体
                        </Link>
                      )}
                    </div>
                  </details>
                );
              })}
            {!rows.some((r) =>
              (r.name + r.technical_name + r.description)
                .toLowerCase()
                .includes(query.toLowerCase()),
            ) && (
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
          {pending.some((c) => c.kind === "object" || c.kind === "link") && (
            <details className="result-row">
              <summary>
                文档实例与实例关系 ·{" "}
                {
                  pending.filter(
                    (c) => c.kind === "object" || c.kind === "link",
                  ).length
                }{" "}
                项待确认
              </summary>
              <div className="result-expanded">
                {pending
                  .filter((c) => c.kind === "object" || c.kind === "link")
                  .map((c) => (
                    <section key={c.id}>
                      <strong>
                        {c.kind === "object" ? c.value.name : "实例关系"}
                      </strong>
                      <p>{c.reason}</p>
                      {c.kind === "object" && (
                        <dl className="ref-definition">
                          {Object.entries(c.value.values).map(([k, v]) => (
                            <div key={k}>
                              <dt>{k}</dt>
                              <dd>{String(v ?? "—")}</dd>
                            </div>
                          ))}
                        </dl>
                      )}
                      {c.kind === "link" && (
                        <p>
                          {c.value.source_id} → {c.value.target_id}
                        </p>
                      )}
                      {c.evidence?.map((ev, i) => (
                        <p className="evidence" key={i}>
                          {ev.quote}（{ev.line_start}–{ev.line_end} 行）
                        </p>
                      ))}
                      {c.conflict && (
                        <p className="inline-error">{c.conflict}</p>
                      )}
                      <div className="result-actions">
                        <button
                          className="button button--primary"
                          disabled={busy}
                          onClick={() => onCandidate([c.id], "accept")}
                        >
                          接受
                        </button>
                        <button
                          className="button button--text"
                          disabled={busy}
                          onClick={() => onCandidate([c.id], "ignore")}
                        >
                          忽略
                        </button>
                      </div>
                    </section>
                  ))}
              </div>
            </details>
          )}
          {pending
            .filter((c) => c.kind === "clarification")
            .map((c) => (
              <div className="clarification" key={c.id}>
                <strong>待澄清</strong>
                <p>{c.reason}</p>
              </div>
            ))}
          {session && (
            <footer className="result-footnote">
              草稿 + 待确认候选 · 接受后才写入草稿
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
