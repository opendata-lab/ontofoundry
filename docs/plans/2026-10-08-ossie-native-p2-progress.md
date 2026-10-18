# P2 上下文与扩展实施进度

> **已被 core-1 主设计取代。** 本文记录 2026-10-08 方案及当时的进展，保留作历史参考；现行模型与实施以 [core-1 主设计](../design/2026-10-14-core-model-and-format-adapters.md) 为准。

基线：2026-10-09，P1 评审提交 `6174500`，worktree `ontograph-ossie-native`，分支 `feat/ossie-native`。

范围：方案 P2、3.1/3.4 与覆盖矩阵；只修改本 worktree，不提交、不启动服务、不 make build、不访问演示目录。保留原生构造、旧版本读取和现有 DataMapping/data_join 路径。

## 核对与里程碑

P1 已完成：文档 ai_context 原样保存（字符串/开放对象）；导入的 Ossie name/description 与字段出现状态独立承载，只有平台新文档回落工作空间名称。v3 已冻结 PlatformExtensionV4、ConceptContext、ExtensionEdit 字段，不新增同一概念的第二份持久化真相。

待补缺口：v4 导出目前有条件启用；概念上下文未导入/导出；嵌套 object_mapping 的注册路径与解析路径不一致；扩展键碰撞与字符串转换缺少统一逆转换/冲突验证和 UI 提示；概念同义词未接入编辑/提案；MCP 未检索文档、概念及语义层同义词。

计划：

- M1：统一 v4 扩展、完整稳定 ID、原扩展保留与可逆碰撞/字符串转换，A/B 严格无损及二次身份测试。
- M2：概念平台上下文编辑、提案与保存作用域/并发保护，前端非标准提示。
- M3：MCP 同义词来源/歧义、语义层查询候选与两处智能体提示词，最终全量回归。

当前测试：P1 评审基线 507 passed / 1 skipped；Web 26 files / 123 tests。P2 尚未执行测试。

下一步：实施 M1，再运行 API 全量与 ruff；每个里程碑完成后追加实际测试数字、下一步及未决问题。

## M1 — 2026-10-09（扩展、身份与原文）

已完成：核对并保留 P1 文档 ai_context、Ossie name/description 行为。v3 标准导出统一添加 version="4" 与完整作用域 ID 注册表（实体/值概念、属性/关系、附加及隐含 owner 角色、规则、语义模型/数据集/字段/关系/指标、递归映射节点、Action/参数/效果）；路径转义 ~ 和 /，修正嵌套 object_mapping /0 路径不一致，兼容读取 P1 旧注册路径。导入恢复 ID，不依赖目标工作空间的 uuid5；owner ID 验证与关系稳定派生 ID 一致。concept_context 已按冻结字段导入/导出，并在合并导入时重映射稳定 ID。

已有扩展原文仍独立保存在草稿 ai_context，未知厂商版本不作为平台元数据解释；v3 不再拒绝这类开放上下文，冻结旧 v2 reader/导入合同保持不变。新增统一 write_extension/reverse_export_edits：仅覆盖本次平台拥有的键，记录 original/written/was_present；保留未知键、输入审计与 null/顺序/重复项；字符串或缺失容器可逆。外部修改已写入部分时明确报 EXTENSION_REVERSE_CONFLICT，不静默删除。二次无修改导出保留输入扩展及审计字节，不增加审计链。

验收：新增 API 12 项（A/B 跨空间 ID、8 种上下文/碰撞输入、逆转换冲突、特殊路径与概念上下文恢复）。A/B 导入→持久化→发布→导出仅撤销本次新增扩展后整体 JSON **0 差异**；二次导出 canonical 字节一致，A 6/6、B 8/8 多元关系原生节点保持。既有直接等于原文件的断言改为方案要求的严格可逆扩展断言；不泛化剥离输入扩展。专项含导入端点 **13 passed**。

