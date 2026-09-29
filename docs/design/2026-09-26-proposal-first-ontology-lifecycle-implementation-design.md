# Proposal-first 本体生命周期实施设计

**日期：** 2026-09-26  
**状态：** 已确认目标设计，待实施  
**权威上位文档：** [OntoFoundry 企业本体智能平台完整设计](./2026-09-01-enterprise-ontology-intelligence-platform-design.md)  
**替换边界：** 取代 [DataAgent Conversation SDK 集成设计](./2026-09-21-dataagent-conversation-sdk-integration-design.md) 中“完整 Ossie 结果直接替换会话草稿”的目标合同；旧合同只作为迁移期兼容路径保留。

本文供实施智能体直接执行。除本文明确留作取舍的事项外，不得自行扩展 Workspace Rule、实体自动融合、Action 执行或多本体 Workspace。

## 1. 要实现的结果

一个 Workspace 只有一批权威本体和一个当前发布指针。多个 Modeling Session 是从某个已发布版本派生的并行工作分支，不是多个本体。

自动建模不再直接覆盖 `draft_json`，而是生成不可变 Proposal Batch。用户接受 Proposal Item 后，变更才通过乐观锁进入会话草稿；拒绝 Proposal 不改变草稿。草稿经过发布预览、B/L/D 三方合并和双重乐观校验后，成为新的不可变整体版本。

```text
Workspace current version Vn
       │
       ├─ create session → pin Vn + version_sha256
       │                      │
       │                      ├─ run pins session revision + draft hash + materials
       │                      │
       │                      └─ DataAgent → Proposal Batch
       │                                      │
       │                         accept/reject │
       │                                      ▼
       │                               Session Draft r+1
       │                                      │
       └────────────────────── B / L / D preview + conflict resolution
                                              │
                                   expected head/revision/hash
                                              ▼
                                  immutable Workspace Version Vn+1
```

## 2. 明确不做

- 不支持一个 Workspace 下多个独立本体、项目或子图发布指针。
- 不增加 `ontology_constraint`。
- Rule 不设计 Workspace 级归属，也不增加通用 `scope` 体系。
- Action 只建模和版本化定义，不实现 Action 执行、权限执行器、补偿或工作流。
- 不把数据库业务行复制进本体版本，不给每一行结构化数据生成 Proposal。
- 不自动融合 Material Object 与 Mapped Object。
- 不把原始材料二进制复制到每个本体版本。
- 不使用名称、技术名、数组位置或版本 ID 判断两个元素是不是同一个对象。
- 不在迁移中重写、删除或原地修改历史 `ontology_versions`。

## 3. 当前实现基线与已知差距

当前仓库已经具备：

- `WorkspaceRecord.current_version_id` 与不可变 `OntologyVersionRecord`；
- `ModelingSessionRecord.base_version_id`、`revision`、`draft_json`；
- 会话保存的 revision 乐观锁；
- 发布时 Workspace/Session 行锁、B/L/D 三方合并和发布指针 CAS；
- Object Type、Attribute、Link Type、Document Object、Document Link、Mapping 的 UUID；
- 材料内容寻址保存、SHA-256、分块和 Evidence；
- 固定 `version_id` 的本体 REST/MCP 查询；
- DataAgent run token、任务 generation guard 和结果消费状态。

当前差距：

1. DataAgent `ontofoundry.model-result/v1` 输出完整 Ossie，成功后以 `mode="replace"` 覆盖草稿并清空候选。
2. `candidates_json` 是会话行中的兼容 JSON；只接受 `object_type/link_type/object/link/mapping`，没有完整 create/update/delete、依赖图、决策幂等和批次身份。
3. `requires`、`derived_by` 是字符串数组，Rule 没有稳定 ID；Action 尚无领域模型。
4. 发布预览只校验 session revision，直接比较最新版与原始草稿；发布请求没有 `expected_current_version_id` 和合并结果摘要。
5. 现有 JSON merge 对“带 `id` 的对象列表”可以细粒度递归合并，但字符串列表是原子字段。

