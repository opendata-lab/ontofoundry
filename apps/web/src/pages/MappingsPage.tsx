import { Button } from "antd";
import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { DocumentMaterials } from "../components/DocumentMaterials";
import { TableSyncDialog } from "../components/TableSyncDialog";
import { TableSyncPanel } from "../components/TableSyncPanel";
import { PageBody, PageTabs } from "../components/layout";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";

export function MappingsPage() {
  const { workspace } = useWorkspaceContext();
  const [params] = useSearchParams();
  const [tab, setTab] = useState("tables");
  const [syncing, setSyncing] = useState(false);
  const [connection, setConnection] = useState(params.get("connection") ?? "");
  const [refreshKey, setRefreshKey] = useState(0);
  return <div className="flex h-full min-h-0 flex-col bg-canvas">
    <PageTabs title="数据管理" activeKey={tab} onChange={setTab} items={[
      { key: "tables", label: "数据表", children: <PageBody><TableSyncPanel workspaceId={workspace.id} refreshKey={refreshKey} onConnectionChange={setConnection} initialConnection={params.get("connection") ?? undefined} initialSchema={params.get("schema") ?? ""} actions={workspace.role ? <Button type="primary" icon={<RefreshCw size={14} />} onClick={() => setSyncing(true)}>同步数据表</Button> : null} /></PageBody> },
      { key: "documents", label: "文档", children: <PageBody><DocumentMaterials workspace={workspace} /></PageBody> },
    ]} />
    {syncing && <TableSyncDialog workspaceId={workspace.id} initialConnection={connection} initialSchema={params.get("schema") ?? ""} initialTable={params.get("table") ?? undefined} onClose={() => { setSyncing(false); setRefreshKey((v) => v + 1); }} />}
  </div>;
}
