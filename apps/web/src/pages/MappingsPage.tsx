import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { DocumentMaterials } from "../components/DocumentMaterials";
import { TableSyncPanel } from "../components/TableSyncPanel";
import { PageBody, PageTabs } from "../components/layout";
import { useWorkspaceContext } from "../hooks/useWorkspaceContext";

export function MappingsPage() {
  const { workspace } = useWorkspaceContext();
  const [params] = useSearchParams();
  const [tab, setTab] = useState("tables");
  return <div className="flex h-full min-h-0 flex-col bg-canvas">
    <PageTabs title="数据管理" activeKey={tab} onChange={setTab} items={[
      { key: "tables", label: "数据表", children: <PageBody><TableSyncPanel pageLayout workspaceId={workspace.id} editable={!!workspace.role} initialConnection={params.get("connection") ?? undefined} initialSchema={params.get("schema") ?? ""} initialTable={params.get("table") ?? undefined} /></PageBody> },
      { key: "documents", label: "文档", children: <PageBody><DocumentMaterials workspace={workspace} /></PageBody> },
    ]} />
  </div>;
}
