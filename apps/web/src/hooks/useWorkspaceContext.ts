import { createContext, useContext } from "react";
import type { User, Workspace } from "../api/types";

export type WorkspaceContext = {
  workspace: Workspace;
  user: User;
  refresh: () => void;
};
export const WorkspaceContextProvider = createContext<WorkspaceContext | null>(
  null,
);
export function useWorkspaceContext() {
  const value = useContext(WorkspaceContextProvider);
  if (!value) throw new Error("Workspace context is missing");
  return value;
}