实施不得删除现有并发保护；目标是在其上增加 Proposal、身份和预览一致性合同。

## 4. 领域元素与稳定身份

### 4.1 Proposal 可操作的元素

`target_kind` 只允许：

```text
object_type
property
link_type
rule
action
material_object
material_link
mapping
```

`evidence` 不是顶层本体元素，而是 Proposal 或 Material Object/Link/Rule 等元素上的来源绑定。Mapped Object/Link 是运行时查询结果，不是 Proposal target。

`OntologyDraft schema_version="2"` 使用统一的顶层元素集合，避免 Proposal 为嵌套数组位置发明第二套寻址方式：

```json
{
  "schema_version": "2",
  "workspace_id": "...",
  "object_types": [],
  "properties": [],
  "link_types": [],
  "rules": [],
  "actions": [],
  "material_objects": [],
  "material_links": [],
  "mappings": []
}
```

Property 增加 `owner_type_id`；Rule 使用受限 `owner_kind/owner_id`；Material Object/Link 保留 `type_id`。编译器和 UI 可以按 owner 分组，但持久化、Diff、Proposal 和 Merge 都以顶层稳定 ID 寻址。

### 4.2 身份规则

- 逻辑身份：`(workspace_id, element_id)`。
- 历史状态：`(workspace_id, version_id, element_id)`。
- 会话状态：`(workspace_id, session_id, session_revision, element_id)`。
- `element_id` 是 UUID，跨版本、重命名和字段修改保持不变。
- `kind` 创建后不可改变；换 kind 表现为 delete + create。
- 同一 `element_id` 的内容用规范化 JSON SHA-256 标识。
- 不同 ID、相同技术名属于唯一性冲突，不视为同一元素修改。

新增身份登记表，避免元素 ID 被跨 kind 重用：

```text
ontology_element_identities
  workspace_id       FK workspaces
  element_id         UUID/string
  kind               enum/string
  created_at
  created_by
  retired_at         nullable，仅表示当前头已删除；历史身份仍保留
  PRIMARY KEY (workspace_id, element_id)
  UNIQUE (workspace_id, element_id, kind)
```

身份表不是元素内容真相；内容仍在草稿和不可变版本快照中。发布和 Proposal 接受时校验 registry 与快照 kind 一致。

### 4.3 Rule

Rule 升级为一等对象：

```json
{
  "id": "uuid",
  "name": "供应商必须有统一编码",
  "technical_name": "supplier_code_required",
  "description": "",
  "owner_kind": "object_type | property | link_type | action",
  "owner_id": "uuid",
  "rule_kind": "constraint | derivation",
  "expression": "...",
  "verbalizes": [],
  "evidence": []
}
```

首期拒绝 `owner_kind=workspace`。编译 Ossie 时，将 Rule 投影回所属元素的 `requires` 或 `derived_by`；导入 Ossie 时创建 Rule。Rule 的稳定 ID 不进入官方 Ossie 字段，保存在 `ai_context.ontofoundry` 扩展与 OntoFoundry 完整快照中。当前扩展 v2 不得静默增加这些字段；Proposal-first 输出使用扩展 v3，导入器同时兼容 v2 和 v3。

### 4.4 Action

Action 是一等定义元素，不是执行记录：

```json
{
  "id": "uuid",
  "name": "审批供应商",
  "technical_name": "approve_supplier",
  "description": "",
  "input_type_id": "uuid",
  "parameters": [],
  "precondition_rule_ids": [],
  "effects": [],
  "evidence": []
}
```

首期只做 CRUD、Proposal、Diff、合并、校验和版本保存。不存在 Action 执行 API。Action 进入 OntoFoundry 完整快照；标准 Ossie 没有对应构造时，只进入 v3 `ai_context.ontofoundry` 扩展，不生成非法标准字段。

