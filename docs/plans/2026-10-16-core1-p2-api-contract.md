# core-1 P2 前后端接口契约

日期：2026-10-16。代码基线：`a5fcd6e`，协调分支：`feat/core1-p2-contract`。

本文件供 P2 后端 P2-01～14 与前端 P2-15～21 在不同分支并行实现。它描述切换后的接口，不表示基线代码已经支持。依据为[主设计](../design/2026-10-14-core-model-and-format-adapters.md) §3、§8A、§14、决定 49～51，[实施计划](2026-10-14-core-model-and-format-adapters-plan.md) §2.4、§2.5、§5、§9，以及 [P1 记录](2026-10-16-core1-p1-backend-progress.md)。已对照 `api/*.py`、`api/client.ts`、`api/types.ts` 与 `api/core.generated.ts`。

只使用现有 REST 路径，以及计划允许的事实提案修订、当前指标表单预览，以及 PR #23 修正增加的只读元素保存影响预检路径。不新增 Dataset CRUD、映射树、数据集引用计数或 MCP 执行接口。下文补齐的请求 envelope、读投影和错误名称是本次协调约定，不是核心模型字段；尚需双方确认的具体选择集中在 §10。P2 必须完整集成后部署；不运行旧版本兼容转换。

## 1. 通用约定

为缩短表格，使用以下路径缩写，拼接时没有额外斜线：

```ts
const W = "/api/v1/workspaces/{workspace_id}";
const S = W + "/sessions/{session_id}";
const O = "/api/v1/ontology/workspaces/{workspace_id}";
const C = W + "/connections/{connection_id}";
const A = S + "/agent-conversation";
```

- 路径中的 id 均按字符串编码。元素、会话、版本和提案为 UUID；材料 id 沿用现有材料系统的字符串。GET 无请求体，表中 `—` 表示无额外参数或无请求体；POST/PUT/PATCH 默认 JSON。没有列出的查询参数不使用。
- 浏览器保持同源 cookie、`credentials: "include"`。REST 的 `version_id?` 仍可用于历史版本浏览，不能据此向 MCP 四工具传版本参数。
- 成功默认 HTTP 200；工作空间、会话、连接、材料创建为 201，消息提交为 202；204 不解析 JSON。二进制、重定向和 SSE 见具体接口。
- 写入只接受 core-1；结构严格禁止额外字段。服务端响应草稿始终补齐九集合及默认值。P1 生成 TS 中因 Pydantic 默认值而可选的字段，不代表前端可以省略响应中的集合。
- 读响应不整体回传。编辑器从核心定义构造请求，删除只读投影。空数组与 null 按各核心类型处理，不能用 truthy 判断丢掉 0、false。
- 同一个请求的校验、依赖展开、修订和提交在事务内完成；失败不留下部分写入。所有草稿写入更新语义 hash；前端不计算、重签服务端 hash。

### 1.1 核心类型的引用

下面所有 TS 段属于同一份类型说明；mock 段另有明确的初始化说明。核心字段完全引用 P1 已生成的类型，不在这里另造核心接口：

```ts
import type {
  CoreDraft, ObjectType, Property, LinkType, Rule, Dataset, DatasetColumn,
  DataMapping, MappingSource, ColumnBinding, ExpressionBinding, DataJoin,
  SimpleMetric, RatioMetric, ExpressionMetric, ColumnReference, ValueKind,
  MaterialObject, MaterialLink, MaterialEvidence, ManualEvidence,
} from "../../apps/web/src/api/core.generated";

type UUID = string;
type ISODate = string;     // YYYY-MM-DD
type ISOTime = string;    // ISO 8601 with offset
type SHA256 = string;     // 64 lowercase hexadecimal characters
type Scalar = string | number | boolean | null;
type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
type Metric = SimpleMetric | RatioMetric | ExpressionMetric;
type EvidenceEntry = MaterialEvidence | ManualEvidence;
type TargetKind = "object_type" | "property" | "link_type" | "rule" |
  "metric" | "dataset" | "mapping" | "material_object" | "material_link";
type ElementByKind = {
  object_type: ObjectType; property: Property; link_type: LinkType; rule: Rule;
  metric: Metric; dataset: Dataset; mapping: DataMapping;
  material_object: MaterialObject; material_link: MaterialLink;
};
type CoreElement = ElementByKind[TargetKind];
type CollectionKey = "object_types" | "properties" | "link_types" | "rules" |
  "metrics" | "datasets" | "mappings" | "material_objects" | "material_links";
type Draft = CoreDraft & Required<Pick<CoreDraft, CollectionKey>> & {
  schema_version: "core-1";
};
type Page<T> = { total: number; items: T[]; next_cursor: string | null };
type Items<T> = { items: T[] };
type VersionQuery = { version_id?: UUID };
```

`Metric` 是三个生成类型的联合；不要给 ratio 补 `dataset_id/time_field/value_kind` 输入，不给 simple 补 `value_kind`。Property.value_kind 和 ExpressionMetric.value_kind 本身是合法输入。Dataset 无 technical_name、evidence、连接别名、采集时间；DataMapping 无 evidence。ObjectType.extends 是一个 UUID 或 null。DataJoin、Path、条件、来源键组的顺序及联合形状直接遵循生成类型。

### 1.2 错误

P2 改造的业务接口统一抛 ServiceError，输出：

```ts
type ErrorResponse = {
  error: {
    code: string; message: string;
    items?: { proposal_id: UUID; reason: string }[];
    conflicts?: MergeConflict[];
    references?: { name: string; field: string }[] | string[];
    current_version_id?: UUID | null;
    errors?: ValidationIssue[];
  };
};
```

下表用错误组引用每条接口的错误。`HTTP_ERROR` 是现有客户端对没有 ServiceError code 的 HTTP 错误的兜底名称，**不是后端 ServiceError code**。保留不变的登录、设置、连接、材料、会话对话接口仍可能返回原有 `detail`，不能宣称基线所有错误已经统一。框架请求结构校验仍可能为 HTTP 422 `detail` 数组。

| 错误组 | HTTP / ServiceError code | 含义与前端处理 |
|---|---|---|
| G | 404 `NOT_FOUND`、`SESSION_NOT_FOUND`、`BATCH_NOT_FOUND`；409 `CONFLICT`、`ELEMENT_KIND_CONFLICT` | 资源/会话/批次不存在、普通唯一性/事务冲突，或同一元素 UUID 被用于不同种类；展示中文 message |
| Auth | 401/403；403 `INSTANCES_FORBIDDEN`、`MAPPINGS_FORBIDDEN` | 未登录或权限不足；后一个名称为 P2 对映射拒绝的协调约定；不显示被拒绝的数据 |
| V | 422 `WORKSPACE_MISMATCH`、`VALIDATION_FAILED`、`INSTANCE_VALIDATION_FAILED` | 空间错误、核心图/表达式或事实值错误；定位 errors，不走 Ossie 校验 |
| E | 409 `VERSION_CHANGED`、`SESSION_REVISION_CHANGED`；422 `ELEMENT_SCOPE_INVALID`、`ELEMENT_NOT_FOUND`、`ELEMENT_VALIDATION_FAILED` | 最新版或草稿已变；越出保存范围、目标缺失、元素候选图不合法；刷新后重开编辑器 |
| P | 409 `PROPOSAL_STALE`、`PROPOSAL_CONFLICT`、`PROPOSAL_NOT_DECIDABLE`、`PROPOSAL_NOT_RESTORABLE`、`PROPOSAL_UNDO_CONFLICT`；422 `PROPOSAL_NOT_FOUND`、`DECISION_DUPLICATE`、`DEPENDENCY_INCOMPLETE` | 提案过期/冲突/状态不支持，撤销会覆盖后续编辑，目标不在会话、重复决定或依赖不齐；整批决定失败 |
| I | 409 `IDEMPOTENCY_MISMATCH` | 同一决定幂等键使用了不同请求；不能改请求后复用该键 |
| Pub | 409 `PREVIEW_OUTDATED`、`MERGE_CONFLICTS`；422 `RESOLUTION_INVALID`、`CONFLICTS_UNRESOLVED`、`CORE_VALIDATION_FAILED` | 重新预览、打开冲突解决器、修正解答或核心校验错误；P2 用 CORE_VALIDATION_FAILED 替代 OSSIE_VALIDATION_FAILED |
| Read | 422 `INVALID_CURSOR`、`INVALID_OBJECT_REF` | REST 游标与筛选/版本/权限/日期不匹配，或实例 ref 非法；清游标重读 |
| Data | 422 `MAPPING_REQUIRED`、`BINDING_NOT_READY`、`SOURCE_AMBIGUOUS`、`JOIN_COLUMN_NOT_FOUND`、`INSTANCE_NOT_UNIQUE`；504 `QUERY_TIMEOUT`；502 `QUERY_FAILED` | 无绑定、来源未就绪、多连接歧义、已知列不存在、定位不唯一、只读查询超时/失败；不返回伪行或伪 0 |
| Evidence | 422 `EVIDENCE_INVALID`、`EVIDENCE_ID_DUPLICATE`、`MANUAL_EVIDENCE_IMMUTABLE` | 材料跨空间或哈希/行号/引文不匹配；证据 UUID 重复；修改已存人工证据或删除他人人工证据 |

`MAPPINGS_FORBIDDEN`、`CORE_VALIDATION_FAILED`、`BINDING_NOT_READY`、`SOURCE_AMBIGUOUS`、`INSTANCE_NOT_UNIQUE`、`QUERY_TIMEOUT/QUERY_FAILED` 是 P2 需要落地的稳定命名，不能把它们误认为 P1 已实现。Evidence 三个代码已按现有 `domain/evidence.py` 核对；新增人工证据的作者/时间由服务端覆盖，不能由前端据错误文案猜 code。

## 2. 公共读投影

### 2.1 版本、概览、核心资源

```ts
type ValidationIssue = {
  code?: string; message: string; path?: string;
  element_id?: UUID; element_kind?: TargetKind;
};
type ValidationReport = {
  standard: "core-1";
  schema_status: "passed" | "failed";
  semantic_status: "passed" | "failed";
  errors: ValidationIssue[]; warnings: ValidationIssue[]; publishable: boolean;
};
type Counts = {
  object_types: number; link_types: number; attributes: number; rules: number;
  metrics: number;
  datasets?: number; mappings?: number;
  material_objects?: number; material_links?: number;
};
type VersionEnvelope = {
  workspace_id: UUID; version_id: UUID;
  version_sha256: SHA256; version_content_sha256: SHA256;
  normalized_snapshot_sha256: SHA256;
};
type VersionSummary = VersionEnvelope & {
  version: number; status: "published"; message: string;
  published_at: ISOTime; validation: ValidationReport; counts: Counts;
};
type BindingStatus = "bound" | "unbound" | "virtual" | "missing_key" |
  "cross_connection" | "metadata_stale" | "forbidden";
type SQLReference = {
  sql: string; params: Record<string, Scalar>; dialect: string;
  database: string; note?: string;
};
type DatasetRead = Dataset & {
  binding_status: BindingStatus;
  database?: string; schema?: string | null;
  metadata_snapshot_id?: string | null; observed_at?: ISOTime | null;
};
type MetricRead =
  | (SimpleMetric & {
      value_kind: ValueKind | null; binding_status: BindingStatus;
      sql_reference?: SQLReference;
    })
  | (RatioMetric & {
      dataset_id: UUID; value_kind: "decimal"; binding_status: BindingStatus;
      components: { numerator: SimpleMetric; denominator: SimpleMetric };
      sql_reference?: SQLReference;
    })
  | (ExpressionMetric & {
      binding_status: BindingStatus; sql_reference?: SQLReference;
    });
type Effective<T> = T & {
  inherited_from: UUID | null; binding_status: BindingStatus;
};
type PropertyRead = Effective<Property> & {
  binding?: ColumnBinding | ExpressionBinding; physical_type?: string | null;
};
type LinkRead = Effective<LinkType> & { direction: "forward" | "reverse" };
type MappingRead = DataMapping & { binding_status: BindingStatus };
type ObjectTypeRead = ObjectType & {
  properties: PropertyRead[]; links: LinkRead[]; rules: Effective<Rule>[];
  child_types: Pick<ObjectType, "id" | "name" | "technical_name">[];
  binding_status: BindingStatus;
  mapping?: MappingRead | null;
  instance_source_type_ids?: UUID[];
};
 // The outer kind identifies the resource; definition.kind keeps the metric union.
type ResourceRead =
  | { kind: "object_type"; definition: ObjectTypeRead }
  | { kind: "link_type"; definition: LinkRead }
  | { kind: "metric"; definition: MetricRead }
  | { kind: "dataset"; definition: DatasetRead }
  | { kind: "metric"; definition: {
      id: UUID; name: string; technical_name: string; description?: string;
      synonyms?: string[]; binding_status: "forbidden";
    } };
type TypeList = VersionEnvelope & Items<ResourceRead> & {
  next_cursor: null; ambiguous: boolean;
};
type TypeDetail = VersionEnvelope & (
  | { ambiguous: false; item: ResourceRead }
  | { ambiguous: true; item: null; candidates: ResourceRead[] }
 );
type GraphNode = {
  id: UUID; kind: "object_type"; label: string; technical_name: string;
  description: string; tags: string[]; attribute_count?: number;
};
type GraphEdge = {
  id: string; kind: "link_type" | "extends"; label: string;
  technical_name: string; source: UUID; target: UUID;
  link_type_id?: UUID; multiplicity?: LinkType["multiplicity"];
  description?: string; tags?: string[];
};
type TypeGraph = VersionEnvelope & { nodes: GraphNode[]; edges: GraphEdge[] };
type WorkspaceOverview = {
  version: VersionSummary | null; graph: TypeGraph | null;
  details: null | {
    object_count?: number; link_count?: number; evidence_material_count?: number;
    mapping_count?: number;
    objects?: Pick<DocumentFactRead, "id" | "type_id" | "display_text">[];
    links?: Pick<MaterialLink, "id" | "type_id" | "source_id" | "target_id">[];
    mappings?: { id: UUID; type_id: UUID; binding_status: BindingStatus }[];
  };
};
```

