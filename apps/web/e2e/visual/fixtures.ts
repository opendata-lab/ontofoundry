import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { effectiveProperties } from "../../src/lib/coreModel";
import { documentDisplayText } from "../../src/lib/instanceDisplay";
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

type ExampleInstances = { material_objects?: Partial<Draft["material_objects"][number]>[]; material_links?: Partial<Draft["material_links"][number]>[] };

// Instances left core-1 for the instance store; the backend fixture keeps the examples' instances.
const INSTANCE_FIXTURES = JSON.parse(
  readFileSync(new URL("../../../api/tests/fixtures/document_instances.json", import.meta.url), "utf8"),
) as Record<string, ExampleInstances>;

function readExample(fileName: string): CoreDraft & ExampleInstances {
  const fileUrl = new URL(`../../../../docs/design/core-1-examples/${fileName}`, import.meta.url);
  const parsed = JSON.parse(readFileSync(fileUrl, "utf8")) as { draft: CoreDraft };
  return structuredClone({ ...parsed.draft, ...(INSTANCE_FIXTURES[fileName.replace(/\.json$/, "")] ?? {}) });
}

/** Serves the instance store reads the client merges into drafts; other requests pass through. */
async function mockInstances(page: Page, draft: Draft) {
  const items = [
    ...draft.material_objects.map((element) => ({ target_kind: "material_object", element })),
    ...draft.material_links.map((element) => ({ target_kind: "material_link", element })),
  ].map((item) => ({ ...item, target_id: item.element.id, revision: 1, state: "active", session_id: null, hash: "0".repeat(64) }));
  await page.route(
    (url) => url.pathname.startsWith("/api/") && /\/(instances|instance-baseline)$/.test(url.pathname),
    (route) => route.fulfill({ json: { change_sequence: 1, items } }),
  );
}

function toStoredDraft(source: CoreDraft & ExampleInstances): Draft {
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
      value_type_id: null,
      ...p,
    })),
    link_types: (source.link_types ?? []).map((l) => ({
      description: "",
      synonyms: [],
      tags: [],
      evidence: [],
      verbalizes: [],
      source_role_name: null,
      target_role_name: null,
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
      source_kind: "table" as const,
      connection_id: null,
      display_name: null,
      query_sql: null,
      table_name: null,
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
    material_objects: (source.material_objects ?? []).map((o) => ({ values: {}, evidence: [], ...o }) as Draft["material_objects"][number]),
    material_links: (source.material_links ?? []).map((l) => ({ evidence: [], ...l }) as Draft["material_links"][number]),
    value_types: (source.value_types ?? []).map((v) => ({ description: "", evidence: [], display_name: null, ...v })),
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
  const cityObject = partial.object_types?.find((o) => o.name === "city");
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
    [`${base}/connections/conn-visual-retail/schemas`]: { items: ["public", "fiction_archive"] },
    [`${base}/connections/conn-visual-retail/tables`]: { items: [{ name: "parties" }, { name: "daily_sales" }, { name: "fiction_stores" }] },
    [`${base}/connections/conn-visual-retail/assets/sync-jobs`]: { id: "visual-sync", connection_id: "conn-visual-retail", schema_name: "public", scope: "all", state: "succeeded", total: 3, processed: 3, available: 3, failed: 0, duration_ms: 240, error: null, batches: [{ id: "visual-batch", ordinal: 0, state: "succeeded", attempt: 1, duration_ms: 240, error: null, tables: ["parties", "daily_sales", "fiction_stores"], results: [{ table_name: "parties", state: "succeeded" }, { table_name: "daily_sales", state: "succeeded" }, { table_name: "fiction_stores", state: "succeeded" }] }] },
    [`${base}/connections/conn-visual-retail/assets`]: {
      connection_id: "conn-visual-retail",
      version_id: null,
      metadata_snapshot_id: "snapshot-visual-retail",
      observed_at: "2026-10-17T02:00:00Z",
      error: null,
      changes: [],
      status: "ready",
      items: [
        { name: "parties", schema: "public", observed_at: "2026-10-17T02:00:00Z", comment: "当事人主数据", missing: false, datasets: [], columns: [{ name: "party_id", type: "varchar(32)", primary_key: true, nullable: false }, { name: "party_name", type: "varchar(120)", primary_key: false, nullable: false }, { name: "level", type: "varchar(16)", primary_key: false, nullable: true }] },
        { name: "daily_sales", schema: "public", observed_at: "2026-10-17T02:00:00Z", comment: "门店日销售汇总", missing: false, datasets: [], columns: [{ name: "stat_date", type: "date", primary_key: true, nullable: false }, { name: "store_id", type: "varchar(16)", primary_key: true, nullable: false }, { name: "amount", type: "numeric(12,2)", primary_key: false, nullable: true }] },
        { name: "legacy_refunds", schema: "public", observed_at: "2026-10-17T02:00:00Z", comment: "已下线的退款表", missing: true, datasets: [], columns: [{ name: "refund_id", type: "varchar(32)", primary_key: true, nullable: false }] },
      ],
    },
  };
  // Match the backend prefix only: a "**/api/**" glob also catches Vite's
  // /src/api/*.ts modules and stops the app from loading.
  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    async (route) => {
      const { pathname, searchParams } = new URL(route.request().url());
      if (pathname.endsWith("/assets/sync-jobs") && route.request().method() === "GET") {
        await route.fulfill({ json: { items: [] } });
      } else if (pathname.endsWith("/assets/synced")) {
        // Only the synced schema is registered; fiction_archive exists on the server but was never synced.
        await route.fulfill({ json: { items: [{ schema: "public", assets: responses[pathname.replace(/\/synced$/, "")] }] } });
      } else if (pathname.endsWith("/assets") && searchParams.get("schema_name") === "fiction_archive") {
        await route.fulfill({ json: { ...(responses[pathname] as object), items: [], observed_at: null } });
      } else {
        await route.fulfill({ json: responses[pathname] ?? { items: [] } });
      }
    },
  );
}

