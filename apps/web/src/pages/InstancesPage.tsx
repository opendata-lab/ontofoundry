import {
  ArrowLeft,
  Box,
  Search,
  Network,
  FileText,
  Database,
} from "lucide-react";
import { useEffect, useState } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { workspaceRequest } from "../api/client";
import type { DocumentObject, DocumentLink } from "../api/types";
import { instanceNeighborhood } from "../lib/instanceGraph";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { useSnapshot } from "../hooks/useSnapshot";
import { usePageTab } from "../hooks/usePageTab";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { EmptyModel } from "../components/EmptyModel";
import { OntologyGraph } from "../components/OntologyGraph";

export function InstancesPage() {
  const { workspace } = useWorkspaceContext();
  const { typeId, objectId } = useParams();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const dbKey = params.get("key");
  const sessionId = params.get("session");
  const databaseDetail = objectId === "database" && dbKey !== null;
  const { draft, error, load, suffix } = useSnapshot(workspace);
  const [source, setSource] = useState(params.get("source") ?? "document");
  const [depth, setDepth] = useState(1);
  const [neighborhood, setNeighborhood] = useState<{
    center_id: string;
    objects: (DocumentObject & { key: string })[];
    links: DocumentLink[];
    warnings: string[];
    truncated: boolean;
  } | null>(null);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [databaseRows, setDatabaseRows] = useState<Record<string, unknown>[]>(
    [],
  );
  const [more, setMore] = useState(false);
  const [dbError, setDbError] = useState("");
  const [loading, setLoading] = useState(false);
  const [graphOpen, setGraphOpen] = useState(false);
  const mapping = draft?.mappings.find((m) => m.type_id === typeId);
  useEffect(() => {
    setDepth(1);
    setGraphOpen(false);
  }, [typeId, objectId, dbKey]);
  useEffect(() => {
    setNeighborhood(null);
    if (!databaseDetail) return;
    let active = true;
    setLoading(true);
    setDbError("");
    workspaceRequest<NonNullable<typeof neighborhood>>(
      workspace.id,
      "/instance-neighborhood",
      {
        type_id: typeId,
        key: dbKey,
        session_id: sessionId,
        depth,
      },
    )
      .then((r) => {
        if (active) setNeighborhood(r);
      })
      .catch((e: Error) => {
        if (active) setDbError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [workspace.id, typeId, databaseDetail, dbKey, sessionId, depth]);
  useEffect(() => {
    if (objectId || source !== "database" || !mapping) return;
    let active = true;
    setLoading(true);
    setDbError("");
    const timer = setTimeout(
      () =>
        workspaceRequest<{
          items: Record<string, unknown>[];
          has_more: boolean;
        }>(workspace.id, "/mapping-preview", {
          mapping,
          q: query,
          offset: page * 20,
          limit: 20,
        })
          .then((r) => {
            if (!active) return;
            setDatabaseRows(r.items);
            setMore(r.has_more);
          })
          .catch((e: Error) => {
            if (active) setDbError(e.message);
          })
          .finally(() => {
            if (active) setLoading(false);
          }),
      250,
    );
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [mapping, source, query, page, workspace.id, objectId]);
  const type = draft?.object_types.find((t) => t.id === typeId);
  const object = databaseDetail
    ? neighborhood?.objects.find((o) => o.id === neighborhood.center_id)
    : draft?.objects.find((o) => o.id === objectId && o.type_id === typeId);
  usePageTab({
    title: object
      ? `实例 · ${object.name}`
      : type
        ? `${type.name} · ${objectId ? "实例详情" : "实例列表"}`
        : undefined,
  });
  if (error) return <ErrorSurface message={error} retry={load} />;
  if (!draft) return <LoadingSurface label="正在读取实例…" />;
  if (!type) return <EmptyModel text="没有找到业务对象" />;
  const all = draft.objects.filter((o) => o.type_id === typeId);
  const filtered = all.filter((o) =>
    (o.name + JSON.stringify(o.values))
      .toLowerCase()
      .includes(query.toLowerCase()),
  );
  const availableObjects = databaseDetail
    ? (neighborhood?.objects ?? [])
    : draft.objects;
  const availableLinks = databaseDetail
    ? (neighborhood?.links ?? [])
    : draft.links;
  const links = object
    ? availableLinks.filter(
        (l) => l.source_id === object.id || l.target_id === object.id,
      )
    : [];
  const related = links
    .map((l) => ({
      link: l,
      object: availableObjects.find(
        (o) =>
          o.id === (l.source_id === object?.id ? l.target_id : l.source_id),
      ),
    }))
    .filter((x) => x.object);
  const dbLink = (tid: string, key: string) => {
    const query = new URLSearchParams({ source: "database", key });
    if (sessionId) query.set("session", sessionId);
    return `/workspaces/${workspace.id}/objects/${tid}/instances/database?${query}`;
  };
  const linkTo = (o: DocumentObject) =>
    "key" in o
      ? dbLink(o.type_id, String(o.key))
      : `/workspaces/${workspace.id}/objects/${o.type_id}/instances/${o.id}${suffix}`;
  const neighborhoodGraph = object
    ? instanceNeighborhood(availableObjects, availableLinks, object.id, depth)
    : { objects: [], links: [] };
  return (
    <div className="ref-detail-page">
      <header className="breadcrumb-bar">
        <Link to={"../objects" + suffix}>
          <ArrowLeft size={14} />
          业务对象
        </Link>
        <span>/</span>
        <Link to={"../objects/" + type.id + suffix}>{type.name}</Link>
        <span>/</span>
        <Link to={"../objects/" + type.id + "/instances" + suffix}>
          实例列表
        </Link>
        {object && (
          <>
            <span>/</span>
            <span>{object.name}</span>
          </>
        )}
      </header>
      <div className="detail-identity">
        <span className="catalog-object-icon">
          <Box size={23} />
        </span>
        <div>
          <h1>{object?.name ?? type.name}</h1>
          <small>
            {type.name} / {type.technical_name}
          </small>
        </div>
        <div className="toolbar-spacer" />
        {object && (
          <button
            className="button button--primary"
            onClick={() => setGraphOpen(!graphOpen)}
          >
            <Network size={14} />
            {graphOpen ? "返回详情" : "实例图谱"}
          </button>
        )}
      </div>
      {objectId && dbError && <p className="inline-error">{dbError}</p>}
      {databaseDetail &&
        neighborhood?.warnings.map((w) => (
          <p className="muted" key={w}>
            {w}
          </p>
        ))}
      {neighborhood?.truncated && (
        <p className="muted">
          已达到查询范围上限，当前结果仅为部分关系。请缩小范围或选择新的中心实例。
        </p>
      )}
      {!objectId ? (
        <>
          <div className="instance-search">
            <label className="ref-search">
              <input
                placeholder="请输入关键字"
                aria-label="搜索实例"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPage(0);
                }}
              />
              <Search size={16} />
            </label>
            <select
              aria-label="实例来源"
              value={source}
              onChange={(e) => {
                setSource(e.target.value);
                setPage(0);
              }}
            >
              <option value="document">文档实例</option>
              <option value="database" disabled={!mapping}>
                数据库实例{mapping ? "" : "（未映射）"}
              </option>
            </select>
          </div>
          <div className="ref-tabs detail-tabs">
            <span className="active-tab">实例列表</span>
          </div>
          <div className="instance-table-wrap">
            {dbError && <p className="inline-error">{dbError}</p>}
            {loading ? (
              <p className="muted">正在按映射查询…</p>
            ) : (
              <table className="ref-table">
                <thead>
                  <tr>
                    <th>名称 / 标识</th>
                    {type.attributes.slice(0, 4).map((a) => (
                      <th key={a.id}>{a.name}</th>
                    ))}
                    <th>来源</th>
                  </tr>
                </thead>
                <tbody>
                  {source === "document"
                    ? filtered.slice(page * 20, page * 20 + 20).map((o) => (
                        <tr key={o.id}>
                          <td>
                            <Link className="text-link" to={linkTo(o)}>
                              {o.name}
                            </Link>
                          </td>
                          {type.attributes.slice(0, 4).map((a) => (
                            <td key={a.id}>
                              {String(o.values[a.technical_name] ?? "—")}
                            </td>
                          ))}
                          <td>
                            <FileText size={13} />
                            文档
                          </td>
                        </tr>
                      ))
                    : databaseRows.map((o, i) => (
                        <tr key={i}>
                          <td>
                            <Link
                              className="text-link"
                              to={dbLink(type.id, String(o.__key))}
                            >
                              {String(o.__key)}
                            </Link>
                          </td>
                          {type.attributes.slice(0, 4).map((a) => (
                            <td key={a.id}>
                              {String(o[a.technical_name] ?? "—")}
                            </td>
                          ))}
                          <td>
                            <Database size={13} />
                            实时查询
                          </td>
                        </tr>
                      ))}
                </tbody>
              </table>
            )}
            {source === "document" && !filtered.length && (
              <EmptyModel text="暂无文档实例，可从建模材料中抽取" />
            )}
            <footer className="pagination">
              <span>
                {source === "document"
                  ? "共 " + filtered.length + " 条"
                  : "按需查询 · 每页 20 条"}
              </span>
              <button
                className="button button--text"
                disabled={page === 0}
                onClick={() => setPage(page - 1)}
              >
                上一页
              </button>
              <b>{page + 1}</b>
              <button
                className="button button--text"
                disabled={
                  source === "document"
                    ? (page + 1) * 20 >= filtered.length
                    : !more
                }
                onClick={() => setPage(page + 1)}
              >
                下一页
              </button>
            </footer>
          </div>
        </>
      ) : loading ? (
        <LoadingSurface label="正在查询实例及关联关系…" />
      ) : !object ? (
        <EmptyModel text="此实例不存在" />
      ) : graphOpen ? (
        <div className="instance-graph">
          <OntologyGraph
            mode="semantic"
            query=""
            graph={{
              workspace_id: workspace.id,
              version_id: "instances",
              version_sha256: "",
              nodes: neighborhoodGraph.objects
                .filter((o, i, a) => a.findIndex((x) => x.id === o.id) === i)
                .map((o) => ({
                  id: o.id,
                  kind: "object_type",
                  label: o.name,
                  technical_name:
                    draft.object_types.find((t) => t.id === o.type_id)?.name ??
                    "",
                  description: databaseDetail ? "数据库实例" : "文档实例",
                  tags: [],
                })),
              edges: neighborhoodGraph.links.map((l) => ({
                id: l.id,
                kind: "link_type",
                label:
                  draft.link_types.find((t) => t.id === l.type_id)?.name ??
                  "关系",
                technical_name: "document",
                source: l.source_id,
                target: l.target_id,
              })),
            }}
            onSelect={(selected) => {
              if (selected?.category === "node") {
                const next = availableObjects.find(
                  (o) => o.id === selected.item.id,
                );
                if (next && next.id !== object.id) navigate(linkTo(next));
              }
            }}
          />
          <div className="graph-caption">
            {databaseDetail ? "数据库只读 Join" : "文档原生实例"} ·{" "}
            <label>
              展开范围{" "}
              <select
                aria-label="实例图谱深度"
                value={depth}
                onChange={(e) => setDepth(Number(e.target.value))}
              >
                <option value={1}>1 跳</option>
                <option value={2}>2 跳</option>
                <option value={3}>3 跳</option>
              </select>
            </label>{" "}
            · 点击其他节点设为中心
          </div>
        </div>
      ) : (
        <div className="instance-detail-content">
          <div className="property-tiles">
            {type.attributes.slice(0, 4).map((a) => (
              <div key={a.id}>
                <span>{a.name}</span>
                <strong>
                  {String(object.values[a.technical_name] ?? "—")}
                </strong>
              </div>
            ))}
          </div>
          <section className="detail-section">
            <h2>全部属性</h2>
            <dl className="ref-definition">
              {type.attributes.map((a) => (
                <div key={a.id}>
                  <dt>{a.name}</dt>
                  <dd>{String(object.values[a.technical_name] ?? "—")}</dd>
                </div>
              ))}
            </dl>
          </section>
          <div className="instance-related-columns">
            <section className="detail-section">
              <h2>关联关系</h2>
              {related.length ? (
                related.map((r) => (
                  <Link
                    className="relation-list-row"
                    key={r.link.id}
                    to={linkTo(r.object!)}
                  >
                    <Network size={15} />
                    {
                      draft.link_types.find((t) => t.id === r.link.type_id)
                        ?.name
                    }
                    <strong>{r.object!.name}</strong>
                  </Link>
                ))
              ) : (
                <EmptyModel text="暂无关联关系" />
              )}
            </section>
            <section className="detail-section">
              <h2>来源证据</h2>
              {databaseDetail ? (
                <p>
                  数据库实时查询 · {mapping?.table_name}
                  <br />
                  标识字段：{mapping?.key_column}
                  <br />
                  没有全量同步或写回源系统。
                </p>
              ) : object.evidence.length ? (
                object.evidence.map((ev, i) => (
                  <div className="evidence" key={i}>
                    <a
                      href={
                        "/api/v1/workspaces/" +
                        workspace.id +
                        "/materials/" +
                        ev.material_id
                      }
                      target="_blank"
                      rel="noreferrer"
                    >
                      <FileText size={14} />
                      查看原文 {ev.line_start}–{ev.line_end} 行
                    </a>
                    <p>{ev.quote}</p>
                  </div>
                ))
              ) : (
                <EmptyModel text="暂无文档证据" />
              )}
            </section>
          </div>
        </div>
      )}
    </div>
  );
}