## 5. Material 与 Mapped 实例

### 5.1 Material Object / Link

- 来自上传材料或人工录入；
- 具有稳定 UUID；
- 可以作为 Proposal target；
- 接受后进入会话草稿；
- 发布后进入不可变版本；
- 至少携带一个 Evidence，人工创建可以使用 `manual` provenance 而不是伪造材料引用。

Evidence 最小合同：

```json
{
  "id": "uuid",
  "material_id": "uuid",
  "material_sha256": "64 hex",
  "locator": {
    "heading": "供应商管理",
    "line_start": 42,
    "line_end": 47
  },
  "quote": "短原文"
}
```

保存或接受时校验 `material_id` 属于同一 Workspace、SHA-256 与不可变材料记录一致、行号范围和 quote 可在规范化文本中核验。

### 5.2 Mapped Object / Link

- 由版本化 Mapping 和实时结构化数据查询产生；
- 不进入 `draft_json.objects/links`；
- 不逐行产生 Proposal；
- 稳定引用由版本中的 `mapping_id` 与源主键值组成；
- 固定 `version_id` 只固定 Mapping，不冻结源库数据。

Material 与 Mapped 实例可以在统一查询响应中返回，但必须有 `source_kind=material|mapped|manual`。在没有显式身份绑定能力前，不按名称自动融合。

### 5.3 材料保留

- 原文件按内容 SHA-256 不可变保存，同一 Workspace 内去重。
- Material 元数据不得原地指向另一份内容。
- 被 Proposal、会话草稿或任何已发布版本引用时禁止物理删除，只允许归档。
- 本体版本保存材料引用清单及哈希，不重复保存二进制。
- 备份与恢复必须同时覆盖 PostgreSQL 和材料存储；只恢复数据库不算成功。

## 6. 会话、运行与 MCP 固定上下文

### 6.1 会话创建

创建 Session 时原子固定：

```json
{
  "workspace_id": "...",
  "base_version_id": "... | null",
  "base_version_sha256": "... | empty-snapshot-hash",
  "revision": 0,
  "draft_sha256": "..."
}
```

`draft_json` 从该版本复制；空 Workspace 使用规范化空快照。Session 不随后续 Workspace 发布自动换基线。

### 6.2 每次建模运行

每个 modeling run 固定：

- `workspace_id`、`session_id`；
- `base_version_id`、`base_version_sha256`；
- `source_session_revision`、`source_draft_sha256`；
- 材料 ID、材料 SHA-256 清单；
- DataAgent topic/task/run token；
- Agent、Skill、模型和结果 schema 版本。

开始运行后 session revision 变化不会取消远端任务，但其结果只能落为 `stale` Batch，不得自动进入可接受状态。

### 6.3 MCP

建模上下文禁止调用无版本的 `latest`。至少提供或复用：

```text
get_ontology_manifest(workspace_id, version_id)
list_ontology_elements(workspace_id, version_id, kind, cursor)
get_ontology_elements(workspace_id, version_id, element_ids)
```

响应必须包含 `workspace_id`、`version_id`、`version_sha256`。BFF 根据 Session 注入或校验这三个值，不让模型读取其他 Workspace/Version。当前 Session Draft 通过本次运行固定的只读上下文文件或内部受限接口提供，不能冒充已发布 MCP 版本。

## 7. Proposal 合同

### 7.1 DataAgent 输出

新结果 schema：`ontofoundry.proposals/v1`。

```json
{
  "schema_version": "ontofoundry.proposals/v1",
  "run_token": "...",
  "workspace_id": "...",
  "session_id": "...",
  "base_version_id": "...",
  "base_version_sha256": "...",
  "source_session_revision": 12,
  "source_draft_sha256": "...",
  "items": [
    {
      "client_ref": "new-supplier-type",
      "operation": "create",
      "target_kind": "object_type",
      "target_id": null,
      "expected_target_hash": null,
      "before": null,
      "after": {
        "name": "供应商",
        "technical_name": "supplier"
      },
      "field_changes": [],
      "evidence": [],
      "depends_on": []
    }
  ]
}
```

