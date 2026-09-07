import type {
  OntologyType,
  TypeGraph,
  WorkspaceOverview,
  User,
  VersionSummary,
  Workspace,
  Draft,
  ModelingSession,
  Material,
  Capabilities,
  DataConnection,
  DataTable,
} from "./types";

type ErrorBody = {
  error?: {
    code?: string;
    message?: string;
  };
  detail?: unknown;
};

export class ApiError extends Error {
  status: number;
  code: string;
  detail: unknown;

  constructor(
    message: string,
    status: number,
    code = "HTTP_ERROR",
    detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
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
    throw new ApiError(
      body.error?.message ??
        (typeof body.detail === "string"
          ? body.detail
          : body.detail
            ? JSON.stringify(body.detail)
            : null) ??
        "请求失败（HTTP " + response.status + "）",
      response.status,
      body.error?.code,
      body.detail,
    );
  }
  return response.json() as Promise<T>;
}

export const api = {
  me: () => request<User>("/api/v1/auth/me"),
  workspaces: () => request<{ items: Workspace[] }>("/api/v1/workspaces"),
  createWorkspace: (payload: {
    name: string;
    slug: string;
    description: string;
  }) =>
    request<Workspace>("/api/v1/workspaces", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  workspace: (workspaceId: string) =>
    request<Workspace>("/api/v1/workspaces/" + workspaceId),
  overview: (workspaceId: string) =>
    request<WorkspaceOverview>(
      "/api/v1/workspaces/" + workspaceId + "/overview",
    ),
  version: (workspaceId: string) =>
    request<VersionSummary>(
      "/api/v1/ontology/workspaces/" + workspaceId + "/version",
    ),
  types: (workspaceId: string, params?: { kind?: string; q?: string }) => {
    const query = new URLSearchParams();
    if (params?.kind) query.set("kind", params.kind);
    if (params?.q) query.set("q", params.q);
    const suffix = query.size ? "?" + query.toString() : "";
    return request<{ items: OntologyType[] }>(
      "/api/v1/ontology/workspaces/" + workspaceId + "/types" + suffix,
    );
  },
  graph: (workspaceId: string, focusId?: string) => {
    const suffix = focusId
      ? "?" + new URLSearchParams({ focus_id: focusId }).toString()
      : "";
    return request<TypeGraph>(
      "/api/v1/ontology/workspaces/" +
        workspaceId +
        "/type-graph/neighborhood" +
        suffix,
    );
  },
  exportUrl: (workspaceId: string, versionId: string) =>
    "/api/v1/ontology/workspaces/" +
    workspaceId +
    "/versions/" +
    versionId +
    "/export",
};

export function workspaceRequest<T>(
  id: string,
  suffix: string,
  body?: unknown,
  method?: string,
) {
  return request<T>(
    "/api/v1/workspaces/" + id + suffix,
    body === undefined
      ? { method: method ?? "GET" }
      : {
          method: method ?? "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
  );
}

export const modelingApi = {
  sessions: (id: string) =>
    workspaceRequest<{
      items: Pick<ModelingSession, "id" | "title" | "task_status">[];
    }>(id, "/sessions"),
  create: (id: string, title = "新的建模会话") =>
    workspaceRequest<ModelingSession>(id, "/sessions", { title }),
  get: (id: string, sid: string) =>
    workspaceRequest<ModelingSession>(id, "/sessions/" + sid),
  save: (s: ModelingSession, draft: Draft, extra = {}) =>
    workspaceRequest<ModelingSession>(
      s.workspace_id,
      "/sessions/" + s.id,
      { revision: s.revision, draft, ...extra },
      "PUT",
    ),
  candidates: (s: ModelingSession, ids: string[], action: string) =>
    workspaceRequest<ModelingSession>(
      s.workspace_id,
      "/sessions/" + s.id + "/candidates",
      { revision: s.revision, ids, action },
    ),
  chat: (s: ModelingSession, content: string, mode: string) =>
    workspaceRequest<ModelingSession>(
      s.workspace_id,
      "/sessions/" + s.id + "/messages",
      { revision: s.revision, content, mode },
    ),
  cancel: (s: ModelingSession) =>
    workspaceRequest<ModelingSession>(
      s.workspace_id,
      "/sessions/" + s.id + "/cancel",
      {},
    ),
  validate: (s: ModelingSession) =>
    workspaceRequest<VersionSummary["validation"]>(
      s.workspace_id,
      "/sessions/" + s.id + "/validate",
      {},
    ),
  publish: (s: ModelingSession, message: string) =>
    workspaceRequest<{ version: VersionSummary; session: ModelingSession }>(
      s.workspace_id,
      "/sessions/" + s.id + "/publish",
      { revision: s.revision, message },
    ),
  snapshot: (id: string) => workspaceRequest<Draft>(id, "/published-snapshot"),
  materials: (id: string) =>
    workspaceRequest<{ items: Material[] }>(id, "/materials"),
  upload: (id: string, file: File) =>
    request<Material>(
      "/api/v1/workspaces/" +
        id +
        "/materials?name=" +
        encodeURIComponent(file.name),
      { method: "POST", body: file },
    ),
  capabilities: (id: string) =>
    workspaceRequest<Capabilities>(id, "/capabilities"),
  connections: (id: string) =>
    workspaceRequest<{ items: DataConnection[] }>(id, "/connections"),
  tables: (id: string, connectionId: string) =>
    workspaceRequest<{ items: DataTable[] }>(
      id,
      "/connections/" + connectionId + "/tables",
    ),
};