全量：已有 PostgreSQL 服务仅创建/删除临时测试库，`cd apps/api && uv run --python 3.13 pytest -q`（设置隔离测试 URL）→ **519 passed, 1 skipped, 0 failures**（209.00s）；`uv run --python 3.13 ruff check src tests` **通过**。Web 在 M2 编辑接线期间基线全量仍 **26 files / 123 tests passed**；新增组件/适配专项继续验证。

下一步：M2 概念编辑/提案接受、作用域与并发校验，以及扩展碰撞 UI 提示。未决：MCP 同义词来源/语义层候选尚未实施；1 项 MySQL 外部测试无隔离环境。未提交、未启动服务、未访问演示目录或业务数据库。

## M2 — 2026-10-09（概念上下文编辑与提案）

已完成：复用冻结的 ConceptContext（synonyms 有序列表、instructions 可选说明）；实体和值概念均按稳定 ID 存入 extension_v4.concept_context。元素面板“基本信息”可编辑同义词（每行一项）及上下文说明，显式标注“平台扩展，导出到其他工具会被忽略”。值概念在目录提供上下文入口，原生值概念字段保持只读。编辑适配只投影上下文，回写时不在原生节点增加字段，不改 ai_context、语义模型或原生角色。新空空间从 API 获取 v3 草稿。

提案合同允许 object_type/value_type 的 after.concept_context（平台输入投影，null 可清除）；解析使用冻结模型校验后存入提案，接受时写唯一扩展字段，删除概念同步清理上下文。before 可携带正确的读取投影，原生元素哈希算法保持不变；服务端独立固定旧上下文并检查 stale，防止上下文单独人工改动被旧提案覆盖。保持证据校验与禁止智能体撰写人工证据。概念上下文差异进入发布预览及版本对比；三方合并按稳定 ID/字段合并，同义词换序冲突不吞掉。

元素保存只允许目标概念上下文变化，拒绝其他概念及注册表等扩展字段的越界编辑；沿用 revision/版本 CAS。合并导入保留输入未声明的本地上下文，但显式 v4 concept_context 空集合可清除输入概念的上下文。扩展覆盖生成导入说明与 PLATFORM_EXTENSION_COLLISION 非阻断预览警告；导入 UI 直接显示碰撞路径与“记录原值、可逆恢复”的说明。

新增 API **19 项**：SQLite/PostgreSQL 的实体/值概念元素保存、创建/更新提案接受→预览→发布→导出→跨空间导入；另覆盖保存作用域、独立上下文 stale/拒绝、字段/顺序合并、清除/删除、证据规则和显式空上下文导入。前端新增 **5 项**：实体和值概念编辑/回写保真，以及碰撞提示不藏在折叠说明中。

全量：临时 PostgreSQL 测试库下 `cd apps/api && uv run --python 3.13 pytest -q` → **538 passed, 1 skipped, 0 failures**（224.62s）；ruff **通过**。Web `npx vitest run` → **27 files / 128 tests passed**（4.77s）；`npm run lint`、`npx tsc -b` **通过**；`git diff --check` 通过。

下一步：M3 MCP 同义词检索/来源/歧义与建模、问数提示词，并做最终全量验证。未决：当前 MCP 仍未检索概念平台同义词和 B 的语义层同义词；1 项 MySQL 外部测试仍跳过。未提交、未启动服务、未访问演示目录或业务库。


## M3 — 2026-10-09（MCP、提示词与最终验收）

已完成：MCP search_ontology_types、get_ontology_type、list/get_ontology_elements 读取实体/值概念平台上下文，并增加文档、semantic_model、dataset、dataset_field、metric 的只读上下文候选。匹配返回 matches/source/value/scope_id/standard，列表及详情返回完整 synonyms/synonym_sources；文档同义词保留文档作用域，不自动复制给概念。概念扩展标注 standard=false；原生文档/语义层标注 standard=true。重复项和数组顺序不去重、不排序。多个候选返回 ambiguous；同技术名详情返回 candidates，不取第一个。沿用已有权限：语义层候选需要 mapping 读取权限，文档/概念上下文使用 ontology 读取权限。

