# Ossie 原生化与无损往返实施方案

日期：2026-10-08 · 分支：`feat/ossie-native`（基于 `demo/2026-10`）

## 1. 原则

1. **Apache Ossie 是模型的规范层**（固定版本 `ossie/assets/vendor/apache-ossie`：`ontology/ontology.json` +
   `core-spec/osi-schema.json`）。Ossie 能表达的构造，平台必须原生、无损承载。
2. **只有 Ossie 表达不了的需求才扩展**，且只放在 Ossie 允许的扩展点：文档级 `ai_context` 的附加键
   `ontofoundry`；语义层的 `custom_extensions`（`vendor_name="ONTOFOUNDRY"`，`data` 为 JSON 字符串）。
   扩展对其他工具可以有损；**不得为平台方便改写 Ossie 原生构造**（例如把多元关系拆成二元）。
3. **只有一种标准导出**，由唯一草稿编译，不设"源文件版"。
4. 本轮**不考虑权限裁剪**（后续单独设计）；导出即完整导出。

## 2. 现状差距

| # | 差距 | 类型 |
| --- | --- | --- |
| G1 | 导出覆盖文档级 `ai_context`（instructions 写死、synonyms 换成空间描述）→ 原同义词丢失 | 违反原则 |
| G2 | 发布时以工作空间 name/description 覆盖 Ossie 文档的 name/description | 违反原则 |
| G3 | 只支持二元关系；`roles` ≥ 2 的关系被跳过（A 6 条、B 8 条） | 能力缺失 |
| G4 | 语义模型被精简重建：dataset 描述/ai_context/字段 datatype、计算字段、复合键连接、未绑定对象的 dataset、metrics、模型级 ai_context 丢失（B：41 dataset、371 field、14 join 其中 13 复合键、27 metric） | 能力缺失 |
| G5 | 概念映射只支持"单表 + 单键 + 属性→列"；referent mapping、多根、递归树、SQL 表达式丢失 | 能力缺失 |
| G6 | Ossie 中出现了但平台未建模的构造被静默跳过（导入报告只是告知） | 违反原则 |

## 3. 目标数据模型（草稿 schema v3）

读时迁移 v1 → v2 → v3，历史行不改写（沿用 `domain/snapshot.py` 的做法）。所有新元素有稳定 UUID
（导入时 `uuid5(workspace, 作用域路径)` 确定性生成），纳入 `ontology_element_identities`。

### 3.1 文档层

| 字段 | 说明 |
| --- | --- |
| `ossie_name: str \| None`、`ossie_description: str \| None` | Ossie 文档自己的 name/description；导入文档保留空字符串与字段缺省原样；**回落到工作空间信息仅用于平台新建的文档**（G2） |
| `ai_context: str \| dict \| None` | 原样保存导入的 AIContext（字符串或对象，含其他厂商附加键）；**输入中已有的扩展原文独立保存**。导出时合并平台扩展；键碰撞时记录原值与本次新增内容，逆转换只撤销本次新增或覆盖的部分（G1） |
| `ontology_requires` | 已有，保持 |

### 3.2 概念与关系层

- `object_types` 保持（EntityType）。**新增 `value_types[]`，完整保存所有 Ossie `ValueType`**：
  `{id, concept, description, extends[], identify_by[], requires[], derived_by[]}`，不从属性推断。
  关系的所属概念（owner）可以是 EntityType 或 ValueType；继承与角色引用支持内置概念（`Integer`、`Date`…、`Any`）。
- **原生保真规则**（适用于所有 Ossie 原生节点）：记录每个字段**是否出现**（不出现 ≠ 空值 ≠ 默认值）与数组位置；
  `identify_by`、`extends` 等保存有序引用；**取消规范外限制**（如表达式 480 字上限），不改写原生字符串，
  **导入时不推断缺省**（不补读法、不补基数、不排序）。现有 compiler 的排序与补全只用于平台新建、从未出现过该字段的元素。
- `properties` 保持（= 所属概念到值概念的二元关系）。
- **`link_types` 统一承载一元、二元与多元关系**（不新增并行集合）：
  - 显式 `owner_ref`（隐含首角色：所属概念，EntityType 或 ValueType）+ `roles: list[RoleRef]`（**附加角色**有序列表，可为空=一元关系）；
    `RoleRef = {id, name: str|None, concept: {kind: "object_type"|"value_type"|"builtin"|"any", ref: UUID|str}}`。
  - **端点兼容视图**（`source_type_id`/`target_type_id`/`target_role_name`）仅对"可表达的二元关系"提供；旧的一对多关系
    在迁移时保留其方向对应（不翻转语义）。多元/一元关系的兼容视图为空，旧代码路径对其显式只读。
  - `multiplicity` 允许缺省（不推断）；`verbalizes` 保留 `{concept:role}` 原文。
  - **提案合同**：`roles` 内可嵌套 `client_ref`；合并时**角色内容与角色顺序分别合并**（现有 merge 对换序无冲突的问题需修正）；
    实例的角色值覆盖隐含首角色，并按角色概念校验类型与基数。
