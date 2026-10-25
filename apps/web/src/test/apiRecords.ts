// Sessions, workspaces and published versions as the server returns them, for
// tests that render pages and hooks around them.
import type { Draft, ModelingSession, ModelingSessionSummary, VersionSummary, Workspace } from "../api/types";
import { emptyDraft } from "../lib/coreModel";

export function modelingSession(
  extra: Partial<ModelingSession> = {},
  draft: Draft = emptyDraft(extra.workspace_id ?? "w1"),
): ModelingSession {
  const workspaceId = extra.workspace_id ?? draft.workspace_id;
  return {
    id: "s1",
    workspace_id: workspaceId,
    title: "建模会话",
    mode: "model",
    base_version_id: null,
    revision: 1,
    draft,
    draft_sha256: "d".repeat(64),
    base_version_sha256: "b".repeat(64),
    pending_proposal_count: 0,
    latest_batch_id: null,
    base_diff: [],
    graph: {
      workspace_id: workspaceId,
      version_id: "",
      version_sha256: "",
      version_content_sha256: "",
      normalized_snapshot_sha256: "",
      nodes: [],
      edges: [],
    },
    material_ids: [],
    task_status: "idle",
    task_detail: "",
    dataagent_topic_id: null,
    dataagent_task_id: null,
    updated_at: "2026-10-16T08:00:00Z",
    ...extra,
  };
}

export function sessionSummary(
  extra: Partial<ModelingSessionSummary> & Pick<ModelingSessionSummary, "id" | "title">,
): ModelingSessionSummary {
  return {
    task_status: "idle",
    updated_at: "2026-10-16T08:00:00Z",
    base_version_id: null,
    has_unpublished_changes: false,
    ...extra,
  };
}

export function workspace(extra: Partial<Workspace> = {}): Workspace {
  return {
    id: "w1",
    slug: "demo-sales",
    name: "示例销售空间",
    description: "",
    role: "admin",
    visibility: "member",
    current_version: 1,
    version_id: "v1",
    version_sha256: "a".repeat(64),
    object_type_count: 0,
    link_type_count: 0,
    updated_at: "2026-10-16T08:00:00Z",
    ...extra,
  };
}

export function versionSummary(version: number, extra: Partial<VersionSummary> = {}): VersionSummary {
  return {
    workspace_id: "w1",
    version_id: `v${version}`,
    version_sha256: String(version).repeat(64),
    version_content_sha256: String(version).repeat(64),
    normalized_snapshot_sha256: String(version).repeat(64),
    version,
    status: "published",
    message: "",
    published_at: "2026-10-16T08:00:00Z",
    validation: {
      standard: "core-1",
      schema_status: "passed",
      semantic_status: "passed",
      errors: [],
      warnings: [],
      publishable: true,
    },
    counts: { object_types: 0, link_types: 0, attributes: 0, rules: 0, metrics: 0 },
    ...extra,
  };
}
