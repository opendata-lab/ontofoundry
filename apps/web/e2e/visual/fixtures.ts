import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { CoreDraft } from "../../src/api/core.generated";
import type {
  DataAgentHealth,
  DataConnection,
  Comparison,
  Draft,
  EvidenceView,
  MergeConflict,
  Member,
  Metric,
  ModelingSession,
  ProposalBatchDetail,
  ProposalItem,
  PublishPreview,
  VersionSummary,
  Workspace,
} from "../../src/api/types";

export const WORKSPACE_ID = "ws-visual-demo";

function readExample(fileName: string): CoreDraft {
  const fileUrl = new URL(`../../../../docs/design/core-1-examples/${fileName}`, import.meta.url);
  const parsed = JSON.parse(readFileSync(fileUrl, "utf8")) as { draft: CoreDraft };
  return structuredClone(parsed.draft);
}

function toStoredDraft(source: CoreDraft): Draft {
  return {
    schema_version: "core-1",
    workspace_id: source.workspace_id,
    object_types: (source.object_types ?? []).map((o) => ({
      description: "",
      synonyms: [],
      tags: [],
      evidence: [],
      extends: null,
      derived_by: [],
      title_property_id: null,
      ...o,
    })),
    properties: (source.properties ?? []).map((p) => ({
      description: "",
      synonyms: [],
      evidence: [],
      identifier: false,
      unique: false,
      required: false,
      ...p,
    })),
    link_types: (source.link_types ?? []).map((l) => ({
      description: "",
      synonyms: [],
      tags: [],
      evidence: [],
      inverse_name: null,
      data_join: null,
      ...l,
    })),
    rules: (source.rules ?? []).map((r) => ({ description: "", evidence: [], ...r })),
    metrics: (source.metrics ?? []).map((m) => {
      const common = { description: "", synonyms: [], evidence: [] };
      if (m.kind === "simple") return { ...common, filters: [], measure: null, time_field: null, ...m } as Metric;
      if (m.kind === "expression") return { ...common, value_kind: null, time_field: null, ...m } as Metric;
      return { ...common, ...m } as Metric;
    }),
    datasets: (source.datasets ?? []).map((d) => ({
      description: "",
      dialect: null,
      schema_name: null,
      snapshot_date_column: null,
      columns: null,
      ...d,
    })),
    mappings: (source.mappings ?? []).map((m) => ({
      fields: {},
      membership_source_id: null,
      inherited_link_bindings: {},
      ...m,
      sources: (m.sources ?? []).map((s) => ({ key_columns: [], ...s })),
    })),
    material_objects: (source.material_objects ?? []).map((o) => ({ values: {}, evidence: [], ...o })),
    material_links: (source.material_links ?? []).map((l) => ({ evidence: [], ...l })),
  };
}

/**
 * Deterministic core-1 draft built from the inheritance and partial-mapping
 * examples so both tabs of MappingsPage render every visual state (registered
 * datasets, snapshot tags, metric/object counts, independent/shared/virtual/unbound
 * modes, and mapped/partial/unmapped StatusMark states).
 */
function buildMappingsDraft(): Draft {
  const inheritance = readExample("06-inheritance.json");
  const partial = readExample("10-partial.json");

  inheritance.workspace_id = WORKSPACE_ID;

  // Give one dataset a daily snapshot column so the snapshot Tag renders.
  const contracts = inheritance.datasets?.find((d) => d.name === "contracts");
  if (contracts) {
    contracts.snapshot_date_column = "stat_date";
  }

  // Leave one property unbound on `supplier` so the partial state (1/2) renders.
  const supplierMapping = inheritance.mappings?.find((m) => m.id === "f3a4f071-6959-5546-8efd-2d24bb6123bc");
  if (supplierMapping?.fields) {
    delete supplierMapping.fields.name;
  }

  // Append the unmapped `city` object and its identifier property from 10-partial.
  const cityObject = partial.object_types?.find((o) => o.technical_name === "city");
  const cityProps = (partial.properties ?? []).filter((p) => p.owner_type_id === cityObject?.id);
  if (cityObject) {
    inheritance.object_types = [...(inheritance.object_types ?? []), cityObject];
    inheritance.properties = [...(inheritance.properties ?? []), ...cityProps];
  }

  return toStoredDraft(inheritance);
}

const FIXTURE_DRAFT = buildMappingsDraft();

const FIXTURE_WORKSPACE: Workspace = {
  id: WORKSPACE_ID,
  name: "星河零售示例空间",
  slug: "xinghe-retail-demo",
  description: "用于界面视觉回归测试的虚构工作空间",
  current_version: 3,
  version_id: "ver-visual-demo-3",
  version_sha256: "a".repeat(64),
  updated_at: "2026-10-16T08:00:00Z",
  role: "admin",
  visibility: "member",
  object_type_count: FIXTURE_DRAFT.object_types.length,
  link_type_count: FIXTURE_DRAFT.link_types.length,
};

