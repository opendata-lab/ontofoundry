import { Button } from "antd";
import { PageBody, PageHeader } from "../components/PageHeader";
import { Plus } from "lucide-react";
import { useRef } from "react";
import { DataConnections } from "../components/DataConnections";
import { usePageTab } from "../hooks/usePageTab";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";

/**
 * 数据连接。
 *
 * 独立成页而不是挂在数据映射下：连接是一次性配置且承载数据库凭据，映射是随本体
 * 演进的建模产物。两者放在一页时，每次改映射都要越过一块几乎不变的区域。
 */
export function ConnectionsPage() {
  const { workspace } = useWorkspaceContext();
  const openDialog = useRef<(() => void) | null>(null);
  usePageTab({ title: "数据连接" });
  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <PageHeader title="数据连接">
        {workspace.role === "admin" && (
          <Button type="primary" icon={<Plus size={14} />} onClick={() => openDialog.current?.()}>
            添加连接
          </Button>
        )}
      </PageHeader>
      <PageBody>
      <DataConnections onReady={(open) => (openDialog.current = open)} />
      </PageBody>
    </div>
  );
}