规则：

- `create` 使用 batch 内唯一 `client_ref`；DataAgent 不自行决定最终 UUID。
- 服务端先以 `UUIDv5(session_id, run_token)` 计算稳定 `proposal_batch_id`，再以 `UUIDv5(proposal_batch_id, client_ref)` 确定性分配 create 的 `target_id`，重试得到同一 Batch 和同一元素 ID。
- 同一 Batch 内引用新元素时使用 `client_ref`，入库前统一解析为最终 UUID。
- `update/delete` 必须携带现有 `target_id`、完整 `before` 和 `expected_target_hash`；target 必须存在于该 run 固定的草稿中。
- `create` 的 `before` 必须为 null；`delete` 的 `after` 必须为 null；`update` 两者都非 null。
- `field_changes` 是展示和索引数据，`before/after` 才是应用与冲突检测的权威。
- Agent 不能输出 Mapped Object/Link 行级 Proposal。
- 整个结果先做 JSON Schema、空间/会话/版本/run token、引用、唯一性和领域校验；失败不能部分入库。

### 7.2 持久化

新增表：

```text
proposal_batches
  id
  workspace_id
  session_id
  dataagent_task_id
  run_token
  schema_version
  base_version_id
  base_version_sha256
  source_session_revision
  source_draft_sha256
  material_manifest_json
  producer_json              # agent/skill/model versions
  result_sha256
  status                     # validating|available|stale|failed
  error_json
  created_at
  UNIQUE (workspace_id, session_id, run_token)
  UNIQUE (workspace_id, session_id, result_sha256)

proposal_items
  id                         # server proposal UUID
  batch_id
  workspace_id
  session_id
  ordinal
  fingerprint
  operation                  # create|update|delete
  target_kind
  target_id
  expected_target_hash
  before_json
  after_json
  field_changes_json
  evidence_json
  status                     # pending|accepted|rejected|stale|conflict|superseded
  decided_by nullable
  decided_at nullable
  accepted_revision nullable
  created_at
  UNIQUE (batch_id, ordinal)
  UNIQUE (batch_id, fingerprint)

proposal_item_dependencies
  item_id
  depends_on_item_id
  PRIMARY KEY (item_id, depends_on_item_id)

proposal_decisions
  id
  workspace_id
  session_id
  item_id
  idempotency_key
  decision                   # accept|reject|restore
  expected_session_revision
  result_session_revision nullable
  actor_id
  created_at
  UNIQUE (workspace_id, session_id, idempotency_key)
```

所有跨表查询同时带 Workspace 和 Session 条件；不要仅凭全局 UUID 假定空间归属。PostgreSQL 外键和唯一约束是生产合同，SQLite 测试不能代替真实并发验收。

### 7.3 状态与不可变性

- Batch 和 Item 的生成内容入库后不可修改；只更新状态与决策字段。
- Create Proposal 的预分配 `target_id` 在 accepted 前不写入 `ontology_element_identities`；拒绝提案不会污染正式身份登记。Update/delete 的 target 必须已经登记或可从 legacy 快照回填验证。
- source revision/hash 不等于当前 Session 时，Batch 为 stale，Items 不可接受，但仍可查看。
- 新 Batch 可以将同一目标上的旧 pending Item 标记 superseded；不得删除历史。
- accepted Item 不允许改为 rejected；撤销通过新的反向 Proposal 或人工草稿编辑完成。
- reject 不改草稿；restore 只把 rejected 且仍未过期的 Item恢复为 pending。

## 8. 接受、拒绝与人工编辑

### 8.1 API

