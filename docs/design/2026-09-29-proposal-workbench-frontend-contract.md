# Proposal 工作台前端交互与前后端合同补充

**日期：** 2026-09-29  
**状态：** 已实施（T5、T6，2026-09-30）。与本文的差异：版本历史比较仍使用路径级 Diff（只有发布预览改为元素级 `ElementChange`）；接受后停留在“提案”页签，按本文 §11 的默认取舍。  
**上位文档：** [Proposal-first 本体生命周期实施设计](./2026-09-26-proposal-first-ontology-lifecycle-implementation-design.md)（下称“实施设计”）  
**范围：** 补齐实施设计 §8、§9、§11 在前端信息架构、界面状态、TypeScript 类型、接口响应形状、刷新时序和 draft v2 前端影响面上的空白。领域规则、数据库、迁移以本文上位文档为准，本文不重复、不改写。

UI 草图：`docs/assets/proposal-workbench-2026-09-29/`

- `01-builder-proposals-tab.png`：本体自动构建页右栏“提案”Tab
- `02-proposal-detail-states.png`：提案详情抽屉与各状态样式
- `03-delivery-merge-conflicts.png`：发布页 · 解决冲突
- `04-delivery-publish-preview.png`：发布页 · 无冲突合并预览与确认发布

草图用于表达信息结构和状态，不是像素级规范。4 张图的主区信息结构与交互已于 2026-09-29 确认。**页面外壳一律沿用现有 `AppShell`**（220px 一级导航：本体视图、业务对象、本体关系、数据连接、数据映射、本体自动构建、空间设置），草图中的窄图标侧栏和导航项名称均为示意，不作依据；发布与服务页顶部须有面包屑“本体自动构建 / 发布与服务”（草图 03/04 未画出）。02 的背景页仅为示意，建模页布局以 01 为准；样式一律使用 `apps/web/src/styles/tokens.css` 现有 token。

## 1. 用户流程

1. 用户在“本体自动构建”页选材料、描述场景，在中栏与智能体对话并发起建模。
2. 运行结束后，右栏自动出现新 Proposal Batch，“提案”Tab 显示待审数量徽标。
3. 用户逐条、按依赖组或“接受全部无冲突项”接受；可以拒绝、恢复。
4. 接受成功后，这些变更才进入“本体草稿”Tab，并在草稿中带“本次会话新增/修改”标记；“语义图谱”Tab 同步显示草稿。
5. 用户可以在“本体草稿”Tab 继续人工编辑（沿用现有对象编辑页）。人工编辑会让依赖旧内容的待审提案变为“已过期”。
6. 点击“发布本体”进入发布页：展示服务端三方合并后的实际待发布内容；有冲突时按元素和字段逐项解决，保存后必须重新预览，才能发布。

## 2. 本体自动构建页右栏

### 2.1 Tab 结构

`ModelResults` 由两个 Tab 改为三个：

| Tab | 内容 | 数据来源 |
|---|---|---|
| 提案 `{pending数}` | 当前会话的 Proposal Batch 与 Item | `GET …/proposal-batches` |
| 本体草稿 | 现有“本体模型列表”，改为读取 v2 草稿，并标记相对基线的变更 | `session.draft` + `session.base_diff` |
| 语义图谱 | 现有“语义图谱概览” | `session.draft` |

默认选中规则：

- 进入页面时，当前会话有 `pending` 提案则选“提案”，否则选“本体草稿”。
- 运行完成且产生新的 `available` Batch 时，自动切到“提案”；用户正停留在其他 Tab 且在输入或编辑时不强制切换，只更新徽标。
- 接受成功后留在“提案”Tab，显示非阻塞提示“已写入草稿 r{n} · 查看草稿”，“本体草稿”Tab 显示 `+{本次接受数}` 小徽标，切过去后清除。
- 选中的 Tab 按会话保存在 URL `?panel=proposals|draft|graph`，与现有 `usePageTab` 一致，刷新不丢失。

### 2.2 提案 Tab

自上而下：