`counts.attributes` 沿用现有展示键，表示 properties 数量，不是核心集合名。删 actions 数量；增加的指标、数据集、事实数量都是权限投影。无映射权限省略 datasets/mappings 数量和内容，无实例权限省略事实、材料数量和内容；省略不等于 0。全局材料总数从既有 materials 列表按权限取得，evidence_material_count 只表示已被事实引用的材料数，不能冒充全部材料数。全局服务层展示现有 MCP 入口，不创建模型集合或服务发现接口。未发布空间概览返回 null version/graph，进入建模仍能取得九集合空草稿。

ResourceRead 外层用 `definition` 避免资源种类 `metric` 与指标判别字段 `simple/ratio/expression` 冲突；这是读 DTO，保存只抽取核心字段。无映射权限不返回 Dataset 项，指标只保留授权摘要和 forbidden，不输出带数据集名称的 expression、分量、列或 SQL。对象物理绑定、关系 data_join、physical_type、采集标识也省略；无实例权限裁剪事实证据。`definition` 包装是 §10 待协调的命名选择。

### 2.2 会话、差异、发布

```ts
type FieldChange = { path: string; before: Json; after: Json };
type ElementChange = {
  element_kind: TargetKind; element_id: UUID; label: string;
  owner_label?: string | null; change: "created" | "updated" | "deleted";
  field_changes: FieldChange[];
  before: CoreElement | null; after: CoreElement | null;
};
type ModelingSession = {
  id: UUID; workspace_id: UUID; title: string; base_version_id: UUID | null;
  revision: number; draft: Draft; draft_sha256: SHA256; base_version_sha256: SHA256;
  pending_proposal_count: number; latest_batch_id: UUID | null;
  base_diff: ElementChange[];
  graph: Omit<TypeGraph, "version_id"> & { version_id: UUID | "" };
  material_ids: string[]; task_status: string; task_detail: string;
  dataagent_topic_id: string | null; dataagent_task_id: string | null;
  dataagent_task_mode?: string | null; dataagent_run_token?: string | null;
  uploaded_material_ids?: string[]; last_result_task_id?: string | null;
  result_state?: string; result_warnings?: string[];
  result_claimed_at?: ISOTime | null; updated_at: ISOTime;
  validation?: ValidationReport;
};
type ModelingSessionSummary = Pick<ModelingSession,
  "id" | "title" | "task_status" | "updated_at" | "base_version_id"> & {
  has_unpublished_changes: boolean;
};
type MergeConflict = {
  key: string; element_kind: TargetKind | null; element_id: UUID | null;
  element_label: string; path: string;
  kind: "field" | "delete_modify" | "duplicate_name" | "dangling_reference";
  base: Json; latest: Json; draft: Json;
  allowed: ("latest" | "draft" | "custom" | "both")[];
};
type Resolution = { choice: "latest" | "draft" | "custom" | "both"; value?: Json };
type Impact = { element_kind: TargetKind; element_id: UUID; label: string; reason: string };
type PublishPreview = {
  session_revision: number; base_version_id: UUID | null;
  base_version_number: number | null; current_version_id: UUID | null;
  current_version_number: number | null; next_version_number: number;
  current_version_sha256: SHA256; merged_snapshot_sha256: SHA256;
  merged_model: Draft; validation: ValidationReport; changes: ElementChange[];
  labels: Record<UUID, string>; impacts: Impact[];
  auto_merged: (ElementChange & { side: "latest" | "both" })[];
};
type PublishResult = { version: VersionSummary; session: ModelingSession };
type Comparison = {
  left: VersionSummary | null; right: VersionSummary;
  changes: { path: string; kind: "added" | "removed" | "changed";
    before: Json; after: Json }[];
  impacts: { kind: TargetKind; id: UUID; label: string }[];
};
```

不再有 candidates、legacy_mapping_form、requires_change、ossie、actions。derived_by 始终是核心成员分支，不能用 Rule 表达式列表覆盖。草稿只存本地定义；有效继承项从核心选择器推导，或由资源读取接口返回；不要求会话再维护第二份物理模型。

## 3. 保留不变的 REST 接口

下列路径、请求、响应业务含义不变。G、Auth 为公共错误；没有精确 ServiceError 的旧 HTTP 失败按 §1.2 处理。它们仍列入清单，避免重写页面时漏接。

### 3.1 类型

```ts
type User = { id: UUID; subject: string; display_name: string; email: string | null };
type Workspace = {
  id: UUID; slug: string; name: string; description: string;
  role: "admin" | "member" | null; visibility: "member" | "published_only";
  current_version: number | null; version_id: UUID | null;
  version_sha256: SHA256 | null; object_type_count: number; link_type_count: number;
  updated_at: ISOTime;
};
type WorkspaceCreate = { name: string; slug: string; description: string };
type Connection = {
  id: UUID; name: string; kind: "mysql" | "doris" | "postgresql";
  host: string; port: number; database: string; username: string;
};
type ConnectionCreate = Omit<Connection, "id"> & { password: string };
type CatalogColumn = {
  name: string; type: string; primary_key: boolean;
  nullable?: boolean | null; comment?: string | null;
};
type DataTable = { name: string; schema: string | null; columns: CatalogColumn[] };
type Material = {
  id: string; name: string; byte_size: number; chunk_count: number; sha256: SHA256;
  created_at: ISOTime; archived_at: ISOTime | null;
};
type Member = { id: number; user_id: UUID; name: string; subject: string; role: "admin" | "member" };
type Scope = "ontology:read" | "mappings:read" | "instances:read";
type ServiceToken = { id: UUID; name: string; created_at: ISOTime; scopes: Scope[] };
type Health = { ok: boolean; checks: { name: string; ok: boolean; message: string; hint: string }[] };
type RunRef = { task_id: string; status: string; detail: string; metadata: { mode: string } };
 // Upstream SDK messages and interaction payloads retain their existing protocol.
type ConversationSnapshot = { messages: Record<string, Json>[]; run: RunRef | null };
```

### 3.2 清单

| 方法 + 路径 | 查询 / 请求体 TS | 响应 TS | 错误与说明 |
|---|---|---|---|
| GET `/api/v1/auth/me` | — | `User` | Auth |
| GET `/api/v1/auth/login` | `{return_to?:string}`，默认 `/` | 302，OAuth URL，无 JSON | 旧认证 HTTP 错误 |
| GET `/api/v1/auth/callback` | OAuth provider 的 `{code:string;state:string}` | 302，设置 cookie | 旧认证 HTTP 错误；UI 不自行构造 |
| POST `/api/v1/auth/logout` | — | 204 | Auth |
| GET `/api/v1/workspaces` | — | `Items<Workspace>` | G、Auth |
| POST `/api/v1/workspaces` | `WorkspaceCreate` | `Workspace`，201 | G：名称/slug 冲突；Auth；422 请求校验 |
| GET `W` | — | `Workspace` | G、Auth |
| PATCH `W` | `{name:string;description:string}` | `Workspace` | G、Auth；管理员；422 请求校验 |
| GET `/api/v1/ontology/workspaces` | — | `Items<Workspace & {mcp_endpoint:string}>` | G、Auth；服务接入用目录 |
| GET `W/members` | — | `Items<Member>` | G、Auth |
| POST `W/members` | `{subject:string;role?:"member"\|"admin"}` | `{ok:true}` | 管理员；404 未登录过的用户，409 已有成员 |
| DELETE `W/members/{member_id}` | — | `{ok:true}` | 管理员；404 无成员，422 不能删自己 |
| GET `W/service-tokens` | — | `Items<ServiceToken>` | 管理员；G、Auth |
| POST `W/service-tokens` | `{name:string;scopes?:Scope[]}` | `{id:UUID;name:string;token:string;scopes:Scope[]}` | 管理员；G、Auth；明文仅此次返回 |
| DELETE `W/service-tokens/{token_id}` | — | `{ok:true}` | 管理员；G、Auth |
| GET `W/settings/dataagent-health` | — | `Health` | G、Auth；失败检查可能以 200 的 ok=false 返回 |
| GET `W/connections` | — | `Items<Connection>` | G、Auth；连接管理内部字段保留 |
| POST `W/connections` | `ConnectionCreate` | `Connection`，201 | 管理员；409 同名，422/502 连接失败；不返回密码 |
| POST `C/test` | — | `{ok:true}` | G、Auth；连接测试 HTTP 错误 |
| GET `C/tables` | `{table?:string;schema_name?:string}` | `Items<DataTable>` | G、Auth；只读目录，指定不存在的表为 404 |
| POST `C/table-material` | `{tables:string[];schema_name?:string}` | `Material`，201 | G、Auth；不存在的表404，数量不在1～20为422；只生成建模材料 |
| GET `W/materials` | `{include_archived?:boolean}`，默认 false | `Items<Material>` | G、Auth |
| POST `W/materials` | query `{name:string}`；body 原始文件字节 | `Material`，201 | G、Auth；413 大小超限，422 不支持的文本/编码 |
| GET `W/materials/{material_id}` | — | 文件字节，Content-Type 按材料 | G、Auth |
| POST `W/materials/{material_id}/archive` | — | `Material` | G、Auth |
| POST `W/materials/{material_id}/restore` | — | `Material` | G、Auth |
| DELETE `W/materials/{material_id}` | — | 204 | 管理员；409 `MATERIAL_IN_USE`，error.references 沿用 `string[]`，不混同核心引用提示 |
| GET `A` | — | `ConversationSnapshot` | G、Auth；未配置/上游失败沿用 HTTP 503/502 |
| POST `A/messages` | `{content:string;metadata?:Record<string,Json>}` | `RunRef`，202 | G、Auth；409 任务竞争；只接收 proposals 结果 |
| GET `A/events` | `{after_id?:number}`，默认 0 | `text/event-stream`，原 SDK 帧协议 | G、Auth；无任务 404；保持重连/恢复 |
| POST `A/cancel` | `{task_id:string}` | `RunRef` | G、Auth；409 任务已换 |
| POST `A/interactions` | `{task_id:string;kind:"permission"\|"question";request_id:string;payload?:Record<string,Json>}` | `Record<string,Json>`，上游 SDK 回执 | G、Auth；409 任务不属于会话 |
| GET `A/files/{rel_path}` | 路径按段 URL 编码 | 文件字节 | G、Auth；只允许 Topic 内文件，不作为本体格式导出 |

