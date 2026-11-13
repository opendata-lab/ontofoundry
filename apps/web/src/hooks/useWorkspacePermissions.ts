import type { User, Workspace, WorkspaceRole } from "../api/types";
import { useWorkspaceContext } from "./useWorkspaceContext";

export const ROLE_LABELS: Record<WorkspaceRole, string> = {
  admin: "管理员",
  member: "可编辑",
  viewer: "可查看",
};

export const ROLE_OPTIONS: { value: WorkspaceRole; label: string }[] = [
  { value: "viewer", label: "可查看" },
  { value: "member", label: "可编辑" },
  { value: "admin", label: "管理员" },
];

export type WorkspacePermissions = {
  role: WorkspaceRole | null;
  visibility: Workspace["visibility"];
  isPlatformAdmin: boolean;
  canRead: boolean;
  canEdit: boolean;
  canManage: boolean;
  isViewer: boolean;
  isPublicNonMember: boolean;
  readOnlyBanner: string | null;
};

export function getWorkspacePermissions(
  workspace: Workspace,
  user?: User | null,
): WorkspacePermissions {
  const isPlatformAdmin = Boolean(user?.is_platform_admin);
  const role: WorkspaceRole | null = isPlatformAdmin ? "admin" : (workspace.role ?? null);
  const canManage = isPlatformAdmin || role === "admin";
  const canEdit = canManage || role === "member";
  const isViewer = !isPlatformAdmin && role === "viewer";
  const isPublicNonMember = !isPlatformAdmin && role === null;
  const canRead =
    canEdit ||
    isViewer ||
    Boolean(workspace.is_public) ||
    workspace.visibility === "public";
  const readOnlyBanner = isViewer
    ? "你是本空间的可查看成员，只能查看"
    : isPublicNonMember
      ? "你不是本空间成员，只能阅读"
      : null;

  return {
    role,
    visibility: workspace.visibility,
    isPlatformAdmin,
    canRead,
    canEdit,
    canManage,
    isViewer,
    isPublicNonMember,
    readOnlyBanner,
  };
}

/** Derives workspace read/edit/manage capabilities and read-only banner copy. */
export function useWorkspacePermissions(): WorkspacePermissions {
  const { workspace, user } = useWorkspaceContext();
  return getWorkspacePermissions(workspace, user);
}