1. **批次头部**：批次选择（默认最新 `available` 批次；历史批次可切换，只读）、来源运行时间、`基于草稿 r{source_session_revision}`、待审数量；右侧按钮“接受全部无冲突项”“全部拒绝”。
2. **筛选分段**：全部 / 冲突 / 修改 / 删除 / 新增，带数量。
3. **分组列表**，排序固定：冲突与已过期 → 修改 → 删除 → 新增 → 历史（已接受、已拒绝、已被取代，默认折叠）。
4. **提案卡片**（`ProposalCard`）：
   - 左侧类型图标：实体、属性、关系、规则、Action、材料对象、材料关系、映射；类型同时用文字表示，不只靠颜色。
   - 标题：`{操作} {类型} · {显示名}`，属性显示 `所属实体.属性名`，规则显示归属元素。
   - 摘要：update 显示最多 3 个字段的行内差异，更多字段折叠为“另有 n 处修改”。
   - 依赖：属于依赖组时显示芯片“依赖组 n 项”，按钮变为“接受整组”。
   - 证据：`{材料名} 第 a–b 行`，点击打开详情。
   - Action 固定显示灰色标签“仅定义 · 不可执行”。
   - 操作：待审显示“接受”“拒绝”；已拒绝显示“恢复”；已过期和冲突不能接受，显示“拒绝”和“基于当前草稿重新建模”。
5. **详情抽屉**（`ProposalDetail`，点击卡片打开）：字段差异表（字段 / 草稿当前值 / 提案值）、长文本行内 diff、证据原文块与“在材料中查看”、依赖列表、操作栏。

“接受全部无冲突项”的语义：当前批次中所有 `pending`、且依赖闭包全部为 `pending` 的 Item，一次请求原子提交。请求被拒时整批不生效，界面逐项标出失败原因。

“基于当前草稿重新建模”：把中栏输入框填入固定提示词（“请基于当前草稿重新评估以下已过期提案：…”）并聚焦，不自动发送。

### 2.3 本体草稿 Tab

- 保留现有分类（实体、关系、映射、属性），新增“规则”“Action”“材料实例”三个分类。
- 每行显示相对 `base_version_id` 的变更标记：`新增`、`已修改`、`待删除`。待删除项不在草稿里，由 `session.base_diff` 中 `change=deleted` 的条目按 `label` 以删除线插入列表，直到发布。
- 底部说明改为“会话草稿 · 基于 v{n} · r{revision} · 发布前需预览合并结果”。

### 2.4 空状态、加载与错误

| 情况 | 表现 |
|---|---|
| 从未运行 | 提案 Tab：“向智能体描述场景并开始建模，提案会出现在这里” |
| 运行中 | 提案 Tab 顶部显示“正在生成提案…”；已有批次仍可操作 |
| Batch `validating` | 批次头部显示“正在校验提案”，卡片不可操作 |
| Batch `failed` | 错误块显示 `error_json.message`，提供“重新建模” |
| 生成期间草稿已变化 | 批次头部提示“生成期间草稿已变化（r{a} → r{b}），受影响的提案已标为已过期”；其余提案照常可操作 |
| 决策 409 | 不弹通用 toast；重新拉取会话和批次，对失败 Item 就地显示原因 |

## 3. 前端组件拆分

```text
components/
  ModelResults.tsx          三 Tab 容器（重构，保留文件名）
  proposals/
    ProposalPanel.tsx       批次头部 + 筛选 + 分组列表
    ProposalCard.tsx
    ProposalDetail.tsx      抽屉
    FieldDiff.tsx           字段差异表 / 行内 diff，发布页复用
    EvidenceQuote.tsx
    elementMeta.ts          target_kind → 图标、中文名、显示名解析
  DraftElements.tsx         原“本体模型列表”，改读 v2
  merge/
    MergeConflicts.tsx      发布页冲突树 + 三方对比
hooks/
  useProposals.ts           拉取批次、决策提交、幂等键、409 处理
lib/
  draftView.ts              v2 草稿选择器（见 §7）
```

## 4. TypeScript 类型

加到 `apps/web/src/api/types.ts`，字段名与后端 JSON 一致：

