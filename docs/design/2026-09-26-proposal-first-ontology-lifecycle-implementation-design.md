# Proposal-first 本体生命周期实施设计

**日期：** 2026-09-26  
**状态：** 已实施（T0–T8，2026-09-30）；各阶段交付见第 13 节。迁移期仍保留两条兼容路径，均列入[旧路径清理提案](../plans/2026-09-30-legacy-full-result-cleanup-proposal.md)：旧形态的发布请求（只带 `revision`，不做三值校验；新前端不再使用）与 `modeling_result_contract=full` 回退开关（默认已为 `proposals`）。在它们被移除前，§16 中“新运行只生成提案”和“发布锁定三个 expected 值”对新前端与默认配置成立，对这两条兼容路径不成立。  
**权威上位文档：** [OntoFoundry 企业本体智能平台完整设计](./2026-09-01-enterprise-ontology-intelligence-platform-design.md)  
**替换边界：** 取代 [DataAgent Conversation SDK 集成设计](./2026-09-21-dataagent-conversation-sdk-integration-design.md) 中“完整 Ossie 结果直接替换会话草稿”的目标合同；旧合同只作为迁移期兼容路径保留。

本文供实施智能体直接执行。除本文明确留作取舍的事项外，不得自行扩展 Workspace Rule、实体自动融合、Action 执行或多本体 Workspace。

## 1. 要实现的结果

一个 Workspace 只有一批权威本体和一个当前发布指针。多个 Modeling Session 是从某个已发布版本派生的并行工作分支，不是多个本体。

自动建模不再直接覆盖 `draft_json`，而是生成不可变 Proposal Batch。用户接受 Proposal Item 后，变更才通过乐观锁进入会话草稿；拒绝 Proposal 不改变草稿。草稿经过发布预览、B/L/D 三方合并和双重乐观校验后，成为新的不可变整体版本。