问数系统提示词补充“优先按同义词定位概念/指标”，说明来源、作用域与歧义候选；建模提示词允许 after.concept_context.synonyms/instructions 的平台字段（null 清除、遗漏保留），不替换原生概念 name/description，不改变证据规则。MCP 仅查询原生语义层元数据，不提前实现 P3 派生视图或 P4 指标执行。

两份手工模型已在本地完成无损及编辑验证；原始素材与具体审计数据保存在仓库外。

MCP 示例（实际测试断言结果的字段摘录）：

```json
两份手工模型已在本地完成无损及编辑验证；原始素材与具体审计数据保存在仓库外。
```

扩展复核补充 **2 项**：不解释输入已有的 opaque vendor export_edits；新导出的 Action/规则元数据不包含平台 evidence（输入已有扩展原文仍保留），Action 所属规则也进入稳定 ID 注册表。前端再补 **1 项**值概念公开读取投影，避免丢失平台上下文。

最终全量：`cd apps/api && uv run --python 3.13 pytest -q`（使用已运行 PostgreSQL 上的隔离临时测试库；未访问业务库）→ **550 passed, 1 skipped, 0 failures**（267.76s）；`uv run --python 3.13 ruff check src tests` **通过**。`cd apps/web && npx vitest run` → **27 files / 129 tests passed**（4.52s）；`npm run lint`、`npx tsc -b` **通过**。覆盖矩阵生成检查及 `git diff --check` 通过。相较 P1 增加 API **43 项**、Web **6 项**。

A/B 验收：导入→持久化→发布→导出，仅逆转换本次平台新增/覆盖扩展后整体 JSON **0 差异**（不删除输入原有扩展）；二次导入恢复完整元素/角色/映射节点稳定 ID，二次未修改导出 canonical JSON 一致；A 的 6/6、B 的 8/8 多元关系原生节点不变。字符串 AIContext、未知厂商扩展、键碰撞、特殊作用域路径均通过可逆/身份测试。

下一步：P2 实施与验收已完成，待评审方提交。无新增 Alembic 迁移：复用 P0 已冻结的 extension_v4/concept_context 字段；旧快照读时迁移与哈希算法保持。未决：1 项 MySQL 外部测试因缺少隔离环境跳过；P2 无其他已知未完成验收项。未执行真实智能体建模或生产运行；未提交、未启动/重启服务、未 make build、未访问演示目录或业务库。已清理本次临时测试脚本与日志。


## M4 — 2026-10-09（评审修复：紧凑扩展与对外投影；已完成，下方保留初轮记录）

已完成实现：默认 ID 使用 uuid5(id_namespace, "ossie:" + RFC6901 作用域路径)，初次命名空间为 workspace UUID；导出只保留一个 id_namespace，从而跨空间也能恢复同一派生身份。ids 只写实际 UUID 与当前路径派生 UUID 不同的例外（平台新建、重命名、移动、换序），隐含 owner 仍从关系 ID 派生，Action/参数/效果/Action 规则已有显式 ID 不重复登记。兼容已有完整 ids 和 P1 旧路径。id_namespace 仅是开放 ai_context.ontofoundry 的导出元数据，不增加冻结快照字段或修改哈希算法。

显示名等于标准概念/关系名不写出；规则名称/技术名/说明等于导入默认值不写出；新扩展省略空集合与默认字段。源扩展已有的键在清除/覆盖时仍记录原值并可逆恢复，其他厂商原文不丢弃。字符串 AIContext 的逆转换合同保持。注册关系路径使用实际导出名，技术名未给出时与标准 name 回落保持一致。

对外读取统一 public_projection：MCP 搜索/详情/元素列表/元素详情/类型图及实例邻域、REST 类型查询/详情/类型图及实例邻域递归去除 native_presence、position、origin、map_presence、client_ref 等保真/解析字段；角色数组顺序、引用、读法、表达式、匹配来源/作用域、歧义与必要结构保持。文档 ai_context 的平台注册表/逆转换日志只用于导出，不进入公开上下文；用户实例 values、原生开放上下文及其他厂商数据中同名业务键保留。完整草稿编辑及固定建模上下文仍采用冻结原生合同，避免保存/提案/哈希回归。REST 显式 kind=metric/dataset/dataset_field/semantic_model 可读取对应上下文，默认目录集合保持；权限沿用 mapping 读取限制。

