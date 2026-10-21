# 实例库：本体元数据与实体实例分开存储

日期：2026-10-21。状态：已确认，待实施。来源：用户 2026-10-21“明确区分两个存储边界”。

## 1. 背景

用户要求区分：

- **本体元数据仓库**：对象类型、属性、关系定义、规则、指标、数据集、映射、版本和提案。
- **实例库**：业务实体、属性值、关系实例和来源证据。
- 已在 MySQL、Doris 等业务系统中的数据不复制，通过数据映射按需查询源系统。

现状：

| 内容 | 存放位置 | 是否符合 |
|---|---|---|
| 本体定义、版本、提案 | 平台 PostgreSQL：会话草稿、版本快照、提案批次 | 符合 |
| 业务库中的实体 | 不复制，按映射只读查询源系统 | 符合 |
| 文档抽取的实例与关系实例 | core-1 草稿和版本快照中的 `material_objects`、`material_links`，与定义并列 | 不符合 |

后果：实例随本体显式发布进入版本，每个版本快照都携带全部实例；规模增长后存储、发布对比和 MCP 读取变慢，版本差异里混入大量实例变化；实例抽取 Workflow 上线后最先暴露。

## 2. 决定

| 编号 | 决定 | 状态 |
|---|---|---|
| IS-01 | core-1 移除 `material_objects`、`material_links`；实例及关系实例存入独立的实例库，按工作空间存储，通过 id 引用本体中的类型和属性。 | 已确认 |
| IS-02 | 不迁移已有实例：迁移时从会话草稿和版本快照中删除这两个字段，已有实例随之丢弃（用户 2026-10-21 确认，沿用“不为旧数据做兼容”）。切换清单见 §6。 | 已确认 |
| IS-03 | 业务库中的实体不复制，平台不建实体索引：Entity Resolver 直接只读查询源系统，数据始终最新；实测某张表过慢时，再单独评估为该表建“业务主键 + 标题列”索引。 | 已确认（2026-10-21） |
| IS-04 | 实例的生效时机：实例（含关系两端）能按当前已发布版本完整校验通过时，接受即生效；依赖本会话尚未发布的任何定义（新类型、已有类型上的新属性、改动过的属性或关系）时，接受后为“待发布”，发布时按合并后的模型统一校验再生效。 | 已确认（2026-10-21，按 Codex 评审细化） |
| IS-05 | 本体发布时如删除或改动被实例引用的类型、属性或关系，发布预览列出受影响实例，发布被阻止，需先处理实例（删除或改为其他类型）。不自动删除、不自动改写。检查放在共享发布服务中，覆盖会话发布与元素详情保存两条通路；预览记录受影响实例集合的版本，接受新实例使预览失效。 | 已确认（2026-10-21） |
| IS-08 | IS-05 中的“改动”只指影响实例解释的变更：删除类型、属性或关系，修改属性英文标识或值类型，修改关系端点；改描述、同义词、显示名不阻止发布。其他会话的待发布实例不阻止本次发布，在其会话发布时再校验。 | 已确认（2026-10-21，Codex 推荐） |
| IS-09 | 固定历史版本读取实例：实例是实时数据，读取时按所用版本校验；与该版本不兼容的实例不返回，响应注明“已过滤 N 条与本版本不兼容的实例”，不用旧定义解释新值，不做实例快照。 | 已确认（2026-10-21，Codex 推荐） |
| IS-10 | 只有显式“放弃会话”操作才丢弃该会话的待发布实例；取消任务、关闭页面、切换会话均保留。放弃需二次确认，重复放弃无副作用，写审计记录。 | 已确认（2026-10-21，Codex 推荐） |
| IS-11 | 实例并发：实例自身带 revision，接受、撤销提案时按实例 revision 做比较更新；实例、关系、证据、历史与提案决定同一事务提交。 | 已确认（2026-10-21，Codex 评审） |
| IS-06 | 实例不产生本体版本；每条实例保留修改历史（谁、何时、因哪条提案、改前改后），用于审计和回溯。 | 已确认 |
| IS-07 | 证据单独成表，按材料可查；结构沿用现有材料证据与人工证据（材料 id、内容哈希、行号、引用原文；人工证据的作者与时间），校验规则不变。 | 已确认 |
| IS-12 | 命名：原“事实”统一称“实例”——文档实例（从文档抽取、经审阅、带证据，存于实例库）、数据库实例（按映射实时查询，不复制）、关系实例；原“事实抽取”称“实例抽取”。“事实”易被理解为已核实为真，证据只说明出处。界面文案在实例库分离时一并修改；现有代码英文名（`material_objects`、`fact_revision` 等）不单独改，新表直接使用 instance 命名。 | 已确认（2026-10-21） |