- `rules`：已原生（`requires`/`derived_by`），owner 可为多元关系。
- `material_links`（文档实例关系）新增 `role_values: list[{role_id, object_id|null, value|null}]`
  承载 n 元事实；二元保留 `source_id/target_id`。

### 3.3 语义与映射层（OSI 原生，`ontology_mappings[]` 一组一个模型）

| 集合 | 字段（与 osi-schema 一一对应，另加 `id`、父 id、`position`） |
| --- | --- |
| `semantic_models` | `map_name, map_description, name, description, ai_context, custom_extensions[]` |
| `datasets` | `semantic_model_id, name, source, primary_key[], unique_keys[[]], description, ai_context, custom_extensions[]` |
| `dataset_fields` | `dataset_id, name, expression{dialects[]}, dimension, label, description, datatype, ai_context, custom_extensions[]` |
| `dataset_relationships` | `semantic_model_id, name, from, to, from_columns[], to_columns[], ai_context, custom_extensions[]` |
| `metrics` | `semantic_model_id, name, expression{dialects[]}, description, datatype, ai_context, custom_extensions[]` |
| `concept_mappings` | `semantic_model_id, concept_id` |
| `mapping_nodes` | `concept_mapping_id, parent_id, slot, kind, relationship, concept, expression, position` —— 递归树原样。`slot` 区分 `object_mappings`、`link_mappings`、`object_mapping`、`children`、`referent_mappings`；link 节点必有一个 object 子节点，referent 节点必有 relationship；`concept` 引用支持内置类型 |

- **数据源连接**：dataset 只存 Ossie 的 `source`；平台连接别名放模型级
  `custom_extensions(ONTOFOUNDRY).connection_alias`（凭据仍在环境/连接配置，不进版本）。
- **现有 `mappings`（DataMapping）与 `link.data_join` 降为派生视图**：
  `mapping_view(draft, type_id) -> DataMapping | None` 只对"单 dataset、单键、字段为单列表达式"的概念返回；
  `join_view(draft, link_id) -> DataJoin | None` 对"两端都有 mapping_view、连接为同连接等值"的二元关系返回（支持复合键）。
  改造 `api/instances.py`、`services/instance_query.py`、会话/MCP 投影与演示脚本使用视图；视图只检查查询所需字段。
  其余概念显示"复杂映射：暂只读"。映射表单的保存改为写入原生结构（`apply_mapping_view`）。
  v2 → v3 迁移把每条 DataMapping/data_join 转成 dataset + fields + concept_mapping 树 + dataset_relationship。
- **指标归属概念**不新增字段：由指标表达式引用的 dataset → concept_mapping 推导，返回**零到多个**概念，有歧义时标明。

### 3.4 平台扩展（Ossie 表达不了的）

| 内容 | 位置 |
| --- | --- |
| 中文显示名、标签、必填属性、规则 id/名称、Action、稳定 ID 注册表 | 文档 `ai_context.ontofoundry`（`version` 升为 4，含 `ids: {作用域路径: uuid}` 以便二次导入还原身份） |
| 概念级同义词/说明 | `ai_context.ontofoundry.concept_context: {稳定ID: {synonyms, instructions}}`，标注非标准 |
| 指标执行参数、默认过滤、可累加性 | 指标 `custom_extensions(ONTOFOUNDRY)` |
| 连接别名 | 语义模型 `custom_extensions(ONTOFOUNDRY)` |
| 文档实例、证据 | 只在平台，不导出（不属于模型） |

## 4. 分阶段计划

每阶段：全量测试（API、Web）+ lint 绿；A/B 两文件往返测试按阶段收紧断言；演示分支功能不回归。

| 阶段 | 交付物 | 验收 |
| --- | --- | --- |
| **P0 合同冻结** | ① 两份 schema 逐字段覆盖矩阵（每个属性 → v3 字段 / 扩展 / 不支持）；② 冻结完整 v3 数据模型、canonical 规则（领域字段 vs 原生 JSON）与哈希算法版本；③ v2→v3 迁移合同与会话切换事务；④ 导入遇到不支持的构造**拒绝并指明路径**（G6） | 矩阵覆盖全部 `$defs`；v3 模型与迁移有单元测试；P1/P3 不得以同一 v3 表示不同结构 |
| **P1 概念与关系** | ValueType、统一 `link_types`（owner_ref + roles，一元/二元/多元）、原生保真规则、`material_links.role_values`；导入/导出；提案合同（嵌套 client_ref、角色内容与顺序分别合并）；MCP 返回完整角色；前端关系目录/详情只读展示多元关系、图谱超边节点 | A 的 6 条、B 的 8 条多元关系往返等价；旧 v1/v2 快照读取与哈希回归；提案/合并回归 |
| **P2 上下文与扩展**（含快修 G1/G2） | 文档 `ai_context` 原样承载、Ossie name/description；扩展 v4 + ID 注册表；概念级同义词扩展（按稳定 ID）；MCP `search_ontology_types` 命中同义词并返回来源 | 同义词作用域正确；字符串形 ai_context 可逆；二次导入元素 ID 不变 |
| **P3 语义模型与映射树** | 3.3 全部集合（含 slot）；v2→v3 映射迁移；`mapping_view`/`join_view`；实例查询、邻域、MCP、演示脚本改用视图；映射表单写原生结构；「数据映射」增加「语义模型」只读页签 | **A、B 两文件无损往返**（第 5 节）；验收连接别名、键、双向邻域及映射编辑结果；问数演示链路回归 |
| **P4 指标查询** | 依赖 `sqlglot`；MCP `list_metrics`、`query_metric(metric_id, group_by[], filters[], limit)`：单 dataset、按字段表达式改写逻辑列、ANSI_SQL→目标方言、函数白名单、只读连接、超时/行数上限；多 dataset 指标只解释不执行 | B 中单 dataset 指标可执行，结果与手写 SQL 一致；越界表达式被拒绝 |

