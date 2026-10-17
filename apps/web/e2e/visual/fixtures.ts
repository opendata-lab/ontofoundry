import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import type { CoreDraft } from "../../src/api/core.generated";
import type {
  DataAgentHealth,
  DataConnection,
  Draft,
  Member,
  Metric,
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
