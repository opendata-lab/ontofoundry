import { materialLinkEndpoints } from "../../lib/instanceGraph";
import { ArrowRight, Search, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { Draft, MaterialObject } from "../../api/types";
import { workspaceRequest } from "../../api/client";
import {
  inheritedProperties,
  isObject,
  type PanelProps,
} from "../../lib/elementModel";
import { EvidenceSection } from "./ElementPanels";

const PAGE_SIZE = 6;
export function ElementInstances({
  draft,
  type,
  open,
  sessionId,
  canBrowseDatabase,
  initialObjectId,
}: PanelProps & {
  sessionId: string | null;
  canBrowseDatabase: boolean;
  initialObjectId?: string;
}) {
  const mapping = draft.mappings.find((m) => m.type_id === type.id);
  const [source, setSource] = useState(() =>
    !initialObjectId &&
    canBrowseDatabase &&
    mapping &&
    !draft.material_objects.some((o) => o.type_id === type.id)
      ? "database"
      : "document",
  );
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [more, setMore] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<MaterialObject | null>(
    draft.material_objects.find((o) => o.id === initialObjectId) ?? null,
  );
  const [neighbors, setNeighbors] = useState<{
    objects: (MaterialObject & { key: string })[];
    links: Draft["material_links"];
    warnings: string[];
    truncated: boolean;
  } | null>(null);
  useEffect(() => {
    if (source !== "database" || !mapping || !canBrowseDatabase) return;
    let active = true;
    const timer = window.setTimeout(() => {
      setBusy(true);
      setError("");
      workspaceRequest<{ items: Record<string, unknown>[]; has_more: boolean }>(
        draft.workspace_id,
        "/mapping-preview",
        { mapping, q: query, offset: page * PAGE_SIZE, limit: PAGE_SIZE },
      )
        .then((result) => {
          if (active) {
            setRows(result.items);
            setMore(result.has_more);
          }
        })
        .catch((e: Error) => {
          if (active) setError(e.message);
        })
        .finally(() => {
          if (active) setBusy(false);
        });
    }, 250);
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [source, mapping, query, page, draft.workspace_id, canBrowseDatabase]);
  const visitDatabase = async (typeId: string, key: string) => {
    if (!canBrowseDatabase) return;
    setBusy(true);
    setError("");
    try {
      const result = await workspaceRequest<
        NonNullable<typeof neighbors> & { center_id: string }
      >(draft.workspace_id, "/instance-neighborhood", {
        type_id: typeId,
        key,
        session_id: sessionId,
        depth: 1,
      });
      setNeighbors(result);
      setSelected(
        result.objects.find((o) => o.id === result.center_id) ?? null,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "读取实例失败");
    } finally {
      setBusy(false);
    }
  };
  const objects = neighbors?.objects ?? draft.material_objects;
  const links = (neighbors?.links ?? draft.material_links).map((fact) => ({
    ...fact,
    ...materialLinkEndpoints(
      fact,
      draft.link_types.find((r) => r.id === fact.type_id),
    ),
  }));
  const propertiesFor = (id: string) => {
    const owner = draft.object_types.find((t) => t.id === id);
    return owner
      ? [
          ...draft.properties.filter((p) => p.owner_type_id === id),
          ...inheritedProperties(draft, owner).map((p) => p.property),
        ]
      : [];
  };
  const properties = propertiesFor(type.id),
    sideProperties = propertiesFor(selected?.type_id ?? type.id);
  const identifiers = properties.filter((p) => p.identifier);
  const valueProperties = properties.filter((p) => !p.identifier).slice(0, 4);
  const documentRows = draft.material_objects.filter(
    (o) =>
      o.type_id === type.id &&
      `${o.name} ${JSON.stringify(o.values)}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  const documentPage = documentRows.slice(
    page * PAGE_SIZE,
    (page + 1) * PAGE_SIZE,
  );
  const related = selected
    ? links
        .filter(
          (l) =>
            l.source_id === selected.id ||
            l.target_id === selected.id ||
            l.role_values?.some((v) => v.object_id === selected.id),
        )
        .flatMap((l) => {
          const roleIds =
            l.role_values?.flatMap((v) =>
              v.object_id && v.object_id !== selected.id ? [v.object_id] : [],
            ) ?? [];
          return [
            ...new Set(
              roleIds.length
                ? roleIds
                : [l.source_id === selected.id ? l.target_id : l.source_id],
            ),
          ].flatMap((id) => {
            const other = objects.find((o) => o.id === id);
            return other ? [{ link: l, other }] : [];
          });
        })
    : [];
  if (!isObject(type)) {
    const facts = links.filter((l) => l.type_id === type.id);
    return (
      <>
        <div className="om-table-wrap">
          <table className="om-table">
            <thead>
              <tr>
                <th>来源实例</th>
                <th>目标实例</th>
              </tr>
            </thead>
            <tbody>
              {facts.map((l) => (
                <tr key={l.id}>
                  <td>{objects.find((o) => o.id === l.source_id)?.name}</td>
                  <td>{objects.find((o) => o.id === l.target_id)?.name}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <button
          type="button"
          className="element-text-button om-detail-section"
          onClick={() =>
            open({
              kind: "object_type",
              id: type.source_type_id,
              tab: "instances",
            })
          }
        >
          查看来源对象实例
          <ArrowRight size={14} />
        </button>
      </>
    );
  }
  const clearSide = () => {
    setSelected(null);
    setNeighbors(null);
  };
  return (
    <>
      <div className="om-mapping-tools">
        <label className="om-search">
          <Search size={16} />
          <input
            aria-label="搜索实例"
            placeholder="搜索实例"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
              clearSide();
            }}
          />
        </label>
        {mapping && (
          <select
            aria-label="实例来源"
            value={source}
            onChange={(e) => {
              setSource(e.target.value);
              setPage(0);
              setRows([]);
              setError("");
              clearSide();
            }}
          >
            <option value="document">文档实例</option>
            <option value="database" disabled={!canBrowseDatabase}>
              数据库实例
            </option>
          </select>
        )}
      </div>
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      {busy && (
        <p role="status" className="element-note">
          正在读取实例…
        </p>
      )}
      <div className="om-instance-layout">
        <div className="om-instance-main">
          <div className="om-table-wrap">
            <table className="om-table om-instances">
              <thead>
                <tr>
                  <th>
                    实例标识 <span className="om-tag om-tag-key">标识</span>
                  </th>
                  {valueProperties.map((p) => (
                    <th key={p.id}>{p.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {source === "document"
                  ? documentPage.map((o) => (
                      <tr
                        key={o.id}
                        className="om-open-row"
                        tabIndex={0}
                        onClick={() => setSelected(o)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") setSelected(o);
                        }}
                      >
                        <td>
                          <button
                            type="button"
                            className="element-text-button"
                            onClick={() => setSelected(o)}
                          >
                            {identifiers
                              .map((p) => o.values[p.technical_name])
                              .filter((v) => v != null)
                              .join(" + ") || o.name}
                          </button>
                        </td>
                        {valueProperties.map((p) => (
                          <td key={p.id}>
                            {o.values[p.technical_name] == null
                              ? ""
                              : String(o.values[p.technical_name])}
                          </td>
                        ))}
                      </tr>
                    ))
                  : rows.map((row, index) => (
                      <tr
                        key={String(row.__key ?? index)}
                        className="om-open-row"
                      >
                        <td>
                          <button
                            type="button"
                            className="element-text-button"
                            disabled={busy || !canBrowseDatabase}
                            onClick={() =>
                              void visitDatabase(type.id, String(row.__key))
                            }
                          >
                            {String(row.__key ?? "")}
                          </button>
                        </td>
                        {valueProperties.map((p) => (
                          <td key={p.id}>
                            {row[p.technical_name] == null
                              ? ""
                              : String(row[p.technical_name])}
                          </td>
                        ))}
                      </tr>
                    ))}
                {!busy &&
                  !(source === "document" ? documentRows : rows).length && (
                    <tr>
                      <td
                        colSpan={valueProperties.length + 1}
                        className="om-blank"
                      >
                        无匹配实例
                      </td>
                    </tr>
                  )}
              </tbody>
            </table>
          </div>
          <div className="om-pager">
            {source === "document" && <span>共 {documentRows.length} 条</span>}
            <button
              type="button"
              className="button button--secondary"
              disabled={busy || page === 0}
              onClick={() => {
                setPage(page - 1);
                clearSide();
              }}
            >
              上一页
            </button>
            <span>
              {page + 1}
              {source === "document"
                ? ` / ${Math.max(1, Math.ceil(documentRows.length / PAGE_SIZE))}`
                : ""}
            </span>
            <button
              type="button"
              className="button button--secondary"
              disabled={
                busy ||
                (source === "document"
                  ? (page + 1) * PAGE_SIZE >= documentRows.length
                  : !more)
              }
              onClick={() => {
                setPage(page + 1);
                clearSide();
              }}
            >
              下一页
            </button>
          </div>
        </div>
        {selected && (
          <aside className="om-instance-side" aria-label="实例详情">
            <header>
              <h3>{selected.name}</h3>
              <button
                type="button"
                className="icon-button"
                aria-label="关闭实例详情"
                onClick={clearSide}
              >
                <X size={15} />
              </button>
            </header>
            <div className="om-side-content">
              <section>
                <h3>属性</h3>
                <dl className="om-info-grid">
                  {sideProperties
                    .filter((p) => selected.values[p.technical_name] != null)
                    .map((p) => (
                      <div className="om-info-pair" key={p.id}>
                        <dt>{p.name}</dt>
                        <dd>{String(selected.values[p.technical_name])}</dd>
                      </div>
                    ))}
                </dl>
              </section>
              <section>
                <h3>关联实例</h3>
                {related.map(({ link, other }) => (
                  <div
                    className="om-related-instance"
                    key={`${link.id}:${other.id}`}
                  >
                    <small>
                      {
                        draft.link_types.find((r) => r.id === link.type_id)
                          ?.name
                      }
                    </small>
                    <button
                      type="button"
                      className="element-text-button"
                      disabled={busy}
                      onClick={() => {
                        if ("key" in other)
                          void visitDatabase(other.type_id, String(other.key));
                        else setSelected(other);
                      }}
                    >
                      {
                        draft.object_types.find((o) => o.id === other.type_id)
                          ?.name
                      }{" "}
                      · {other.name}
                    </button>
                  </div>
                ))}
                {!related.length && <span className="muted">无关联实例</span>}
              </section>
              {neighbors?.warnings.map((warning) => (
                <p className="element-note" key={warning}>
                  {warning}
                </p>
              ))}
              {neighbors?.truncated && (
                <p className="element-note">
                  结果已达到查询范围上限，仅展示部分关系。
                </p>
              )}
              <EvidenceSection
                workspaceId={draft.workspace_id}
                evidence={selected.evidence}
              />
            </div>
          </aside>
        )}
      </div>
    </>
  );
}