```text
GET  /api/v1/workspaces/{wid}/sessions/{sid}/proposal-batches
GET  /api/v1/workspaces/{wid}/sessions/{sid}/proposal-batches/{bid}
POST /api/v1/workspaces/{wid}/sessions/{sid}/proposal-decisions
```

决策请求：

```json
{
  "idempotency_key": "uuid",
  "expected_session_revision": 12,
  "decisions": [
    {"proposal_id": "...", "decision": "accept"}
  ]
}
```

响应返回新的 Session、逐项结果和 validation。批量 accept 默认原子；依赖组必须一起接受。请求混入其他 Workspace/Session、缺少依赖、存在环、目标过期或领域校验失败时整批回滚。

### 8.2 接受事务

顺序固定：

1. 锁定 Session 行并比较 `expected_session_revision`。
2. 读取全部 Item、依赖和幂等决策记录。
3. 比较 `source_draft_sha256` 与 Item `expected_target_hash`。
4. 按依赖拓扑应用 create/update/delete；禁止按数组位置更新。
5. 校验 Workspace、稳定 ID、kind、名称、引用、实例类型、Evidence 和 Mapping。
6. 规范化 draft 并计算新 SHA-256。
7. 更新 `draft_json`、`draft_sha256`、`revision+1`。
8. 写 decision，更新 Item 状态和 `accepted_revision`。
9. 同一事务提交。

同一 idempotency key、同一请求体重复调用返回第一次结果；同键不同请求体返回 409。revision 或目标内容变化返回 409，并把 Item 标记 conflict/stale，不覆盖人工修改。

### 8.3 人工编辑

现有保存草稿 API继续使用 revision 乐观锁，并同步更新 `draft_sha256`。人工编辑某 target 后，读取时动态或后台把以旧 target hash 为前提的 pending Proposal 标记 stale；不要求保存请求扫描所有历史 Batch 才能提交。

## 9. 三方合并与发布

### 9.1 合并身份

发布使用：

```text
B = Session.base_version_id 的规范化快照
L = Workspace.current_version_id 的规范化快照
D = Session.draft_json
```

按稳定 `element_id` 和带 ID 的子元素递归合并：

- 只改一侧：自动取修改侧；
- 双方相同修改：自动合并；
- 同一元素不同字段：自动合并；
- 同一标量字段不同值：冲突；
- 删除与修改：冲突；
- 不同 ID 新增：默认都保留，再做技术名和引用语义校验；
- scalar list 不按数组位置合并；应一等化的内容必须先转换为带 ID 元素。

冲突路径必须包含 `element_kind`、`element_id`、字段路径、base/latest/draft；UI 按元素分组。解决值允许 latest、draft 或 custom；“都保留”只适用于能按 ID 合并的集合。

### 9.2 预览

```text
POST /api/v1/workspaces/{wid}/sessions/{sid}/preview
```

请求：

```json
{"expected_session_revision": 12}
```

服务端执行完整三方合并、领域校验、Ossie 编译和 Diff。成功响应：

```json
{
  "session_revision": 12,
  "base_version_id": "...",
  "current_version_id": "...",
  "current_version_sha256": "...",
  "merged_snapshot_sha256": "...",
  "validation": {},
  "changes": [],
  "impacts": [],
  "ossie": {}
}
```

存在冲突时返回 409 和结构化 conflicts，不产生可发布 token。冲突解决 API继续要求 `current_version_id` 与 session revision，并把解决后的 merged snapshot 保存为新草稿、推进 revision、把 Session base 推进到被合并的 current version；之后必须重新预览。

### 9.3 发布

请求：

```json
{
  "expected_session_revision": 12,
  "expected_current_version_id": "...",
  "expected_merged_snapshot_sha256": "...",
  "message": "..."
}
```

事务中锁 Workspace 和 Session，再重新计算 B/L/D 合并结果并逐项比较三个 expected 值。任何值变化返回 409，用户必须重新预览；不允许因为变化“恰好能自动合并”就静默发布用户没看过的内容。