连接管理不是核心模型；保留 Connection.name、host 等不表示允许在 Dataset、DataMapping、指标或 MCP 中写 connection_alias。DatasetPicker 优先使用下面的 assets 快照；`tables` 仍供连接浏览/指定表结构和材料选择使用，不另开 picker API。

## 4. 修改的 REST 接口

### 4.1 工作空间与已发布读接口

| 方法 + 路径 | 查询 / 请求体 TS | 响应 TS | 错误 | mock |
|---|---|---|---|---|
| GET `W/overview` | — | `WorkspaceOverview` | G、Auth | M01 |
| GET `O/version` | `VersionQuery` | `VersionSummary` | G、Auth；未发布 NOT_FOUND | M02 |
| GET `O/types` | `VersionQuery & {q?:string;kind?:"object_type"\|"link_type"\|"metric"\|"dataset"}` | `TypeList` | G、Auth；旧 kind 422 | M03 |
| GET `O/types/{type_id}` | `VersionQuery`；优先传 UUID，保留已有技术名查找 | `TypeDetail` | G、Auth | M04 |
| GET `O/type-graph/neighborhood` | `VersionQuery & {focus_id?:UUID;depth?:number}`，depth=1，1～3 | `TypeGraph` | G、Auth | M05 |
| GET `W/published-snapshot` | — | `Draft` | G、Auth；无发布版为空草稿 | M06 |
| GET `W/ontology` | — | `Draft`；上行现有别名 | 同上 | M06 |
| GET `W/versions` | — | `Items<VersionSummary>` | G、Auth | M07 |
| GET `W/versions/{version_id}/presentation` | — | `{version:VersionSummary;model:Draft}` | G、Auth | M08 |
| GET `W/version-comparison` | `{right_id:UUID;left_id?:UUID}`；省略 left 为与空模型比较 | `Comparison` | G、Auth；相同版本 422 | M09 |
| GET `W/capabilities` | — | `{agent_configured:boolean;model:string;max_file_mb:number;connections_configured:boolean;skills:string[]}` | G、Auth | M10 |

变化：四类资源取代 value_type、document、semantic_model、dataset_field 等旧资源节点；规则保留所属对象/关系/属性上下文，不新开规则列表接口。关系图只画本体对象、关系与继承，不画指标/数据集/value_type/角色节点。历史 presentation 保留，替代前端过去用 `api.definition()` 调 export 读定义的做法；去掉 legacy_mapping_form。`capabilities.skills` 改为 `ontofoundry-modeling`。

`published-snapshot` 用于有编辑权限的核心定义读取；只读公开访问应走授权资源投影。presentation 中不可见的 datasets/mappings/事实集合输出空数组，指标只保留可安全公开的结构化定义，含物理表达式或无权读取的数据集定义不返回；这是一份授权读模型，不能据此全量保存。版本计数和对比影响同样裁剪。版本摘要三个 hash 名称保留；`version_sha256` 与 `version_content_sha256` 是发布 envelope hash，`normalized_snapshot_sha256` 是 core 草稿语义 hash，不混用。

### 4.2 草稿、会话与元素保存

```ts
type SessionCreate = { title?: string };
type SessionSave = {
  revision: number; draft: Draft; title?: string; material_ids?: string[];
};
type AffectedItem = {
  target_kind: TargetKind; target_id: UUID; expected_target_hash: SHA256;
};
type ElementSave = {
  target_kind: "object_type" | "link_type" | "metric" | "dataset" | "mapping";
  target_id: UUID; expected_current_version_id: UUID | null;
  session_id?: UUID | null; expected_session_revision?: number | null;
  draft: Draft; affected_items?: AffectedItem[];
};
type ElementSaveImpact = {
  current_version_id: UUID | null; session_revision: number | null;
  affected_items: (AffectedItem & { reason: string })[];
};
type ElementSaveResult = {
  version: VersionSummary; draft: Draft; session: ModelingSession | null;
};
```

| 方法 + 路径 | 查询 / 请求体 TS | 响应 TS | 错误 | mock |
|---|---|---|---|---|
| GET `W/sessions` | — | `Items<ModelingSessionSummary>` | G、Auth | M11 |
| POST `W/sessions` | `SessionCreate`；默认“新的建模会话” | `ModelingSession`，201 | G、Auth | M12 |
| GET `S` | — | `ModelingSession` | G、Auth | M13 |
| PUT `S` | `SessionSave` | `ModelingSession`，含本次 validation | G、Auth、V、Evidence；409 SESSION_REVISION_CHANGED | M14 |
| POST `S/validate` | —；可发 `{}` | `ValidationReport` | G、Auth；校验不通过为 200 publishable=false | M15 |
| POST `W/element-saves/preview` | `ElementSave`；只读候选预检 | `ElementSaveImpact` | G、Auth、E、V | M35 |
| POST `W/element-saves` | `ElementSave` | `ElementSaveResult` | G、Auth、E、V、Pub、Evidence、Data | M16 |

`save_session` 仍保存**整个会话草稿**，不发布；revision 是现有请求字段，不换名为 expected_session_revision。它拒绝旧 schema/旧字段和结构错误；编辑中可暂存可遍历但语义未完整的草稿，返回 validation，最终接受提案/发布必须通过最终图校验。空键、未采集列不等于结构错误。已知不存在的引用不得作为就绪绑定使用。

`save_element` 延续现有“保存立即生成活动版本”的行为，保留 current version CAS。有 session_id 必须同时给 expected_session_revision；没有时两项为空/省略。仅保存选择的聚合，返回的 session 保留其他未发布修改；不要把整个会话草稿误发布。作用域如下：

| 目标 | 可以一起保存 | 不可顺带覆盖 |
|---|---|---|
| object_type | 该对象本地定义、本地属性、对象及本地属性所属 Rule、它自己的 DataMapping | 任何关系定义、继承定义、Dataset、Metric、其他对象及文档事实 |
| link_type | 该关系及 owner_kind=link_type 的 Rule、关系自身 data_join | 两端对象/属性、Dataset、其他关系；不修改对象标识 |
| metric | 该条完整指标 | ratio 分量或其他指标，除非显式列在受影响组中 |
| dataset | 该条 Dataset | 未列明的映射、关系和指标；删列/改名/快照变化不得漏掉引用检查 |
| mapping | 该条 DataMapping | 对象定义、其他映射和 Dataset；绑定继承关系只写允许的 inherited_link_bindings |

`affected_items` 是计划 P2-03 的“显式带受影响项/校验 hash”的 envelope：按九类目标和 UUID 列出需要联动改写的已有元素，hash 对照服务器当前编辑基线。只允许从服务器解析的依赖图得到的必要改写，不允许借它扩大任意保存范围。技术名改写按旧图 UUID 引用重建；Dataset 删除/删列/改来源/快照展示直接依赖与 ratio 间接影响，最终图合法。新增多元素、删除目标本身或无法在单聚合合法表达的改动，使用完整会话保存、预览、发布或提案原子组，不添加批量删除路由。等价搬迁不强造指标算法修改；本体改动不触发指标修订。

前端跨聚合改名先调用 `POST W/element-saves/preview`：输入与保存完全相同的候选 `ElementSave`（无需先提交受影响项），服务端基于会话当前 revision 的草稿；没有会话则基于当前发布版，按 UUID 解析改写并计算必要的跨聚合确认清单。响应只返回 `AffectedItem` 的三项及中文 reason；前端展示确认后去掉 reason，把清单原样放入保存请求的 affected_items，不计算 hash。预检自身不写会话、不盖章证据、不发布；传入的 affected_items 不代表用户确认，也不会扩大预检范围。独立无关修改仍报 ELEMENT_SCOPE_INVALID，版本/revision 过时报对应 409；无法形成合法保存图报 ELEMENT_VALIDATION_FAILED。Dataset 变更同时列明指标直接及 ratio 间接影响，即使算法文本未变化。保存再次核对版本、revision 与所有 hash；预检不是写锁或授权令牌。预检和保存之间内容有变必须重新预检。

提案 after 中的 MappingSource.id 必填且保留本地来源名（例如 main），它不是由服务端分配的元素 UUID；inherited_link_bindings 仍按既有提案 wire 的条目数组提交，不把核心字典直接回传。PR #23 同步修正提案 JSON Schema，核心 Schema 不变。

保存成功时，将目标聚合和确认清单全部同步回会话；合并后的会话图仍须合法，保留其他未发布修改。会话暂存只阻断结构、证据与可适用的已登记来源列问题：JOIN_COLUMN_NOT_FOUND 仅表示已知来源列不存在；名称重复或悬空语义引用进入 validation，不伪报物理列错误。接受和发布继续阻断完整图错误。

`revise` 是后端内部 CAS/hash 边界，**不是 REST 路由**。保存、决定、冲突解决等写会话复用它或等价事务能力，不能回退旧版本，不接 legacy_mappings/legacy_joins/semantic_changes。proposals 运行中允许人工改草稿，受影响提案实时变 stale；发布仍按现有运行状态限制。

### 4.3 提案读取、决定与撤销

```ts
type ProposalStatus = "pending" | "accepted" | "rejected" | "stale" | "conflict" | "superseded";
type EvidenceView = EvidenceEntry & { material_name?: string; material_archived?: boolean };
type DuplicateCandidate = {
  id: UUID; type_id: UUID; display_text: string;
  expected_target_hash: SHA256;
};
type ProposalItem = {
  id: UUID; batch_id: UUID; ordinal: number; client_ref: string | null;
  operation: "create" | "update" | "delete"; target_kind: TargetKind; target_id: UUID;
  display_name: string; owner_label: string | null;
  before: CoreElement | null; after: CoreElement | null;
  field_changes: FieldChange[]; evidence: EvidenceView[]; reason: string;
  depends_on: UUID[]; dependency_group: UUID[];
  atomic_group_id: UUID | null;
  duplicate_candidates: DuplicateCandidate[];
  status: ProposalStatus;
  stored_status: "pending" | "accepted" | "rejected" | "superseded";
  status_reason: string; accepted_revision: number | null; decided_at: ISOTime | null;
};
type ProposalBatch = {
  id: UUID; status: "validating" | "available" | "failed"; created_at: ISOTime;
  source_session_revision: number; base_version_id: UUID | null;
  counts: Record<ProposalStatus, number>; error: { code: string; message: string } | null;
};
type ProposalBatchDetail = ProposalBatch & { items: ProposalItem[] };
type DecisionRequest = {
  idempotency_key: string; expected_session_revision: number;
  decisions: { proposal_id: UUID; decision: "accept" | "reject" | "restore" }[];
};
type DecisionResult = {
  session: ModelingSession;
  results: { proposal_id: UUID; status: ProposalStatus; reason?: string }[];
  validation: ValidationReport;
};
```

| 方法 + 路径 | 查询 / 请求体 TS | 响应 TS | 错误 | mock |
|---|---|---|---|---|
| GET `S/proposal-batches` | `{limit?:number;cursor?:string}`，默认20，1～100 | `Items<ProposalBatch> & {next_cursor:string\|null}` | G、Auth、Read | M17 |
| GET `S/proposal-batches/{batch_id}` | — | `ProposalBatchDetail` | G、Auth | M18 |
| POST `S/proposal-decisions` | `DecisionRequest` | `DecisionResult` | G、Auth、P、I、V、Evidence；SESSION_REVISION_CHANGED | M19 |
| GET `W/proposal-metrics` | — | `ProposalMetrics`，见下 | G、Auth | M20 |

```ts
type ProposalMetrics = {
  batches: { total: number; validating?: number; available?: number; failed?: number };
  batch_failure_rate: number; items: Record<ProposalStatus, number>;
  stale_rate: number; decisions: Record<"accept" | "reject" | "restore", number>;
};
```