## 3. 存储

| 表 | 主要字段 | 说明 |
|---|---|---|
| `document_instances` | id、workspace_id、type_id、values（JSON）、state（staged／active／deleted）、session_id（staged 时）、revision、created_by／at、updated_by／at | 一条文档实例；state、revision、作者与时间是平台生命周期与审计信息，不属于本体语义 |
| `instance_links` | id、workspace_id、link_type_id、source_instance_id、target_instance_id、state、session_id、revision、时间与作者 | 一条关系实例 |
| `instance_evidence` | id、owner_kind（instance／link）、owner_id、kind（material／manual）、material_id、material_sha256、line_start、line_end、heading、quote、note、created_by／at | 来源证据；material_id 建索引 |
| `instance_history` | owner_kind、owner_id、revision、operation、before、after、proposal_item_id、actor、at | 只追加；`(owner_kind, owner_id, revision)` 唯一 |

删除实例为软删除并写历史；关系实例随两端实例删除而失效。

## 4. 流程变化

- **提案链路**：实例仍由抽取运行产生提案、人工审阅。运行上下文除固定草稿外附带“实例基线”（本次可能更新的实例及其 revision/hash）；`show_element`、本地 `check_part`／`prepare_result`、服务端结果解析、有效状态计算、接受与撤销都改为从实例基线定位实例目标并生成 before/hash。混合批次（定义 + 实例）在同一事务内接受。
- **重复实例审阅**：现有 `fact_revision` 保持“修订待审提案”的职责（把待审的新增实例提案改为对已有实例的更新提案，原提案 superseded），返回值不变；实例的实际写入只发生在提案接受事务内。另需的直接编辑入口另行设计。
- **接受**：按 IS-04 写入 staged 或 active，按 IS-11 做并发校验，校验引用的定义和证据。
- **发布**：版本快照只含定义；共享发布服务按 IS-05 检查，并把本会话 staged 实例按合并模型校验后转为 active。
- **读取**：MCP `search_objects`、`get_object` 与 REST 实例接口读 active 实例，按 IS-09 处理固定版本；权限不变（无实例权限不能读实例和证据）。staged 实例只在所属会话的审阅与管理界面中可见。分页游标绑定实例集合的变更序号，实例变化后旧游标失效。
- **材料用量**：实例证据部分改查 `instance_evidence`；定义证据、提案、导入、运行清单及历史引用仍照原方式合并统计。已删除实例及实例历史中的证据仍阻止删除材料。

## 5. 切换清单（IS-02）

- 停止在途运行，失效旧运行的固定草稿（manifest 中的 `pinned_draft`）及未确认导入的转换结果；历史报告保留为审计内容。
- 删除字段后同步重算会话草稿哈希、基线哈希和版本内容哈希。
- 重启服务并清理读取缓存。

## 6. 契约与界面

- core-1 JSON Schema、Pydantic 模型、前端类型同步移除两个字段；实例另有读写模型并导出 JSON Schema。
- Ossie 导出：实例原本就不进入 Ossie 语义层，导出器移除对快照实例的读取。原生完整包本期不含实例，实例导出另议。
- 界面：文档实例页、实例页、提案详情和发布面板改为读实例库；版本对比不再显示实例变化，实例变化看实例历史。

## 7. 影响范围

后端：`domain/core.py`、`domain/models.py`、`domain/validation.py`、`domain/instance_validation.py`、`domain/dependencies.py`、`api/proposals.py`、`services/fact_revision.py`、`services/instance_query.py`、`services/material_usage.py`、`services/mcp_ontology.py`、`services/ontology_query.py`、`services/public_projection.py`、`services/demo.py`、`adapters/ossie/exporter.py`、契约与 Schema。

前端：`api/types.ts`、生成的 `core.generated.ts`、`lib/coreModel.ts`、`DocumentMaterials`、`ModelResults`、`TranslationReport`、`ElementInspector`、`ElementInstances`、`ProposalDetail`、`reviewMeta`、`PublishPanel`。

建模 Skill：实例片段（`05-facts`）、`show_element`、`check_part`、`prepare_result` 与 `check_result` 按实例基线调整，拆分 Skill 时归入 entity-extraction。

概念文档：同步更新 `docs/concepts/evidence-and-instances.md` 中实例的存储、读取和原生包范围。

## 8. 不做

- 不复制业务库实体，不做跨来源实体合并。
- 不为实例建版本快照，不做实例的分支或三方合并。
- 不迁移已有实例。
