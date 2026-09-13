import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, workspaceRequest } from "../api/client";
import type { Draft, TypeGraph, VersionSummary } from "../api/types";
import { OntologyGraph } from "./OntologyGraph";
import { ErrorSurface, LoadingSurface } from "./AsyncState";
import "../styles/ontology-reading.css";

export function OntologyReading({
  workspaceId,
  versionId,
  mode,
  graph,
  query,
  tag,
  member,
}: {
  workspaceId: string;
  versionId: string;
  mode: "business" | "technical";
  graph: TypeGraph;
  query: string;
  tag: string;
  member: boolean;
}) {
  const navigate = useNavigate();
  const [model, setModel] = useState<Draft | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [section, setSection] = useState("objects");
  const [code, setCode] = useState<unknown>(null);
  const [codeOpen, setCodeOpen] = useState(false);
  const [codeError, setCodeError] = useState("");
  const [codeSearch, setCodeSearch] = useState("");
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    let active = true;
    setModel(null);
    setError("");
    workspaceRequest<{ model: Draft; version: VersionSummary }>(
      workspaceId,
      `/versions/${versionId}/presentation`,
    )
      .then((r) => {
        if (active) setModel(r.model);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [workspaceId, versionId, attempt]);
  useEffect(() => {
    let active = true;
    setCode(null);
    setCodeError("");
    setCopied(false);
    if (codeOpen)
      api
        .definition(workspaceId, versionId)
        .then((r) => {
          if (active) setCode(r);
        })
        .catch((e: Error) => {
          if (active) setCodeError(e.message);
        });
    return () => {
      active = false;
    };
  }, [workspaceId, versionId, codeOpen]);
  if (error)
    return (
      <ErrorSurface message={error} retry={() => setAttempt(attempt + 1)} />
    );
  if (!model) return <LoadingSurface label="正在读取同版本本体定义…" />;
  const matches = (t: {
    name: string;
    technical_name: string;
    description: string;
    tags: string[];
  }) =>
    (!tag || t.tags.includes(tag)) &&
    `${t.name} ${t.technical_name} ${t.description}`
      .toLowerCase()
      .includes(query.toLowerCase());
  const objects = model.object_types.filter(matches);
  const relations = model.link_types.filter(matches);
  const names = new Map(model.object_types.map((t) => [t.id, t.name]));
  const rules = [
    ...(!query && !tag
      ? (model.requires ?? []).map((expression, i) => ({
          id: `workspace-${i}`,
          name: "工作空间",
          kind: "约束",
          expression,
          href: "../delivery",
        }))
      : []),
    ...[
      ...objects.map((t) => ({ ...t, href: `../objects/${t.id}` })),
      ...relations.map((t) => ({ ...t, href: `../relations/${t.id}` })),
    ].flatMap((t) =>
      [
        t,
        ...("attributes" in t
          ? t.attributes.map((a) => ({
              ...a,
              href: t.href,
              name: `${t.name} · ${a.name}`,
            }))
          : []),
      ].flatMap((owner) =>
        (["requires", "derived_by"] as const).flatMap((kind) =>
          (owner[kind] ?? []).map((expression, i) => ({
            id: `${owner.id}-${kind}-${i}`,
            name: owner.name,
            kind: kind === "requires" ? "约束" : "派生规则",
            expression,
            href: t.href,
          })),
        ),
      ),
    ),
  ];
  const jsonText = code ? JSON.stringify(code, null, 2) : "";
  return (
    <div className="ontology-reading">
      <div className="reading-main">
        <div className="reading-heading">
          <div>
            <h2>{mode === "business" ? "业务概念与口径" : "本体技术定义"}</h2>
            <p className="muted">
              同一已发布版本 · {objects.length} 个对象 · {relations.length}{" "}
              条关系
            </p>
          </div>
          <button
            className="button button--secondary"
            onClick={() => setCodeOpen(!codeOpen)}
          >
            {codeOpen ? "收起标准定义" : "查看标准定义"}
          </button>
        </div>
        {mode === "business" ? (
          <>
            <div className="business-graph">
              <OntologyGraph
                graph={graph}
                  query={query}
                onSelect={(selected) => {
                  if (
                    selected?.category === "node" &&
                    selected.item.kind === "object_type"
                  )
                    navigate(`../objects/${selected.item.id}`);
                  else if (
                    selected?.category === "edge" &&
                    selected.item.kind === "link_type"
                  )
                    navigate(`../relations/${selected.item.id}`);
                }}
              />
            </div>
            <div className="business-object-list">
              {objects.map((t) => (
                <Link key={t.id} to={`../objects/${t.id}`}>
                  <strong>{t.name}</strong>
                  <span>{t.description || "尚未填写业务说明"}</span>
                </Link>
              ))}
            </div>
            <h3>
              规则与约束 <small>{rules.length}</small>
            </h3>
            {rules.length ? (
              <div className="rule-cards">
                {rules.map((rule) => (
                  <article key={rule.id}>
                    <div>
                      <Link to={rule.href}>{rule.name}</Link>
                      <span className="reading-badge">{rule.kind}</span>
                    </div>
                    <code>{rule.expression}</code>
                    <small>已定义 · 尚未启用执行</small>
                  </article>
                ))}
              </div>
            ) : (
              <p className="muted">当前范围没有定义规则或约束。</p>
            )}
          </>
        ) : (
          <>
            <div className="reading-switch" aria-label="技术定义分类">
              {[
                ["objects", "对象"],
                ["relations", "关系"],
                ["rules", "规则与约束"],
                ...(member ? [["mappings", "数据映射"]] : []),
              ].map(([key, label]) => (
                <button
                  key={key}
                  aria-pressed={section === key}
                  onClick={() => setSection(key)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="reading-table">
              <table className="ref-table">
                {section === "objects" && (
                  <>
                    <thead>
                      <tr>
                        <th>业务对象</th>
                        <th>技术名</th>
                        <th>父类型</th>
                        <th>标识属性</th>
                        <th>自有属性</th>
                      </tr>
                    </thead>
                    <tbody>
                      {objects.map((t) => (
                        <tr key={t.id}>
                          <td>
                            <Link to={`../objects/${t.id}`}>{t.name}</Link>
                          </td>
                          <td>
                            <code>{t.technical_name}</code>
                          </td>
                          <td>
                            {t.extends?.map((id) => names.get(id)).join("、") ||
                              "—"}
                          </td>
                          <td>
                            {t.attributes
                              .filter((a) => a.identifier)
                              .map((a) => a.name)
                              .join("、") || "—"}
                          </td>
                          <td>{t.attributes.length}</td>
                        </tr>
                      ))}
                    </tbody>
                  </>
                )}
                {section === "relations" && (
                  <>
                    <thead>
                      <tr>
                        <th>关系</th>
                        <th>起点 → 终点</th>
                        <th>基数</th>
                        <th>标识关系</th>
                      </tr>
                    </thead>
                    <tbody>
                      {relations.map((t) => (
                        <tr key={t.id}>
                          <td>
                            <Link to={`../relations/${t.id}`}>{t.name}</Link>
                            <small>{t.technical_name}</small>
                          </td>
                          <td>
                            {names.get(t.source_type_id)} →{" "}
                            {names.get(t.target_type_id)}
                          </td>
                          <td>{t.multiplicity}</td>
                          <td>{t.identifier ? "是" : "否"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </>
                )}
                {section === "rules" && (
                  <>
                    <thead>
                      <tr>
                        <th>归属</th>
                        <th>类型</th>
                        <th>表达式</th>
                        <th>运行状态</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rules.map((t) => (
                        <tr key={t.id}>
                          <td>
                            <Link to={t.href}>{t.name}</Link>
                          </td>
                          <td>{t.kind}</td>
                          <td>
                            <code>{t.expression}</code>
                          </td>
                          <td>执行未启用</td>
                        </tr>
                      ))}
                    </tbody>
                  </>
                )}
                {section === "mappings" && member && (
                  <>
                    <thead>
                      <tr>
                        <th>业务对象</th>
                        <th>数据源</th>
                        <th>表与主键</th>
                        <th>属性映射</th>
                      </tr>
                    </thead>
                    <tbody>
                      {model.mappings
                        .filter((m) => objects.some((t) => t.id === m.type_id))
                        .map((m) => (
                          <tr key={m.id}>
                            <td>
                              <Link to={`../objects/${m.type_id}`}>
                                {names.get(m.type_id)}
                              </Link>
                            </td>
                            <td>{m.connection_alias}</td>
                            <td>
                              {m.schema_name ? m.schema_name + "." : ""}
                              {m.table_name}
                              <small>{m.key_column}</small>
                            </td>
                            <td>
                              {Object.entries(m.fields)
                                .map(([a, c]) => `${a} → ${c}`)
                                .join("；")}
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </>
                )}
              </table>
            </div>
            {!objects.length && !relations.length && (
              <p className="muted">没有匹配当前条件的本体定义。</p>
            )}
          </>
        )}
      </div>
      {codeOpen && (
        <aside className="definition-code" aria-label="Ossie JSON 标准定义">
          <h3>Ossie JSON</h3>
          <input
            aria-label="搜索标准定义"
            placeholder="搜索概念或字段"
            value={codeSearch}
            onChange={(e) => setCodeSearch(e.target.value)}
          />
          <button
            className="button button--text"
            disabled={!code}
            onClick={() =>
              navigator.clipboard
                .writeText(jsonText)
                .then(() => setCopied(true))
                .catch(() => setCodeError("复制失败，请手动选择文本"))
            }
          >
            {copied ? "已复制" : "复制 JSON"}
          </button>
          {codeError ? (
            <p role="alert">{codeError}</p>
          ) : !code ? (
            <p>正在读取…</p>
          ) : (
            <pre>
              {jsonText.split("\n").map((line, i) => (
                <span
                  key={i}
                  className={
                    codeSearch &&
                    line.toLowerCase().includes(codeSearch.toLowerCase())
                      ? "code-match"
                      : ""
                  }
                >
                  {line}
                  {"\n"}
                </span>
              ))}
            </pre>
          )}
        </aside>
      )}
    </div>
  );
}