- 列表是批次列表，详情在已有 batch 路由，**不新增**独立提案列表/GET item。九种 target_kind 与计划 §2.4 完全一致。before/after 为已解析、带 UUID 的核心元素；agent create 输入无自身 id、client_ref 必填的协议，不直接照搬为浏览器编辑 DTO。
- 撤销沿用 `decision:"reject"` 操作 accepted 项；restore 只将 rejected 恢复待审，不表示恢复已撤销的历史内容后自动接受。不另设 `/undo`。
- 服务端扩展同 atomic_group_id 的组，按组压缩 DAG，必要依赖仍须完整；前端先展示同组联动数量并选齐依赖，不能用原子组替代普通 depends_on。同一组显式收到相反决定为 PROPOSAL_CONFLICT。整组应用到副本后一次校验，不能逐条因中间图非法而拒绝名称交换。results 包含实际联动处理的所有项；幂等重放返回首次响应。idempotency_key 长8～64，decisions 1～500条；超过展开后的组预算也须整批拒绝，不能拆组提交。
- 拒绝/撤销不得拆开原子组；撤销已接受项还须撤销已接受的下游依赖，漏项为 DEPENDENCY_INCOMPLETE。接受后另有人编辑过目标时为 PROPOSAL_UNDO_CONFLICT，不能悄悄覆盖。动态 status/dependency_group 根据当前图计算，stored_status 与历史报告保留。
- duplicate_candidates 为文档事实同类型、同完整业务标识的提示；业务标识按属性 UUID 字节序，0/false 有值，缺任一项不猜。列表为空表示无候选，其他目标也固定空数组。提示不阻断两条 create 都接受，分页仍按事实 UUID。
- 候选追加到已有事实的 hash 来自当前会话已有事实核心内容，非 display_text 或业务键 hash。候选只包含当前会话可修订的已有事实；同批 pending create 的重复提示与重定向策略见 §10。
- proposal-metrics 删除 `legacy_active_runs`；不把此诊断接口做成全局数量来源。

提案上传合同名保留 `ontofoundry.proposals/v1`，仅接新内容：保留 run_token、workspace/session、base_version_id/hash、source_session_revision/draft_hash、before/after、expected_target_hash、depends_on、evidence、reason。自动引用 walker 覆盖九集合、表达式 UUID 引用、JOIN 列组和 inherited_link_bindings 的 UUID 字典键。agent 同批创建可用 `{client_ref:string}`；继承关系绑定键以 `{link_type_id:UUID|ClientRef,data_join}` 条目数组输入再转核心字典。sources.id、列、quote、values 和 SQL 字面量不是元素引用。可信导入构造入口属于 P4，本期不向浏览器开放。

### 4.4 发布预览、冲突、发布

| 方法 + 路径 | 请求体 TS | 响应 TS | 错误 | mock |
|---|---|---|---|---|
| POST `S/preview` | `{expected_session_revision:number}` | `PublishPreview` | G、Auth、Pub；SESSION_REVISION_CHANGED | M21 |
| POST `S/resolve-merge` | `{expected_session_revision:number;expected_current_version_id:UUID\|null;resolutions:Record<string,Resolution>}` | `ModelingSession` | G、Auth、Pub、V；SESSION_REVISION_CHANGED | M22 |
| POST `S/publish` | `{expected_session_revision:number;expected_current_version_id:UUID\|null;expected_merged_snapshot_sha256:SHA256;message?:string}` | `PublishResult` | G、Auth、Pub、V、Evidence | M23 |

三方合并涵盖九集合。预览移除 ossie、requires_change、legacy_mapping_form；空模型（例09）和仅数据集指标（例13）均可发布。预览时有冲突仍为 409 `MERGE_CONFLICTS`，从 error.conflicts 进入解决器，不在成功体另造 conflicts 列表。

resolutions 必须恰好覆盖本次冲突 key，choice 必须在 allowed 中；custom 要给字段对应类型的 value。解决后 revision 增一、base 移至所确认的 current version，再预览。发布严格核对 session revision、current version、merged hash，任何变化重新预览；拒绝仅 revision 的旧发布形态，不保留 legacy current/revision 解答别名。发布成功同步返回 session 新基线和草稿，不因待审提案而隐式接受它们。

### 4.5 数据目录、数据集登记与映射预览

```ts
type SchemaChange = {
  table: string; column: string | null; kind: "added" | "removed" | "changed";
  before: Json; after: Json;
};
type AssetTable = DataTable & {
  comment?: string | null; missing: boolean;
  datasets: DatasetRead[];
};
type Assets = {
  connection_id: UUID; version_id: UUID | null; items: AssetTable[];
  metadata_snapshot_id: string | null; observed_at: ISOTime | null;
  error: string | null; changes: SchemaChange[];
  status: "ready" | "stale" | "unobserved";
};
type TypedKeyPart =
  | { type: "string"; value: string }
  | { type: "integer"; value: string }
  | { type: "decimal"; value: string }
  | { type: "float"; value: number }
  | { type: "boolean"; value: boolean }
  | { type: "date"; value: ISODate }
  | { type: "datetime"; value: ISOTime };
type TypedKey = TypedKeyPart[];
type SnapshotDates = { dataset_id: UUID; date: ISODate | null }[];
type MappingPreviewRequest = {
  mapping: DataMapping; session_id?: UUID;
  q?: string; key?: TypedKey; offset?: number; limit?: number;
  snapshot_date?: ISODate;
};
type MappingPreview = {
  items: { __key: TypedKey; __type_id: UUID; __ref: string;
    values: Record<string, Scalar>; display_text: string }[];
  has_more: boolean; source: "database"; snapshot_dates: SnapshotDates;
};
```

| 方法 + 路径 | 查询 / 请求体 TS | 响应 TS | 错误 | mock |
|---|---|---|---|---|
| GET `C/schemas` | — | `Items<string>` | G、Auth、Data | M24 |
| GET `C/assets` | `VersionQuery & {schema_name?:string}`，默认空字符串 | `Assets` | G、Auth、Data | M25 |
| POST `C/assets/refresh` | query 同上；无 body | `Assets` | G、Auth、Data；采集失败可为200 stale，保留上次快照 | M26 |
| POST `W/mapping-preview` | `MappingPreviewRequest` | `MappingPreview` | G、Auth、V、Data、Read | M27 |

schemas/assets 纳入统一映射授权；assets 原来的旧 mappings/key_column/state 投影删除，改为关联的扁平 DatasetRead，不恢复旧三状态 MappingStatus。GET assets 读已采集快照；refresh 显式只读采集结构，失败 error 非空，不能把上次列清单清空伪称当前无列。metadata_snapshot_id/observed_at 只由服务端附带。

DatasetPicker：读取连接 → schemas → assets（无快照时显式 refresh）→ 选择表/视图 → 构造 Dataset（复制列 name/type/comment 为 name/physical_type/comment）→ 用 dataset element-saves 或会话草稿保存。物理位置只存 dialect/schema_name/table_name；不回传 connection_id、primary_key、nullable 或 metadata_snapshot_id。服务器根据已有采集记录匹配位置并补只读采集信息；不要求新登记 API。Dataset.columns 可空，不能手工制造采集时间。P2 不显示“被 N 个对象/K 个关系/M 个指标引用”的后续计数。

映射只选已登记 Dataset；自身字段、成员来源、继承关系本地绑定均用 core DataMapping。mapping-preview 的 mapping 是本次表单的临时绑定；Dataset、对象、属性和祖先定义取 session_id 对应草稿或当前发布快照，不能客户端塞表位置、任意 SQL 或未登记 Dataset。允许预览尚未保存的同对象绑定，不写草稿；key 按有序类型元组精确定位，q 模糊过滤，offset 默认0、0～10000，limit 默认20、1～100。独立绑定按 id=main 选主来源，shared_parent 按祖先解析，不能拿 sources[0] 猜。

### 4.6 实例浏览

```ts
type DocumentFactRead = MaterialObject & {
  ref: string; source: "document"; display_text: string;
};
type DatabaseInstanceRead = {
  id: string; ref: string; type_id: UUID; key: TypedKey;
  source: "database"; display_text: string;
  values: Record<string, Scalar>; evidence: [];
};
type InstanceRead = DocumentFactRead | DatabaseInstanceRead;
type InstanceEnvelope = VersionEnvelope & {
  queried_at: ISOTime; data_mode: "live" | "snapshot";
  quality_issues: ValidationIssue[];
};
type InstanceList = InstanceEnvelope & {
  items: InstanceRead[]; source: "document" | "database";
  next_cursor: string | null; truncated: boolean; snapshot_dates: SnapshotDates;
};
type InstanceDetail = InstanceEnvelope & { item: InstanceRead; snapshot_dates: SnapshotDates };
type InstanceLinkRead = {
  id: string; type_id: UUID; source_id: string; target_id: string;
  evidence: EvidenceEntry[];
};
type InstanceNeighborhood = {
  center_id: string; objects: InstanceRead[]; links: InstanceLinkRead[];
  warnings: string[]; truncated: boolean; source: "document" | "database";
  depth: number; snapshot_dates: SnapshotDates;
};
type NeighborhoodRequest = {
  type_id: UUID; key: TypedKey; session_id?: UUID; depth?: number;
  snapshot_date?: ISODate;
};
```

| 方法 + 路径 | 查询 / 请求体 TS | 响应 TS | 错误 | mock |
|---|---|---|---|---|
| GET `O/objects` | `VersionQuery & {type_id?:UUID;source?:"document"\|"database";q?:string;cursor?:string;limit?:number;snapshot_date?:ISODate}` | `InstanceList` | G、Auth、Read、Data | M28 |
| GET `O/objects/{ref}` | `VersionQuery & {snapshot_date?:ISODate}` | `InstanceDetail` | G、Auth、Read、Data | M29 |
| GET `O/objects/{ref}/neighborhood` | `VersionQuery & {depth?:number;snapshot_date?:ISODate}` | `InstanceEnvelope & InstanceNeighborhood` | G、Auth、Read、Data | M30 |
| POST `W/instance-neighborhood` | `NeighborhoodRequest` | `InstanceNeighborhood` | G、Auth、V、Read、Data | M31 |

默认 source=document、q=""、limit=20（1～100）、depth=1（1～3）。数据库搜索必须指定 type_id；虚拟父返回实际具体 type_id。文档仍按事实 UUID 检索/去重，display_text 按标题 → 完整标识 → 可见材料引文前80字 → UUID；0/false 有值，manual.note 不代引文。文档搜索包含 display_text 和属性值，材料事实删独立 name；`values.name` 这种属性技术名合法。REST 文档 ref 保持 `doc.<事实UUID>`，MCP 使用裸事实 UUID。

数据库 ref 的建议字节协议（§10 待双方确认后锁定）：`db.` + **UTF-8 JSON 的 base64url，无末尾 =**。JSON payload 为 `[具体type_id, TypedKey]`，key 次序是有效主来源 key_columns 次序。例04的 `["O100",1]` 为 `[{type:"string",value:"O100"},{type:"integer",value:"1"}]`；整数/decimal 用规范十进制字符串保精度、float 必须有限、null 键不可定位。`"1"` 与整数1、两个子类型相同局部键都不同。拒绝旧 `[type_id,String(key)]`，不接受分隔符拼接，也不把 ref 当业务标识。服务端生成，前端仅转传和 URL 编码；数据库 id 与 ref 统一使用这个 ref，邻接端点指相同 id。文档邻接端点仍是事实 UUID。

snapshot_date 仅是本次浏览参数，不入模型、不入身份 ref；省略时每个 Dataset 独立取全表最大日期，先选日再加成员/属性过滤。明确传某日时每个快照 Dataset 精确查当日，不自动退回，不强制主附使用同一个“最新日”。非快照来源不加这个日期谓词。响应 snapshot_dates 记录每个实际来源日期，文档为空数组。文档请求带 snapshot_date 应 422 拒绝。日期、版本、筛选、来源、权限均绑定游标；详情/邻接沿用列表日期参数，不能点开后悄悄回到最新日。无当日数据为空列表/NOT_FOUND，不补 0 或延续旧行。

