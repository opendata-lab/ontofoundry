import { DataAssets } from "../components/DataAssets";
import { Database, ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { modelingApi } from "../api/client";
import type { DataConnection } from "../api/types";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { useSnapshot } from "../hooks/useSnapshot";
import { DatasetPicker } from "../components/DatasetPicker";
import { usePageTab } from "../hooks/usePageTab";

export function MappingsPage() {
  const { workspace } = useWorkspaceContext();
  const snapshot = useSnapshot(workspace);
  const [connections, setConnections] = useState<DataConnection[]>([]);
  const [error, setError] = useState("");
  const [view, setView] = useState<"assets" | "mappings">("assets");
  // DatasetPicker 选中表之后在这里提示，和连接测试无关，所以没随连接管理搬走。
  const [status, setStatus] = useState("");
  const [assetBusy, setAssetBusy] = useState(false);
  usePageTab({ busy: assetBusy });
  const [picker, setPicker] = useState(false);
  // 连接列表仍要读：DataAssets 按它解析数据源。管理入口在「数据连接」页。

  useEffect(() => {
    modelingApi
      .connections(workspace.id)
      .then((r) => setConnections(r.items))
      .catch((e: Error) => setError(e.message));
  }, [workspace.id]);
  return (
    <div className="ref-catalog">
      <header className="catalog-toolbar">
        <h1>数据映射</h1>
        <div className="toolbar-spacer" />
        <button
          className="button button--secondary"
          onClick={() => setPicker(true)}
        >
          <Database size={14} />
          浏览数据目录
        </button>
      </header>
      <div className="management-content">
        {(error || snapshot.error) && (
          <div className="inline-error">{error || snapshot.error}</div>
        )}
        {status && (
          <p className="muted" role="status">
            {status}
          </p>
        )}
        <div className="reading-switch">
          <button
            aria-pressed={view === "assets"}
            disabled={assetBusy}
            onClick={() => setView("assets")}
          >
            数据源与资产
          </button>
          <button
            aria-pressed={view === "mappings"}
            disabled={assetBusy}
            onClick={() => setView("mappings")}
          >
            本体映射
          </button>
        </div>
        {view === "assets" ? (
          <DataAssets
            key={workspace.id + ":" + snapshot.sessionId}
            onBusyChange={setAssetBusy}
            workspaceId={workspace.id}
            connections={connections}
            draft={snapshot.draft}
            sessionId={snapshot.sessionId}
          />
        ) : (
          <>
            <h2>本体与数据集</h2>
            <table className="ref-table">
              <thead>
                <tr>
                  <th>业务对象</th>
                  <th>数据集</th>
                  <th>标识字段</th>
                  <th>已映射属性</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {snapshot.draft?.object_types.map((t) => {
                  const m = snapshot.draft?.mappings.find(
                    (m) => m.type_id === t.id,
                  );
                  return (
                    <tr key={t.id}>
                      <td>
                        {t.name}
                        <small>{t.technical_name}</small>
                      </td>
                      <td>{m?.table_name ?? "未映射"}</td>
                      <td>{m?.key_column ?? "—"}</td>
                      <td>
                        {Object.keys(m?.fields ?? {}).length}/
                        {t.attributes.length}
                      </td>
                      <td>
                        <Link
                          className="button button--text"
                          to={"../objects/" + t.id + snapshot.suffix}
                        >
                          查看与编辑
                          <ExternalLink size={13} />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
      </div>
      <DatasetPicker
        workspaceId={workspace.id}
        open={picker}
        onClose={() => setPicker(false)}
        onSelect={(c, t) =>
          setStatus(
            c.name + " / " + t.name + " 已选择。进入对应本体的编辑页配置映射。",
          )
        }
      />
    </div>
  );
}