export const REVIEW_SESSION_ID = "session-visual-review";

const SUPPLIER = FIXTURE_DRAFT.object_types.find((item) => item.name === "supplier")!;
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
  counts: { pending: 3, accepted: 1, rejected: 1, stale: 1, conflict: 0, superseded: 0, unacceptable: 0 },
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
        display_name: "供应范围",
        name: "service_scope",
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
  instance_change_sequence: 1,
  affected_instances: [],
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
  await mockInstances(page, FIXTURE_DRAFT);
}

export const ELEMENT_DRAFT = structuredClone(FIXTURE_DRAFT);
export const ELEMENTS = {
  object: ELEMENT_DRAFT.object_types.find((item) => item.name === "person")!,
  derived: ELEMENT_DRAFT.object_types.find((item) => item.name === "vip_party")!,
  relation: ELEMENT_DRAFT.link_types.find((item) => item.name === "signer")!,
  metric: ELEMENT_DRAFT.metrics.find((item) => item.name === "vip_party_count")!,
  dataset: ELEMENT_DRAFT.datasets.find((item) => item.name === "contracts")!,
};
ELEMENTS.dataset.columns!.push({ name: "stat_date", physical_type: "date", comment: "每日快照日期" });

/** Inspector requests reuse the common workspace fixture and never reach a backend. */
export async function mockElementsApi(page: Page, options: { impact?: boolean } = {}) {
  await mockMappingsApi(page);
  const base = `/api/v1/workspaces/${WORKSPACE_ID}`;
  const preview: import("../../src/api/types").MetricPreview = {
    definition_hash: "f".repeat(64),
    context_version: FIXTURE_WORKSPACE.version_id,
    session_revision: null,
    status: "ok",
    value: 1280,
    value_kind: "integer",
    snapshot_dates: [],
    warnings: [],
    total_query: {
      sql: "SELECT COUNT(*) FROM inheritance_demo.parties WHERE level = :level",
      params: { level: "VIP" },
      dialect: "mysql",
      database: "inheritance_demo",
    },
  };
  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    async (route) => {
      const { pathname } = new URL(route.request().url());
      if (pathname === `${base}/published-snapshot`) {
        await route.fulfill({ json: ELEMENT_DRAFT });
      } else if (pathname === `/api/v1/modeling/workspaces/${WORKSPACE_ID}/metrics/preview`) {
        await route.fulfill({ json: preview });
      } else if (pathname === `${base}/element-saves/preview`) {
        const impact: import("../../src/api/types").ElementSaveImpact = {
          current_version_id: FIXTURE_WORKSPACE.version_id,
          session_revision: null,
          affected_items: options.impact ? [{
            target_kind: "material_object",
            target_id: ELEMENT_DRAFT.material_objects.find((item) => item.type_id === ELEMENTS.object.id)!.id,
            expected_target_hash: "1".repeat(64),
            reason: "当前元素修改需要同步此依赖的定义或引用",
          }] : [],
        };
        await route.fulfill({ json: impact });
      } else {
        await route.fallback();
      }
    },
  );
  await mockInstances(page, ELEMENT_DRAFT);
}