普通附表 LEFT JOIN 保留主实例；membership_source 用 EXISTS 限成员；多层 shared_parent 逐级应用父范围、分支 OR、本层扩展交集；虚拟父只对 `(具体type_id,typed key)` 去重。关系浏览只列匹配项，direct 与 mapping_table 保留方向、自环、平行关系，跨连接/缺键/缺列不给伪 JOIN。图返回 warnings/truncated 保留既有预算（最多100对象/300边、50查询、15秒）；模型声明唯一性不触发扫描，精确定位多行报 INSTANCE_NOT_UNIQUE。

## 5. 新增 REST 接口

### 5.1 将重复事实新建提案修订为更新

`POST S/proposal-items/{id}/revision`，完整路径：

`/api/v1/workspaces/{workspace_id}/sessions/{session_id}/proposal-items/{id}/revision`

```ts
type FactProposalRevision = {
  expected_session_revision: number;
  target_id: UUID; expected_target_hash: SHA256;
  after: MaterialObject;
  reason?: string;
};
 // Response: ProposalBatchDetail
```

无查询参数。响应为新修订批次 `ProposalBatchDetail`（mock M32）。错误 G、Auth、P、V、Evidence、409 SESSION_REVISION_CHANGED；目标 hash 不匹配用 PROPOSAL_STALE。只允许当前有效 pending、material_object/create 项；accepted 项不原地改，先走正常撤销或另提更新。

人明确选择当前会话中已有事实，`after.id=target_id` 且 type_id 与原提案相同；after 是人工确认的最终属性和证据集合，须保留已有证据并追加选定新证据，证据 UUID 不重铸、不因 quote 相同合并。服务端读取真实 before、验证 expected_target_hash，构建 operation=update 的新 pending 项，旧项 superseded；重建受影响依赖、原子组和待审数量，不直接改事实、不增加草稿 revision。前端成功后重读 session 与批次。若需要把依赖旧 create 的 material_link 端点转到已有事实 UUID，必须在同次修订批次显式重写并校验；不能丢邻接或静默迁移已接受事实。原子组不能只修订一半。

请求/返回的名称、修订原子组的范围和“pending 目标”的处理为 §10 的协调项；它们不改变计划已确认的“人工修订、追加证据、不自动合并”语义。

### 5.2 未保存指标表单数值预览

`POST /api/v1/modeling/workspaces/{workspace_id}/metrics/preview`

```ts
type MetricPreviewRequest = {
  session_id?: UUID; expected_session_revision?: number;
  expected_current_version_id?: UUID | null;
  metric: Metric; components?: SimpleMetric[];
  time_range?: { start: ISOTime | ISODate; end: ISOTime | ISODate };
  trend_grain?: "month";
};
type MetricPreview = {
  definition_hash: SHA256;
  context_version: UUID | null; session_revision: number | null;
  status: "ok" | "unable"; reason_code?: string; reason?: string;
  value: Scalar; value_kind: ValueKind | null;
  total_query: SQLReference | null; trend_query?: SQLReference | null;
  trend?: { period: ISODate; value: Scalar }[];
  snapshot_dates: { dataset_id: UUID; period: ISODate | null; date: ISODate | null }[];
  warnings: string[];
};
```

无查询参数。200 `MetricPreview`（mock M33）；G、Auth、V，409 SESSION_REVISION_CHANGED/VERSION_CHANGED 属于请求上下文错误。提供 session_id 时必须有 expected_session_revision；没有 session_id 时应显式发送 expected_current_version_id（可为 null），从当前发布快照读取 Dataset。两个 guard 都发送时两个都检查。time_range 为半开 `[start,end)`，start<end；ratio 的 components 必须完整覆盖两个引用，可同 UUID 覆盖本次 simple 分量，不能借 components 提交无关指标。表达式、列、条件和时间引用都限同一登记 Dataset。请求不接 Dataset 定义、SQL、连接或本体统计对象。

在内存候选图校验完整 metric 和分量，包含尚未保存的表单；合法但无法执行时 200 `status:"unable"`，value=null，不写会话/版本/提案。约定 reason_code：

| reason_code | 含义 |
|---|---|
| `expression_not_supported` | 语义引用可接受，但平台预览 AST/函数白名单不支持 |
| `engine_not_supported` | 当前引擎不支持该执行方式，例如 median |
| `binding_not_ready` | 来源/列清单/结果类型未就绪 |
| `source_ambiguous` | 服务端连接配置不能唯一定位 |
| `forbidden` | 缺映射或实例/数据读取权限，SQL/params 也不返回 |
| `query_timeout` / `query_failed` | 只读执行超时/失败，保留可安全展示的诊断 |

这些是预览**结果原因**，不是 ServiceError code；HTTP 身份认证失败仍为 401/403。能访问空间但不足以执行预览时用 forbidden，不泄露表/SQL/数值。非法模型输入使用 V/422，不包装成 unable。缺时间字段时可返回总值并 warnings 解释无趋势，trend_query=null/trend 省略，不编造按月点。

definition_hash 是候选定义、ratio 分量、范围/粒度和服务器上下文的预览指纹；前端用请求序号与当前表单状态对应，回包 hash 随同结果保存，表单/范围/分量变化后作废。不要求前端用 JSON.stringify 计算相同 hash，也不能只比较返回 hash 而忽略请求竞态。

value 可为 null（SUM空集、零分母），COUNT空集为0。total_query 是实际执行的一条聚合 SQL/params，月趋势另跑 trend_query；禁止实例分页后由前端汇总。总计按全范围重算，不把月均值、月去重、月比率相加。ratio 两分量各自过滤和归时间，不能共享分子 WHERE。快照每个 Dataset/周期独立选末日，选日不受固定条件缩小；snapshot_dates.period=null 表示总值，月趋势为月首。例13总提交数10，核心仓库8，占比0.8，跨日去重仓库2。

## 6. 服务接入：MCP 四工具

保留 `POST O/mcp`（JSON-RPC 2.0），不新建 REST `/tools`。服务接入页由已有工作空间目录、service-tokens 和此端点拼接说明。保留 initialize、notifications/initialized、tools/list、tools/call、server/discover、ping 与现有协议/请求头协商；GET 同一路径仍405，不声称支持 SSE。浏览器通常只显示配置说明，不执行 MCP 数据库查询。

HTTP 请求头沿用服务 Bearer token；建模 run token 使用现有认证路径。输入 extra forbid，四工具**全部不接受 version_id/workspace_id/connection_alias/source=database**；workspace 从 URL，版本由 Principal 解析。以下类型是工具 arguments，不是 REST JSON 请求 envelope：

```ts
type ToolName = "search_ontology" | "get_ontology" | "search_objects" | "get_object";
type MCPMeta = { _meta?: Record<string, Json> };
type ToolArguments =
  | { name: "search_ontology"; arguments: SearchOntologyArgs }
  | { name: "get_ontology"; arguments: GetOntologyArgs }
  | { name: "search_objects"; arguments: SearchObjectsArgs }
  | { name: "get_object"; arguments: GetObjectArgs };
type MCPRequest = { jsonrpc: "2.0"; id: string | number } & (
  | { method: "initialize"; params: MCPMeta & {
      protocolVersion: string; capabilities: Record<string, Json>;
      clientInfo: { name: string; version: string };
    } }
  | { method: "tools/list" | "ping" | "server/discover"; params?: MCPMeta }
  | { method: "tools/call"; params: MCPMeta & ToolArguments }
);
type MCPNotification = { jsonrpc: "2.0"; method: "notifications/initialized"; params?: MCPMeta };
type ToolDescription = {
  name: ToolName; description: string; inputSchema: Record<string, Json>;
  annotations: { readOnlyHint: true; destructiveHint: false };
};
type MCPResponse<T> = { jsonrpc: "2.0"; id: string | number | null } & (
  | { result: T }
  | { error: { code: number; message: string; data?: Json } }
);
type OntologyKind = "object_type" | "property" | "link_type" | "rule" | "metric";
type Paging = { cursor?: string; limit?: number };
type SearchOntologyArgs = Paging & { query: string; kinds?: OntologyKind[] };
type GetOntologyArgs = Paging & {
  ids?: UUID[]; kinds?: OntologyKind[];
  include?: ("semantic" | "physical" | "rules" | "adjacency")[];
};
type SearchObjectsArgs = Paging & { type_id?: UUID; q?: string };
type GetObjectArgs = Paging & {
  id: UUID; include?: ("properties" | "evidence" | "adjacency")[];
};
type MCPEnvelope = { workspace_id: UUID; version_id: UUID | null; field_segments?: FieldSegment[] };
type OntologyHit = {
  id: UUID; kind: OntologyKind; name: string; technical_name: string;
  summary: string; matched_synonyms: string[];
  owner_kind?: "object_type" | "property" | "link_type"; owner_id?: UUID;
  dataset?: Pick<Dataset, "id" | "name">;
};
type MCPList<T> = MCPEnvelope & Page<T>;
type MCPObjectHit = Pick<DocumentFactRead, "id" | "type_id" | "display_text"> & {
  values: Record<string, Scalar>;
};
type MCPAdjacency = {
  link_type_id: UUID; direction: "forward" | "reverse";
  source_id: UUID; target_id: UUID;
};
type MCPObject = MCPObjectHit & {
  properties?: Page<{ property_id: UUID; value: Scalar }>;
  evidence?: Page<EvidenceView>;
  adjacency?: Page<MCPAdjacency>;
};
// Read-only execution projection derived from the existing core definitions.
type MembershipRead = {
  type_id: UUID; mapping_id: UUID; binding_mode: DataMapping["binding_mode"];
  membership_source_id: string | null; derived_by: NonNullable<ObjectType["derived_by"]>;
};
type EffectiveLinkRead = {
  link_type_id: UUID; source_type_id: UUID; target_type_id: UUID;
  data_join: DataJoin | null;
};
type EffectiveBindingRead = {
  type_id: UUID; sources: MappingSource[];
  fields: Record<string, ColumnBinding | ExpressionBinding>;
  memberships: MembershipRead[]; links: EffectiveLinkRead[];
};
type MCPElement = {
  id: UUID; kind: OntologyKind; name: string; technical_name: string;
  description?: string; synonyms?: string[];
  definition?: CoreElement; binding_status?: BindingStatus;
  inherited_from?: UUID | null;
  properties?: Page<PropertyRead>; rules?: Page<Effective<Rule>>;
  links?: Page<LinkRead>;
  child_types?: Page<Pick<ObjectType, "id" | "name" | "technical_name">>;
  datasets?: Page<DatasetRead>; sources?: Page<MappingSource>;
  effective_bindings?: Page<EffectiveBindingRead>;
  components?: { numerator: SimpleMetric; denominator: SimpleMetric };
  dataset_id?: UUID; value_kind?: ValueKind | null;
  instance_source_type_ids?: UUID[]; sql_reference?: SQLReference;
};
type FieldSegment = {
  element_id: UUID; field: string; start: number; end: number; total: number;
  text: string; next_cursor: string | null;
};
// Character ranges are Unicode code points, half-open; field is a JSON Pointer.
type MCPGetOntology = MCPEnvelope & {
  total: number; elements: MCPElement[]; missing: UUID[]; next_cursor: string | null;
  field_segments?: FieldSegment[];
};
type MCPCallResult<T> = {
  content: { type: "text"; text: string }[];
  structuredContent: T; isError?: boolean;
};
```

| 工具 | arguments | structuredContent | 约束 |
|---|---|---|---|
| search_ontology | `SearchOntologyArgs` | `MCPList<OntologyHit>` | query 必填；只搜五种语义元素，指标无对象 owner |
| get_ontology | `GetOntologyArgs` | `MCPGetOntology` | 不传 ids 为授权轻量目录及 total；传 ids 为定义与所选投影；ids=[] 为 invalid_arguments；最多100个 |
| search_objects | `SearchObjectsArgs` | `MCPList<MCPObjectHit>` | 仅已接受文档事实，按 UUID 计数/分页，父类型展开仍保留实际 type_id |
| get_object | `GetObjectArgs` | `MCPEnvelope & {item:MCPObject}` | id 为事实 UUID；include 默认 properties；直接邻接分关系/方向分页，不递归邻居全文 |

limit 默认20、1～100；get_ontology include 默认 semantic。Dataset/Mapping 仅作为 physical 投影，不是独立 kinds/tool。get_ontology 的 definition 是核心定义，外侧 properties/rules/links 是有效继承项；无物理权限不得借 definition 泄露 data_join、expression、Dataset 或证据。只输出可见字段，不能依赖 frontend 再裁剪。

