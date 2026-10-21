import type {
  Dataset, DatasetCheckResult, DatasetPreview, SyncJob,
  ExportPreview,
  ImportPreview,
  ImportSource,
  ImportConfirm,
  ImportConfirmed,
  ImportCompletionRequest,
  Assets,
  TableRows,
  Capabilities,
  Comparison,
  DataConnection,
  DataTable,
  Decision,
  DecisionResult,
  Draft,
  ElementSave,
  ElementSaveImpact,
  ElementSaveResult,
  FactProposalRevision,
  ISODate,
  InstanceDetail,
  InstanceEnvelope,
  InstanceList,
  InstanceNeighborhood,
  Items,
  LinkedTable,
  MappingPreview,
  MappingPreviewRequest,
  Material,
  ManagedMaterial,
  MergeConflict,
  MetricPreview,
  MetricPreviewRequest,
  ModelingSession,
  RegisteredTable,
  ModelingSessionSummary,
  NeighborhoodRequest,
  ProposalBatch,
  ProposalBatchDetail,
  PublishPreview,
  PublishResult,
  Resolution,
  ResourceKind,
  TypeDetail,
  TypeGraph,
  TypeList,
  User,
  ValidationIssue,
  ValidationReport,
  VersionSummary,
  Workspace,
  WorkspaceOverview,
} from "./types";

type ErrorBody = {
  message?: string;
  hint?: string;
  error?: {
    code?: string;
    message?: string;
    items?: { proposal_id: string; reason: string }[];
    conflicts?: MergeConflict[];
    references?: { name: string; field: string }[] | string[];
    current_version_id?: string | null;
    errors?: ValidationIssue[];
  };
  detail?: unknown;
};

export class ApiError extends Error {
  status: number;
  code: string;
  detail: unknown;
  /** Per-item reasons, e.g. which proposals were stale (body.error.items). */
  items: { proposal_id: string; reason: string }[];
  conflicts: MergeConflict[];
  currentVersionId: string | null;
  references: { name: string; field: string }[] | string[];
  /** Core validation errors with element locations (body.error.errors). */
  errors: ValidationIssue[];