成功后：创建 `vN+1`，更新 Workspace current pointer，把 Session `base_version_id` 推进到新版本，`draft_json` 保存实际发布快照，revision+1。任何失败均回滚，不留下孤立版本。

## 10. 旧数据兼容与迁移

### 10.1 快照 schema

引入 `OntologyDraft schema_version="2"`：

- v1 `object_types[].attributes[]` 提升为顶层 `properties[]`，增加 `owner_type_id` 并保持原稳定 ID；
- `rules[]` 成为顶层一等元素，通过受限 owner 关联；
- `actions[]` 成为顶层一等元素；
- v1 `objects[]/links[]` 规范化为 `material_objects[]/material_links[]`，Evidence 明确材料来源；
- Mapping 保持版本化。

历史 v1 `ontology_versions.snapshot_json` 不改写。读取层支持 v1/v2；从 v1 创建新 Session 时规范化为 v2 草稿。

### 10.2 Legacy Rule ID

v1 中 `requires/derived_by` 没有 ID。规范化时以 UUIDv5 分配迁移 ID：

```text
namespace = workspace_id
name = owner_kind + owner_id + rule_kind + normalized_expression
```

相同 legacy 表达式重复读取获得相同 ID。进入 v2 后，修改 expression 保留已分配 ID。历史 v1 之间表达式发生变化时无法证明它们是同一规则，历史 Diff 可以显示 remove/add；不得用模型相似度猜测身份。

### 10.3 旧会话和旧运行

- 已存在 Session 在首次写入前按 CAS 从 v1 draft 升到 v2，并计算 `draft_sha256`。
- 已开始的 `ontofoundry.model-result/v1` run 允许按旧路径完成，但只限切换时间点之前已有 task_id/run_token 的运行。
- 切换后新 modeling run 只接受 `ontofoundry.proposals/v1`。
- 旧 `candidates_json` 保留读取兼容，不迁移成伪 Proposal；已有候选可以只读展示或由用户重新建模。
- 至少一个稳定发布周期内不删除 `candidates_json` 和旧结果消费代码；清理必须独立迁移并有部署数据统计依据。

### 10.4 Alembic

迁移必须线性追加，不修改已发布 revision：

1. 新增 identity、proposal 四组表及索引；
2. Modeling Session 增加 `base_version_sha256`、`draft_sha256`，先 nullable；
3. 扫描全部历史版本和现有 Session 中已有稳定 ID，回填 identity registry；同一 Workspace 内同一 ID 出现不同 kind 时立即中止迁移并输出冲突清单，不自动改 ID；
4. 回填当前 Session 哈希和基线哈希；
5. 校验无 null 后再收紧非空约束；
6. 不删除旧列。

Identity 回填包含 Object Type、Property、Link Type、Material Object/Link 和 Mapping；legacy Rule 在 v1→v2 规范化时按上节规则分配。只存在于历史版本、不在当前头的元素登记为 retired，但仍禁止复用。

升级在含真实数据的 PostgreSQL 副本验证；downgrade 只删除新表/列，不修改历史版本快照和材料。

## 11. 前端交互

完整的界面结构、TypeScript 类型、接口响应与错误码、刷新时序、draft v2 前端影响面和 UI 草图见 [Proposal 工作台前端交互与前后端合同补充](./2026-09-29-proposal-workbench-frontend-contract.md)。以下为摘要。

工作台右侧恢复 Proposal 列表，而不是把 Agent 完整结果直接显示为新草稿：

- 按 conflict/stale → update/delete → create → evidence 分组排序；
- 展示 operation、target kind、before/after、字段 Diff、Evidence 和依赖；
- 支持单条、依赖组和全部无冲突项接受；
- 支持拒绝与恢复；
- accepted 后移入历史并刷新 Session Draft；
- stale Proposal 只读，提供“基于当前草稿重新建模”；
- Material 与 Mapped 实例使用来源文字和图标，不只靠颜色；
- Action 显示“定义已建模/不可执行”，不得显示可运行状态。