const FIXTURE_WORKSPACES: Workspace[] = [
  FIXTURE_WORKSPACE,
  {
    ...FIXTURE_WORKSPACE,
    id: "ws-visual-lab",
    name: "云杉设备示例空间",
    slug: "yunshan-equipment-demo",
    description: "设备与维护记录的虚构建模空间",
    role: "member",
    current_version: null,
    version_id: null,
    version_sha256: null,
    object_type_count: 0,
    link_type_count: 0,
  },
  {
    ...FIXTURE_WORKSPACE,
    id: "ws-visual-reader",
    name: "青禾供应链示例空间",
    slug: "qinghe-supply-demo",
    description: "供访客查看的虚构本体",
    role: null,
    visibility: "published_only",
    object_type_count: 6,
    link_type_count: 4,
  },
];

const FIXTURE_CONNECTIONS: DataConnection[] = [
  {
    id: "conn-visual-retail",
    name: "星河零售只读库",
    kind: "postgresql",
    host: "retail-db.example.invalid",
    port: 5432,
    database: "xinghe_demo",
    username: "demo_reader",
  },
  {
    id: "conn-visual-equipment",
    name: "云杉设备分析库",
    kind: "mysql",
    host: "equipment-db.example.invalid",
    port: 3306,
    database: "yunshan_demo",
    username: "demo_reader",
  },
];

const FIXTURE_MEMBERS: Member[] = [
  { id: 1, user_id: "user-visual-demo", name: "林晓", subject: "demo:linxiao", role: "admin" },
  { id: 2, user_id: "user-visual-member", name: "陈宁", subject: "demo:chenning", role: "member" },
];

const FIXTURE_HEALTH: DataAgentHealth = {
  ok: false,
  checks: [
    { name: "配置完整性", ok: true, message: "配置完整", hint: "" },
    { name: "连通性", ok: true, message: "连接成功", hint: "" },
    {
      name: "Agent 存在性",
      ok: false,
      message: "未找到示例 Agent",
      hint: "请在 DataAgent 管理端检查示例 Agent 的配置",
    },
  ],
};

const FIXTURE_VERSIONS: VersionSummary[] = [3, 2, 1].map((version) => ({
  workspace_id: WORKSPACE_ID,
  version_id: `ver-visual-demo-${version}`,
  version_sha256: String(version).repeat(64),
  version_content_sha256: String(version).repeat(64),
  normalized_snapshot_sha256: String(version).repeat(64),
  version,
  status: "published",
  message: ["", "初始本体", "补充合同与当事人关系", "补充设备与车辆继承关系"][version],
  published_at: `2026-10-${13 + version}T08:00:00Z`,
  validation: {
    standard: "core-1",
    schema_status: "passed",
    semantic_status: "passed",
    errors: [],
    warnings: [],
    publishable: true,
  },
  counts: {
    object_types: FIXTURE_DRAFT.object_types.length,
    link_types: FIXTURE_DRAFT.link_types.length,
    attributes: FIXTURE_DRAFT.properties.length,
    rules: FIXTURE_DRAFT.rules.length,
    metrics: FIXTURE_DRAFT.metrics.length,
  },
}));

export async function mockMappingsApi(page: Page) {
  const base = `/api/v1/workspaces/${WORKSPACE_ID}`;
  const responses: Record<string, unknown> = {
    "/api/v1/auth/me": { id: "user-visual-demo", subject: "demo:linxiao", display_name: "林晓", email: null },
    "/api/v1/workspaces": { items: FIXTURE_WORKSPACES },
    [base]: FIXTURE_WORKSPACE,
    [`${base}/published-snapshot`]: FIXTURE_DRAFT,
    [`${base}/connections`]: { items: FIXTURE_CONNECTIONS },
    [`${base}/members`]: { items: FIXTURE_MEMBERS },
    [`${base}/settings/dataagent-health`]: FIXTURE_HEALTH,
    [`${base}/versions`]: { items: FIXTURE_VERSIONS },
  };
  // Match the backend prefix only: a "**/api/**" glob also catches Vite's
  // /src/api/*.ts modules and stops the app from loading.
  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    async (route) => {
      const { pathname } = new URL(route.request().url());
      await route.fulfill({ json: responses[pathname] ?? { items: [] } });
    },
  );
}

export const REVIEW_SESSION_ID = "session-visual-review";