```ts
export type TargetKind =
  | "object_type" | "property" | "link_type" | "rule" | "action"
  | "material_object" | "material_link" | "mapping";

export type ProposalStatus =
  | "pending" | "accepted" | "rejected" | "stale" | "conflict" | "superseded";

// 现有 types.ts 的 `Evidence`（v1 文档实例证据）在 T1 切换 v2 时删除，
// 调用点（DocumentObject、DocumentLink、Candidate、InstancesPage、ObjectDetailPage）
// 一并改用下面的判别联合。
// 存储形态：与草稿、版本快照中的 JSON 完全一致。
export type MaterialEvidence = {
  kind: "material";
  id: string;
  material_id: string;
  material_sha256: string;
  locator: { heading?: string; line_start: number; line_end: number };
  quote: string;
};
export type ManualEvidence = {
  kind: "manual";
  id: string;
  note: string;
  created_by: string;
  created_at: string;
};
export type Evidence = MaterialEvidence | ManualEvidence;

// 展示形态：仅出现在 Proposal、预览等详情 DTO 中，服务端联表补充材料名。
export type EvidenceView =
  | (MaterialEvidence & { material_name: string; material_archived: boolean })
  | ManualEvidence;

export type FieldChange = {
  path: string;                   // 如 "description"、"values.credit_level"
  before: unknown;
  after: unknown;
};

export type ProposalItem = {
  id: string;
  batch_id: string;
  ordinal: number;
  operation: "create" | "update" | "delete";
  target_kind: TargetKind;
  target_id: string;
  display_name: string;           // 服务端按 after ?? before 计算
  owner_label?: string;           // 属性、规则的归属元素显示名
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  field_changes: FieldChange[];
  evidence: EvidenceView[];
  depends_on: string[];           // item id
  dependency_group: string[];     // 接受时必须一起提交的闭包，含自身
  status: ProposalStatus;         // 有效状态：stale/conflict 由服务端读取时计算，从不落库
  stored_status: "pending" | "accepted" | "rejected" | "superseded";
  status_reason?: string;         // stale/conflict 的人类可读原因
  accepted_revision?: number;
  decided_at?: string;
};

export type ProposalBatch = {
  id: string;
  status: "validating" | "available" | "failed";
  created_at: string;
  source_session_revision: number;
  base_version_id: string | null;
  counts: Record<ProposalStatus, number>;
  error?: { code: string; message: string };
};

export type ProposalBatchDetail = ProposalBatch & { items: ProposalItem[] };

export type DecisionResult = {
  session: ModelingSession;
  results: { proposal_id: string; status: ProposalStatus; reason?: string }[];
  validation: VersionSummary["validation"];
};

export type MergeConflict = {
  key: string;                    // 提交 resolutions 时使用的稳定键
  element_kind: TargetKind;
  element_id: string;
  element_label: string;
  path: string;
  kind: "field" | "delete_modify" | "duplicate_name" | "dangling_reference";
  base: unknown;
  latest: unknown;
  draft: unknown;
  allowed: ("latest" | "draft" | "custom" | "both")[];
};

// 按元素聚合的变更，发布预览和会话 base_diff 共用。
export type ElementChange = {
  element_kind: TargetKind;
  element_id: string;
  label: string;                  // 删除时取 before 的名称，前端无需再查
  owner_label?: string;           // 属性、规则的归属元素显示名
  change: "created" | "updated" | "deleted";
  field_changes: FieldChange[];   // created/deleted 时为空
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
};

export type Impact = { element_kind: TargetKind; element_id: string; label: string; reason: string };

export type PublishPreview = {
  session_revision: number;
  base_version_id: string | null;
  current_version_id: string | null;
  current_version_number: number | null;   // 空空间为 null
  next_version_number: number;             // 由服务端给出，前端不自行推断
  current_version_sha256: string;
  merged_snapshot_sha256: string;
  validation: VersionSummary["validation"];
  changes: ElementChange[];                // 相对 current version，按元素聚合
  impacts: Impact[];
  ossie: Record<string, unknown>;          // 完整 Ossie 文档，仅在抽屉中展示
  auto_merged: (ElementChange & { side: "latest" | "both" })[];  // 来自其他会话、由合并带入的变更
};
```