export const INSTANCE_TYPE = ELEMENTS.object;
export const INSTANCE_FACT = ELEMENT_DRAFT.material_objects.find((item) => item.type_id === INSTANCE_TYPE.id)!;
export const INSTANCE_LABEL = documentDisplayText(ELEMENT_DRAFT, INSTANCE_FACT);

/** Fixed overview, conversation and document instances share the existing virtual workspace. */
export async function mockCanvasApi(page: Page, options: { emptySession?: boolean; proposalIssue?: "failed" | "unacceptable" } = {}) {
  await mockReviewApi(page);
  const base = `/api/v1/workspaces/${WORKSPACE_ID}`;
  const overview: import("../../src/api/types").WorkspaceOverview = {
    version: { ...FIXTURE_VERSIONS[0], counts: { ...FIXTURE_VERSIONS[0].counts, datasets: ELEMENT_DRAFT.datasets.length } },
    graph: {
      ...FIXTURE_VERSIONS[0],
      nodes: ELEMENT_DRAFT.object_types.map((type) => ({
        id: type.id, kind: "object_type", label: type.display_name || type.name, name: type.name,
        description: type.description, tags: type.tags, attribute_count: effectiveProperties(ELEMENT_DRAFT, type.id).length,
      })),
      edges: [
        ...ELEMENT_DRAFT.link_types.map((link) => ({
          id: link.id, kind: "link_type" as const, label: link.display_name || link.name, name: link.name,
          source: link.source_type_id, target: link.target_type_id, link_type_id: link.id,
          description: link.description, multiplicity: link.multiplicity,
        })),
        ...ELEMENT_DRAFT.object_types.filter((type) => type.extends).map((type) => ({
          id: `extends:${type.id}`, kind: "extends" as const, label: "继承", name: "extends",
          source: type.id, target: type.extends!,
        })),
      ],
    },
    details: {
      object_count: ELEMENT_DRAFT.material_objects.length,
      link_count: ELEMENT_DRAFT.material_links.length,
      evidence_material_count: 1,
      mapping_count: ELEMENT_DRAFT.mappings.length,
      objects: ELEMENT_DRAFT.material_objects.map((fact) => ({
        id: fact.id, type_id: fact.type_id, display_text: documentDisplayText(ELEMENT_DRAFT, fact),
      })),
      links: ELEMENT_DRAFT.material_links,
      mappings: ELEMENT_DRAFT.mappings.map((mapping) => ({ id: mapping.id, type_id: mapping.type_id, binding_status: "bound" })),
    },
  };
  const responses: Record<string, unknown> = {
    [`${base}/overview`]: overview,
    [`${base}/published-snapshot`]: ELEMENT_DRAFT,
    [`${base}/materials`]: { items: [{ id: "material-visual-guide", name: "星河采购业务说明.md", byte_size: 1280, chunk_count: 6, sha256: "b".repeat(64) }] },
  };
  if (options.emptySession) responses[`${base}/sessions`] = { items: [] };
  if (options.proposalIssue) {
    const failed = options.proposalIssue === "failed";
    const notice = { run_token: "fictional-run", summary: failed ? "修正次数已用完，本轮未生成符合契约的结果" : "关系的目标连接列不是唯一属性或完整标识；依赖该关系的提案不可接受", affected_count: failed ? 0 : 2, reviewable_count: failed ? 0 : 4 };
    responses[`${base}/sessions/${REVIEW_SESSION_ID}`] = { ...REVIEW_SESSION, task_status: failed ? "failed" : "finished", proposal_notice: notice };
    const batch = structuredClone(REVIEW_BATCH);
    if (failed) {
      batch.status = "failed";
      batch.error = { code: "REPAIR_BUDGET_EXHAUSTED", message: notice.summary };
      batch.items = [];
      batch.counts = { pending: 0, accepted: 0, rejected: 0, stale: 0, conflict: 0, superseded: 0, unacceptable: 0 };
    }
    else {
      batch.items.slice(0, 2).forEach((item) => { item.status = "unacceptable"; item.stored_status = "unacceptable"; item.status_reason = notice.summary; });
      batch.counts.unacceptable = 2;
      batch.counts.pending = 1;
    }
    responses[`${base}/sessions/${REVIEW_SESSION_ID}/proposal-batches`] = { items: [batch], next_cursor: null };
    responses[`${base}/sessions/${REVIEW_SESSION_ID}/proposal-batches/${batch.id}`] = batch;
  }

  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    async (route) => {
      const { pathname } = new URL(route.request().url());
      if (Object.hasOwn(responses, pathname)) await route.fulfill({ json: responses[pathname] });
      else await route.fallback();
    },
  );
  await mockInstances(page, ELEMENT_DRAFT);
}
