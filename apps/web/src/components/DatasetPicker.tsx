import { Modal } from "antd";
import type { Dataset, Draft, ElementSaveResult, Workspace } from "../api/types";
import { TableSyncPanel } from "./TableSyncPanel";

/** Table registration is managed independently from ontology dataset creation. */
export function DatasetPicker({ workspace, open, onClose }: {
  workspace: Workspace; draft: Draft | null; sessionId: string | null; open: boolean; onClose: () => void;
  onRegistered: (result: ElementSaveResult, dataset: Dataset) => void; onOpenDataset: (id: string) => void;
}) {
  return <Modal open={open} title="同步数据表" width="var(--review-dialog-width)" footer={null} onCancel={onClose}><TableSyncPanel workspaceId={workspace.id} editable={!!workspace.role} /></Modal>;
}
