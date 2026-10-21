# 事实仓库：本体元数据与实体事实分开存储

日期：2026-10-21。状态：已确认，待实施。来源：用户 2026-10-21“明确区分两个存储边界”。

## 1. 背景

用户要求区分：

- **本体元数据仓库**：对象类型、属性、关系定义、规则、指标、数据集、映射、版本和提案。
- **实体事实仓库**：业务实体、属性值、关系实例和来源证据。
- 已在 MySQL、Doris 等业务系统中的数据不复制，通过数据映射按需查询源系统。

现状：

| 内容 | 存放位置 | 是否符合 |
|---|---|---|
| 本体定义、版本、提案 | 平台 PostgreSQL：会话草稿、版本快照、提案批次 | 符合 |
| 业务库中的实体 | 不复制，按映射只读查询源系统 | 符合 |
| 文档抽取的事实与事实关系 | core-1 草稿和版本快照中的 `material_objects`、`material_links`，与定义并列 | 不符合 |

后果：接受一条事实即产生新本体版本；每个版本快照复制全部事实，规模增长后存储、发布对比和 MCP 读取变慢；事实抽取 Workflow 上线后最先暴露。

## 2. 决定

| 编号 | 决定 | 状态 |
|---|---|---|
| FS-01 | core-1 移除 `material_objects`、`material_links`；事实及事实关系存入独立的事实仓库，按工作空间存储，通过 id 引用本体中的类型和属性。 | 已确认 |
| FS-02 | 不迁移已有事实：迁移时从会话草稿和版本快照中删除这两个字段，已有事实随之丢弃（用户 2026-10-21 确认，沿用“不为旧数据做兼容”）。 | 已确认 |
| FS-03 | 业务库中的实体不复制，平台不建实体索引：Entity Resolver 直接只读查询源系统，数据始终最新；实测某张表过慢时，再单独评估为该表建“业务主键 + 标题列”索引。 | 已确认（2026-10-21） |
| FS-04 | 事实的生效时机：引用的类型都已发布时，接受即生效；引用本会话新建、尚未发布的类型时，接受后为“待发布”，随会话发布一起生效，会话放弃则丢弃。 | 已确认（2026-10-21） |
| FS-05 | 本体发布时如删除或改动被事实引用的类型、属性或关系，发布预览列出受影响事实，发布被阻止，需先处理事实（删除或改为其他类型）。不自动删除、不自动改写。 | 已确认（2026-10-21） |
| FS-06 | 事实不产生本体版本；每条事实保留修改历史（谁、何时、因哪条提案、改前改后），用于审计和回溯。 | 已确认 |
| FS-07 | 证据单独成表，按材料可查；结构沿用现有材料证据与人工证据（材料 id、内容哈希、行号、引用原文；人工证据的作者与时间），校验规则不变。 | 已确认 |

## 3. 存储

| 表 | 主要字段 | 说明 |
|---|---|---|
| `entity_facts` | id、workspace_id、type_id、values（JSON）、state（staged／active）、session_id（staged 时）、revision、created_by／at、updated_by／at | 一条文档事实 |
| `fact_links` | id、workspace_id、link_type_id、source_fact_id、target_fact_id、state、session_id、revision、时间与作者 | 一条事实关系 |
| `fact_evidence` | id、owner_kind（fact／link）、owner_id、kind（material／manual）、material_id、material_sha256、line_start、line_end、heading、quote、note、created_by／at | 来源证据；material_id 建索引 |
| `fact_history` | owner_kind、owner_id、revision、operation、before、after、proposal_item_id、actor、at | 只追加 |

删除事实为软删除并写历史；事实关系随两端事实删除而失效。

## 4. 流程变化

- **提案**：事实仍由抽取运行产生提案、人工审阅；提案格式中的事实部分保留，目标改为事实仓库。接受时按 FS-04 写入 staged 或 active，校验引用的类型、属性和证据。
- **事实修改**：现有 `fact_revision` 改为直接修改事实仓库并写历史，不再改草稿。
- **发布**：版本快照只含定义；发布时把本会话 staged 事实转为 active；按 FS-05 检查引用。
- **读取**：MCP `search_objects`、`get_object` 与 REST 实例接口读 active 事实；权限不变（无实例权限不能读事实和证据）。
- **材料用量**：按 `fact_evidence.material_id` 统计，不再遍历快照。

## 5. 契约与界面

- core-1 JSON Schema、Pydantic 模型、前端类型同步移除两个字段；事实另有读写模型并导出 JSON Schema。
- Ossie 导出：事实原本就不进入 Ossie 语义层，导出器移除对快照事实的读取。原生完整包本期不含事实，事实导出另议。
- 界面：文档事实页、实例页、提案详情和发布面板改为读事实仓库；版本对比不再显示事实变化，事实变化看事实历史。

## 6. 影响范围

后端：`domain/core.py`、`domain/models.py`、`domain/validation.py`、`domain/instance_validation.py`、`domain/dependencies.py`、`api/proposals.py`、`services/fact_revision.py`、`services/instance_query.py`、`services/material_usage.py`、`services/mcp_ontology.py`、`services/ontology_query.py`、`services/public_projection.py`、`services/demo.py`、`adapters/ossie/exporter.py`、契约与 Schema。

前端：`api/types.ts`、`lib/coreModel.ts`、`DocumentMaterials`、`ModelResults`、`TranslationReport`、`ElementInspector`、`ElementInstances`、`ProposalDetail`、`reviewMeta`、`PublishPanel`。

建模 Skill：事实片段（`05-facts`）的输出结构与合并脚本按新契约调整，拆分 Skill 时归入 entity-extraction。

## 7. 不做

- 不复制业务库实体，不做跨来源实体合并。
- 不为事实建版本快照，不做事实的分支或三方合并。
- 不迁移已有事实。