`ModelingSession` 增加：

```ts
draft_sha256: string;
base_version_sha256: string;
pending_proposal_count: number;
latest_batch_id: string | null;
base_diff: ElementChange[];   // 相对 base_version 的变更；已删除元素靠 label/before 渲染删除线，草稿本身不保留墓碑
```

旧 `candidates` 字段在迁移期保留为可选，仅用于只读展示遗留候选。

## 5. 接口合同补全

实施设计已定义路径，这里补齐响应和错误。

### 5.1 批次

`GET /api/v1/workspaces/{wid}/sessions/{sid}/proposal-batches?limit=20&cursor=`  
返回 `{ items: ProposalBatch[], next_cursor: string | null }`，按 `created_at` 倒序，不含 items。

`GET …/proposal-batches/{bid}`  
返回 `ProposalBatchDetail`。`items` 按 `ordinal` 排序，一次返回全部（单批上限 500 条；超过上限在结果消费阶段直接判为 failed）。

### 5.2 决策

`POST …/proposal-decisions`，请求见实施设计 §8.1；`decision` 取值 `accept | reject | restore`。

- 前端在用户点击时生成一次 `idempotency_key`，失败重试复用同一个键；只有用户重新操作才换新键。
- `accept` 请求必须包含完整 `dependency_group`；前端从 Item 上直接取，不自行计算依赖图。
- 成功：200 `DecisionResult`。

错误响应沿用后端现有 `ServiceError` 信封（`main.py` 中的 `service_error_handler`），新增字段放在 `error` 内：

```json
{ "error": { "code": "...", "message": "...", "items": [{ "proposal_id": "...", "reason": "..." }], "conflicts": [], "current_version_id": null } }
```

新接口一律抛 `ServiceError` 子类，不使用 `HTTPException(detail=...)`。`ServiceError` 增加可选 `details: dict`，`service_error_handler` 把它合并进 `error` 对象（与现有 `PublishValidationError` 的 `validation` 同一机制，改为通用实现）。前端 `ApiError` 增加 `items`、`conflicts`、`currentVersionId` 三个可选字段，从 `body.error` 解析；每个错误码都有客户端单测。

| HTTP | code | 前端处理 |
|---|---|---|
| 409 | `SESSION_REVISION_CHANGED` | 重拉会话和批次，提示“草稿已更新，请重新确认” |
| 409 | `PROPOSAL_STALE` | 重拉批次，相关卡片显示已过期 |
| 409 | `IDEMPOTENCY_MISMATCH` | 视为程序错误，换新键不自动重试，展示错误 |
| 422 | `DEPENDENCY_INCOMPLETE` | 就地提示缺失依赖，展开依赖组 |
| 422 | `VALIDATION_FAILED` | 在卡片上显示 `items[].reason` |
| 409 | `PROPOSAL_CONFLICT` | 重拉批次，相关卡片显示冲突 |
| 409 | `PROPOSAL_NOT_RESTORABLE` | restore 目标不是已拒绝状态；重拉批次 |
| 422 | `DEPENDENCY_CYCLE` / `DEPENDENCY_CROSS_BATCH` | 视为结果合同错误，展示错误，不重试 |
| 422 | `EVIDENCE_INVALID` | 证据材料跨空间、哈希或原文不符；在卡片证据区显示原因 |
| 409 | `MATERIAL_IN_USE` | 材料被引用，删除改为提示归档 |

### 5.3 会话

`GET/PUT …/sessions/{sid}` 响应增加 §4 列出的字段。`PUT` 保存草稿后，受影响的 pending 提案在读取批次时按哈希动态呈现为 stale（实施设计 §8.2–8.3），前端保存成功后重拉当前批次。运行期间保存草稿和提交决策不再被禁止，只受 revision 乐观锁约束。

### 5.4 预览、冲突解决、发布