const SUPPLIER = FIXTURE_DRAFT.object_types.find((item) => item.technical_name === "supplier")!;
const REVIEW_EVIDENCE: EvidenceView[] = [
  {
    kind: "material",
    id: "evidence-visual-supplier",
    material_id: "material-visual-guide",
    material_sha256: "b".repeat(64),
    material_name: "星河采购业务说明.md",
    material_archived: false,
    locator: { line_start: 12, line_end: 14, heading: "供应商范围" },
    quote: "供应商是向星河零售提供商品或服务的组织，统一登记名称与供应范围。",
  },
  {
    kind: "manual",
    id: "evidence-visual-confirmation",
    created_by: "林晓",
    created_at: "2026-10-17T02:00:00Z",
    note: "已确认供应商范围包含商品与服务。",
  },
];

function reviewItem(overrides: Partial<ProposalItem>): ProposalItem {
  return {
    id: "proposal-visual-supplier",
    batch_id: "batch-visual-review",
    ordinal: 0,
    client_ref: null,
    operation: "update",
    target_kind: "object_type",
    target_id: SUPPLIER.id,
    display_name: "供应商",
    owner_label: null,
    before: { ...SUPPLIER, description: "提供商品的组织" },
    after: { ...SUPPLIER, description: "提供商品或服务的组织" },
    field_changes: [{ path: "description", before: "提供商品的组织", after: "提供商品或服务的组织" }],
    evidence: REVIEW_EVIDENCE,
    reason: "依据采购业务说明，补充供应商的服务范围。",
    depends_on: [],
    dependency_group: [],
    atomic_group_id: null,
    duplicate_candidates: [],
    status: "pending",
    stored_status: "pending",
    status_reason: "",
    accepted_revision: null,
    decided_at: null,
    ...overrides,
  };
}

const REVIEW_BATCH: ProposalBatchDetail = {
  id: "batch-visual-review",
  status: "available",
  created_at: "2026-10-17T02:00:00Z",
  source_session_revision: 7,
  base_version_id: "ver-visual-demo-2",
  counts: { pending: 3, accepted: 1, rejected: 1, stale: 1, conflict: 0, superseded: 0 },
  error: null,
  items: [
    reviewItem({}),
    reviewItem({
      id: "proposal-visual-property",
      ordinal: 1,
      operation: "create",
      target_kind: "property",
      target_id: "property-visual-service-scope",
      display_name: "供应范围",
      owner_label: "供应商",
      before: null,
      after: {
        id: "property-visual-service-scope",
        owner_type_id: SUPPLIER.id,
        name: "供应范围",
        technical_name: "service_scope",
        value_kind: "string",
        description: "供应商提供的商品或服务范围",
        identifier: false,
        unique: false,
        required: false,
        synonyms: [],
        evidence: [],
      },
      field_changes: [],
      depends_on: ["proposal-visual-supplier"],
      dependency_group: ["proposal-visual-property", "proposal-visual-supplier"],
    }),
    reviewItem({ id: "proposal-visual-name", ordinal: 2, display_name: "供应商名称", evidence: [] }),
    reviewItem({ id: "proposal-visual-accepted", ordinal: 3, status: "accepted", stored_status: "accepted", accepted_revision: 7 }),
    reviewItem({ id: "proposal-visual-rejected", ordinal: 4, status: "rejected", stored_status: "rejected" }),
    reviewItem({ id: "proposal-visual-stale", ordinal: 5, status: "stale", status_reason: "目标在提案生成后已被修改" }),
  ],
};

const REVIEW_DRAFT = structuredClone(FIXTURE_DRAFT);
REVIEW_DRAFT.object_types.find((item) => item.id === SUPPLIER.id)!.description = "提供商品或服务的组织";

const REVIEW_SESSION: ModelingSession = {
  id: REVIEW_SESSION_ID,
  workspace_id: WORKSPACE_ID,
  title: "供应商范围修订",
  base_version_id: "ver-visual-demo-2",
  revision: 7,
  draft: REVIEW_DRAFT,
  draft_sha256: "d".repeat(64),
  base_version_sha256: "2".repeat(64),
  pending_proposal_count: 3,
  latest_batch_id: REVIEW_BATCH.id,
  base_diff: [{
    element_kind: "object_type",
    element_id: SUPPLIER.id,
    label: "供应商",
    change: "updated",
    before: REVIEW_BATCH.items[0].before,
    after: REVIEW_BATCH.items[0].after,
    field_changes: REVIEW_BATCH.items[0].field_changes,
  }],
  graph: {
    workspace_id: WORKSPACE_ID,
    version_id: "",
    version_sha256: "d".repeat(64),
    version_content_sha256: "d".repeat(64),
    normalized_snapshot_sha256: "d".repeat(64),
    nodes: [],
    edges: [],
  },
  material_ids: ["material-visual-guide"],
  task_status: "finished",
  task_detail: "",
  dataagent_topic_id: null,
  dataagent_task_id: null,
  updated_at: "2026-10-17T02:00:00Z",
};

