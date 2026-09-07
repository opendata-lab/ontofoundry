import {
  Box,
  Edit3,
  ArrowLeft,
  Database,
  GitBranch,
  Network,
} from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { modelingApi } from "../api/client";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { ErrorSurface, LoadingSurface } from "../components/AsyncState";
import { useSnapshot } from "../hooks/useSnapshot";
import { usePageTab } from "../hooks/usePageTab";

export function ObjectDetailPage({ relation = false }: { relation?: boolean }) {
  const { typeId } = useParams();
  const { workspace } = useWorkspaceContext();
  const { draft, error, load, sessionId, suffix } = useSnapshot(workspace);
  const [tab, setTab] = useState("definition");
  const [actionError, setActionError] = useState("");
  const navigate = useNavigate();
  const type = (relation ? draft?.link_types : draft?.object_types)?.find(
    (t) => t.id === typeId,
  );
  usePageTab({
    title: type ? type.name + (sessionId ? " · 草稿" : "") : undefined,
  });
  if (error) return <ErrorSurface message={error} retry={load} />;
  if (!draft) return <LoadingSurface label="正在读取本体详情…" />;
  if (!type)
    return (
      <div className="empty-state">
        <p>没有找到此本体</p>
        <Link to="../objects">返回业务对象</Link>
      </div>
    );
  const edit = async () => {
    try {
      const s = sessionId
        ? await modelingApi.get(workspace.id, sessionId)
        : await modelingApi.create(workspace.id, "编辑「" + type.name + "」");
      navigate(
        "../" +
          (relation ? "relations/" : "objects/") +
          type.id +
          "/edit?session=" +
          s.id,
      );
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "打开编辑失败");
    }
  };
  const mapping = draft.mappings.find((m) => m.type_id === type.id);
  const relations = draft.link_types.filter(
    (r) => r.source_type_id === type.id || r.target_type_id === type.id,
  );
  return (
    <div className="ref-detail-page">
      <header className="breadcrumb-bar">
        <Link to={"../" + (relation ? "relations" : "objects") + suffix}>
          <ArrowLeft size={14} />
          {relation ? "本体关系" : "业务对象"}
        </Link>
        <span>/</span>
        <span>{type.name}</span>
        <div className="toolbar-spacer" />
        <span className="muted">
          {sessionId ? "会话草稿" : "已发布 v" + workspace.current_version}
        </span>
      </header>
      <div className="detail-identity">
        <span className="catalog-object-icon">
          {relation ? <GitBranch size={23} /> : <Box size={23} />}
        </span>
        <div>
          <h1>{type.name}</h1>
          <small>{type.technical_name}</small>
        </div>
        <div className="toolbar-spacer" />
        {workspace.role && (
          <button className="button button--primary" onClick={edit}>
            <Edit3 size={14} />
            编辑本体
          </button>
        )}
      </div>
      {actionError && <p className="inline-error">{actionError}</p>}
      <div className="ref-tabs detail-tabs">
        <button
          aria-selected={tab === "definition"}
          onClick={() => setTab("definition")}
        >
          本体定义
        </button>
        <button
          aria-selected={tab === "relations"}
          onClick={() => setTab("relations")}
        >
          关联关系
        </button>
        {workspace.role && (
          <button
            aria-selected={tab === "mapping"}
            onClick={() => setTab("mapping")}
          >
            数据映射
          </button>
        )}
        {!relation && workspace.role && (
          <Link to={"../objects/" + type.id + "/instances" + suffix}>
            实例列表
          </Link>
        )}
      </div>
      <div className="detail-content">
        {tab === "definition" && (
          <>
            <section className="detail-section">
              <h2>基本信息</h2>
              <dl className="ref-definition">
                <div>
                  <dt>名称</dt>
                  <dd>{type.name}</dd>
                </div>
                <div>
                  <dt>API 标识</dt>
                  <dd>{type.technical_name}</dd>
                </div>
                <div>
                  <dt>标签</dt>
                  <dd>{type.tags.join(" · ") || "—"}</dd>
                </div>
                <div className="wide">
                  <dt>描述</dt>
                  <dd>{type.description || "尚未填写"}</dd>
                </div>
              </dl>
            </section>
            {"attributes" in type ? (
              <section className="detail-section">
                <h2>属性定义</h2>
                <table className="ref-table">
                  <thead>
                    <tr>
                      <th>属性名称</th>
                      <th>API 标识</th>
                      <th>类型</th>
                      <th>标识</th>
                      <th>必填</th>
                    </tr>
                  </thead>
                  <tbody>
                    {type.attributes.map((a) => (
                      <tr key={a.id}>
                        <td>{a.name}</td>
                        <td>{a.technical_name}</td>
                        <td>{a.value_kind}</td>
                        <td>{a.identifier ? "是" : "—"}</td>
                        <td>{a.required ? "是" : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            ) : (
              <section className="detail-section">
                <h2>关系定义</h2>
                <p>
                  {
                    draft.object_types.find((t) => t.id === type.source_type_id)
                      ?.name
                  }{" "}
                  →{" "}
                  {
                    draft.object_types.find((t) => t.id === type.target_type_id)
                      ?.name
                  }
                </p>
                <p className="muted">基数：{type.multiplicity}</p>
              </section>
            )}
          </>
        )}
        {tab === "relations" && (
          <section className="detail-section">
            <h2>关联关系</h2>
            {relations.length ? (
              relations.map((r) => (
                <Link
                  className="relation-list-row"
                  to={"../relations/" + r.id + suffix}
                  key={r.id}
                >
                  <GitBranch size={16} />
                  <strong>{r.name}</strong>
                  <span>
                    {
                      draft.object_types.find((t) => t.id === r.source_type_id)
                        ?.name
                    }{" "}
                    →{" "}
                    {
                      draft.object_types.find((t) => t.id === r.target_type_id)
                        ?.name
                    }
                  </span>
                </Link>
              ))
            ) : (
              <p className="muted">暂无关联关系</p>
            )}
            <Link className="button button--text" to="../view">
              <Network size={14} />
              在本体图谱中查看
            </Link>
          </section>
        )}
        {tab === "mapping" && (
          <section className="detail-section">
            <h2>数据映射</h2>
            {"data_join" in type && type.data_join ? (
              <dl className="ref-definition">
                <div>
                  <dt>来源对象字段</dt>
                  <dd>{type.data_join.source_column}</dd>
                </div>
                <div>
                  <dt>目标对象字段</dt>
                  <dd>{type.data_join.target_column}</dd>
                </div>
                <div className="wide">
                  <dt>查询方式</dt>
                  <dd>
                    根据两端对象的数据映射，按上述字段等值连接；仅支持同一连接。
                  </dd>
                </div>
              </dl>
            ) : mapping ? (
              <>
                <p>
                  <Database size={15} /> {mapping.table_name} · 标识字段{" "}
                  {mapping.key_column}
                </p>
                <table className="ref-table">
                  <thead>
                    <tr>
                      <th>本体属性</th>
                      <th>数据字段</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(mapping.fields).map(([a, c]) => (
                      <tr key={a}>
                        <td>{a}</td>
                        <td>{c}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            ) : (
              <p className="muted">
                尚未配置映射，可在编辑本体中选择数据集和字段。
              </p>
            )}
            <button className="button button--text" onClick={edit}>
              编辑映射
            </button>
          </section>
        )}
      </div>
    </div>
  );
}