physical 的 `effective_bindings` 是现有定义推导的只读 DTO，不属于核心模型：对象按实际具体 type_id 返回完整有效 sources/fields、从根到当前的成员声明及有效关系绑定。`memberships` 明确保留每层 membership_source_id 与 derived_by；继承属性不丢归属，具体子对象的 inherited_link_bindings 覆盖此视角的关系 data_join，原 LinkType 定义仍可为 null。虚拟父返回所有可查询具体绑定，并以 instance_source_type_ids 指明展开。关系元素返回两端有效绑定；`datasets` 覆盖有效来源与关系映射表，指标（包括 ratio）也返回完整 DatasetRead 和列清单，ratio 的 components 保留各分量固定条件和时间字段。每个 DatasetRead 保留自身 snapshot_date_column，不能用主来源的快照声明覆盖附来源。sources 是兼容的平铺有效来源；需要恢复成员语义必须读 effective_bindings。分页续取 datasets/effective_bindings 与其他嵌套列表使用同工具签名游标。后端通过 EffectiveBindingRead/MembershipRead/EffectiveLinkRead 校验输出。

`POST O/mcp` 无查询参数，请求 `MCPRequest | MCPNotification`。普通响应为 `MCPResponse<T>`，tools/list 的 T 为 `{tools:ToolDescription[]}`，tools/call 的 T 为上面的 `MCPCallResult<工具结果>`；ping 返回空对象，initialize 返回 `{protocolVersion:string;capabilities:Record<string,Json>;serverInfo:{name:string;version:string};instructions:string}`，server/discover 返回 `{supportedVersions:string[];capabilities:Record<string,Json>;instructions:string}`。notification 为202空响应。G/Auth 适用于传输认证；协议失败沿用 JSON-RPC 数字错误，不强行改成 ServiceError。

沿用基线 MCP 2026-07-28 与现有旧协议协商：Accept 包含 application/json 与 text/event-stream；当前协议要求 Mcp-Protocol-Version、Mcp-Method（等于 method）、tools/call 的 Mcp-Name（等于工具名），以及 params._meta 中的 io.modelcontextprotocol/protocolVersion、clientCapabilities。不能把“旧协议协商”删掉当成 core-1 模型清理。请求超过256KiB为413；解析/参数/方法错误沿用 -32700/-32600/-32602/-32601，头不匹配 -32020、不支持的协议 -32022。

工具错误 code 为小写 `invalid_arguments`、`cursor_invalid`、`version_unavailable`（以及权限错误），通过原 JSON-RPC/工具错误机制返回，不与 REST 大写 code 混用。text 内容 JSON 与 structuredContent 一致。建模用 pinned_version_id（空基线返回空 core 目录）；问数每次用 current_version_id，未发布为空目录；固定版被清理报 version_unavailable。返回版本仅供追溯，不接受调用方指定。

cursor 签名绑定 workspace、解析版本、工具、filters、projection、权限指纹和 section/偏移；问数发布或授权变化后 cursor_invalid，重新开始；固定建模版本不随发布改变。嵌套列表也用 total/items/next_cursor，同工具带 section 游标续取；总预算256KiB，按元素分页，超大表达式/描述明确字段分段，不硬截断字符串。超大字段从当前定义体省略，用 field_segments 明确其 JSON Pointer、Unicode 字符半开范围、总长度和 next_cursor；继续用同一工具续取。该命名为 §10 待确认项，未拼齐不能当成可编辑的完整定义。

无 can_read_mappings：不返回数据集名称/说明/数量、表列、物理类型、JOIN、元数据采集标识/时间、SQL/params、含来源的 expression；semantic 摘要可保留 forbidden。无 can_read_instances：不返回事实、证据、quote；包括 REST MetricRead 以及 MCP ratio.components 的所有嵌套分量。目录、总数、嵌套和缓存用同一授权投影，所有层级无 connection_alias。DataAgent 通过 mysql.query/doris.query 自己查询数据库，MCP 不提供 query_metric 或数据库实例工具。

## 7. 删除或 P2 下线的路由

删除后的路径没有业务请求/响应契约；前端不得发送。未注册默认404（GET MCP 为明确405），不新增专用“已下线”接口/错误码，不留点击后500的按钮。

| 方法 + 路径/工具 | 原因 | 前端替代 |
|---|---|---|
| POST `W/publish` | 绕开会话，计划 P2-06 明确删除 | 创建/保存会话 → preview → publish；内部 publish_draft 不是公共 API |
| GET `W/published-legacy-form` | 旧映射回写退出 | 从 core Draft.datasets/mappings/link_types 及授权读投影取数据 |
| GET `W/semantic-models` | 删除语义树与旧 metric 查询投影 | published-snapshot/session 读取 core；已发布四类资源读 O/types |
| POST `W/semantic-change-preview` | 旧 SemanticChange/树 diff | 本地核心编辑与 validation，正式发布 preview 看依赖影响 |
| POST `W/semantic-saves` | 独立语义树写通道删除 | Dataset/Metric/Mapping 走 element-saves 或会话保存 |
| POST `W/metrics/{metric_id}/sql-preview` | 只编译已存 metric，不能执行未保存表单 | §5.2 完整 metric 预览 |
| POST `S/candidates` | 完整 model-result/candidates 流程删除 | proposal-batches/detail/decisions；会话删除 candidates 字段 |
| POST `W/imports/ossie` | P2 尚无新适配器/提案导入 | 隐藏导入按钮；P4 才恢复基于报告和 pending 提案的入口；不沿用 merge/replace |
| GET `O/versions/{version_id}/export` | ossie_json 删除，P5 导出未交付 | 隐藏下载按钮；只读定义改用 W/versions/{version_id}/presentation；P5 恢复格式化导出 |
| MCP `get_ontology_version/search_ontology_types/get_ontology_type/get_ontology_graph/export_ontology/expand_object_graph/list_metrics/query_metric/get_ontology_manifest/list_ontology_elements/get_ontology_elements`；保留工具的旧 ref/source/version 参数 | MCP 收敛语义/文档事实 | search_ontology/get_ontology/search_objects/get_object；数据库统计由 DataAgent 查询工具完成 |

基线不存在的 `/imports/native`、`/exports/*`、`/datasets`、`/mappings` CRUD、`/revisions` 等不要先造占位路由。会话对话附件下载和材料下载仍保留，不等同本体导入/导出。版本历史、presentation、comparison、正常发布与冲突解决不下线。

## 8. 前端 mock：每个新增/修改接口的最小响应

下面是 TypeScript mock 工厂约定，不是服务器接受的输入格式。所有变量先初始化再使用；展开后就是响应对象，没有省略号占位字段。业务定义直接取 `docs/design/core-1-examples/` 的 draft，共用 P1 夹具，不复制成另一套核心 JSON。每个 M 编号与上表一一对应。hash 是不参与密码学校验的固定64位测试占位，游标只允许 mock 自己签发；接真后端必须原样使用服务端值。元数据时间、版本/会话/批次 UUID 是测试 envelope，不代表设计样例已存在真实数据库。

```ts
// Fixture initialization in the mock handler; adapt only the import path.
import example13 from "../../docs/design/core-1-examples/13-dataset-metrics.json";
import example07 from "../../docs/design/core-1-examples/07-instances-and-evidence.json";
import example04 from "../../docs/design/core-1-examples/04-composite-key.json";
// P1 validates these JSON fixtures; unknown bridges JSON import literal widening.
const d13 = example13.draft as unknown as Draft;
const d07 = example07.draft as unknown as Draft;
const d04 = example04.draft as unknown as Draft;
const wid = d13.workspace_id;
const vid = "10000000-0000-4000-8000-000000000001";
const sid = "10000000-0000-4000-8000-000000000002";
const bid = "10000000-0000-4000-8000-000000000003";
const pid = "10000000-0000-4000-8000-000000000004";
const cid = "10000000-0000-4000-8000-000000000005";
const h = "1".repeat(64);
const now = "2026-10-16T00:00:00Z";
const env: VersionEnvelope = {
  workspace_id: wid, version_id: vid, version_sha256: h,
  version_content_sha256: h, normalized_snapshot_sha256: h,
};
const valid: ValidationReport = {
  standard: "core-1", schema_status: "passed", semantic_status: "passed",
  errors: [], warnings: [], publishable: true,
};
const graph: TypeGraph = { ...env, nodes: [], edges: [] };
const version: VersionSummary = {
  ...env, version: 1, status: "published", message: "登记代码行日统计指标",
  published_at: now, validation: valid,
  counts: { object_types: 0, link_types: 0, attributes: 0, rules: 0,
    metrics: 6, datasets: 1, mappings: 0, material_objects: 0, material_links: 0 },
};
const session: ModelingSession = {
  id: sid, workspace_id: wid, title: "代码行统计建模", base_version_id: vid,
  revision: 2, draft: d13, draft_sha256: h, base_version_sha256: h,
  pending_proposal_count: 0, latest_batch_id: null, base_diff: [], graph,
  material_ids: [], task_status: "idle", task_detail: "",
  dataagent_topic_id: null, dataagent_task_id: null, updated_at: now,
  validation: valid,
};
const ds: DatasetRead = {
  ...d13.datasets[0], binding_status: "bound", database: "dev_demo", schema: "dev_demo",
  metadata_snapshot_id: "10000000-0000-4000-8000-000000000006", observed_at: now,
};
const commit = d13.metrics.find(m => m.technical_name === "commit_count")! as SimpleMetric;
const metric: MetricRead = { ...commit, value_kind: "integer", binding_status: "bound" };
const resource: ResourceRead = { kind: "metric", definition: metric };
const counts: Record<ProposalStatus, number> = {
  pending: 0, accepted: 0, rejected: 0, stale: 0, conflict: 0, superseded: 0,
};
const batch: ProposalBatch = {
  id: bid, status: "available", created_at: now, source_session_revision: 2,
  base_version_id: null, counts: { ...counts, pending: 1 }, error: null,
};
const proposal: ProposalItem = {
  id: pid, batch_id: bid, ordinal: 0, client_ref: "commit_total",
  operation: "create", target_kind: "metric", target_id: commit.id,
  display_name: "提交数", owner_label: null, before: null, after: commit,
  field_changes: [], evidence: [], reason: "登记总提交数", depends_on: [],
  dependency_group: [pid], atomic_group_id: null, duplicate_candidates: [],
  status: "pending", stored_status: "pending", status_reason: "",
  accepted_revision: null, decided_at: null,
};
const noCommit: Draft = {
  ...d13, metrics: d13.metrics.filter(m =>
    m.id !== commit.id && !(m.kind === "ratio" && m.denominator_id === commit.id)),
};
// A pending create is not already in the session draft.
const pendingSession: ModelingSession = {
  ...session, base_version_id: null, draft: noCommit, latest_batch_id: bid, pending_proposal_count: 1,
};
const assets: Assets = {
  connection_id: cid, version_id: vid,
  metadata_snapshot_id: ds.metadata_snapshot_id!, observed_at: now,
  error: null, changes: [], status: "ready",
  items: [{ name: ds.table_name, schema: "dev_demo", comment: ds.description,
    columns: (ds.columns ?? []).map(c => ({ name: c.name,
      type: c.physical_type ?? "unknown", primary_key: false, comment: c.comment })),
    missing: false, datasets: [ds] }],
};
const fact: DocumentFactRead = {
  ...d07.material_objects[0], ref: "doc." + d07.material_objects[0].id,
  source: "document", display_text: "C001",
};
const ie: InstanceEnvelope = { ...env, queried_at: now,
  data_mode: "snapshot", quality_issues: [] };
const docNeighborhood: InstanceNeighborhood = {
  center_id: fact.id, objects: [fact], links: [], warnings: [],
  truncated: false, source: "document", depth: 1, snapshot_dates: [],
};
const preview: PublishPreview = {
  session_revision: 2, base_version_id: vid, base_version_number: 1,
  current_version_id: vid, current_version_number: 1, next_version_number: 2,
  current_version_sha256: h, merged_snapshot_sha256: h,
  merged_model: d13, validation: valid, changes: [], labels: {}, impacts: [], auto_merged: [],
};
```

