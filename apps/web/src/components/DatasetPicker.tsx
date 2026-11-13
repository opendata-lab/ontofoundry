import type { Dataset, Draft, ElementSaveResult, Workspace } from "../api/types";
import { getWorkspacePermissions } from "../hooks/useWorkspacePermissions";
import { TableSyncDialog } from "./TableSyncDialog";

/** Table registration is managed independently from ontology dataset creation. */
export function DatasetPicker({ workspace, open, onClose }: {
  workspace: Workspace; draft: Draft | null; sessionId: string | null; open: boolean; onClose: () => void;
  onRegistered: (result: ElementSaveResult, dataset: Dataset) => void; onOpenDataset: (id: string) => void;
}) {
  return open && getWorkspacePermissions(workspace).canEdit ? <TableSyncDialog workspaceId={workspace.id} onClose={onClose} /> : null;
}