工作量：P0–P3 约 28–40 人日，P4 另 5–8 人日，另留迁移余量。

不在本轮：权限裁剪导出；跨 dataset 指标执行；复杂映射与语义层的可视化编辑（只读）；上游 Ossie 提案。

## 5. 无损断言

`原文件 → 导入 → 持久化 → 发布 → 导出`，导出结果：

1. 通过固定版本官方 schema 与平台语义 lint；
2. **仅剥离本次导出新增的平台扩展**（输入文件中已有的扩展，包括已有的 `ontofoundry`/`ONTOFOUNDRY` 条目，保留），
   并逆转已记录的转换（字符串形 AIContext 为挂扩展而转成对象、为扩展新建的空容器）后，与**原始 JSON** 相等：
   仅忽略对象键顺序；**数组顺序、缺省字段（不出现 ≠ 空值）、null、表达式文本全部保留**；
3. 二次 `导入 → 导出` 与第一次导出字节一致（幂等），且元素 ID 不变；
4. 编辑任一元素后再导出，只有预期字段变化。

测试：`apps/api/tests/test_real_ossie_roundtrip.py` 收紧为上述断言（当前为"差异分类"），并为两份 schema
每个 `$defs` 构造补最小用例；另补：缺省 vs 空数组、扩展键碰撞（输入已含 ontofoundry 键）、字符串形 AIContext、
并发编辑后导出、多元关系角色换序合并。

## 6. 影响面（主要文件）

后端（`apps/api/src/ontofoundry_api/`）：`domain/models.py`、`domain/snapshot.py`（v3 迁移）、`domain/canonical.py`
（注册新集合与有序数组）、`domain/instance_validation.py`、`ossie/importer.py`、`ossie/compiler.py`、`ossie/mappings.py`、
`contracts/proposals.py` + 生成 schema、`services/proposals.py`、`services/merge.py`、`services/element_diff.py`、
`services/identities.py`、`services/instance_query.py`、`services/ontology_query.py`、`api/mcp.py`、`api/connections.py`、`api/instances.py`；
新增 `services/metric_query.py`。前端（`apps/web/src/`）：`api/types.ts`、关系目录/详情、`components/OntologyGraph.tsx`
（超边）、`pages/MappingsPage.tsx`（语义模型页签）、映射表单写原生结构。

## 7. 风险

| 风险 | 对策 |
| --- | --- |
| 迁移集中、哈希变化导致活动会话提案失效 | **读取保持纯函数**（不在读时改写）；会话切换到 v3 通过 revision 校验的独立事务完成，隔离旧运行结果与提案；保留旧 pinned manifest 与旧哈希验证算法；三方合并的 base/latest/draft 统一先迁移再合并；旧 mapping 的 ID 不换 kind 复用 |
| canonical 哈希对原生 JSON 的改写 | **按路径区分"领域字段"与"原生 JSON"**：原生 JSON（AIContext、custom_extensions、表达式、unique_keys 等）保留 null、数组顺序与重复项；哈希算法版本化（`hash_algorithm` 字段），旧版本按旧算法验证 |
| `link_types` 结构变化波及面大（提案、合并、MCP、前端） | 二元兼容视图保持现有字段；按模块逐个切换并全量回归 |
| 实例查询依赖 DataMapping | `mapping_view` 派生保持接口不变 |
| 指标 SQL 安全 | 只读账号 + AST 白名单 + 单 dataset + 超时/行数限制；拒绝而非尽力执行 |

## 8. 实施方式

单写者：按阶段由 Codex 实施，Claude 评审每阶段 diff 并运行验收（全量测试 + A/B 往返 + 演示链路冒烟）。
阶段间不并行修改同一文件。完成后用
`/Users/guoruping/project/bigdata/onedata/skills/account-ossie-skill/assets/REDACTED` 与
`/Users/guoruping/project/bigdata/onedata/skills/arch-ossie-semantics/assets/REDACTED` 做最终验证。