const REVIEW_PREVIEW: PublishPreview = {
  session_revision: 7,
  base_version_id: "ver-visual-demo-2",
  base_version_number: 2,
  current_version_id: "ver-visual-demo-3",
  current_version_number: 3,
  next_version_number: 4,
  current_version_sha256: "3".repeat(64),
  merged_snapshot_sha256: "e".repeat(64),
  merged_model: REVIEW_DRAFT,
  validation: {
    ...FIXTURE_VERSIONS[0].validation,
    warnings: [{ message: "供应商名称尚未绑定数据来源" }],
  },
  changes: REVIEW_SESSION.base_diff,
  labels: { [SUPPLIER.id]: "供应商" },
  impacts: [],
  auto_merged: [],
};

const REVIEW_CONFLICTS: MergeConflict[] = [
  {
    key: `/object_types/${SUPPLIER.id}/description`,
    element_kind: "object_type",
    element_id: SUPPLIER.id,
    element_label: "供应商",
    path: "description",
    kind: "field",
    base: "提供商品的组织",
    latest: "经资质审核的商品供应组织",
    draft: "提供商品或服务的组织",
    allowed: ["latest", "draft", "custom"],
  },
  {
    key: `/object_types/${SUPPLIER.id}/tags`,
    element_kind: "object_type",
    element_id: SUPPLIER.id,
    element_label: "供应商",
    path: "tags",
    kind: "field",
    base: ["采购"],
    latest: ["采购", "资质管理"],
    draft: ["采购", "服务"],
    allowed: ["latest", "draft", "custom", "both"],
  },
];

/** Adds review data while keeping the common workspace API interception. */
export async function mockReviewApi(page: Page, options: { conflicts?: boolean } = {}) {
  await mockMappingsApi(page);
  const base = `/api/v1/workspaces/${WORKSPACE_ID}`;
  const sessionPath = `${base}/sessions/${REVIEW_SESSION_ID}`;
  const comparison: Comparison = {
    left: null,
    right: FIXTURE_VERSIONS[0],
    changes: [
      { path: `/object_types/${SUPPLIER.id}/description`, kind: "changed", before: "提供商品的组织", after: "提供商品或服务的组织" },
      { path: "/properties/service_scope", kind: "added", before: null, after: { name: "供应范围", value_kind: "string" } },
    ],
    impacts: [{ kind: "object_type", id: SUPPLIER.id, label: "供应商" }],
  };
  const responses: Record<string, unknown> = {
    [`${base}/sessions`]: { items: [{ ...REVIEW_SESSION, has_unpublished_changes: true }] },
    [sessionPath]: REVIEW_SESSION,
    [`${sessionPath}/preview`]: REVIEW_PREVIEW,
    [`${sessionPath}/proposal-batches`]: { items: [REVIEW_BATCH], next_cursor: null },
    [`${sessionPath}/proposal-batches/${REVIEW_BATCH.id}`]: REVIEW_BATCH,
    [`${sessionPath}/agent-conversation`]: { messages: [], run: null },
    [`${base}/capabilities`]: { agent_configured: true, model: "demo-model", max_file_mb: 256, connections_configured: true, skills: [] },
    [`${base}/materials`]: { items: [] },
    [`${base}/version-comparison`]: comparison,
  };
  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    async (route) => {
      const { pathname, searchParams } = new URL(route.request().url());
      if (pathname === `${sessionPath}/preview` && options.conflicts) {
        await route.fulfill({
          status: 409,
          json: { error: { code: "MERGE_CONFLICTS", message: "合并存在冲突", conflicts: REVIEW_CONFLICTS, current_version_id: "ver-visual-demo-3" } },
        });
      } else if (pathname === `${base}/version-comparison`) {
        const left = FIXTURE_VERSIONS.find((version) => version.version_id === searchParams.get("left_id")) ?? null;
        await route.fulfill({ json: {
          ...comparison,
          left,
          right: FIXTURE_VERSIONS.find((version) => version.version_id === searchParams.get("right_id")) ?? comparison.right,
          changes: left ? comparison.changes : [{ path: `/object_types/${SUPPLIER.id}`, kind: "added", before: null, after: { name: "供应商" } }],
        } });
      } else if (Object.hasOwn(responses, pathname)) {
        await route.fulfill({ json: responses[pathname] });
      } else {
        await route.fallback();
      }
    },
  );
}
