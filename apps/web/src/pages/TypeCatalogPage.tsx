import {
  Box,
  GitBranch,
  Plus,
  Search,
  Tag,
  CheckCircle2,
  Rocket,
  RefreshCw,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { modelingApi } from "../api/client";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { EmptyModel } from "../components/EmptyModel";
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
  const [actionError, setActionError] = useState("");
  const navigate = useNavigate();
  const create = async () => {
    try {
      const s = sessionId
        ? await modelingApi.get(workspace.id, sessionId)
        : await modelingApi.create(
            workspace.id,
            kind === "object_type" ? "手工编辑业务对象" : "手工编辑本体关系",
          );
      navigate(
        "../" +
          (kind === "object_type" ? "objects/new/edit" : "relations/new/edit") +
          "?session=" +
          s.id,
      );
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "创建失败");
    }
  };
  if (error) return <ErrorSurface message={error} retry={load} />;
  if (!draft) return <LoadingSurface label="正在读取本体目录…" />;
  const items = kind === "object_type" ? draft.object_types : draft.link_types;
  const tags = [...new Set(items.flatMap((i) => i.tags))];
  const filtered = items.filter(
    (i) =>
      (!tag || i.tags.includes(tag)) &&
      (i.name + i.technical_name + i.description)
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <div className="ref-catalog">
      <header className="catalog-toolbar">
        <h1>{kind === "object_type" ? "业务对象" : "本体关系"}</h1>
        <span className="muted">{sessionId ? "会话草稿" : "已发布"}</span>
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
      {actionError && <p className="inline-error">{actionError}</p>}
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
            to={
              "../" +
              (kind === "object_type" ? "objects/" : "relations/") +
              item.id +
              suffix
            }
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
              <span className="available">
                <CheckCircle2 size={12} />
                {sessionId ? "草稿" : "可用"}
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
                            r.target_type_id === item.id,
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
              <Tag size={13} />
              {item.tags.length ? item.tags.join(" · ") : "未设置标签"}
            </div>
            <footer>
              <span>{workspace.name}</span>
              <span>
                {sessionId ? "未发布" : "v" + workspace.current_version}
              </span>
            </footer>
          </Link>
        ))}
      </div>
      {!filtered.length && query && <EmptyModel text="没有匹配的本体模型" />}
      {!items.length && !workspace.role && <EmptyModel text="暂无已发布本体" />}
    </div>
  );
}
