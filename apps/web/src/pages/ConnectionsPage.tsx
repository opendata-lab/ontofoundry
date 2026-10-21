import { Button } from "antd";
import { PageBody, PageHeader, PageToolbar } from "../components/layout";
import { Plus } from "lucide-react";
import { useRef } from "react";
import { DataConnections } from "../components/DataConnections";
import { usePageTab } from "../hooks/usePageTab";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";

/** Connections are managed separately from the evolving ontology mappings. */
export function ConnectionsPage() {
  const { workspace } = useWorkspaceContext();
  const openDialog = useRef<(() => void) | null>(null);
  usePageTab({ title: "数据连接" });
  return (
    <div className="flex h-full min-h-0 flex-col bg-canvas">
      <PageHeader title="数据连接" />
      <PageBody>
        {workspace.role === "admin" && (
          <PageToolbar>
          <Button type="primary" icon={<Plus size={14} />} onClick={() => openDialog.current?.()}>
            添加连接
          </Button>
          </PageToolbar>
        )}
        <DataConnections onReady={(open) => (openDialog.current = open)} />
      </PageBody>
    </div>
  );
}