体积（同一仓库 A/B fixture、UTF-8 紧凑 JSON，包含逆转换日志；bytes）：A 原模型 18,588，修复前导出 69,774 / 扩展 51,171（175 条 ID），修复后导出 18,840 / 扩展 **237**（0 条 ID 例外）；B 原模型 163,092，修复前导出 495,932 / 扩展 332,825（1,460 条 ID），修复后导出 163,344 / 扩展 **237**（0 条 ID 例外）。缩进两空格的扩展均 **322 bytes**，仍小于 2KB。仅撤销本次扩展后 A/B 整体 JSON 0 差异。

当前测试：M4 专项初轮 62 passed / 2 failed（测试 fixture 缺少必需 verbalizes、旧断言假定导出空 concept_context 可清除），已修正 fixture，并显式验证输入 {} 清除、紧凑导出遗漏空集合保留本地上下文；重命名/移动/角色换序专项通过。Web 全量 **27 files / 129 tests passed**（13.88s），lint、tsc -b 通过；ruff 与覆盖矩阵检查通过。API 全量正在运行，最终数字待下方追加。

下一步：完成最终 API 全量，确认 MCP/REST 无内部字段、平台新建/重命名 ID 稳定与 A/B 体积上限，清理临时测试文件。未决：MySQL 外部测试隔离环境缺失；最终 API 验收未结束。未提交、未启动服务、未访问演示目录或业务库。


### M4 最终验收 — 2026-10-09

已完成 **7 项新增 API 回归**：新建/重命名/移动/角色换序后的例外 ID、旧完整注册表兼容、源扩展默认键省略且可逆/缺省与 null 冲突保护、平台关系缺少技术名时的实际导出路径、SQLite/PostgreSQL 的 MCP 与 REST 清洁投影/权限/原快照不变、业务 JSON 同名字段保留。已有 A/B 身份测试同时收紧为紧凑及缩进格式扩展均 ≤2KB、同空间与跨空间身份稳定、隐含 owner ID 稳定、严格逆转换 0 差异。Action 内显式 ID 不在 ids 中重复记录。

源扩展的空默认键也从当前载荷省略（原值只留审计），通过容器级 original/written 区分真正缺省与 null；若外部重新添加已省略键，逆转换明确报 EXTENSION_REVERSE_CONFLICT。旧输入原文和原审计仍全部恢复。P1 两条旧 MCP 测试不再要求角色的内部存储字段外泄，改为固定验证 id/name/concept 完整结构和所有角色的顺序；首次全量仅此两条旧合同断言失败（553 passed / 1 skipped），修正后专项 **9 passed**，扩展/身份专项 **19 passed**。

最终全量：`cd apps/api && uv run --python 3.13 pytest -q`（已有 PostgreSQL 上仅创建/删除隔离临时测试库）→ **557 passed, 1 skipped, 0 failures**（596.64s）；`uv run --python 3.13 ruff check src tests` **通过**。Web `npx vitest run` → **27 files / 129 tests passed**（13.88s）；`npm run lint`、`npx tsc -b` **通过**。覆盖矩阵生成检查与 `git diff --check` **通过**。

两份手工模型已在本地完成无损及编辑验证；原始素材与具体审计数据保存在仓库外。

下一步：M4 实施和验收完成，待评审方提交。边界：已发布版本的冻结产物与原哈希不改写，新发布产物使用精简扩展；输入已有大扩展的原文仍按 G1 保留在审计中，不能因体积删除。完整编辑草稿/固定建模上下文保持冻结合同，查询接口采用干净投影。未决：MySQL 外部测试因缺少隔离环境跳过，M4 无其他已知未完成验收项。已清理本次临时脚本与日志；未提交、未启动/重启服务、未 make build、未访问演示目录或业务数据库。