例07客户未指定 title_property_id，故 mock display_text 为完整标识 `C001`，不能擅自改为其 name 属性。文档材料只作读投影测试，不能声称夹具中的材料已上传可用于写入验证。实例相关 M28～M30 使用例07仅保留客户事实、移除退货事实和 material_links 的独立最小快照，其 env 的测试版本号与例13采用相同占位；实际 mock handler 应按场景隔离 store，不能把两个不相同的 draft 合成同一个真实不可变版本。

```ts
const responses = {
  // M01 GET W/overview — example13 has no ontology objects.
  M01: { version, graph, details: {
    object_count: 0, link_count: 0, evidence_material_count: 0, mapping_count: 0,
    objects: [], links: [], mappings: [],
  } } satisfies WorkspaceOverview,
  // M02 GET O/version
  M02: version,
  // M03 GET O/types?kind=metric&q=提交数
  M03: { ...env, items: [resource], next_cursor: null, ambiguous: false } satisfies TypeList,
  // M04 GET O/types/{commit.id}
  M04: { ...env, item: resource, ambiguous: false } satisfies TypeDetail,
  // M05 GET O/type-graph/neighborhood — metrics do not become graph nodes.
  M05: graph,
  // M06 GET W/published-snapshot or W/ontology
  M06: d13,
  // M07 GET W/versions
  M07: { items: [version] },
  // M08 GET W/versions/{vid}/presentation
  M08: { version, model: d13 },
  // M09 GET W/version-comparison — identical content in two distinct releases.
  M09: { left: version, right: { ...version, version: 2,
    version_id: "10000000-0000-4000-8000-000000000011" },
    changes: [], impacts: [] } satisfies Comparison,
  // M10 GET W/capabilities
  M10: { agent_configured: true, model: "DataAgent", max_file_mb: 20,
    connections_configured: true, skills: ["ontofoundry-modeling"] },
  // M11 GET W/sessions
  M11: { items: [{ id: sid, title: session.title, task_status: "idle", updated_at: now,
    base_version_id: vid, has_unpublished_changes: false }] },
  // M12 POST W/sessions — starts at revision 0, subsequent mocks are later reads.
  M12: { ...session, revision: 0 },
  // M13 GET S — separate pending proposal scenario.
  M13: pendingSession,
  // M14 PUT S {revision:2,draft:d13} — no publication.
  M14: { ...session, revision: 3 },
  // M15 POST S/validate
  M15: valid,
  // M16 POST W/element-saves — standalone Dataset save.
  M16: { version, draft: d13, session: null } satisfies ElementSaveResult,
  // M17 GET S/proposal-batches
  M17: { items: [batch], next_cursor: null },
  // M18 GET S/proposal-batches/{bid}
  M18: { ...batch, items: [proposal] } satisfies ProposalBatchDetail,
  // M19 POST S/proposal-decisions accept — adds only the selected simple metric.
  M19: { session: { ...pendingSession, revision: 3, pending_proposal_count: 0,
      draft: { ...noCommit, metrics: [...noCommit.metrics, commit] } },
    results: [{ proposal_id: pid, status: "accepted" }], validation: valid } satisfies DecisionResult,
  // M20 GET W/proposal-metrics
  M20: { batches: { total: 1, available: 1 }, batch_failure_rate: 0,
    items: { ...counts, pending: 1 }, stale_rate: 0,
    decisions: { accept: 0, reject: 0, restore: 0 } } satisfies ProposalMetrics,
  // M21 POST S/preview
  M21: preview,
  // M22 POST S/resolve-merge — name conflict resolved to the example13 name.
  M22: { ...session, revision: 3 },
  // M23 POST S/publish after M21
  M23: { version: { ...version, version: 2,
      version_id: "10000000-0000-4000-8000-000000000012" },
    session: { ...session, revision: 3,
      base_version_id: "10000000-0000-4000-8000-000000000012" } } satisfies PublishResult,
  // M24 GET C/schemas
  M24: { items: ["dev_demo"] },
  // M25 GET C/assets?schema_name=dev_demo
  M25: assets,
  // M26 POST C/assets/refresh?schema_name=dev_demo
  M26: assets,
  // M28 GET O/objects?source=document&type_id=... — first page, limit=1.
  M28: { ...ie, source: "document", items: [fact], next_cursor: null,
    truncated: false, snapshot_dates: [] } satisfies InstanceList,
  // M29 GET O/objects/{fact.ref}
  M29: { ...ie, item: fact, snapshot_dates: [] } satisfies InstanceDetail,
  // M30 GET O/objects/{fact.ref}/neighborhood — depth=1, no links in this variant.
  M30: { ...ie, ...docNeighborhood },
};
```

例04提供 M27、M31 的复合键用例。对其 fixture 仅增加虚构源数据 `order_id=O100,line_no=1,qty=2,unit_price=10`，数量×单价=20。为避免在文档伪造一串难核验的 base64，示例调用一个明确的纯编码函数；前端真实业务不得自行依赖此函数构造 ref。

```ts
// Browser mock utility; production refs always come from the backend.
const encodeMockRef = (typeId: UUID, key: TypedKey) => "db." +
  btoa(JSON.stringify([typeId, key])).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const lineType = d04.object_types.find(t => t.technical_name === "order_line")!;
const lineKey: TypedKey = [{ type: "string", value: "O100" }, { type: "integer", value: "1" }];
const lineRef = encodeMockRef(lineType.id, lineKey);
const line: DatabaseInstanceRead = {
  id: lineRef, ref: lineRef, type_id: lineType.id, key: lineKey,
  source: "database", display_text: "1 / O100", evidence: [],
  values: { order_no: "O100", line_no: 1, quantity: 2, unit_price: 10, line_amount: 20 },
};
const M27: MappingPreview = {
  items: [{ __key: lineKey, __type_id: line.type_id, __ref: lineRef,
    values: line.values, display_text: line.display_text }],
  has_more: false, source: "database", snapshot_dates: [],
};
const M31: InstanceNeighborhood = {
  center_id: lineRef, objects: [line], links: [], warnings: [], truncated: false,
  source: "database", depth: 1, snapshot_dates: [],
};
```

M32 使用例07客户事实，增加一条同客户编号的新证据提案场景。最终 after 由人工确认，已有事实 UUID 保留；以下为修订成功的新批次响应，原批次对应项重读变 superseded。新增证据应在 mock store 预置材料或用服务端盖章的人工证据，不用不存在的材料测试真实写入。

```ts
const revisionBid = "10000000-0000-4000-8000-000000000013";
const revisionPid = "10000000-0000-4000-8000-000000000014";
const appended: ManualEvidence = {
  kind: "manual", id: "10000000-0000-4000-8000-000000000015",
  note: "人工确认追加客户事实证据", created_by: "mock_user", created_at: now,
};
const M32: ProposalBatchDetail = {
  ...batch, id: revisionBid, items: [{
    ...proposal, id: revisionPid, batch_id: revisionBid, client_ref: null,
    operation: "update", target_kind: "material_object", target_id: fact.id,
    display_name: fact.display_text, before: d07.material_objects[0],
    after: { ...d07.material_objects[0], evidence: [...(fact.evidence ?? []), appended] },
    field_changes: [], evidence: [appended], reason: "改为更新已有客户事实并追加证据",
    depends_on: [], dependency_group: [revisionPid], atomic_group_id: null,
    duplicate_candidates: [],
  }],
};
// Example duplicate hint on the original create item, before revision:
const duplicate_candidates: DuplicateCandidate[] = [{
  id: fact.id, type_id: fact.type_id, display_text: fact.display_text, expected_target_hash: h,
}];
```

M33 请求可直接使用例13 commit 指标，`time_range={start:"2026-10-01",end:"2026-11-01"}`、`trend_grain:"month"`；不要求先保存指标，不传对象/映射。SQL/params 与 mock 三行数据一致。

```ts
const M33: MetricPreview = {
  definition_hash: h, context_version: vid, session_revision: null, status: "ok",
  value: 10, value_kind: "integer",
  total_query: {
    sql: "SELECT SUM(`commit_count`) AS value FROM `dev_demo`.`code_lines_daily` WHERE `stat_date` >= :start AND `stat_date` < :end",
    params: { start: "2026-10-01", end: "2026-11-01" }, dialect: "mysql", database: "dev_demo",
  },
  trend_query: {
    sql: "SELECT DATE_FORMAT(`stat_date`, '%Y-%m-01') AS period, SUM(`commit_count`) AS value FROM `dev_demo`.`code_lines_daily` WHERE `stat_date` >= :start AND `stat_date` < :end GROUP BY DATE_FORMAT(`stat_date`, '%Y-%m-01') ORDER BY period",
    params: { start: "2026-10-01", end: "2026-11-01" }, dialect: "mysql", database: "dev_demo",
  },
  trend: [{ period: "2026-10-01", value: 10 }], snapshot_dates: [], warnings: [],
};
const unable: MetricPreview = {
  definition_hash: h, context_version: vid, session_revision: null, status: "unable",
  reason_code: "binding_not_ready", reason: "数据集列清单尚未就绪，无法预览",
  value: null, value_kind: null, total_query: null, trend_query: null,
  snapshot_dates: [], warnings: [],
};
```

补充交互 mock：

```ts
const staleError: ErrorResponse = { error: {
  code: "SESSION_REVISION_CHANGED", message: "草稿已更新，请刷新后重新确认",
} };
const conflict: MergeConflict = {
  key: "metrics/00000000-0000-4000-8000-000000013101/name",
  element_kind: "metric", element_id: commit.id, element_label: "提交数", path: "name",
  kind: "field", base: "提交数", latest: "总提交数", draft: "代码提交数",
  allowed: ["latest", "draft", "custom"],
};
const conflictError: ErrorResponse = { error: {
  code: "MERGE_CONFLICTS", message: "与最新版本存在冲突，请先解决",
  conflicts: [conflict], current_version_id: vid,
} };
const atomicDetail: ProposalBatchDetail = {
  ...batch, counts: { ...counts, pending: 2 }, items: [
    { ...proposal, atomic_group_id: bid, dependency_group: [pid, revisionPid] },
    { ...proposal, id: revisionPid, ordinal: 1, client_ref: "core_total",
      target_id: d13.metrics[1].id, after: d13.metrics[1], display_name: "核心仓库提交数",
      atomic_group_id: bid, dependency_group: [pid, revisionPid] },
  ],
};
const revoked: DecisionResult = {
  session: { ...pendingSession, revision: 4, pending_proposal_count: 0 },
  results: [{ proposal_id: pid, status: "rejected" }], validation: valid,
};
```

MCP 是修改的服务协议，M34 给出 tools/call 的完整 JSON-RPC 响应，下面也给四种调用的最小 structuredContent；实际 JSON-RPC `result` 为 `{content:[{type:"text",text:JSON.stringify(payload)}],structuredContent:payload}`。不新增 REST mock 路由。get_ontology 以例13指标目录项示意；physical 完整投影按 §6 增补，不复用 REST ResourceRead 包装。

```ts
const mcEnv: MCPEnvelope = { workspace_id: wid, version_id: vid };
const mcpSearch: MCPList<OntologyHit> = { ...mcEnv, total: 1,
  items: [{ id: commit.id, kind: "metric", name: "提交数", technical_name: "commit_count",
    summary: "按代码行日统计的提交数求和", matched_synonyms: [],
    dataset: { id: ds.id, name: ds.name } }], next_cursor: null };
const mcpOntology: MCPGetOntology = { ...mcEnv, total: 1,
  elements: [{ id: commit.id, kind: "metric", name: "提交数", technical_name: "commit_count",
    definition: commit, binding_status: "bound" }], missing: [], next_cursor: null };
const mcpObjects: MCPList<MCPObjectHit> = { ...mcEnv, total: 1,
  items: [{ id: fact.id, type_id: fact.type_id, display_text: fact.display_text,
    values: fact.values ?? {} }], next_cursor: null };
const mcpObject: MCPEnvelope & { item: MCPObject } = { ...mcEnv,
  item: { id: fact.id, type_id: fact.type_id, display_text: fact.display_text,
    values: fact.values ?? {}, properties: { total: Object.keys(fact.values ?? {}).length,
      items: Object.entries(fact.values ?? {}).map(([name, value]) => ({
        property_id: d07.properties.find(p => p.owner_type_id === fact.type_id && p.technical_name === name)!.id,
        value,
      })), next_cursor: null } } };
```