- `POST …/preview`，请求 `{ expected_session_revision }`。
  - 200：`PublishPreview`。
  - 409 `MERGE_CONFLICTS`：`error.conflicts: MergeConflict[]`，外加 `error.current_version_id`，供解决时回传。
  - 409 `SESSION_REVISION_CHANGED`：重拉会话后重新预览。
- `POST …/resolve-merge`（现有接口改形）：请求

  ```json
  {
    "expected_session_revision": 9,
    "expected_current_version_id": "...",
    "resolutions": {
      "<conflict.key>": { "choice": "latest" | "draft" | "both" | "custom", "value": null }
    }
  }
  ```

  `custom` 时 `value` 必填且按字段类型校验。成功返回新的 `ModelingSession`（base 已推进到 current，revision+1）。前端随后**自动**重新调用 preview，不允许复用旧预览。
- `POST …/publish`：请求见实施设计 §9.3。409 `PREVIEW_OUTDATED`（三个 expected 值任一不符）时，前端丢弃当前预览，显示警示条“当前最新版本在你预览后已变化，已重新合并”，并自动重新预览。

现有 `resolutions: dict[str, str]` 与 `publish {revision, message}` 在切换后不再被前端使用；后端在迁移期同时接受旧形状，按实施设计 T8 的节奏移除。

## 6. 刷新时序

```text
dataagent-run-change(active)  → model.reload()                     （已有）
dataagent-complete            → model.reload() + proposals.reload()
                                若 session.latest_batch_id 变化且该批次 available → 切到“提案”Tab
dataagent-error               → model.reload() + proposals.reload()（已有 reload）
决策成功                        → 用响应里的 session 替换本地会话；重拉当前批次
草稿保存成功                     → 重拉当前批次
```

后端必须保证：运行结果落库（Batch 状态已离开 `validating`）之后，才向会话 SDK 报告完成。这与现在“结果替换草稿后才报告完成”的顺序一致，前端不做轮询。若 complete 到达时批次仍是 `validating`（例如异步校验），前端每 2 秒重拉一次，最多 30 秒。

## 7. draft v2 对现有前端的影响

v2 把属性提到顶层 `properties[]`（`owner_type_id`），把 `objects/links` 改为 `material_objects/material_links`，新增 `rules/actions`。以下文件直接读取 v1 结构，实施设计 §15 未全部列出：

```text
components/ModelResults.tsx      components/OntologyReading.tsx
components/MappingForm.tsx       components/DataAssets.tsx
components/OssieImportDialog.tsx hooks/useSnapshot.ts
pages/ObjectEditorPage.tsx       pages/ObjectDetailPage.tsx
pages/TypeCatalogPage.tsx        pages/InstancesPage.tsx
pages/MappingsPage.tsx           pages/OntologyViewPage.tsx
pages/DeliveryPage.tsx
```

策略：

1. API 所有草稿与快照响应统一输出 v2（后端经实施设计 §15 的唯一 `read_snapshot` 边界规范化历史 v1 版本），前端只处理 v2，不做双格式分支。
2. 新增 `lib/draftView.ts`，提供 `propertiesOf(draft, typeId)`、`rulesOf(draft, ownerId)`、`typeById`、`materialObjectsOf(draft, typeId)` 等选择器。上面各文件改为调用选择器，不在组件内直接拼接数组。
3. `ObjectEditorPage` 保存时按 v2 写回：修改属性即修改顶层 `properties[]` 中对应 ID 的元素，不重排数组。
4. 这一步归入实施设计 T1，前端和后端在同一个 PR 中切换，避免中间状态。

## 8. 发布页

现有 `DeliveryPage` 在一页内堆叠了会话选择、差异预览、统计、版本说明、校验 JSON、发布、冲突、版本历史和服务接入，信息层级混乱。重构为：

### 8.1 页面结构

“发布与服务”页顶部三个页面 Tab，沿用 `usePageTab`，URL `?tab=publish|history|service`：

| Tab | 内容 | 来源 |
|---|---|---|
| 发布 | 本节 8.2–8.3 | 重写 `ReleaseReview` |
| 版本历史 | 现有“已发布版本”表格与 `HistoryComparison` | 原样迁移 |
| 服务接入 | 现有 REST API、MCP、只读访问令牌 | 原样迁移 |