发布页必须展示服务端三方合并后的实际待发布快照。预览返回的 current version 或 session revision 过期时，禁用旧发布结果并重新加载；不得只弹普通 toast 后继续沿用旧预览。

## 12. 安全与权限

- 所有 Proposal API先 `require_member`，并同时验证 Batch、Item、Session、Material、Version 属于路由 Workspace。
- DataAgent 只获得固定版本的只读本体 MCP 和本次 Session/Material 上下文，不获得发布权限。
- Agent 不分配发布版本号、不改变 Workspace current pointer、不接受 Proposal。
- Material quote 和结构化数据样例属于敏感内容；非成员与只读本体服务令牌不得读取。
- Action Definition 不意味着执行授权；本阶段无执行端点。
- JSON 中的 Workspace/Version 声明不能代替数据库归属校验。

## 13. 实施顺序

必须按以下顺序，保持每一步可回归、可部署：

### T0 — 锁定现有行为

- 为完整结果替换、候选接受、会话 revision、三方发布、预览差异补 characterization tests。
- 在 PostgreSQL 增加两个并发发布用例，不只跑 SQLite。

### T1 — v2 领域模型与兼容读取

- 新增 RuleDefinition、ActionDefinition、Evidence/来源字段和 v1→v2 规范化适配器。
- 编译、导入、导出和 Diff 支持 v2；不改历史快照。
- 测试 Rule ID 稳定、Action 扩展往返、legacy Ossie 往返。

### T2 — 数据库迁移与哈希

- 新增 identity/proposal/decision/dependency 表。
- 回填 Session base/draft hash。
- 在 PostgreSQL 验证唯一约束、外键、upgrade/downgrade。

### T3 — Proposal 结果契约与消费

- 增加 `ontofoundry.proposals/v1` JSON Schema、解析、引用解析、确定性 create ID、指纹和原子落库。
- generation guard、run token、revision/hash 不匹配落 stale，不能写 draft。
- 新运行通过 feature flag 选择 proposal contract；旧活动 run 继续兼容。

### T4 — Proposal API 与接受事务

- 实现列表、详情、accept/reject/restore。
- 完成依赖拓扑、批量原子性、幂等键和 target hash 冲突。
- 保存草稿同步计算 hash，人工修改使旧 Proposal 过期。

### T5 — 工作台 Proposal UI

- 替换完整草稿结果展示主流程。
- 接受、拒绝、恢复、依赖、stale、Evidence 和错误状态都有前端测试。

### T6 — 发布预览与双重乐观锁

- 预览改为真实 B/L/D merged snapshot。
- 发布请求增加 expected current version 与 merged hash。
- 冲突解决按元素/字段呈现，解决后强制重新预览。

### T7 — MCP 与固定上下文

- 核对固定 version 工具响应包含 Workspace/Version/SHA。
- BFF 强制会话绑定；运行固定 draft/material manifest。
- 测试 Agent 请求其他 Workspace/Version 被拒绝。

### T8 — 切换与清理准备

- 新 run 默认只生成 Proposal。
- 观测旧活动 run 清零、失败率、stale 率和决策结果。
- 停止生成完整替换结果，但保留读取兼容。
- 单独提出后续删除旧字段/代码的迁移，不在本任务中直接删除。

## 14. 测试与验收矩阵

### 14.1 领域与 Proposal

- 每个 target kind 的 create/update/delete。
- Create client_ref 重试分配同一 UUID。
- Update/delete 的 before/hash 不匹配变 stale/conflict。
- Rule owner 不存在、owner=workspace、Action 引用不存在 Rule 均拒绝。
- Proposal 依赖缺失、跨 Batch、成环、部分接受均拒绝。
- 同幂等键同请求返回相同结果；同键不同请求 409。
- 接受失败不改变 draft、revision、Item 状态。