```ts
// M34 POST O/mcp; method=tools/call, name=search_ontology.
const M34: MCPResponse<MCPCallResult<typeof mcpSearch>> = {
  jsonrpc: "2.0", id: 1,
  result: { content: [{ type: "text", text: JSON.stringify(mcpSearch) }],
    structuredContent: mcpSearch },
};
```

mock 必须按 source/date/version/权限隔离，并补无法预览、过期响应、重复事实、原子组联动和409冲突状态；不能让所有写操作固定返回同一 revision。以上 M 编号是各自最小场景，不是一条可以按编号连续执行的事务脚本。

## 9. 只读推导字段与前端回传边界

| 字段/内容 | 来源 | 前端写入规则 |
|---|---|---|
| simple.value_kind | 聚合与登记列类型；未知为 null | 不回传；count/count_distinct=integer，avg/median=decimal，sum/min/max 沿度量类型 |
| ratio.dataset_id/value_kind/components | 两个同数据集数值型 simple 分量，结果 decimal | 不回传；预览分量通过请求 components，核心 ratio 无 time_field |
| expression.value_kind、Property.value_kind | 核心声明 | 可以回传，不能误删为派生字段；不做 SQL 类型推断 |
| display_text、文档 ref、数据库 ref/key/id | 标题/完整标识/可见引文/UUID 或物理键，服务端编码身份 | 不写 MaterialObject，不新增 name；数据库 ref 仅用于读取定位 |
| binding_status、physical_type、database/schema、sql_reference | 有效绑定、服务端来源解析、授权元数据及编译 | 不回传核心；Dataset.schema_name 和 columns[].physical_type 是合法核心输入，不能混淆 |
| metadata_snapshot_id、observed_at | 服务端元数据采集记录 | 不回传 Dataset，禁止伪造采集时间 |
| inherited_from、有效 properties/links/rules、child_types、instance_source_type_ids | 单父祖先链和有效绑定 | 不存进草稿；继承定义保留原 UUID/owner；只编辑本地定义或允许的本地绑定 |
| counts、matches/摘要、display_name/owner_label、field_changes、duplicate_candidates | 读时授权和显示推导 | 不回传核心或 agent after |
| dependency_group、atomic_group_id、effective status | 服务端引用图和提案记录 | 决定请求只发选中 proposal_id/decision；不能自行指定原子组 |
| base_diff、graph、validation、labels、impacts、auto_merged | 草稿、版本和权限派生 | 不写 Draft；不把 Rule 折叠成字符串后丢 UUID |
| definition_hash、query、trend、snapshot_dates、warnings | 本次预览/实例读取 | 不持久化到指标/来源；表单变化即失效 |
| revision/version/hash | 服务端并发与内容标识 | 只放规定的 expected/revision envelope，不作为模型字段；原样回传，不伪造 |
| 人工 evidence.created_by/created_at | 人工保存由服务器盖章；可信导入另按计划处理 | 不允许客户端伪造作者/时间；保留已有证据不重铸 UUID |

把读对象 spread 到核心请求里会触发 extra forbid；前端应按生成类型的字段白名单构造，不能简单删一个 binding_status 就发送整个读响应。原生 columns 是可携带的元数据副本，不等于已经验证数据库存在；不从 unknown 状态捏造就绪 SQL。只读推导与执行参数都不增加 core-1 字段。

## 10. 尚需协调方确认的细节

下列是设计/计划明确行为之后仍未指定的 wire 细节。**协调方已确认（2026-10-16）：以下“本文推荐”列全部作为前后端共同基线**；实施中如需调整，先改本文件并在后端进度记录“契约变更”一节写明，前端据此同步。它们不是重新讨论已确认的业务取舍。

| 点 | 当前缺口、具体例子 | 本文推荐 |
|---|---|---|
| 读 DTO 与受影响组 envelope | 生成 Metric.kind=ratio 与资源分类 kind=metric 不能占同一字段；计划只说“带受影响项/校验 hash”，未命名 | REST ResourceRead 用 kind+definition；affected_items 用目标种类/id/expected_target_hash，作为请求 envelope，不加到模型 |
| 事实修订响应及 pending 候选 | 例07已有 C001 可安全修订；两个仍 pending 的 C001 create 中，后者不能更新一个尚不存在的事实 UUID | 本期修订目标限当前会话已有事实；读取可以提示其他 pending 重复，但应另带可识别的提案来源 DTO 后才能支持点选。本文 duplicate_candidates 仅承诺可修订已有事实。修订创建新批次、旧项 superseded，不增加草稿 revision；双方须确认依赖端点同批重写实现 |
| ref、快照日期与日期选择粒度 | 例04 O100+1 必须保留类型和键序；例12数量12-31、状态12-30不能共用主日期 | 锁定 §4.6 JSON+base64url；首版浏览用单个 snapshot_date 精确指定所有快照来源当日，默认各自最新；需要逐 Dataset 指定不同日期时，先协调为请求参数映射，不加入模型、不自动回退 |
| 预览字段名称和数值表示 | 计划 `context_version/session_revision` 是简写；decimal 可能超 JS 安全精度，0.8 不能整数截断 | 本文键为 context_version、session_revision；数值 Scalar 允许精确数值字符串，前端不得无条件 Number；HTTP结构/陈旧错误与 status=unable 分开。双方锁定驱动数值序列化规则 |
| MCP 字段分段 wire shape | 计划要求超大 expression 可续取，但未定义片段字段名，普通 Page 不足以表达半个字段 | 不默默截断；采用 §6 FieldSegment DTO，用同工具 cursor 续取；后端与服务接入示例一起核对其定位方式；只影响读 envelope，不改核心模型、不增加工具 |
| 错误标准化范围 | 当前不少路由仍抛 HTTPException，旧 PublishValidationError.code 为 OSSIE_VALIDATION_FAILED | 新/改业务路径按 §1.2 ServiceError；未改周边保留旧错误兜底。新错误代码名与 OpenAPI 在后端实现时逐项核对，不宣称本文件等于已实现的 OpenAPI |

仅文档交付不运行迁移、不清库、不改 JSON Schema/Pydantic/TS、不发布 DataAgent、不 commit。P2 实现时按计划同步 schema、生成类型、客户端、技能及服务端响应校验；此处引用生成核心类型不代替最终漂移检查。


### PR #23：M35 保存影响预检与例06物理投影 mock

以下沿用 §8 的初始化变量；M35 单独使用例07的已发布编辑场景。候选将 customer_no 改成 customer_code，而事实仍为旧键，服务端根据旧图 UUID 重写。h 仅为 mock 占位，真实 hash 来自服务器规范化的当前编辑基线。

```ts
const customerNumber = d07.properties.find(p => p.technical_name === "customer_no")!;
const M35Request: ElementSave = {
  target_kind: "object_type", target_id: customerNumber.owner_type_id,
  expected_current_version_id: vid, session_id: sid, expected_session_revision: 2,
  draft: { ...d07, properties: d07.properties.map(p => p.id === customerNumber.id
    ? { ...p, technical_name: "customer_code" } : p) },
};
const M35: ElementSaveImpact = {
  current_version_id: vid, session_revision: 2,
  affected_items: [{ target_kind: "material_object", target_id: d07.material_objects[0].id,
    expected_target_hash: h, reason: "当前元素修改需要同步此依赖的定义或引用" }],
};
const confirmedSave: ElementSave = { ...M35Request,
  affected_items: M35.affected_items.map(({ reason, ...item }) => item) };
```

例06的 `get_ontology` 请求 person/device/vehicle/asset，并带 physical、adjacency。以下 mock 从同一份设计示例构造有效绑定和 DatasetRead；不手写第二份本体。设备与车辆可以有相同来源键 `"1"`，实例响应仍返回各自实际 type_id 与 TypedKey，反向负责人边从具体设备/车辆指向当事人，按具体 ref 去重。

```ts
import example06 from "../../docs/design/core-1-examples/06-inheritance.json";
const d06 = example06.draft as unknown as Draft;
const page06 = <T,>(items: T[]): Page<T> => ({ total: items.length, items, next_cursor: null });
const obj06 = (name: string) => d06.object_types.find(o => o.technical_name === name)!;
const mapping06 = (name: string) => d06.mappings.find(m => m.type_id === obj06(name).id)!;
const binding06 = (name: string): EffectiveBindingRead => {
  const own = mapping06(name);
  const chain = own.binding_mode === "shared_parent" ? [mapping06("party"), own] : [own];
  return {
    type_id: obj06(name).id,
    sources: chain.flatMap(m => m.sources ?? []),
    fields: Object.assign({}, ...chain.map(m => m.fields)),
    memberships: chain.map(m => ({ type_id: m.type_id, mapping_id: m.id,
      binding_mode: m.binding_mode, membership_source_id: m.membership_source_id ?? null,
      derived_by: d06.object_types.find(o => o.id === m.type_id)!.derived_by ?? [] })),
    links: d06.link_types.filter(l =>
      l.source_type_id === obj06(name).id || l.target_type_id === obj06(name).id ||
      (name === "person" && (l.source_type_id === obj06("party").id || l.target_type_id === obj06("party").id)) ||
      (["device", "vehicle"].includes(name) && l.source_type_id === obj06("asset").id)
    ).map(l => ({ link_type_id: l.id, source_type_id: l.source_type_id,
      target_type_id: l.target_type_id,
      data_join: own.inherited_link_bindings?.[l.id] ?? l.data_join ?? null })),
  };
};
const physical06 = (names: string[]) => {
  const bindings = names.map(binding06);
  const ids = new Set(bindings.flatMap(b => b.sources.map(s => s.dataset_id)));
  return {
    effective_bindings: page06(bindings),
    datasets: page06(d06.datasets.filter(d => ids.has(d.id)).map(d =>
      ({ ...d, binding_status: "unbound" as const }))),
  };
};
const person06 = obj06("person");
const asset06 = obj06("asset");
const mcp06: MCPGetOntology = {
  workspace_id: d06.workspace_id, version_id: vid, total: 4, missing: [], next_cursor: null,
  elements: [{ id: person06.id, kind: "object_type", name: person06.name,
    technical_name: person06.technical_name, definition: person06, ...physical06(["person"]) },
  { id: asset06.id, kind: "object_type", name: asset06.name,
    technical_name: asset06.technical_name, definition: asset06,
    instance_source_type_ids: [obj06("device").id, obj06("vehicle").id],
    ...physical06(["device", "vehicle"]) },
  ...["device", "vehicle"].map((name): MCPElement => ({
    id: obj06(name).id, kind: "object_type", name: obj06(name).name,
    technical_name: obj06(name).technical_name, definition: obj06(name),
    ...physical06([name]),
  }))],
};
```

person 的 memberships 依次包含 party 的 independent 和 person 的 shared_parent（membership_source_id="extension"）；sources 同时有 main 与 extension。asset 的 effective_bindings 分为 device/vehicle 两项，两者 responsible_party 的 data_join 都取各自本地 inherited_link_bindings，datasets 分别为 devices/vehicles。单独请求 device/vehicle 时，同一个有效 join 同时出现在 adjacency.links 的 data_join 中，inherited_from 仍为 asset；不能把本地绑定归属伪装成新关系定义。

快照与 ratio 预览补充：只有明确的业务 time_field 才生成趋势；缺字段时 trend/trend_query 为 null，warnings 提示仅返回总值。按快照日期看趋势逐周期选末日，按上线日期看分组先选快照再归月（主设计 §3.6：10月1、12月2）。snapshot_dates 保留总值与各趋势周期实际选日；ratio 两分量同数据集但时间字段不同导致同一业务周期使用不同日期时，可有同 dataset_id/period 的多条实际 date，相同日期去重。分子分母同一 UUID 时 components 只提交一个唯一 simple 项，同时覆盖两个引用；重复提交仍 422。