  constructor(
    message: string,
    status: number,
    code = "HTTP_ERROR",
    detail?: unknown,
    error?: ErrorBody["error"],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.items = error?.items ?? [];
    this.conflicts = error?.conflicts ?? [];
    this.references = error?.references ?? [];
    this.currentVersionId = error?.current_version_id ?? null;
    this.errors = error?.errors ?? [];
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ErrorBody;
    const message =
      body.error?.message ??
      body.message ??
      detailMessage(body.detail) ??
      "请求失败（HTTP " + response.status + "）";
    throw new ApiError(
      body.hint ? message + "\n" + body.hint : message,
      response.status,
      body.error?.code,
      body.detail,
      body.error,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// FastAPI answers with a string, a structured {code, message} object, or a
// list of validation errors; show people the sentence, never the JSON.
function detailMessage(detail: unknown): string | null {
  if (!detail) return null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => detailMessage(item))
      .filter((item): item is string => Boolean(item));
    return messages.length ? messages.join("；") : null;
  }
  if (typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    for (const key of ["message", "msg", "detail"]) {
      const value = detailMessage(record[key]);
      if (value) return value;
    }
  }
  return null;
}

function json(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

/** Query string from defined values only; "" for none. */
function query(params: Record<string, string | number | boolean | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  return search.size ? "?" + search.toString() : "";
}

const ontologyPath = (workspaceId: string) => "/api/v1/ontology/workspaces/" + workspaceId;
const sessionPath = (s: Pick<ModelingSession, "id" | "workspace_id">) =>
  `/api/v1/workspaces/${s.workspace_id}/sessions/${s.id}`;

export const api = {
  me: () => request<User>("/api/v1/auth/me"),
  workspaces: () => request<Items<Workspace>>("/api/v1/workspaces"),
  createWorkspace: (payload: { name: string; slug: string; description: string }) =>
    request<Workspace>("/api/v1/workspaces", json("POST", payload)),
  workspace: (workspaceId: string) => request<Workspace>("/api/v1/workspaces/" + workspaceId),
  overview: (workspaceId: string) =>
    request<WorkspaceOverview>("/api/v1/workspaces/" + workspaceId + "/overview"),
  version: (workspaceId: string, versionId?: string) =>
    request<VersionSummary>(ontologyPath(workspaceId) + "/version" + query({ version_id: versionId })),
  types: (
    workspaceId: string,
    params?: { kind?: ResourceKind; q?: string; version_id?: string },
  ) => request<TypeList>(ontologyPath(workspaceId) + "/types" + query({ ...params })),
  type: (workspaceId: string, typeId: string, versionId?: string) =>
    request<TypeDetail>(
      ontologyPath(workspaceId) + "/types/" + encodeURIComponent(typeId) + query({ version_id: versionId }),
    ),
  graph: (workspaceId: string, focusId?: string, depth?: number) =>
    request<TypeGraph>(
      ontologyPath(workspaceId) + "/type-graph/neighborhood" + query({ focus_id: focusId, depth }),
    ),
  versions: (workspaceId: string) =>
    request<Items<VersionSummary>>("/api/v1/workspaces/" + workspaceId + "/versions"),
  presentation: (workspaceId: string, versionId: string) =>
    request<{ version: VersionSummary; model: Draft }>(
      `/api/v1/workspaces/${workspaceId}/versions/${versionId}/presentation`,
    ),
  comparison: (workspaceId: string, rightId: string, leftId?: string) =>
    request<Comparison>(
      `/api/v1/workspaces/${workspaceId}/version-comparison` + query({ right_id: rightId, left_id: leftId }),
    ),
};

export function workspaceRequest<T>(id: string, suffix: string, body?: unknown, method?: string) {
  return request<T>(
    "/api/v1/workspaces/" + id + suffix,
    body === undefined ? { method: method ?? "GET" } : json(method ?? "POST", body),
  );
}

export const modelingApi = {
  sessions: (id: string) => workspaceRequest<Items<ModelingSessionSummary>>(id, "/sessions"),
  create: (id: string, title = "新的建模会话") =>
    workspaceRequest<ModelingSession>(id, "/sessions", { title }),
  get: (id: string, sid: string) => workspaceRequest<ModelingSession>(id, "/sessions/" + sid),
  /** Saves the whole session draft; it does not publish. */
  save: (session: ModelingSession, draft: Draft, extra: { title?: string; material_ids?: string[]; linked_tables?: LinkedTable[] } = {}) =>
    request<ModelingSession>(sessionPath(session), json("PUT", { revision: session.revision, draft, ...extra })),
  validate: (s: ModelingSession) => request<ValidationReport>(sessionPath(s) + "/validate", json("POST", {})),
  snapshot: (id: string) => workspaceRequest<Draft>(id, "/published-snapshot"),
  /** Previews cross-aggregate impact read-only before saving an element. */
  previewElementSave: (id: string, payload: ElementSave) =>
    workspaceRequest<ElementSaveImpact>(id, "/element-saves/preview", payload),
  /** Saves one aggregate and publishes it right away (current-version CAS). */
  saveElement: (id: string, payload: ElementSave) =>
    workspaceRequest<ElementSaveResult>(id, "/element-saves", payload),
  materials: (id: string) => workspaceRequest<Items<Material>>(id, "/materials"),
  materialOverview: (id: string) => workspaceRequest<Items<ManagedMaterial>>(id, "/materials/overview"),
  materialDownloadUrl: (id: string, materialId: string) => `/api/v1/workspaces/${id}/materials/${materialId}`,
  deleteMaterial: (id: string, materialId: string) => workspaceRequest<void>(id, `/materials/${materialId}`, undefined, "DELETE"),
  archiveMaterial: (id: string, materialId: string) =>
    workspaceRequest<Material>(id, `/materials/${materialId}/archive`, {}),
  restoreMaterial: (id: string, materialId: string) =>
    workspaceRequest<Material>(id, `/materials/${materialId}/restore`, {}),
  upload: (id: string, file: File) =>
    request<Material>(
      "/api/v1/workspaces/" + id + "/materials?name=" + encodeURIComponent(file.name),
      { method: "POST", body: file },
    ),
  capabilities: (id: string) => workspaceRequest<Capabilities>(id, "/capabilities"),
};

export const catalogApi = {
  connections: (id: string) => workspaceRequest<Items<DataConnection>>(id, "/connections"),
  tables: (id: string, connectionId: string, params?: { table?: string; schema_name?: string }) =>
    workspaceRequest<Items<DataTable>>(id, `/connections/${connectionId}/tables` + query({ ...params })),
  tableMaterial: (id: string, connectionId: string, tables: string[], schemaName?: string) =>
    workspaceRequest<Material>(id, `/connections/${connectionId}/table-material`, {
      tables,
      ...(schemaName ? { schema_name: schemaName } : {}),
    }),
  schemas: (id: string, connectionId: string) =>
    workspaceRequest<Items<string>>(id, `/connections/${connectionId}/schemas`),
  assets: (id: string, connectionId: string, params?: { schema_name?: string; version_id?: string }) =>
    workspaceRequest<Assets>(id, `/connections/${connectionId}/assets` + query({ ...params })),
  refreshAssets: (id: string, connectionId: string, params?: { schema_name?: string }, tables?: string[]) =>
    workspaceRequest<SyncJob>(id, `/connections/${connectionId}/assets/sync-jobs` + query({ ...params }), tables?.length ? { scope: "selected", tables } : { scope: "all" }),
  tableRows: (id: string, connectionId: string, params: { table_name: string; schema_name?: string }) =>
    workspaceRequest<TableRows>(id, `/connections/${connectionId}/assets/rows` + query({ ...params })),
  syncJobs: (id: string, connectionId: string, schema_name?: string) => workspaceRequest<Items<SyncJob>>(id, `/connections/${connectionId}/assets/sync-jobs` + query({ schema_name })),
  syncJob: (id: string, connectionId: string, jobId: string) => workspaceRequest<SyncJob>(id, `/connections/${connectionId}/assets/sync-jobs/${jobId}`),
  retrySync: (id: string, connectionId: string, jobId: string) => workspaceRequest<SyncJob>(id, `/connections/${connectionId}/assets/sync-jobs/${jobId}/retry`, {}),
  mappingPreview: (id: string, payload: MappingPreviewRequest) =>
    workspaceRequest<MappingPreview>(id, "/mapping-preview", payload),
};

export const instancesApi = {
  list: (
    workspaceId: string,
    params: {
      type_id?: string;
      source?: "document" | "database";
      q?: string;
      cursor?: string;
      limit?: number;
      snapshot_date?: ISODate;
      version_id?: string;
    },
  ) => request<InstanceList>(ontologyPath(workspaceId) + "/objects" + query({ ...params })),
  get: (workspaceId: string, ref: string, params?: { snapshot_date?: ISODate; version_id?: string }) =>
    request<InstanceDetail>(ontologyPath(workspaceId) + "/objects/" + encodeURIComponent(ref) + query({ ...params })),
  neighborhood: (
    workspaceId: string,
    ref: string,
    params?: { depth?: number; snapshot_date?: ISODate; version_id?: string },
  ) =>
    request<InstanceEnvelope & InstanceNeighborhood>(
      ontologyPath(workspaceId) + "/objects/" + encodeURIComponent(ref) + "/neighborhood" + query({ ...params }),
    ),
  /** Neighborhood of a database row against the session or published model. */
  draftNeighborhood: (workspaceId: string, payload: NeighborhoodRequest) =>
    workspaceRequest<InstanceNeighborhood>(workspaceId, "/instance-neighborhood", payload),
};

export const proposalsApi = {
  reviseContent: (workspaceId: string, sessionId: string, proposalId: string, fields: Record<string, unknown>, revision: number) => workspaceRequest<{ proposal_id: string; session_revision: number }>(workspaceId, `/sessions/${sessionId}/proposals/${proposalId}/after`, { fields, expected_session_revision: revision }, "PATCH"),
  reviseDataset: (workspaceId: string, sessionId: string, proposalId: string, dataset: Dataset, revision: number) => workspaceRequest<{ proposal_id: string; session_revision: number }>(workspaceId, `/sessions/${sessionId}/proposals/${proposalId}/dataset`, { dataset, expected_session_revision: revision }, "PUT"),
  batches: (s: Pick<ModelingSession, "id" | "workspace_id">, params?: { limit?: number; cursor?: string }) =>
    request<Items<ProposalBatch> & { next_cursor: string | null }>(
      sessionPath(s) + "/proposal-batches" + query({ ...params }),
    ),
  batch: (s: Pick<ModelingSession, "id" | "workspace_id">, batchId: string) =>
    request<ProposalBatchDetail>(sessionPath(s) + "/proposal-batches/" + batchId),
  decide: (s: ModelingSession, decisions: Decision[], idempotencyKey: string) =>
    request<DecisionResult>(
      sessionPath(s) + "/proposal-decisions",
      json("POST", {
        idempotency_key: idempotencyKey,
        expected_session_revision: s.revision,
        decisions,
      }),
    ),
  /** Turns a pending duplicate-fact create into an update of an existing fact. */
  reviseFact: (s: ModelingSession, proposalId: string, payload: FactProposalRevision) =>
    request<ProposalBatchDetail>(
      sessionPath(s) + "/proposal-items/" + proposalId + "/revision",
      json("POST", payload),
    ),
};

export const publishApi = {
  preview: (s: ModelingSession) =>
    request<PublishPreview>(sessionPath(s) + "/preview", json("POST", { expected_session_revision: s.revision })),
  publish: (session: ModelingSession, preview: PublishPreview, message: string) =>
    request<PublishResult>(
      sessionPath(session) + "/publish",
      json("POST", {
        expected_session_revision: preview.session_revision,
        expected_current_version_id: preview.current_version_id,
        expected_merged_snapshot_sha256: preview.merged_snapshot_sha256,
        message,
      }),
    ),
  resolve: (s: ModelingSession, currentVersionId: string | null, resolutions: Record<string, Resolution>) =>
    request<ModelingSession>(
      sessionPath(s) + "/resolve-merge",
      json("POST", {
        expected_session_revision: s.revision,
        expected_current_version_id: currentVersionId,
        resolutions,
      }),
    ),
};

export const metricsApi = {
  /** Runs the unsaved form definition read-only; nothing is stored. */
  preview: (workspaceId: string, payload: MetricPreviewRequest) =>
    request<MetricPreview>(`/api/v1/modeling/workspaces/${workspaceId}/metrics/preview`, json("POST", payload)),
};

const importPath = (workspaceId: string, adapter: string, importId?: string) =>
  `/api/v1/modeling/workspaces/${encodeURIComponent(workspaceId)}/imports/${encodeURIComponent(adapter)}${importId ? `/${encodeURIComponent(importId)}` : ""}`;
export const importApi = {
  preview: (workspaceId: string, adapter: string, file: File) =>
    request<ImportPreview>(`${importPath(workspaceId, adapter)}?name=${encodeURIComponent(file.name)}`, { method: "POST", body: file, headers: { "Content-Type": "application/json" } }),
  get: (workspaceId: string, source: ImportSource) => request<ImportPreview>(importPath(workspaceId, source.adapter, source.report_id)),
  confirm: (workspaceId: string, adapter: string, importId: string, body: ImportConfirm) =>
    request<ImportConfirmed>(`${importPath(workspaceId, adapter, importId)}/confirm`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  complete: (workspaceId: string, source: ImportSource, body: ImportCompletionRequest) =>
    request<ImportConfirmed>(`${importPath(workspaceId, source.adapter, source.report_id)}/completions`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
};

export const exportApi = {
  preview: (workspaceId: string, adapter: string, versionId: string) =>
    request<ExportPreview>(`/api/v1/modeling/workspaces/${encodeURIComponent(workspaceId)}/exports/${encodeURIComponent(adapter)}?version_id=${encodeURIComponent(versionId)}`),
};


export const datasetApi = {
  registeredTables: (id: string, sessionId?: string) =>
    workspaceRequest<Items<RegisteredTable>>(id, "/registered-tables" + query({ session_id: sessionId })),
  validate: (id: string, dataset: Dataset, revision?: number | null) => workspaceRequest<DatasetCheckResult>(id, "/datasets/validate", { dataset, expected_session_revision: revision ?? null }),
  preview: (id: string, dataset: Dataset) => workspaceRequest<DatasetPreview>(id, "/datasets/preview", { dataset }),
};
