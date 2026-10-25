import type {
  CatalogPage, ElementProjection, DocumentContext, TargetKind,
  Dataset, DatasetCheckResult, DatasetPreview, SyncJob,
  ExportPreview,
  ImportPreview,
  ImportSource,
  ImportConfirm,
  ImportConfirmed,
  ImportCompletionRequest,
  Assets,
  TableRows,
  OntologySearchKind,
  SchemaImpactItem,
  OntologySearchResult,
  Capabilities,
  Comparison,
  DataConnection,
  ConnectionReference,
  DataTable,
  Decision,
  DecisionResult,
  Draft,
  Presentation,
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
  SessionMode,
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
    references?: { name: string; field: string }[] | string[] | ConnectionReference[];
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
  references: { name: string; field: string }[] | string[] | ConnectionReference[];
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

import { definitionReads } from "./definitionReads";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    ...init,
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
  });
  const permission = response.headers.get("X-Ontology-Authorization");
  const workspaceId = path.match(/\/workspaces\/([^/?]+)/)?.[1];
  if (permission && workspaceId) definitionReads.authorizeProjection(workspaceId, permission);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as ErrorBody;
    const message =
      body.error?.message ??
      body.message ??
      detailMessage(body.detail) ??
      "请求失败（HTTP " + response.status + "）";
    if (response.status === 401 || response.status === 403) definitionReads.clear();
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
  const encoded = search.toString();
  return encoded ? "?" + encoded : "";
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
  catalog: (workspaceId: string, params: { version_id: string; kind?: ResourceKind; q?: string; tag?: string; limit?: number; cursor?: string }) =>
    request<CatalogPage>(ontologyPath(workspaceId) + "/catalog" + query({ ...params })),
  elementPresentation: async (workspaceId: string, kind: TargetKind, typeId: string, versionId: string): Promise<ElementProjection> => {
    await api.version(workspaceId, versionId);
    const cached = definitionReads.peek(workspaceId, versionId);
    if (cached) {
      const { version, model } = await cached;
      return { ...version, representation: "element-1", complete: false, model };
    }
    const result = await request<ElementProjection>(ontologyPath(workspaceId) + "/types/" + encodeURIComponent(typeId) + "/presentation" + query({ kind, version_id: versionId }));
    if (result.version_id !== versionId || result.workspace_id !== workspaceId || result.complete !== false)
      throw new Error("版本内容不一致，请刷新后重试");
    return result;
  },
  elementDocuments: async (workspaceId: string, kind: "object_type" | "link_type", typeId: string, versionId: string): Promise<DocumentContext> => {
    const result = await request<DocumentContext>(ontologyPath(workspaceId) + "/types/" + encodeURIComponent(typeId) + "/document-context" + query({ kind, version_id: versionId }));
    if (result.version_id !== versionId || result.workspace_id !== workspaceId) throw new Error("实例版本已变化，请刷新后重试");
    return result;
  },
  /** Ranked search over the published ontology; the same service as the MCP search_ontology tool. */
  searchOntology: (
    workspaceId: string,
    body: { query: string; kinds?: OntologySearchKind[]; expand?: boolean; limit?: number; cursor?: string },
  ) => request<OntologySearchResult>(ontologyPath(workspaceId) + "/search", json("POST", body)),
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
  presentation: async (workspaceId: string, versionId: string): Promise<Presentation> => {
    // The browser revalidates this small authorized envelope before in-memory reuse.
    await api.version(workspaceId, versionId);
    return definitionReads.get(workspaceId, versionId, async () => {
      const r = await request<Presentation>(`/api/v1/workspaces/${workspaceId}/versions/${versionId}/presentation`);
      if (r.version.version_id !== versionId || r.model.workspace_id !== workspaceId)
        throw new Error("版本内容不一致，请刷新后重试");
      return { ...r, model: { ...r.model, ...NO_INSTANCES } };
    });
  },
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

// Document instances live in their own store, not in the core-1 draft. Views keep
// reading them from the draft, so they are merged in after each load and removed
// before a draft is sent back.
type InstanceSet = { change_sequence: number; items: { target_kind: "material_object" | "material_link"; state: string; revision: number; element: Record<string, unknown> }[] };
async function instancesFor(workspaceId: string, sessionId?: string | null): Promise<Pick<Draft, "material_objects" | "material_links">> {
  try {
    const set = await workspaceRequest<InstanceSet>(workspaceId, sessionId ? `/sessions/${sessionId}/instance-baseline` : "/instances");
    const pick = (kind: string) => set.items.filter((i) => i.target_kind === kind).map((i) => ({ ...i.element, state: i.state, revision: i.revision }));
    return { material_objects: pick("material_object") as Draft["material_objects"], material_links: pick("material_link") as Draft["material_links"] };
  } catch {
    // Without instance permission the definitions still show; there are no instances to list.
    return { material_objects: [], material_links: [] };
  }
}
async function withInstances(draft: Draft, sessionId?: string | null): Promise<Draft> {
  return { ...draft, ...(await instancesFor(draft.workspace_id, sessionId)) };
}
async function sessionWithInstances<T extends { session: ModelingSession | null }>(result: T): Promise<T> {
  return result.session ? { ...result, session: await withSessionInstances(result.session) } : result;
}
async function withSessionInstances(session: ModelingSession): Promise<ModelingSession> {
  return { ...session, draft: await withInstances(session.draft, session.id) };
}
const NO_INSTANCES: Pick<Draft, "material_objects" | "material_links"> = { material_objects: [], material_links: [] };
export function definitionsOnly(draft: Draft) {
  const { material_objects: _objects, material_links: _links, ...definitions } = draft;
  void _objects; void _links;
  return definitions;
}

