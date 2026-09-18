import { Plus } from "lucide-react";
import { useRef } from "react";
import { DataConnections } from "../components/DataConnections";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";
import { usePageTab } from "../hooks/usePageTab";

/**
 * 数据连接。
 *
 * 独立成页而不是挂在数据映射下：连接是一次性配置且承载数据库凭据，映射是随本体
 * 演进的建模产物。两者放在一页时，每次改映射都要越过一块几乎不变的区域。
 *
 * 映射编辑不需要这里的 UI——MappingForm 按 connection_alias 静默反查连接来读列名
 * 和预览。
 */
export function ConnectionsPage() {
  const { workspace } = useWorkspaceContext();
  const openDialog = useRef<(() => void) | null>(null);
  usePageTab({ title: "数据连接" });
  return (
    <div className="ref-catalog">
      <header className="catalog-toolbar">
        <h1>数据连接</h1>
        <div className="toolbar-spacer" />
        {workspace.role === "admin" && (
          <button
            className="button button--primary"
            onClick={() => openDialog.current?.()}
          >
            <Plus size={14} />
            添加连接
          </button>
        )}
      </header>
      <div className="management-content">
        <DataConnections onReady={(open) => (openDialog.current = open)} />
      </div>
    </div>
  );
}