### 14.2 材料与实例

- Evidence Material 跨 Workspace、SHA 不匹配、quote 不匹配均拒绝。
- 被 Proposal/草稿/版本引用的材料不能物理删除。
- Material Object/Link 随版本固定；Mapped Object/Link 随源库变化但固定 Mapping。
- 两类同名实例不自动融合。

### 14.3 会话与运行

- Session 固定 base version/hash；Workspace 后续发布不改变它。
- Run 固定 revision/draft/material manifest。
- 运行期间人工编辑后，结果落 stale Batch，不覆盖草稿。
- 重复消费同一结果不重复创建 Batch、Item 或推进 revision。

### 14.4 合并与发布

- 两会话新增不同元素自动合并。
- 同一元素修改不同字段自动合并。
- 同一字段不同值返回字段级冲突。
- 删除/修改冲突。
- 不同 ID、相同技术名形成语义冲突。
- 关系引用被删除类型形成引用冲突。
- 预览后 Session revision 变化，发布 409。
- 预览后 Workspace current version 变化，即使能自动合并也发布 409。
- merged hash 不匹配发布 409。
- 发布成功后实际 snapshot/Ossie/hash 与预览一致。
- PostgreSQL 两个并发发布只有合法顺序成功，不产生重复版本号或孤立 current pointer。

### 14.5 兼容

- 所有历史 v1 版本仍可查看、导出、比较。
- v1 当前版本可创建 v2 Session 并发布 v2 新版本。
- 切换前已开始的完整结果 run 能结束；切换后新 run 拒绝旧 schema。
- 旧 `candidates_json` 数据不丢失且不被误当成新 Proposal。

## 15. 主要代码影响范围

预计涉及：

```text
apps/api/src/ontofoundry_api/domain/models.py
apps/api/src/ontofoundry_api/db_models.py
apps/api/src/ontofoundry_api/alembic/versions/
apps/api/src/ontofoundry_api/api/modeling.py
apps/api/src/ontofoundry_api/api/agent_conversation.py
apps/api/src/ontofoundry_api/services/model_result.py
apps/api/src/ontofoundry_api/services/merge.py
apps/api/src/ontofoundry_api/services/version_diff.py
apps/api/src/ontofoundry_api/ossie/compiler.py
apps/api/src/ontofoundry_api/ossie/importer.py
apps/api/src/ontofoundry_api/api/mcp.py
integrations/dataagent/skills/md2ossie/
apps/web/src/api/types.ts
apps/web/src/api/client.ts
apps/web/src/hooks/useModeling.ts
apps/web/src/components/ModelResults.tsx
apps/web/src/components/ReleaseReview.tsx
apps/web/src/pages/BuilderPage.tsx
apps/web/src/pages/DeliveryPage.tsx
```

实施前先检查这些文件的未提交改动；当前工作区已有与 Ossie、verbalization 相关的用户修改，不得覆盖或回退。

## 16. 完成定义

以下条件全部满足才算完成：

- 新 modeling run 不再直接修改 `draft_json`，只生成 Proposal Batch。
- Proposal 接受/拒绝可审计、幂等、带 revision/hash 乐观锁。
- Rule 和 Action 是带稳定 ID 的一等定义元素；不存在 Workspace Rule 或 ontology_constraint。
- Material 与 Mapped 实例的存储、版本和 UI 来源明确；材料引用可恢复。
- Session/Run/MCP 都固定 Workspace、Version、Draft 和 Material 上下文。
- 发布预览与实际发布使用同一 merged snapshot，并同时锁 session revision 与 Workspace current version。
- 历史版本、旧会话和切换前活动运行不丢失。
- 单元、API、前端、Ossie 往返、迁移以及真实 PostgreSQL 并发测试全部通过。
- README 与主设计的“已实现”清单只在上述验收完成后更新；设计目标不能提前表述成已交付。
