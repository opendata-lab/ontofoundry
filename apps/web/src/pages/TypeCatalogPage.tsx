import { RelationshipRoles } from "../components/RelationshipRoles";
import { relationReadOnly } from "../lib/nativeDraft";
import {
  Box,
  GitBranch,
  Plus,
  Search,
  Rocket,
  RefreshCw,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useElementInspector } from "../hooks/useElementInspector";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { EmptyModel } from "../components/EmptyModel";
import { TagList } from "../components/TagList";
import { useSnapshot } from "../hooks/useSnapshot";

export function TypeCatalogPage({
  kind,
}: {
  kind: "object_type" | "link_type";
}) {
  const { workspace } = useWorkspaceContext();
  const { draft, error, load, sessionId, suffix } = useSnapshot(workspace);
  const [query, setQuery] = useState("");
  const [tag, setTag] = useState("");
  const inspector = useElementInspector();
  const create = () => inspector.open({ kind, id: "new", mode: "edit", sessionId });
  if (error) return <ErrorSurface message={error} retry={load} />;
  if (!draft) return <LoadingSurface label="正在读取本体目录…" />;
  const items = kind === "object_type" ? draft.object_types : draft.link_types;
  const tags = [...new Set(items.flatMap((i) => i.tags))];
  const filtered = items.filter(
    (i) =>
      (!tag || i.tags.includes(tag)) &&
      (i.name + i.technical_name + i.description + ("concept_context" in i ? JSON.stringify(i.concept_context) : "") + ("roles" in i ? JSON.stringify(i.role_concepts ?? i.roles) + JSON.stringify(i.verbalizes) : ""))
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <div className="ref-catalog">
      <header className="catalog-toolbar">
        <h1>{kind === "object_type" ? "本体对象" : "本体关系"}</h1>
        <div className="toolbar-spacer" />
        <select
          aria-label="标签筛选"
          value={tag}
          onChange={(e) => setTag(e.target.value)}
        >
          <option value="">请选择标签</option>
          {tags.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <label className="ref-search">
          <input
            placeholder="请输入检索关键字"
            aria-label="搜索目录"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <Search size={15} />
        </label>
        <button className="button button--secondary" onClick={load}>
          <RefreshCw size={13} />
          刷新
        </button>
      </header>
      <div className="object-card-grid">
        {workspace.role && (
          <div className="object-create-card">
            <button className="button button--primary" onClick={create}>
              <Plus size={15} />
              新建{kind === "object_type" ? "对象" : "关系"}
            </button>
            <Link
              className="button button--primary"
              to={"../delivery" + suffix}
            >
              <Rocket size={14} />
              发布
            </Link>
          </div>
        )}
        {filtered.map((item) => (
          <Link
            className="object-card"
            key={item.id}
            to={inspector.href({ kind, id: item.id, tab: kind === "object_type" ? "properties" : "endpoints", sessionId })}
          >
            <div className="object-card-top">
              <span
                className={
                  "catalog-object-icon " +
                  (kind === "link_type" ? "is-relation" : "")
                }
              >
                {kind === "object_type" ? (
                  <Box size={22} />
                ) : (
                  <GitBranch size={22} />
                )}
              </span>
            </div>
            <h2>{item.name}</h2>
            <p className="api-name">{item.technical_name}</p>
            <div className="object-metrics">
              {"attributes" in item ? (
                <>
                  <span>
                    属性<b>{item.attributes.length}</b>
                  </span>
                  <span>
                    映射
                    <b>
                      {
                        draft.mappings.filter((m) => m.type_id === item.id)
                          .length
                      }
                    </b>
                  </span>
                  <span>
                    关系
                    <b>
                      {
                        draft.link_types.filter(
                          (r) =>
                            r.source_type_id === item.id ||
                            r.target_type_id === item.id || r.owner_ref?.ref === item.id || !!r.roles?.some(role => role.concept.ref === item.id),
                        ).length
                      }
                    </b>
                  </span>
                  <span>
                    文档实例
                    <b>
                      {
                        draft.objects.filter((o) => o.type_id === item.id)
                          .length
                      }
                    </b>
                  </span>
                </>
              ) : relationReadOnly(item) ? (
                <RelationshipRoles link={item} compact />
              ) : (
                <p className="relation-endpoints">
                  {
                    draft.object_types.find((t) => t.id === item.source_type_id)
                      ?.name
                  }{" "}
                  →{" "}
                  {
                    draft.object_types.find((t) => t.id === item.target_type_id)
                      ?.name
                  }
                </p>
              )}
            </div>
            <div className="object-tags">
              <TagList tags={item.tags} empty="未设置标签" />
            </div>
          </Link>
        ))}
      </div>
      {kind === "object_type" && !!draft.value_types?.length && <>
        <h2>值概念</h2>
        <div className="object-card-grid">
          {draft.value_types.filter(value => (!tag || value.tags.includes(tag)) &&
            (value.name + value.technical_name + JSON.stringify(value.concept_context ?? {})).toLowerCase().includes(query.toLowerCase()))
            .map(value => <Link className="object-card" key={value.id} to={inspector.href({ kind: "value_type", id: value.id, tab: "basic", sessionId })}>
              <h2>{value.name}</h2><p className="api-name">{value.technical_name}</p><p>值概念 · 上下文</p>
            </Link>)}
        </div>
      </>}
      {!filtered.length && query && <EmptyModel text="没有匹配的本体模型" />}
      {!items.length && !workspace.role && <EmptyModel text="暂无已发布本体" />}
    </div>
  );
}
