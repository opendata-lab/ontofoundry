import { ArrowLeft, ArrowRight, Database, Search } from "lucide-react";
import { useEffect, useState } from "react";
import type { Draft, MaterialObject } from "../../api/types";
import { workspaceRequest } from "../../api/client";
import { inheritedProperties, isObject, VALUE_KINDS, type PanelProps } from "../../lib/elementModel";
import { EvidenceSection } from "./ElementPanels";

/** The same instance browser can be embedded without route params or page headers. */
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
  const [source, setSource] = useState("document");
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
  const mapping = draft.mappings.find((m) => m.type_id === type.id);
  useEffect(() => {
    if (source !== "database" || !mapping) return;
    let active = true;
    const timer = window.setTimeout(() => {
      setBusy(true);
      setError("");
      workspaceRequest<{ items: Record<string, unknown>[]; has_more: boolean }>(
        draft.workspace_id,
        "/mapping-preview",
        { mapping, q: query, offset: page * 20, limit: 20 },
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
  }, [source, mapping, query, page, draft.workspace_id]);
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
  const links = neighbors?.links ?? draft.material_links;
  const propertyOwner = draft.object_types.find(
    (t) => t.id === (selected?.type_id ?? type.id),
  );
  const properties = propertyOwner
    ? [
        ...draft.properties.filter((p) => p.owner_type_id === propertyOwner.id),
        ...inheritedProperties(draft, propertyOwner).map((p) => p.property),
      ]
    : [];
  if (selected)
    return (
      <section className="element-section">
        <button
          type="button"
          className="element-text-button"
          onClick={() => {
            setSelected(null);
            setNeighbors(null);
          }}
        >
          <ArrowLeft size={14} />
          返回实例列表
        </button>
        <h3>{selected.name}</h3>
        {error && (
          <p className="inline-error" role="alert">
            {error}
          </p>
        )}
        <div className="element-basic-grid">
          {properties.map((p) => (
            <div className="element-field" key={p.id}>
              <span>
                {p.name}
                <small>{VALUE_KINDS[p.value_kind]}</small>
              </span>
              <span className="element-value">
                {String(selected.values[p.technical_name] ?? "—")}
              </span>
            </div>
          ))}
        </div>
        <h3>关联关系</h3>
        {links
          .filter(
            (l) => l.source_id === selected.id || l.target_id === selected.id,
          )
          .map((l) => {
            const other = objects.find(
              (o) =>
                o.id ===
                (l.source_id === selected.id ? l.target_id : l.source_id),
            );
            return (
              other && (
                <button
                  type="button"
                  className="element-relation-row"
                  key={l.id}
                  disabled={busy}
                  onClick={() => {
                    if ("key" in other)
                      void visitDatabase(other.type_id, String(other.key));
                    else setSelected(other);
                  }}
                >
                  <strong>
                    {draft.link_types.find((t) => t.id === l.type_id)?.name}
                  </strong>
                  <span>
                    {other.name}
                    <ArrowRight size={14} />
                  </span>
                </button>
              )
            );
          })}
        {neighbors?.warnings.map((w) => (
          <p className="element-note" key={w}>
            {w}
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
      </section>
    );
  if (!isObject(type)) {
    const materialLinks = draft.material_links.filter(
      (l) => l.type_id === type.id,
    );
    return (
      <section className="element-section">
        <h3>关系实例</h3>
        <table className="element-table">
          <thead>
            <tr>
              <th>源实例</th>
              <th>目标实例</th>
              <th>来源证据</th>
            </tr>
          </thead>
          <tbody>
            {materialLinks.map((l) => (
              <tr key={l.id}>
                <td>
                  {draft.material_objects.find((o) => o.id === l.source_id)
                    ?.name ?? l.source_id}
                </td>
                <td>
                  {draft.material_objects.find((o) => o.id === l.target_id)
                    ?.name ?? l.target_id}
                </td>
                <td>{l.evidence.length} 条</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!materialLinks.length && (
          <p className="element-empty">暂无材料关系实例。</p>
        )}
        <p className="element-note">
          查看数据库关系时，从源对象或目标对象的实例进入。
        </p>
        <button
          type="button"
          className="element-text-button"
          onClick={() =>
            open({
              kind: "object_type",
              id: type.source_type_id,
              tab: "instances",
            })
          }
        >
          查看源对象实例
          <ArrowRight size={14} />
        </button>
      </section>
    );
  }
  const documentRows = draft.material_objects.filter(
    (o) =>
      o.type_id === type.id &&
      `${o.name} ${JSON.stringify(o.values)}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <section className="element-section">
      <div className="element-section-title">
        <h3>实例</h3>
        <span className="muted">
          {source === "document"
            ? `${documentRows.length} 个材料实例`
            : "数据库实时查询"}
        </span>
      </div>
      <div className="element-instance-tools">
        <label className="element-instance-search">
          <Search size={16} />
          <input
            aria-label="搜索实例"
            placeholder="搜索实例"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setPage(0);
            }}
          />
        </label>
        <select
          aria-label="实例来源"
          value={source}
          onChange={(e) => {
            setSource(e.target.value);
            setPage(0);
            setError("");
          }}
        >
          <option value="document">文档实例</option>
          <option value="database" disabled={!mapping}>
            数据库实例{mapping ? "" : "（未映射）"}
          </option>
        </select>
      </div>
      {source === "database" && !canBrowseDatabase && (
        <p className="element-note">
          当前可预览数据列表；保存后再查看实例关系。
        </p>
      )}
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
      <div className="element-table-wrap">
        <table className="element-table">
          <thead>
            <tr>
              <th>名称</th>
              {properties.map((p) => (
                <th key={p.id}>{p.name}</th>
              ))}
              <th>来源</th>
            </tr>
          </thead>
          <tbody>
            {source === "document"
              ? documentRows.map((o) => (
                  <tr key={o.id}>
                    <td>
                      <button
                        className="element-text-button"
                        type="button"
                        onClick={() => setSelected(o)}
                      >
                        {o.name}
                      </button>
                    </td>
                    {properties.map((p) => (
                      <td key={p.id}>
                        {String(o.values[p.technical_name] ?? "—")}
                      </td>
                    ))}
                    <td>文档</td>
                  </tr>
                ))
              : rows.map((row) => (
                  <tr key={String(row.__key)}>
                    <td>
                      <button
                        className="element-text-button"
                        type="button"
                        disabled={busy || !canBrowseDatabase}
                        onClick={() =>
                          void visitDatabase(type.id, String(row.__key))
                        }
                      >
                        {String(row.__key)}
                      </button>
                    </td>
                    {properties.map((p) => (
                      <td key={p.id}>{String(row[p.technical_name] ?? "—")}</td>
                    ))}
                    <td>
                      <Database size={14} />
                    </td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
      {!busy && !(source === "document" ? documentRows : rows).length && (
        <p className="element-empty">暂无实例。</p>
      )}
      {source === "database" && (
        <div className="element-pagination">
          <button
            type="button"
            className="button button--secondary"
            disabled={busy || page === 0}
            onClick={() => setPage(page - 1)}
          >
            上一页
          </button>
          <span>第 {page + 1} 页</span>
          <button
            type="button"
            className="button button--secondary"
            disabled={busy || !more}
            onClick={() => setPage(page + 1)}
          >
            下一页
          </button>
        </div>
      )}
    </section>
  );
}