删除独立的“校验 JSON”按钮和实体/关系/实例/映射统计条：校验结果并入预览，统计并入变更摘要计数。

### 8.2 发布 Tab：合并预览（草图 04）

- 顶部一行：会话选择、`基线 v{base} → 最新 v{current} → 草稿 r{revision}` 芯片、“返回建模”。
- 三步进度条：① 合并预览 ② 解决冲突（无冲突时显示“无需处理”）③ 确认发布。进度只由服务端预览结果决定，不由前端自行推进。
- 左栏“变更摘要”：计数“新增 / 修改 / 删除 / 来自其他会话”，按元素类型分组列出，修改项可展开字段差异（复用 `FieldDiff`）；`auto_merged` 放在默认折叠的“自动合并了其他会话的 n 项变更”。
- 右栏固定“确认发布”卡片：`将发布为 v{next_version_number}`、`当前最新 v{current_version_number}`、校验状态、`预览于 {时间} · 基于最新 v{current}`、版本说明、主按钮“发布 v{next_version_number}”，以及“查看 Ossie JSON”（抽屉）和“重新预览”。
- 校验有错误时发布按钮禁用，错误列表显示在确认卡片内，每条可点击定位到变更摘要中的元素。

### 8.3 发布 Tab：解决冲突（草图 03）

- 同一框架；进度条停在②；提示条说明最新版本变化和自动合并数量。
- 左栏只列冲突项，按“元素 / 字段”显示，状态“待处理 / 已选择”，底部小字“另有 n 项已自动合并”。
- 右栏一次只处理一个冲突：三列只读对比“基线 / 最新 / 我的草稿”，下方单选“采用最新 / 采用我的草稿 / 自定义”（`allowed` 含 `both` 时另有“都保留”），“上一个 / 下一个”切换。
- 底部固定栏：“已解决 a / b” 与“保存并重新预览”；此状态不出现发布按钮和“确认发布”卡片。
- 保存成功后自动重新预览，回到 8.2；`PREVIEW_OUTDATED` 时同样自动重新预览并显示提示条。

## 9. 前端测试清单

- 三 Tab 默认选中规则、URL 保持、徽标数量。
- 运行完成后出现新批次并自动切 Tab；用户正在编辑时不强制切换。
- 单条接受、依赖组接受、接受全部无冲突项、拒绝、恢复。
- 接受成功后“本体草稿”出现新元素且带“新增”标记；拒绝后草稿不变。
- 决策 409 / 422 各 code 的就地展示；重试复用同一幂等键。
- stale / conflict 卡片不能接受，但仍可拒绝；“重新建模”填入输入框但不发送；目标改回原值后卡片恢复为待审。
- Action 卡片显示“仅定义 · 不可执行”，不存在执行按钮。
- 发布页：三个页面 Tab 与 URL 保持；进度条状态由预览结果决定；冲突列表、三方对比、custom 校验、保存后自动重新预览、`PREVIEW_OUTDATED` 自动重新预览、发布按钮启用条件；版本历史与服务接入迁移后原有测试通过。
- `draftView` 选择器单测，以及改用选择器后各页面的现有测试全部通过。

## 10. 与实施顺序的对应

| 本文章节 | 实施设计阶段 |
|---|---|
| §7 draft v2 前端切换 | T1 |
| §4 类型、§5.1–5.3、§6、§2、§3 | T4 后端 + T5 前端 |
| §5.4、§8（含发布页三 Tab 重构） | T6 |

## 11. 本文默认采用的取舍

以下几点上位文档没有规定，本文按推荐做法先定下来，实施时如需改变应先改本文：

- 接受后停留在“提案”Tab，而不是自动跳到“本体草稿”。
- 草稿中的删除在发布前以删除线保留显示。
- 单批上限 500 条提案。
- 不做提案的前端轮询，依赖运行完成事件；只有 `validating` 时有限轮询。
- 冲突解决后自动重新预览，而不是让用户再手动点一次。