```text
Workspace current version Vn
       │
       ├─ create session → pin Vn + normalized_snapshot_sha256
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

首期拒绝 `owner_kind=workspace`。编译 Ossie 时，将 Rule 投影回所属元素的 `requires` 或 `derived_by`；导入 Ossie 时创建 Rule。Rule 的稳定 ID 不进入官方 Ossie 字段，保存在 `ai_context.ontofoundry` 扩展与 OntoFoundry 完整快照中。当前扩展 v2 不得静默增加这些字段；Proposal-first 输出使用扩展 v3，导入器兼容读取 v1、v2 和 v3（v1 与 v2 仅映射布局不同，已由 `parse_mappings` 同时支持）。当前代码的可读白名单是显式的 `("1", "2")`；T1 引入 v3 时改为 `("1", "2", "3")`，并为三个版本各保留一份冻结的导出样本。

### 4.4 Action

Action 是一等定义元素，不是执行记录：

```json
{
  "id": "uuid",
  "name": "审批供应商",
  "technical_name": "approve_supplier",
  "description": "",
  "input_type_id": "uuid",
  "parameters": [
    {
      "id": "uuid",
      "name": "审批意见",
      "technical_name": "comment",
      "value_kind": "string",
      "required": false
    }
  ],
  "precondition_rule_ids": [],
  "effects": [
    {
      "id": "uuid",
      "kind": "set_property | create_link | delete_link",
      "property_id": "uuid | null",
      "link_type_id": "uuid | null",
      "expression": "..."
    }
  ],
  "evidence": []
}
```

`parameters[].value_kind` 取 Property 相同的枚举；`effects[]` 只描述定义，`set_property` 必须给 `property_id`，`create_link/delete_link` 必须给 `link_type_id`，引用对象都必须属于同一草稿。

首期只做 CRUD、Proposal、Diff、合并、校验和版本保存。不存在 Action 执行 API。Action 进入 OntoFoundry 完整快照；标准 Ossie 没有对应构造时，只进入 v3 `ai_context.ontofoundry` 扩展，不生成非法标准字段。

### 4.5 哈希定义

所有哈希都是 SHA-256 的小写十六进制串，但按输入域分为三种算法，**互不通用**：

- **A. 版本信封算法**：只用于 `version_content_sha256`。继续使用现有 `ossie/compiler.py` 的 `sha256_json`（`canonical_json` 编码）对 `{snapshot, ossie, validation}` 求值，历史版本和新版本语义一致，不引入下面的语义规范化。
- **B. 领域快照算法**：用于 `normalized_snapshot_sha256`、`draft_sha256`、`element_sha256`、`merged_snapshot_sha256`，输入只能是 v2 领域快照或其中的单个元素，按下述两步规范化。
- **C. 原始结果算法**：只用于 `proposal_result_sha256`，对 DataAgent 结果文件的原始字节求 SHA-256，不解析、不规范化；结果语义去重另由 Item `fingerprint`（对单个 Item 按算法 B 规范化其 `operation/target_kind/target_id/after`）负责。

算法 B 的规范化分两步：

1. **语义规范化**（按字段固定，不按数据形状猜）：

   | 字段 | 规则 |
   |---|---|
   | 顶层元素集合（`object_types`、`properties`、`link_types`、`rules`、`actions`、`material_objects`、`material_links`、`mappings`）| 按 `id` 升序 |
   | `evidence[]` | 按 `id` 升序 |
   | `tags[]`、`extends[]`、`precondition_rule_ids[]`、`requires[]`、`derived_by[]` | 视为集合，去重后按字符串升序 |
   | `verbalizes[]`、Action `parameters[]`、Action `effects[]` | 有序，保持原顺序 |
| Mapping `fields` 等 JSON 对象 | 对象无顺序，由 JCS 按键排序 |
   | 可选字段值为 `null` | 省略该键 |
   | 字符串 | Unicode NFC |

   v2 领域模型新增数组字段时必须先在本表登记归类，否则算法 B 的规范化函数拒绝该字段（测试会失败）。本表只约束算法 B，不适用于 Ossie 文档或 Proposal 结果。
2. **字节规范化**：采用 RFC 8785 JSON Canonicalization Scheme（JCS），它规定了键排序、数字（含 `-0`、禁止 NaN/Infinity）和字符串转义的唯一编码。

T2 必须附带一组固定输入与期望哈希的测试向量，后续任何版本改动都不得改变这些向量的结果。不同用途的哈希互不比较：

| 名称 | 输入 | 用途 |
|---|---|---|
| `version_content_sha256` | 现有 `ontology_versions.sha256`：`{snapshot, ossie, validation}` | 版本完整性，保持现有语义，不改写历史 |
| `normalized_snapshot_sha256` | 读取层规范化为 v2 后的快照 | Session 基线、预览、发布比较；v1 历史版本按需计算并缓存，不回写 |
| `draft_sha256` | Session 当前 v2 草稿 | Batch 来源和草稿乐观校验 |
| `element_sha256` | 单个元素在草稿中存储的全部字段（含 `id` 与 `evidence`），不含服务端展示用的联表字段（如 `material_name`、`display_name`） | Proposal `expected_target_hash` |
| `merged_snapshot_sha256` | 预览时 B/L/D 合并后的 v2 快照 | 预览与发布一致性 |
| `proposal_result_sha256` | DataAgent 原始结果 JSON | 结果去重 |

空快照是 `{"schema_version":"2","workspace_id":"<wid>"}` 加所有元素集合为空数组后的规范化结果。文档中出现的 `base_version_sha256`、`current_version_sha256` 均指 `normalized_snapshot_sha256`。对外接口不再使用含义模糊的 `version_sha256`：REST、MCP 版本响应同时返回 `version_content_sha256` 与 `normalized_snapshot_sha256`，run manifest、BFF 固定校验和发布预览只使用 `normalized_snapshot_sha256`；现有 `version_sha256` 字段在迁移期保留为 `version_content_sha256` 的别名。

## 5. Material 与 Mapped 实例

### 5.1 Material Object / Link

- 来自上传材料或人工录入；
- 具有稳定 UUID；
- 可以作为 Proposal target；
- 接受后进入会话草稿；
- 发布后进入不可变版本；
- 至少携带一个 Evidence，人工创建可以使用 `manual` provenance 而不是伪造材料引用。

Evidence 是判别联合。材料证据：

```json
{
  "kind": "material",
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

人工来源：

```json
{
  "kind": "manual",
  "id": "uuid",
  "note": "业务专家确认",
  "created_by": "user-id",
  "created_at": "ISO-8601"
}
```

Material Object/Link 至少携带一条任意类型的 Evidence。`manual` Evidence 的 `created_by` 一律由服务端取当前认证主体、`created_at` 取数据库时间，请求中的值被忽略；DataAgent 结果中出现 `kind=manual` 视为结果合同错误，整个结果拒收；update 不得修改或删除他人创建的 `manual` Evidence，只能追加自己的。

保存或接受时，对 `kind=material` 校验 `material_id` 属于同一 Workspace、SHA-256 与不可变材料记录一致、行号范围和 quote 可在规范化文本中核验。

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
- 被 Proposal、会话草稿或任何已发布版本引用时禁止物理删除，只允许归档。`materials` 增加 `archived_at`、`archived_by`（T2 迁移）；归档材料不出现在新建模的材料选择中，但已有证据仍可打开；删除接口先检查 `proposal_items.evidence_json`、所有 Session 草稿和版本快照中的引用，存在引用返回 409 `MATERIAL_IN_USE`。
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

开始运行后 session revision 变化不会取消远端任务。结果仍入库为 `available` Batch，但其中每个 Item 按 §7.3 的规则逐项判断：目标在运行期间被改动的 Item 呈现为 stale，不受影响的 Item 仍可接受。为此，当前 `revise()` 中“运行期间禁止编辑”的限制在 proposal 合同启用后改为：草稿保存和 Proposal 决策只受 revision CAS 约束；旧完整结果合同的运行仍保留原限制和 generation guard。

### 6.3 MCP

建模上下文禁止调用无版本的 `latest`。至少提供或复用：

```text
get_ontology_manifest(workspace_id, version_id)
list_ontology_elements(workspace_id, version_id, kind, cursor)
get_ontology_elements(workspace_id, version_id, element_ids)
```

响应必须包含 `workspace_id`、`version_id`、`version_content_sha256`、`normalized_snapshot_sha256`。BFF 根据 Session 注入 `workspace_id`、`version_id`，并以 Session `base_version_sha256` 校验响应的 `normalized_snapshot_sha256`，不让模型读取其他 Workspace/Version。当前 Session Draft 通过本次运行固定的只读上下文文件或内部受限接口提供，不能冒充已发布 MCP 版本。

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
- 服务端先计算稳定 `proposal_batch_id`，再确定性分配 create 的 `target_id`，重试得到同一 Batch 和同一元素 ID；具体算法（带用途前缀）以 [结果合同](./2026-09-30-proposal-contract-v1.md) §4 为准。
- 同一 Batch 内引用新元素时，任何本应填元素 ID 的字段（如 `owner_type_id`、`source_type_id`、`owner_id`、`precondition_rule_ids[]` 中的一项）改写为对象 `{"client_ref": "new-supplier-type"}`；入库前统一解析为最终 UUID，并自动把被引用 Item 加入 `depends_on`。
- `after` 的结构按 `target_kind` 取 v2 领域模型中对应元素的完整定义（JSON Schema 随 `ontofoundry.proposals/v1` 一起发布，按 `target_kind` 做 `oneOf` 判别）：create 时省略 `id`，其余必填字段必须给出，可省略字段按模型默认值补全，存储与指纹均使用补全后的规范元素；update 时必须是修改后的完整元素，`id` 必须等于 `target_id`。
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
  status                     # validating|available|failed
  error_json
  created_at
  UNIQUE (workspace_id, session_id, run_token)
  UNIQUE (workspace_id, session_id, result_sha256)
  UNIQUE (workspace_id, session_id, id)                 # 供复合外键引用
  FOREIGN KEY (workspace_id, session_id) → modeling_sessions(workspace_id, id)

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
  status                     # 仅存决策状态：pending|accepted|rejected|superseded
  decided_by nullable
  decided_at nullable
  accepted_revision nullable
  created_at
  UNIQUE (batch_id, ordinal)
  UNIQUE (batch_id, fingerprint)
  UNIQUE (workspace_id, session_id, batch_id, id)       # 供依赖与决策项复合外键引用
  FOREIGN KEY (workspace_id, session_id, batch_id) → proposal_batches(workspace_id, session_id, id)

proposal_item_dependencies
  workspace_id
  session_id
  batch_id
  item_id
  depends_on_item_id
  PRIMARY KEY (item_id, depends_on_item_id)
  FOREIGN KEY (workspace_id, session_id, batch_id, item_id)
    → proposal_items(workspace_id, session_id, batch_id, id)
  FOREIGN KEY (workspace_id, session_id, batch_id, depends_on_item_id)
    → proposal_items(workspace_id, session_id, batch_id, id)   # 两端同 Batch 由数据库保证
  CHECK (item_id <> depends_on_item_id)

proposal_decision_requests
  id
  workspace_id
  session_id
  idempotency_key
  request_sha256             # 规范化请求体哈希，用于判断同键异体
  expected_session_revision
  result_session_revision
  response_json              # 首次成功响应，重放时原样返回
  actor_id
  created_at
  UNIQUE (workspace_id, session_id, idempotency_key)
  UNIQUE (workspace_id, session_id, id)
  FOREIGN KEY (workspace_id, session_id) → modeling_sessions(workspace_id, id)

proposal_decision_items
  workspace_id
  session_id
  request_id
  batch_id
  item_id
  decision                   # accept|reject|restore
  PRIMARY KEY (request_id, item_id)
  FOREIGN KEY (workspace_id, session_id, request_id)
    → proposal_decision_requests(workspace_id, session_id, id)
  FOREIGN KEY (workspace_id, session_id, batch_id, item_id)
    → proposal_items(workspace_id, session_id, batch_id, id)   # 请求与 Item 同 Session 由数据库保证
```

只有成功的决策请求才写入这两张表。

所有跨表查询同时带 Workspace 和 Session 条件；不要仅凭全局 UUID 假定空间归属。`proposal_batches`、`proposal_items` 对 `(workspace_id, session_id)` 使用复合外键指向 `modeling_sessions`（需先给后者加 `UNIQUE (workspace_id, id)`），`proposal_items` 对 `(workspace_id, session_id, batch_id)` 复合外键指向 `proposal_batches`；依赖与决策项通过上面的复合外键保证不跨 Workspace、Session、Batch。跨 Batch 依赖由此在数据库层即被拒绝。PostgreSQL 外键和唯一约束是生产合同，SQLite 测试不能代替真实并发验收。

### 7.3 状态与不可变性

- Batch 和 Item 的生成内容入库后不可修改；只更新状态与决策字段。
- Create Proposal 的预分配 `target_id` 在 accepted 前不写入 `ontology_element_identities`；拒绝提案不会污染正式身份登记。Update/delete 的 target 必须已经登记或可从 legacy 快照回填验证。
- Item 的**有效状态**由存储状态和当前草稿共同决定，且 `stale`、`conflict` 只在读取时计算、**永不落库**：
  - 存储状态为 `accepted`、`rejected`、`superseded` 时，有效状态即存储状态；
  - 存储状态为 `pending` 时：update/delete 的目标元素已不存在或 kind 改变 → `conflict`；目标 `element_sha256 ≠ expected_target_hash` → `stale`；create 的 `target_id` 已被占用 → `conflict`；否则再按依赖判断（见下）。
  - **依赖传播**：对 `depends_on` 中的每个依赖 Item——依赖为 `pending` 且可与本 Item 同组接受，或已 `accepted` 且其目标仍在草稿中：不影响；依赖为 `rejected`/`superseded`，或已 `accepted` 但目标已被删除：本 Item 为 `conflict`；依赖的有效状态为 `stale`/`conflict`：本 Item 继承该状态，`status_reason` 注明“依赖 X 已过期/冲突”。依赖尚未接受时其目标本就不在草稿中，**不**据此判 conflict。
  - 引用已存在元素（非 `client_ref`）的字段，只在该元素原本存在、随后被删除时判 `conflict`。
  - 因为不落库，目标内容若被改回原值，Item 自动恢复为 `pending`。
- Batch 不存在整批 stale。Batch 的 `source_session_revision/source_draft_sha256` 只用于展示“基于草稿 r{n}”和审计。
- 新 Batch 可以将同一目标上的旧 pending Item 标记 superseded；不得删除历史。
- accepted Item 不允许改为 rejected；撤销通过新的反向 Proposal 或人工草稿编辑完成。
- reject 不改草稿，只能作用于有效状态为 `pending`、`stale` 或 `conflict` 的 Item；restore 只作用于存储状态为 `rejected` 的 Item，把它改回 `pending`（有效状态随后照常计算）。

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

1. 锁定 Session 行（`SELECT … FOR UPDATE`）。
2. 按 `(workspace_id, session_id, idempotency_key)` 查 `proposal_decision_requests`：已存在且 `request_sha256` 相同 → 直接返回保存的 `response_json`，结束；已存在但哈希不同 → 409 `IDEMPOTENCY_MISMATCH`，结束。
2a. 记录不存在时，比较 `expected_session_revision`，不等 → 409 `SESSION_REVISION_CHANGED`。
2b. 读取全部 Item 与依赖，计算每个 Item 的有效状态。
3. 对每个 update/delete Item，比较当前草稿中目标元素的 `element_sha256` 与 Item `expected_target_hash`；create Item 检查 `target_id` 未被占用。Batch `source_draft_sha256` 与当前 `draft_sha256` 不同本身不阻止接受，只要逐项目标哈希仍一致。
4. 按依赖拓扑应用 create/update/delete；禁止按数组位置更新。
5. 校验 Workspace、稳定 ID、kind、名称、引用、实例类型、Evidence 和 Mapping。
6. 规范化 draft 并计算新 SHA-256。
7. 更新 `draft_json`、`draft_sha256`、`revision+1`。
8. 写 decision，更新 Item 状态和 `accepted_revision`。
9. 同一事务提交。

同一 idempotency key、同一请求体（`request_sha256` 相同）重复调用返回保存的 `response_json`；同键不同请求体返回 409 `IDEMPOTENCY_MISMATCH`。

失败请求整体回滚，不写任何状态。请求中任一 Item 的有效状态不是 `pending`（accept）时返回 409 `PROPOSAL_STALE` 或 `PROPOSAL_CONFLICT`，`error.items` 逐项说明原因。`stale/conflict` 按 §7.3 在读取时计算，从不持久化。PostgreSQL 并发测试必须覆盖：成功后 revision 已推进，再以同键串行重放和并发重放，均返回首次响应。

### 8.3 人工编辑

现有保存草稿 API继续使用 revision 乐观锁，并同步更新 `draft_sha256`。人工编辑某 target 后，以旧 target hash 为前提的 pending Proposal 在读取时自然呈现为 stale（§7.3）；保存请求不扫描、也不改写任何 Batch。

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
  "current_version_number": 14,
  "next_version_number": 15,
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

1. `modeling_sessions` 增加 `UNIQUE (workspace_id, id)`；新增 identity、`proposal_batches`、`proposal_items`、`proposal_item_dependencies`、`proposal_decision_requests`、`proposal_decision_items` 及索引；`materials` 增加 `archived_at`、`archived_by`；
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
- Material quote 和结构化数据样例属于敏感内容；非成员与只读本体服务令牌不得读取。Ossie 导出分两种投影：公开投影不含 `ontology_mappings`，且 `ai_context.ontofoundry` 中去掉 Material Object/Link 与所有 Evidence；完整投影只返回给 `can_read_mappings` 为真的主体（成员且会话登录，或服务令牌带 `mappings:read`/`instances:read`）。REST 导出、MCP、presentation 和任何缓存都调用同一个按主体裁剪的函数，不在各处各自过滤。T3 前必须有越权读取的回归测试。
- Action Definition 不意味着执行授权；本阶段无执行端点。
- JSON 中的 Workspace/Version 声明不能代替数据库归属校验。

## 13. 实施顺序

必须按以下顺序，保持每一步可回归、可部署：

### T0 — 锁定现有行为

- 为完整结果替换、候选接受、会话 revision、三方发布、预览差异补 characterization tests。
- 在 PostgreSQL 增加两个并发发布用例，不只跑 SQLite。

**状态：已完成（2026-09-29）。**

- `apps/api/tests/test_t0_characterization.py`：候选接受与原子回滚、revision 过期、运行中禁止编辑、预览、发布后基线推进、冲突发布不留版本、`resolve-merge` 过期拒绝。标注 `KNOWN GAP` 的两条（运行中禁止编辑 → T3/T4；预览对比未合并草稿 → T6）是目标设计有意改变的行为，对应阶段必须显式修改这些测试，其余测试在 T1–T8 中必须保持通过。
- `apps/api/tests/test_t0_postgres_publish.py`：真实 PostgreSQL 上两会话并发发布——独立修改都成功且版本号 1/2/3 连续、指针指向最新；同字段修改恰好一个成功、失败方不留孤立版本。每条测试使用独立临时数据库。已做变异验证：去掉发布时 Workspace 行锁后测试失败。
- 运行：`make test-pg`（默认连接 `127.0.0.1:55432` 的一次性容器，见测试文件头部说明）。

### T1 — v2 领域模型与兼容读取

**状态：已完成。** v2 模型、`read_snapshot` 边界、算法 B 哈希与测试向量、Ossie 扩展 v3、前端 `lib/draftView`；结果合同见评审交付物文档，codex 复审通过（92/100）。

**评审交付物：** [`ontofoundry.proposals/v1` 结果合同](./2026-09-30-proposal-contract-v1.md)（Schema、ID 分配、证据规则、指纹向量、Action 表达式语言及实施中定稿的差异）。

- **先交付并评审**：`ontofoundry.proposals/v1` 与 v2 元素的 Draft 2020-12 JSON Schema（按 `target_kind` 的 `oneOf`），每个 target kind 至少一组 create/update/delete 正例和反例；Action `effects[].expression` 的语言与求值上下文在此一并定稿（首期建议只允许引用输入参数与 `input_type` 属性的受限表达式，不可执行）。评审通过前不写 T1 代码。评审时必须同时定稿：
  - Manual Evidence 回显：Agent 的 update `after` 可以原样回显 `before` 中已有的 `kind=manual` Evidence，服务端接受时保持这些条目不变；Agent 新增或修改任何 `manual` 条目才整份拒收。
  - Item `fingerprint` 的 JSON 投影：`{"operation", "target_kind", "target_id", "after"}`，其中 `after` 按算法 B 规范化为单个元素、`null` 保留为 `null`；附固定测试向量。
  - 扩展 v3 上线时可读白名单为 `("1", "2", "3")`，v1/v2/v3 各冻结一份导出样本。

- 新增 RuleDefinition、ActionDefinition、Evidence/来源字段和 v1→v2 规范化适配器。
- 编译、导入、导出和 Diff 支持 v2；不改历史快照。
- 测试 Rule ID 稳定、Action 扩展往返、legacy Ossie 往返。

### T2 — 数据库迁移、哈希与固定上下文

**状态：已完成。** Alembic `20260930_000001`（PostgreSQL 上验证升级、约束、降级、再升级与同 id 跨类型中止）、身份登记、会话哈希、运行清单、`ofrun.*` 运行凭据、材料归档与 `MATERIAL_IN_USE`。

- 新增 identity/proposal/decision/dependency 表、`materials.archived_at/archived_by`。
- 按 §4.5 实现规范化哈希函数，回填 Session base/draft hash。
- 在 PostgreSQL 验证唯一约束、复合外键、upgrade/downgrade。
- 固定上下文：run manifest（base version/hash、source revision/draft hash、材料 ID/hash）；MCP 版本化读取响应带 Workspace/Version/SHA；BFF 按 Session 注入并拒绝其他 Workspace/Version；Ossie 公开/完整投影与越权测试。以上是 T3 的准入条件。

### T3 — Proposal 结果契约与消费

**状态：已完成。** `modeling_result_contract` 开关、提案提示词与上下文文件（含元素哈希、Schema、MCP 凭据）、原子入库与幂等、同目标旧提案 superseded、拒收时交回修复或保留失败批次。

- 按 T1 已冻结的 `ontofoundry.proposals/v1` Schema 实现解析、版本协商、引用解析、确定性 create ID、指纹和原子落库；T3 不重新设计 Schema。
- generation guard、run token 校验；结果只入库为 Batch，绝不写 draft；运行期间草稿变化只影响各 Item 的有效状态。
- 新运行通过 feature flag 选择 proposal contract；旧活动 run 继续兼容。

### T4 — Proposal API 与接受事务

**状态：已完成。** 批次列表/详情、决策事务（幂等先于 revision、依赖闭包、完整草稿校验、身份检查），PostgreSQL 并发重放与竞争测试已做变异验证。

- 实现列表、详情、accept/reject/restore。
- 完成依赖拓扑、批量原子性、幂等键和 target hash 冲突。
- 保存草稿同步计算 hash，人工修改使旧 Proposal 过期。

### T5 — 工作台 Proposal UI

**状态：已完成。** 提案/本体草稿/语义图谱三页签、提案卡片与详情抽屉、依赖组接受、过期与冲突状态、草稿变更标记；已在运行中的应用上验证。

- 替换完整草稿结果展示主流程。
- 接受、拒绝、恢复、依赖、stale、Evidence 和错误状态都有前端测试。

### T6 — 发布预览与双重乐观锁

**状态：已完成。** 预览即发布的 B/L/D 合并、结构化冲突与 latest/draft/custom/both 解决、`PREVIEW_OUTDATED`；发布页三页签与冲突解决器，已在运行中的应用上完成“预览过期→解决冲突→发布”全流程。

- 预览改为真实 B/L/D merged snapshot。
- 发布请求增加 expected current version 与 merged hash。
- 冲突解决按元素/字段呈现，解决后强制重新预览。

### T7 — MCP 扩展与验收

**状态：已完成。** `get_ontology_manifest`、`list_ontology_elements`、`get_ontology_elements`，权限裁剪一致；运行凭据只读固定版本。

- 固定上下文的安全部分已在 T2 完成；此处补 `list_ontology_elements` 分页、按 kind 查询等性能与易用性改进。
- 端到端验收：真实 DataAgent 运行只能读到本 Session 固定的 Workspace/Version/Draft/材料。

### T8 — 切换与清理准备

**状态：已完成。** 默认合同改为 `proposals`；`GET /proposal-metrics` 提供旧路径在途运行数、批次失败率、过期率与决策统计；清理步骤另见 [旧路径清理提案](../plans/2026-09-30-legacy-full-result-cleanup-proposal.md)，本任务未删除任何旧字段或代码。

- 新 run 默认只生成 Proposal。
- 观测旧活动 run 清零、失败率、stale 率和决策结果。
- 停止生成完整替换结果，但保留读取兼容。
- 单独提出后续删除旧字段/代码的迁移，不在本任务中直接删除。

## 14. 测试与验收矩阵

### 14.1 领域与 Proposal

- 每个 target kind 的 create/update/delete。
- Create client_ref 重试分配同一 UUID。
- Update/delete 的目标哈希不匹配呈现 stale、目标缺失呈现 conflict，且不落库。
- Rule owner 不存在、owner=workspace、Action 引用不存在 Rule 均拒绝。
- Proposal 依赖缺失、跨 Batch、成环、部分接受均拒绝。
- “新增 Object Type → 新增 Property → 新增 Link Type”三级 create 依赖组：接受前全部为 pending，整组原子接受成功；拒绝根 Item 后其余呈现 conflict；API 与 PostgreSQL 事务测试都覆盖。
- 同幂等键同请求返回保存的首次响应；同键不同请求 409 `IDEMPOTENCY_MISMATCH`；一次请求含多个 Item 时逐项写入 `proposal_decision_items`。
- 失败请求不写任何 Item 状态；stale/conflict 由读取时的哈希比较得出。
- 只读本体令牌读取 Ossie、MCP、presentation 时看不到 Material Object/Link、Evidence 和 mapping。
- 接受失败不改变 draft、revision、Item 状态。

### 14.2 材料与实例

- Evidence Material 跨 Workspace、SHA 不匹配、quote 不匹配均拒绝。
- 被 Proposal/草稿/版本引用的材料不能物理删除。
- Material Object/Link 随版本固定；Mapped Object/Link 随源库变化但固定 Mapping。
- 两类同名实例不自动融合。

### 14.3 会话与运行

- Session 固定 base version/hash；Workspace 后续发布不改变它。
- Run 固定 revision/draft/material manifest。
- 运行期间人工编辑某元素后，结果 Batch 中以该元素为目标的 Item 呈现 stale，其余 Item 仍可接受；改回原值后恢复 pending；草稿不被覆盖。
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
apps/api/src/ontofoundry_api/main.py
apps/api/src/ontofoundry_api/services/errors.py
apps/api/src/ontofoundry_api/api/ontology.py
apps/api/src/ontofoundry_api/api/assets.py
apps/api/src/ontofoundry_api/services/ontology_query.py
apps/api/src/ontofoundry_api/services/instance_query.py
apps/api/src/ontofoundry_api/services/access.py
apps/api/src/ontofoundry_api/services/workspaces.py
integrations/dataagent/skills/md2ossie/
apps/web/src/api/types.ts
apps/web/src/api/client.ts
apps/web/src/hooks/useModeling.ts
apps/web/src/components/ModelResults.tsx
apps/web/src/components/ReleaseReview.tsx
apps/web/src/pages/BuilderPage.tsx
apps/web/src/pages/DeliveryPage.tsx
```

后端新增唯一的快照读取边界 `read_snapshot(record) -> OntologyDraftV2`（v1→v2 规范化在此完成），查询、统计、Diff、实例、presentation、MCP 和合并全部经由它读取；禁止各服务自行判断 v1/v2 或直接读 `snapshot_json` 的嵌套字段。前端影响面见前端合同 §7。

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