export const modelingApi = {
  sessions: (id: string) => workspaceRequest<Items<ModelingSessionSummary>>(id, "/sessions"),
  create: (id: string, title = "新的建模会话", mode: SessionMode = "model") =>
    workspaceRequest<ModelingSession>(id, "/sessions", { title, mode }).then(withSessionInstances),
  get: (id: string, sid: string) => workspaceRequest<ModelingSession>(id, "/sessions/" + sid).then(withSessionInstances),
  /** Saves the whole session draft; it does not publish. */
  save: (session: ModelingSession, draft: Draft, extra: { title?: string; material_ids?: string[]; linked_tables?: LinkedTable[]; mode?: SessionMode } = {}) =>
    request<ModelingSession>(sessionPath(session), json("PUT", { revision: session.revision, draft: definitionsOnly(draft), ...extra })).then(withSessionInstances),
  /** Abandons a session: drops its staged instances; published content is untouched. */
  abandon: (s: Pick<ModelingSession, "id" | "workspace_id">) =>
    request<{ session_id: string; abandoned_at: string; abandoned_by: string }>(sessionPath(s) + "/abandon", json("POST", {})),
  validate: (s: ModelingSession) => request<ValidationReport>(sessionPath(s) + "/validate", json("POST", {})),
  snapshot: async (id: string, versionId?: string | null): Promise<Draft> => {
    const current = await api.workspace(id);
    const fixed = versionId ?? current.version_id;
    if (!fixed) return { schema_version: "core-1", workspace_id: id, object_types: [], properties: [], link_types: [], rules: [], metrics: [], datasets: [], mappings: [], value_types: [], ...NO_INSTANCES };
    const { model } = await api.presentation(id, fixed);
    // Live instances have no historical baseline. Never join them across publication.
    if (current.version_id !== fixed) throw new Error("本体版本已更新，请刷新后查看实例");
    const instances = await instancesFor(id);
    const after = await api.workspace(id);
    if (after.version_id !== fixed) throw new Error("本体版本已更新，请刷新后查看实例");
    return { ...model, ...instances };
  },
  /** Previews cross-aggregate impact read-only before saving an element. */
  previewElementSave: (id: string, payload: ElementSave) =>
    workspaceRequest<ElementSaveImpact>(id, "/element-saves/preview", payload),
  /** Saves one aggregate and publishes it right away (current-version CAS). */
  saveElement: (id: string, payload: ElementSave) =>
    workspaceRequest<ElementSaveResult>(id, "/element-saves", payload)
      .then(async (r) => sessionWithInstances({ ...r, draft: await withInstances(r.draft, r.session?.id) })),
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
  syncedAssets: (id: string, connectionId: string) =>
    workspaceRequest<Items<{ schema: string; assets: Assets }>>(id, `/connections/${connectionId}/assets/synced`),
  assets: (id: string, connectionId: string, params?: { schema_name?: string; version_id?: string }) =>
    workspaceRequest<Assets>(id, `/connections/${connectionId}/assets` + query({ ...params })),
  refreshAssets: (id: string, connectionId: string, params?: { schema_name?: string }, tables?: string[]) =>
    workspaceRequest<SyncJob>(id, `/connections/${connectionId}/assets/sync-jobs` + query({ ...params }), tables?.length ? { scope: "selected", tables } : { scope: "all" }),
  schemaImpact: (id: string, connectionId: string, schemaName?: string) =>
    workspaceRequest<{ connection_id: string; schema_name: string; items: SchemaImpactItem[] }>(id, `/connections/${connectionId}/assets/impact` + query({ schema_name: schemaName })),
  tableRows: (id: string, connectionId: string, params: { table_name: string; schema_name?: string }) =>
    workspaceRequest<TableRows>(id, `/connections/${connectionId}/assets/rows` + query({ ...params })),
  /** Unregisters one synced table; the source database is untouched. */
  deleteTable: (id: string, connectionId: string, schemaName: string, tableName: string) =>
    workspaceRequest<{ schema_name: string; table_name: string }>(id, `/connections/${connectionId}/assets/tables` + query({ schema_name: schemaName, table_name: tableName }), undefined, "DELETE"),
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
    ).then(sessionWithInstances),
  /** Turns a pending duplicate-fact create into an update of an existing fact. */
  reviseFact: (s: ModelingSession, proposalId: string, payload: FactProposalRevision) =>
    request<ProposalBatchDetail>(
      sessionPath(s) + "/proposal-items/" + proposalId + "/revision",
      json("POST", payload),
    ),
};

export const publishApi = {
  preview: (s: ModelingSession) =>
    request<PublishPreview>(sessionPath(s) + "/preview", json("POST", { expected_session_revision: s.revision }))
      .then((p): PublishPreview => ({ ...p, merged_model: { ...p.merged_model, ...NO_INSTANCES } })),
  publish: (session: ModelingSession, preview: PublishPreview, message: string) =>
    request<PublishResult>(
      sessionPath(session) + "/publish",
      json("POST", {
        expected_session_revision: preview.session_revision,
        expected_current_version_id: preview.current_version_id,
        expected_merged_snapshot_sha256: preview.merged_snapshot_sha256,
        expected_instance_change_sequence: preview.instance_change_sequence,
        message,
      }),
    ).then(sessionWithInstances),
  resolve: (s: ModelingSession, currentVersionId: string | null, resolutions: Record<string, Resolution>) =>
    request<ModelingSession>(
      sessionPath(s) + "/resolve-merge",
      json("POST", {
        expected_session_revision: s.revision,
        expected_current_version_id: currentVersionId,
        resolutions,
      }),
    ).then(withSessionInstances),
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
