# 数据集两种来源：基于表与基于表达式

日期：2026-10-20。状态：按 DS-01–DS-18 实施；2026-10-21 按“不靠猜测推断、能交给人工的交给人工”简化 DS-04、DS-06、DS-09、DS-18，§7 与 §9.3 中的推断和确认机制作废。§1 已确认决定是唯一依据；本文正文与[实施计划](../plans/2026-10-20-dataset-sources-plan.md)已统一。不调用外部模型或服务，不提交、不推送。

## 1. 已确认决定

| 编号 | 决定 | 确认日期 |
|---|---|---|
| DS-01 | 指标仍只引用单个数据集，主设计第 49 项的指标边界不变；跨数据集能力通过基于表达式的数据集承载。 | 2026-10-20 |
| DS-02 | 两种来源：基于表，选择一张已登记表或视图；基于表达式，保存一条只读 SELECT，允许 CTE、JOIN、UNION，绑定一个连接，只能引用已登记表或视图。用 sqlglot 解析及只读白名单，禁止多语句，不支持参数和跨连接，保存时以 LIMIT 0 探测列名、类型。与 Ossie Dataset.source 的 table/view/query 对齐。 | 2026-10-20 |
| DS-03 | 数据管理分数据表和文档两层底层材料；表和视图经全量或指定表同步才算登记，平台只能使用已登记表，也据此限制 Agent 上下文。数据集是建立在已登记表上的本体元素。全量同步改后台分批任务，展示进度和分批计时、失败批次可重试、完成部分先保存，去掉 200 张上限；指定表同步共用机制。 | 2026-10-20 |
| DS-04 | 目录为实体类型、值类型、关系、指标、数据集五个页签；“实体”改“实体类型”，“关系”不改名。值类型内容由并行值类型设计负责。数据集详情沿用元素详情框架，含基本信息（名称、英文标识、来源方式、连接、描述、快照日期列）、来源（表位置或 SQL 原文、校验结果）、列、少量数据预览、被引用（对象映射、关系映射、指标，实时推导）。表达式数据集在目录新建或由提案产生；数据管理只管表同步和文档。 | 2026-10-20 |
| DS-05 | 自动构建和 Ossie 导入共用生成、校验、审阅机制。建模 Agent 在单表不足时可提议表达式数据集及其指标，说明理由和证据，例如按各自业务日期 UNION ALL 销售和退款。Ossie query 来源直接对应；跨数据集指标依据 relationships 转换为表达式数据集和单数据集指标的待审阅项，不能确认安全的标待补全，不强行转换。 | 2026-10-20 |
| DS-06 | 平台不做重复计算静态推断，也没有风险确认关卡、校验指纹或确认参数（2026-10-21 简化，原“按主键静态检查并要求确认”作废）。平台只拦截能确定判断的错误：只读单条 SELECT、表已登记、同一连接、列可探测。连接粒度由审阅人看 SQL 判断；技能给出多事实表 UNION ALL、先聚合后连接、只向一端查维度的安全写法。 | 2026-10-21 |
| DS-07 | Agent 可依据材料提出未同步表上的数据集；提案显示“表未同步”，提供“去同步”（只同步该表）及“修改连接和表”，未处理时接受报错。同步或修改后，依赖的映射、指标自动重新校验，列不匹配标在对应提案。Agent 运行中不同步；暂不提供查表工具，后续可另议。 | 2026-10-20 |
| DS-08 | search_ontology、get_ontology 增加 dataset 类型，搜索名称、英文标识、描述、表名；详情给来源方式、表位置或 SQL、列、快照日期列及引用元素。改工具 Schema、说明及对应实现，不改问数提示词；保留四个只读工具和服务端版本固定机制。 | 2026-10-20 |
| DS-09 | 同轮完成 Ossie query 导入导出、字段 datatype 和 dimension.is_time 导出（从属性/列类型及时间用途推导），导入不与登记列类型比对，只在报告中逐字段写明“声明不保存，以登记列类型和指标时间字段为准”（RT-46，2026-10-21 简化）；接受与连接引擎一致的方言表达式。ontofoundry-extension.json 保存快照日期、指标时间字段、一元/多元原形及角色名以供往返；字段 label 继续丢弃并报告。同步维护例外表及逐条 RT。 | 2026-10-20 |
| DS-10 | 实例浏览、指标预览、MCP SQL 参考和问数 Agent 均把表达式数据集当子查询使用。 | 2026-10-20 |
| DS-11 | 不保存不支持的 Ossie 原始形态（一元关系、多元关系的原结构等），也不新增 exchange_shapes；这些按“已转换/不支持”报告即可。快照日期列、指标时间字段、角色名是核心字段，导出写入扩展文件、导入读回核心字段，无需额外存储。§4.2、§4.3、§9.4 中相关持久化作废。 | 2026-10-20 |
| DS-12 | 后台同步先简单做：保留同步任务和分批进度（显示进度、失败批次可重试、完成一批先保存一批），用进程内后台任务执行；服务重启时把中断的任务标为“已中断，可重试”。不做租约、多 worker 抢任务和过期重领。§6.1 相应部分作废。 | 2026-10-20 |
| DS-13 | U-01：数据集也采用 name（必填 ASCII 英文标识）+ display_name（可选中文名称），与实体类型、关系、指标一致；覆盖名称统一 N-01 中“数据集不变”的例外。不考虑旧数据。 | 2026-10-20 |
| DS-14 | U-02：Ossie 跨数据集指标只在证据足够时机械转换（主键已登记、连接方式与缺失匹配处理、时间口径都能确定）；否则保留原文、标为待补全，不要求扫描全表证明。 | 2026-10-20 |
| DS-15 | U-03：首版只支持非递归 CTE，普通 CTE、JOIN、UNION 都支持；WITH RECURSIVE 明确报不支持。 | 2026-10-20 |
| DS-16 | 数据集直接记住连接：Dataset 新增 connection_id（本空间已有连接，非凭据），与 schema_name/table_name 或 query_sql 一起保存，版本与提案自然携带；不采用 §4.2 的 platform_context_json / dataset_bindings / source_fingerprint 复制链，§4.2、§4.3 中相关持久化与 Alembic 作废。导出：纯 Ossie 不带连接；ontofoundry-extension.json 只带连接名称作为匹配提示（不带 id、主机、账号、凭据）；原生导出同样去掉 connection_id、保留连接名称提示。导入：按名称唯一匹配本地连接则自动选上（审阅可改），否则为“未绑定连接”，审阅时选择，未处理时接受报错，与“表未同步”同一套处理。修订主设计中“连接登记不进入 Dataset”的约定：连接 id 进入平台内的 Dataset，但不进入任何导出文件。 | 2026-10-20 |
| DS-17 | 首轮阅读压缩（与本设计一起实现）：表已登记为数据集时不再生成/上传“数据表结构”材料；工作包中的数据集改用紧凑写法（名称、表、列名 类型 注释），详细定义按指针回读；正例不重复附带依赖定义；SKILL、原则、方法入口、速查合并去重。目标：同规模首轮阅读 ≤22 KB。 | 2026-10-20 |
| DS-18 | 构建页“选择数据表”关联的是已登记的数据表，不是已有数据集：会话保存 linked_tables（连接、Schema、表），保存时校验属于本空间且已同步；`GET /workspaces/{id}/registered-tables` 列出已同步的表及其已被哪些数据集使用。建模运行时工作包只放关联表目录（编号 key、表名、注释、列数），完整列、主键和外键写入单独的 tables_file，Agent 用 `read_input.py <tables_file> --tables t1,t3` 按编号一次读齐，再在这些表上提议数据集；只按编号选表，不按表名猜连接（2026-10-21）。 | 2026-10-20（Claude 实现时按用户确认的分层修正） |

## 2. 依据、现状与覆盖关系

以 [AGENTS.md](../../AGENTS.md)、[核心设计](2026-10-14-core-model-and-format-adapters.md) §3.6、§3.7、§5–§7、第 49 项，以及 [数据集](../concepts/datasets-and-binding.md)、[指标](../concepts/metrics.md)、[查询语义](../concepts/query-semantics.md) 为基线。与 [名称统一](2026-10-20-display-name-unification.md)、[harness](2026-10-20-modeling-agent-harness.md) §11、[视觉一致性](2026-10-17-ui-visual-consistency.md)、[ToB 共识](2026-10-19-tob-ui-design-principles.md)、[引用导航](2026-10-19-element-reference-navigation.md)、[目录导航](2026-10-19-ontology-catalog-navigation.md) 衔接。

本文确认后覆盖主设计中“Dataset 仅表位置”、RT-63 拒绝所有 query、RT-69 拒绝所有跨数据集输入，以及数据管理展示数据集的旧安排。第 49 项的单数据集指标、不建数据集关系、不引用本体的原则保留；仅其 Ossie 输入处理路径由本文扩展。DS-13 覆盖名称统一中的 Dataset 例外。

| 现有位置 | 读取到的现状 | 本设计的落点 |
|---|---|---|
| domain/core.py | Dataset 是扁平登记，必填 table_name，无 query；映射仅存 dataset_id；三类指标均限单数据集 | 保持映射、指标的引用结构，增加 Dataset 来源判别 |
| api/assets.py | read_structure 全量超过 200 张拒绝，循环总预算 15 秒；一次成功才保存，RefreshRequest 也限 200；未区分 table/view | 服务层分批、持久化任务，逐批合并表级观察结果 |
| api/connections.py | /tables 和 table-material 直接访问实时库；选表不等于已登记 | 实时发现仅供人工同步选择；业务使用和建模取登记快照 |
| services/dataset_sources.py | 方言、Schema 隐式解析连接，多连接时报歧义 | 显式平台绑定一个连接，语义模型不携带凭据 |
| services/instance_plan.py、metric_query.py | 前者反射 SQLAlchemy Table，后者拼物理表位置 | 共用来源解析与子查询构造，不把 SQL 放进 table_name |
| services/mcp_ontology.py | Kind 不含 dataset；lookup 显式排除 dataset；已有授权、版本、分页和长字段分段 | 扩展原两工具的种类及投影，复用其余机制 |
| adapters/ossie/* | source 按纯表位置解析；字段只优先 ANSI_SQL；字段三项元数据一律损失；扩展已有角色名 | 增加 query、匹配方言和推导字段；保存核心时间字段和连接名称提示 |
| TypeCatalogPage、MappingsPage、DatasetPanel、DatasetPicker | 三个目录 Tab，数据管理是数据集/文档；详情缺 SQL、预览和完整引用分类 | 五 Tab、表/文档管理及统一数据集详情 |

同工作树存在大量并行编辑，以上是本轮阅读时的行为，不把它们当作本文已实现。harness 增量衔接现有接口，不恢复旧流程。指定的 `2026-10-20-value-types.md` 本轮读取时尚不存在；只约定值类型 Tab 的位置、计数和入口，内容、契约及 RT 由那份设计确认，合并前必须补读。

## 3. 概念来源与最小增量

Ossie 的依据是仓库 vendored `core-spec/osi-schema.json`，版本 0.2.0.dev0，PROVENANCE 固定提交 88e0011148283302c9a04cd0287e00e0b9d87354。其 Dataset.source **是字符串**，描述允许物理 table/view 或 query，并没有 table/view/query 三分支对象。平台仍只有两种用户来源，表和视图共用 table 分支，实际对象种类从登记元数据读取。

外部对照于 2026-10-20 核查：LookML 的 SQL derived table 用 SELECT 定义结果，查询时可作为 CTE 或 inline view；Cube 以 sql 定义来源查询，并有 sql_table 简写；Databricks metric view 可选择表状资产或 SQL 查询作为 source。仅借鉴“结果集可以成为来源”，不引入物化、刷新策略或其权限体系。[Looker 官方说明](https://docs.cloud.google.com/looker/docs/sql-experts-derived-tables)、[Cube 官方参数](https://docs.cube.dev/reference/data-modeling/cube)、[Databricks 官方说明](https://docs.databricks.com/gcp/en/uc-semantics/metric-views/basic-modeling)。

| 新增/调整项 | 来源；属于哪层 | 删除会失去什么；已有结构是否能表达 |
|---|---|---|
| Dataset.source_kind=table/query、query_sql | Ossie source 语义，形式参考 derived table；定义可复用结果集的来源，不是选更快表的执行提示 | table_name 不能诚实保存 SELECT，Metric.expression 不能代表明细结果；缺它不能统一映射与跨表指标 |
| table_name 改条件必填，query 分支为空 | 来源互斥的契约约束 | 同时允许表与 SQL 会出现两份相互矛盾的来源 |
| Dataset.display_name 与英文标识约束候选 | 平台展示元数据，沿用名称统一模式，待 U-01 | 只有现有 name 无法独立维护中文名和英文标识；description 不能替代名称 |
| Dataset.connection_id | 已有连接登记的显式引用，平台部署信息，不导出 | 仅靠方言/Schema 不能区分两套同名库；凭据仍只在 ConnectionRecord |
| validation 诊断、引用清单、SQL 叶子表血缘 | SQL AST、元数据和模型实时推导的读模型 | 不持久化核心；缺少响应会妨碍审阅，但已有定义可重算，无须再建核心关系 |
| 人工 warning 确认参数及校验指纹 | 平台审阅操作，执行设施 | 必须区分真正确认与普通点击保存；不加 Dataset.risk_accepted 或永久 safe 标志 |
| 同步任务、批次、耗时 | 平台后台任务，自创执行设施 | 单份 MetadataSnapshotRecord 不能表达中断恢复、批次失败或进度，必须持久化任务 |
| 表级 kind、观察时间、有序主键/外键观察 | 数据库 inspector 的元数据事实，平台登记层 | 支持 table/view 展示、部分新鲜度、复合键及外部关系核对；不新增核心主键概念 |
| datatype、dimension.is_time | Ossie 原生字段，从类型和已声明用途推导 | 输出可推导，无须把 Field 树、时间维度开关再存入核心 |

不引入参数、数据集级 relationships、递归数据集引用、指标连接表、物化模式、执行优先级、缓存策略或新的提案生命周期状态。SQL 虽有执行语法，其在这里定义数据集行集合和输出列；方言转换、超时、LIMIT 和驱动适配仍属执行层。

## 4. 模型、平台绑定与契约

### 4.1 Dataset 的推荐形状

为减少已有读写路径改动，沿用扁平结构，用判别字段和条件约束表达两个分支，不再嵌套一棵 source 树。

| 字段 | 基于表 | 基于表达式 |
|---|---|---|
| id、name、description | 沿用稳定 id、英文标识和说明 | 同左；SQL 改动不更换 id |
| display_name | 可选中文名称 | 同左 |
| source_kind | table；输出显式携带 | query，必须显式提供 |
| dialect | 可空用于未完成外部输入；就绪时必须与绑定连接引擎一致 | 同左；执行不允许 ANSI_SQL 冒充引擎 |
| schema_name | 沿用表命名空间，接受连接内完整限定 | 必须为空；默认命名空间放平台绑定，不让它兼作 SQL 默认 Schema |
| table_name | 非空，且解析为单个物理表/视图标识 | 必须为空 |
| query_sql | 必须为空 | 非空的一条 SELECT/集合查询，建议输入上限 64 KiB UTF-8，保留原文 |
| columns | 登记列元数据副本 | 保存/接受时由 LIMIT 0 探测生成的输出列元数据副本 |
| snapshot_date_column | 可选，必须为输出中的日期类列 | 同左；表示完整结果集的快照，不自动继承任一叶子表快照 |

JSON Schema 用两个互斥分支（oneOf）表达条件；Pydantic 同步验证互斥、字节长度、列名唯一和快照列引用，前端生成类型能按 source_kind 收窄。不让 table_name 留假表名，或让 query 分支的 schema_name 作为第二个位置来源。dialect 和 columns 在待审阅候选中可以缺失；**就绪的模型写入**必须补齐；“可形成提案”与“可接受进草稿”是两次不同的校验。

示意片段只表达来源差别，名称写法以 U-01 最终确认为准：

```json
{
  "source_kind": "query",
  "name": "trade_events",
  "dialect": "mysql",
  "schema_name": null,
  "table_name": null,
  "query_sql": "SELECT sale_no AS event_no, sold_on AS business_date, 'sale' AS event_kind, amount FROM mist_dw.mist_sales UNION ALL SELECT refund_no AS event_no, refunded_on AS business_date, 'refund' AS event_kind, amount FROM mist_dw.mist_refunds",
  "snapshot_date_column": null,
  "columns": null
}
```

此片段可作为未探测候选；不能把 columns=null 的候选写成已验证数据集。禁止在保存时信任客户端或 Agent 自报的列名、类型、已登记标记、校验通过标记。

### 4.2 数据集直接绑定连接

Dataset.connection_id 为本空间已有连接 id，可空表示“未绑定连接”；与来源、列一起随提案、会话、发布版本携带。服务层检查空间归属、映射权限、连接引擎和登记来源。凭据仍只在 ConnectionRecord，domain 不访问数据库或 HTTP。query 的未限定表使用连接默认 Schema。

导出任何格式均移除 connection_id。原生包和 Ossie 扩展只带 connection_name 名称提示，不带主机、账号、凭据；导入按本地连接名称唯一匹配，否则显示“未绑定连接”，人工选择后再校验。不使用额外绑定上下文或来源复制链。

### 4.3 存储与迁移

来源字段位于已有 JSON，无需新增本体存储列。新增 metadata_sync_jobs、metadata_sync_batches 及查询索引需要 Alembic。无旧数据兼容、哈希兼容或旧表形状规范化分支；若清理旧内容，新增与 20261016/20261020 相同边界的清理迁移，并记录清理范围。不保存不支持的一元、多元原形，不增加交换溯源结构。

### 4.4 契约改动清单

同时更新 `domain/core.py` 的 Pydantic、`contracts/ontofoundry.core-1.schema.json`、提案动态 Schema/`ontofoundry.proposals.v1.schema.json`、API 读写模型及 Schema、`apps/web/src/api/core.generated.ts`、`api/types.ts`。生成脚本继续作为核心前端类型来源。平台上下文、校验响应、任务响应属于 API 契约，不能混入 CoreDraft。

建议新增 `contracts/dataset_sources.py`、`contracts/metadata_sync.py` 并生成对应 API Schema，字段均 extra=forbid。核心结构检查可离线完成；连接、登记、权限和列探测由服务层完成。业务错误抛 ServiceError 子类，英文 code、中文 message，路由只校验、授权和转交。

## 5. 来源校验、探测与执行

### 5.1 统一流水线

表单、提案接受、Ossie 完成来源匹配、发布预检及所有实际平台查询共用同一服务；纯导出不访问业务库，不把序列化导出变成隐式同步或探测。

1. 校验核心形状及当前会话/版本，检查绑定、成员权限与数据源范围。
2. 用连接引擎选择 sqlglot 方言，完整解析 SQL；表来源也构造 AST 统一进入执行检查。
3. 遍历所有作用域、CTE、子查询和集合分支，解析真实叶子表、列引用与别名，核对登记。
4. 执行重复计算静态检查，给出可定位诊断及检查局限。
5. 已登记且获得授权时执行 LIMIT 0；通过后返回列、输出类型、静态警告和校验指纹。数据预览需额外实例权限和显式请求。
6. 保存/接受再次核对权限、来源指纹和元数据版本，重新探测；探测后用短事务写本体与绑定。若期间 revision 或登记指纹变化，拒绝并重做，不能拿旧结果提交。

LIMIT 0 在业务库执行，但不返回业务行，也不证明 SQL 成本为零；规划阶段仍可能耗时。发布预检重用最新且指纹一致的探测结果可作为后续优化，首版建议重复执行保证结果明确。

### 5.2 只读 SQL 规则

| 检查项 | 规则 |
|---|---|
| 单语句 | sqlglot.parse 严格返回一个非空查询；一个结尾分号可去掉，连续空语句、多语句、解析回退 Command 都拒绝，不能只取 parse_one 第一项 |
| 查询根 | SELECT，或由 SELECT 组成的 UNION/UNION ALL；支持非递归 CTE、派生子查询及安全窗口函数，内层与外层执行同一白名单 |
| 写入与副作用 | 拒绝 DDL/DML、CTE 内写入、SELECT INTO、INTO OUTFILE/DUMPFILE、FOR UPDATE/SHARE、锁、会话变量赋值、事务/管理命令、存储过程和执行型提示注释 |
| 函数 | 节点与函数双白名单，标量、聚合、日期、窗口逐引擎覆盖；未知 UDF、匿名函数、动态 SQL、文件/网络/外部表函数、序列修改、休眠/锁函数拒绝，不能因外壳是 SELECT 就放行 |
| 参数 | 拒绝 Placeholder/Parameter、绑定占位符、模板替换和会话变量；SQL 字符串字面量不按占位符文本误判。日期范围由消费方外层绑定参数添加，不改变数据集定义 |
| 来源 | FROM/JOIN 只允许作用域内 CTE、子查询或已登记表/视图；禁止直接引用另一核心数据集名作为隐式宏。常量分支或纯常量 SELECT 没有物理叶子表，仍须绑定连接、通过同一白名单和探测，不能旁路权限 |
| 限定与列 | 按引擎识别 database/schema/table 及引号大小写；未限定表只能落到本绑定默认 Schema，禁止沿未知 search_path 猜表；不明/歧义列明确报错 |
| 首版边界 | 递归 CTE、动态表、联邦/远端表函数及未列入白名单的方言构造报 SQL_UNSUPPORTED；不在不支持时换另一种业务算法。递归范围见 U-03 |

表类型与函数返回表类型不能混同。系统目录不因数据库可读而可用。普通注释保留原文显示，不参与执行授权；驱动执行的语句由已检查 AST 生成，禁止字符串拼接完整来源。重新生成执行 AST 必须保持 NULL、DISTINCT、过滤、分支顺序及集合语义，无法保证则拒绝，而非进行“有帮助”的改写。

物理方言映射固定为当前支持的 MySQL、Doris、PostgreSQL；Doris 不能仅用 MySQL 解析成功就宣称兼容，须验证自己的输出和执行。sqlglot 不认识或连接不支持的函数明确报错。新引擎接入不在本设计内。

### 5.3 “已登记”的精确含义

身份是 `(workspace_id, connection_id, database, schema, object_name)`，按引擎标识符规则比较；同名表在别的连接已同步不能满足条件。全量或指定表同步成功并保存了该表结构，且最近一次确定性存在性观察未标为已移除，才算登记；任务正在排队、实时 /tables 列得出名字、材料里提过、Dataset.columns 自带列，都不算登记。

AST 必须做作用域解析。例如 `WITH mist_sales AS (SELECT ... FROM mist_dw.mist_sales)` 中 CTE 名不能遮蔽并漏检其定义里的物理表。子查询、UNION 的每个分支和相关子查询内叶子表都检查；未使用但仍在 SQL 中的 CTE 也检查，不靠优化器删掉未授权分支。视图作为已登记对象使用，不递归同步或展开其数据库内部定义；底层表可见性由数据库视图权限负责。这与“SQL 直接引用必须已登记”一致，视图展开边界须在 UI/方法说明中明示。

建议执行时将已解析物理引用限定到完整位置以隔离默认 Schema 漂移，保存 SQL 原文供审阅，两者不能各自形成可编辑的来源定义。使用前重新核对已登记对象仍属于绑定连接；快照陈旧不自动注销登记，已观察移除则阻断。外部 DDL 与校验之间仍有竞态，真实查询报错后失效相应来源缓存并提示同步，不在后台静默登记或修复。

同一连接内多个已登记 Schema 可 JOIN；不同连接即使指向同服务器也不联邦。表材料生成、选表建模上下文和实例/指标查询全部走这个门槛。人工同步选择页可用受权限约束的实时发现接口，但其结果不能直接进入 Agent 上下文；Agent 不获得发现或同步工具。运行中的建模工作包保持固定，审阅期间同步只影响校验，不悄悄改写 Agent 已读工作包。

### 5.4 列探测与预览

以完整查询为子查询构造 `SELECT * FROM (<query>) AS <唯一别名> LIMIT 0`，CTE 通过引擎支持的作用域安全嵌入或提升，别名去冲突。不直接给原文尾部拼 LIMIT，保留内部 UNION、ORDER BY、LIMIT 的原始含义。MySQL/Doris/PostgreSQL 的 CTE 嵌入与提升分别做实际驱动验证，不兼容报明确错误。

以驱动结果描述拿有序列名和类型；未知类型先保留 unknown/null 并提示，不能猜成 string。驱动类型码、精度等转物理类型文本，业务转换仍交查询执行层。重复名、空名、无法稳定引用的匿名表达式输出报 COLUMN_ALIAS_REQUIRED；提示 `amount * quantity AS total_amount`。SELECT * 可以用，但输出随上游变化，编辑/接受必须重探测并展示依赖影响。列注释仅从可确定的直接列传递；计算/合并列不臆造注释，可按已有列说明机制由用户补充，重探测按同名列保留手写说明，不掩盖类型变化。

输出列必须唯一，快照日期列必须存在且日期类型可确认；字段丢失导致对象绑定、关系键和指标的具体引用报错。不能仅更新 Dataset.columns 就把依赖标为成功。类型未知时列可展示，但依赖该类型的指标/快照保存须待补全。

数据预览推荐默认 20 行、最大 100 行，响应上限 256 KiB；字符串长值带明确截断标记，不落盘业务行、不自动 COUNT 全表。无 ORDER BY 时说明“示例行无固定顺序”。预览按钮与校验分开，不随键入或页签切换执行；失败保留表单 SQL。完整 SQL 未通过校验、尚有未同步叶子表时，不执行 LIMIT 0 或预览。

连接建立建议 5 秒、单次探测/预览数据库语句 10 秒、请求总预算 15 秒；这些是平台配置的执行预算，不是核心字段。复用并补齐 readonly.connect_readonly：PostgreSQL 只读事务及 statement_timeout，MySQL 只读会话及 MAX_EXECUTION_TIME，Doris 使用支持的只读账号及 query_timeout。客户端 read_timeout 不能代替数据库端取消，超时后取消/关闭并回滚，不能在断开 HTTP 后继续跑查询。每个数据源账号的数据库授权只读，白名单是额外约束。

读取元数据及探测至少要求 can_read_mappings；预览业务行另要求 can_read_instances；创建/编辑/接受还需现有成员写入权限，MCP 服务令牌不能调用写操作。连接管理仍沿用管理员权限；同步使用现有成员操作权限并校验映射授权，不新造权限种类。错误脱敏，禁止回传 DSN/密码/内部主机。

### 5.5 响应与错误约定

建议内部 API `POST /workspaces/{id}/datasets/validate`，请求为候选 Dataset、Dataset.connection_id、session_id/预期 revision；响应含 `diagnostics[]`、`columns`、`referenced_tables`、`check_fingerprint`。诊断用 `{code, severity, path, message, related_element_ids, details}`，路径可定位 SQL 作用域/输出列/提案字段。预览用独立 `POST .../datasets/preview`，服务端再次校验，不接受客户端传入任意已校验 SQL 凭证旁路。

至少区分 SQL_MULTIPLE_STATEMENTS、SQL_NOT_READ_ONLY、SQL_UNSUPPORTED、SOURCE_AMBIGUOUS、SOURCE_NOT_REGISTERED、SOURCE_REMOVED、COLUMN_NOT_FOUND、COLUMN_ALIAS_REQUIRED、DIALECT_MISMATCH、QUERY_TIMEOUT、QUERY_FAILED、AGGREGATION_FANOUT、CARDINALITY_UNKNOWN。前五类结构/授权错误不能用人工确认跳过；风险确认只适用于静态业务警告。

## 6. 数据表后台同步

### 6.1 任务与登记存储

保留 MetadataSnapshotRecord 作为**已成功观察的登记表目录**；任务日志不混入该目录，也不把库里发现但未采集成功的表先登记。每个表保存 kind=table/view、columns、按 inspector 顺序的主键、可取得的外键、observed_at 和存在性观察；外键用于导入安全核对，不自动建本体关系。现有按列 primary_key 标记可保留作展示，但复合主键顺序不能只从列顺序反推。

| 持久化对象 | 主要字段及目的 |
|---|---|
| metadata_sync_jobs | id、workspace_id、connection_id、规范化 Schema、scope=all/selected、所选表清单（selected 非空）、创建人/时间、state、inventory_json、inventory_complete、枚举耗时、开始/结束时间、脱敏错误；库存表名只供任务调度，不代表登记 |
| metadata_sync_batches | job_id、ordinal（唯一）、table_names_json、state、attempt、开始/结束时间、duration_ms、逐表结果及脱敏错误；记录成功/缺失/失败及需重试集合，便于恢复半完成批次 |

state 是执行生命周期：任务 queued/running/succeeded/partial_failed/failed/interrupted，批次 queued/running/succeeded/failed/interrupted；进度数字从批次表结果推导，不新增核心字段。无需额外“已登记”核心状态，表目录本身和最后存在性观察表达它。单批次失败可包含已成功保存的表，重试只执行其尚未成功的成员，不撤销成功结果。

任务由进程内后台任务执行，不做租约、多 worker 领取、过期重领。服务启动时将 queued/running 任务及未完成批次标为 interrupted（已中断，可重试）；用户显式重试，成功批次不重做。同连接/Schema 的活动任务串行。读取业务库时不持有平台写事务。

### 6.2 全量、指定表、预算与重试

提交全量任务只枚举并固定本轮表/视图清单，拆批处理；未取得清单时显示“正在发现数据表”，不显示假百分比。建议每批最多 20 张、读取预算 15 秒，单表超时单独报错；达到批次预算前结束并持久化余下调度，不把未执行表算失败。枚举独立预算建议 15 秒，失败可重试枚举，不把枚举失败解释为“库为空”。参数可按连接配置调整，**15 秒不再是整个 Schema 的总预算**，没有表数量总上限。

指定表提交非空名称列表，直接对指定对象取结构/存在性，不先全库枚举；单表“去同步”只提交那张表。旧 refresh 的 tables=[] 不能再解释为全量，改为校验错误；全量通过明确 scope=all 表达。一次所选表很多时只受请求字节预算及分页选择设施约束，不恢复 200 张语义上限。

每张成功观察结果进入小事务，与批次检查点一起提交，完成一批后立即可被平台使用。schema_diff/retain_schema_changes 的未处理漂移语义保留；部分同步只比较并替换本批对象，不触发全 Schema 删除。首次同步失败的表仍未登记；旧表刷新失败保留旧结构及观察时间，标出本次失败，不污染同批成功表。Schema 级 observed_at 不能冒充每张表同一新鲜度。

已确定不存在的指定表记录移除观察、保留旧列供影响展示；全量只有完整枚举成功才可对旧登记但本轮清单已不在的对象作移除观察。批次超时、权限不足或枚举失败都不能把未处理表当删除。连接权限突然缩小时无法区分不可见与物理删除，显示“当前不可见/不存在”并阻断使用，不删除本体数据集或绑定。

重试接口仅针对失败批次/失败成员，追加 attempt，历史耗时与错误保留；成功部分不清空。SQL 连接异常要关闭对应业务连接，其他批次继续；可用数一直展示。全量期间新增表留到下一次同步，不能让总数无限变化。同连接同 Schema 的两个任务按串行顺序合并，避免旧任务覆盖新结构。

### 6.3 API 与界面进度

建议 `POST .../connections/{id}/assets/sync-jobs` 返回 202 与 job_id；`GET .../assets/sync-jobs/{job_id}` 返回任务及批次分页；`POST .../{job_id}/retry` 显式提交失败 batch_id。保留 /assets 已登记表列表并加分页、按连接/Schema/名称/种类过滤。旧 /assets/refresh 的内部调用改走任务协议，不能维持一个假同步 200 响应；前端 DatasetPicker、MappingsPage 与 API client 同轮迁移。实时发现接口按分页返回用于人工选择，若驱动只能一次枚举也在后台受预算执行，不把完整库存塞到浏览器/Agent。

前端刷新恢复后可继续查最近活动任务，建议活动页轮询 2 秒，离开页面停止轮询，任务继续。显示“已处理 60/245，可用 58，失败 2”、正在处理批次、累计耗时；展开 Table 显示批次耗时、成功/失败数和失败对象，并提供“重试失败批次”。已知 0 如实显示，无清单时显示发现中，错误不能显示为 0。完成事件使登记列表及受影响提案校验失效并重取；无需 Agent 参与。

## 7. 重复计算静态检查与人工确认（2026-10-21 作废）

> 本节按 DS-06 简化作废：平台不推断连接粒度，不返回 AGGREGATION_FANOUT / CARDINALITY_UNKNOWN 警告，不要求 warning_confirmations 或 check_fingerprint。下文仅保留作历史记录；§7.2 的雾岭商贸例子仍是技能方法论中的反面说明。

### 7.1 检查依据与规则

仅将已同步主键（包括有序复合键）当作已声明的物理唯一性证据；Ossie relationships 指向“一端”是外部声明，须与已登记键核对后才能作安全依据。对象映射的逻辑唯一键、数据抽样无重复、数据库优化器估计行数均不能冒充物理主键。SQL GROUP BY 可以在 AST 中证明某结果的分组键唯一，属于查询结果推导，不写入模型。视图无主键时不猜。

| 场景 | 结论 |
|---|---|
| 对等值 JOIN，目标列包含目标完整主键，且全部键对应不含会丢失等值性的函数 | 目标至多一行，不会因这一跳放大左侧行；不保证匹配存在，也不保证业务含义正确 |
| 按主键表连接到未证明唯一的一端，随后聚合主键侧金额/计数 | AGGREGATION_FANOUT，指出连接列及被重复的度量，要求确认 |
| SQL 只投影明细但存在上述连接，外部指标将聚合来源侧列 | 追踪输出列血缘，在数据集审阅提示风险；新增/编辑指标也检查消费该输出列的聚合，不能只检查 SQL 内的 SUM |
| 两事实表经共同维度连接、非等值/部分复合键、CROSS JOIN、键未知、窗口或 DISTINCT 使粒度不能证明 | CARDINALITY_UNKNOWN，说明不能证明的节点；不显示“安全”。人工编辑来源可审阅确认，机械 Ossie 转换走待补全 |
| 两端先按同一连接键 GROUP BY，再按完整分组键连接 | 可证明双方至多一行，显示依据；还需检查过滤、NULL 和期间是否保持口径 |
| UNION ALL 事实事件，分支各投影完整业务日期和事件类别 | 不因拼接造成同一事实的笛卡尔放大；仍不证明两个分支的业务事件互斥 |

多跳按作用域传播唯一性和度量血缘；跨任一可能放大节点的 sum/count/avg 等给警告，不能因为末尾 GROUP BY 或 DISTINCT 就认定消除了金额重复。MIN/MAX、COUNT DISTINCT 等不一概按 sum 判断，也不能把一个 DISTINCT 证明扩展至其他度量。连接目标唯一只证明至多一条，不证明没有遗漏、时间快照正确或数据库声明与业务唯一性一致。

### 7.2 具体数据与确认

虚构空间“雾岭商贸”，mist_sales 一单 S1 金额 100，mist_refunds 对 S1 有两笔 10、20。直接 JOIN 的两行销售额为 100、100；SUM 得 200、退款 30，退款率 15%，与销售 100、退款 30 的 30% 不同。诊断展示这类计算影响，定位 sales.sale_no→refunds.sale_no 的多端，不仅给“可能有风险”泛文案。

校验返回 warning ids 和 check_fingerprint，保存/接受请求携带明确的 warning_confirmations。指纹绑定候选来源、消费方定义、元数据内容/主键、绑定连接、预期草稿 revision 和授权上下文。任一变化重新预检；UI 不默认勾选。复用已有 affected_items 影响确认流程，但风险确认是独立清单，不能把确认依赖变化等同于确认重复计算。接受响应及既有决策 response_json 可记录确认摘要，不新增核心永久豁免字段。

未同步、无权限、SQL 不只读或列缺失属于错误，人工确认不能覆盖。直接 query 导入和 Agent 提案可保留风险供人工审阅；**机械转换跨数据集指标时**，发现 fanout 或不能证明语义等价就不生成声称完整的转换结果，保留原文待补全（§9）。人工补全改写后可形成正常候选，再经上述检查。

静态检查不扫描数据证明主键、不判定业务算法等价、不保证未来元数据不漂移。保存通过说明结构和当前执行条件成立，不承诺业务正确；真实查询仍受只读、权限和超时约束。

## 8. 提案、未同步表与重新校验

### 8.1 共用候选流程

Agent、Ossie 和人工创建都形成 Dataset 候选，复用同一结构检查、来源校验、依赖组和接受逻辑。Agent 用已有 reason/evidence 说明为什么单表不足、结果一行代表什么、日期口径与来源定位；不添加只能供技能使用的补偿字段或新的“跨表指标”类型。

提案入库时允许结构合法但尚未登记/未探测的 Dataset，并在现有 pending 提案上附**派生诊断**；不能让严格“只允许已登记来源”的最终模型校验提前吞掉 DS-07 的候选。提案仍只有 pending/accepted/rejected/superseded 决策状态。界面“表未同步”“列待核对”“重复计算待确认”由候选、绑定、登记元数据和最终候选图重算，不写 proposal.status，也不写 Dataset.status。缓存只能作为可失效读缓存，不能变成接受依据。

如候选只能由材料定位库表且未确定连接，显示“来源待匹配”；选择连接后再判定该连接上的“表未同步”。从材料提议不授权访问该表，Agent 不执行实时查表、同步或预览。只有结构本身非法的候选走 harness 现有格式修复路径；未同步是审阅阻塞，不消耗模型修复轮次要求它反复读 Schema。

### 8.2 接受与依赖传播

Dataset 与依赖它的映射、指标使用已有依赖组：接受时合成此次候选最终图，再依次校验 Dataset→对象/关系绑定→simple/expression→ratio。缺任何登记表、必要连接、输出列或快照类型时，该依赖组整组不写；其他独立提案仍能正常处理，不形成半个 ratio 或悬空 dataset_id。

接受前再次检查数据库元数据和 Dataset.connection_id，不信任上次展示诊断。LIMIT 0 放在平台数据库写事务外执行；进入短事务后复核会话 revision、候选 hash、登记指纹及授权，变化则报过期重检。成功时服务端探测列写入被接受 Dataset，并保留探测前后差异供审阅，禁止接受时静默改变已供用户确认的列定义。失败不改变草稿、绑定及决策状态，沿现有幂等重放合同。

“去同步”从提案打开数据管理的数据表任务上下文，携带**确切连接、Schema、单表**，人工发起 selected 任务，任务完成后回到原提案；表达式涉及三张未同步表时逐表显示入口，不把点击某表变成全量同步。“修改连接和表”在候选编辑区修改平台绑定和 table 分支位置；query 分支需同时编辑 SQL 叶子引用，不做跨方言或表名全文替换。

同步成功/观察移除、来源编辑或改绑都会使该 Dataset 及它的依赖提案校验失效。依赖清单从现有 dataset_id、列引用和 ratio 分量图实时计算；SQL 的物理表血缘从 AST 推导。不持久化第二份“谁依赖未同步表”的关系。活动审阅页在任务轮询完成后自动调用批量重新校验；其他会话下次读取就重算，接受再强制校验，无需后台扫描改写所有提案状态。

例：材料说 mist_sales.total_amount，但同步只发现 amount。数据集的表登记诊断消失，映射的 fields.amount、指标的 measure.column 各自显示“列 total_amount 不存在”，ratio 显示分量阻塞；不将列自动改为 amount。用户修改后重新校验依赖闭包。新探测列还可能引出类型变化，不能仅按列名存在就通过。

## 9. Ossie 导入、导出和往返

### 9.1 query 来源与引擎方言

source 是完整表标识则走 table；是单条 SELECT/CTE/UNION 则走 query_sql。不能仅用字符串是否包含 SELECT 判断，字符串、引号和注释必须由解析器区分。先用导入的来源匹配步骤确定本地引擎；引擎未知时保留原文、位置和候选，诊断为待补全，不能把 ANSI_SQL 推定成 MySQL。适配器转换阶段不连接业务库，随后由共用来源完成服务登记校验和探测。

导出 table 为正确引用的完整位置，query 为保存的来源查询（或保证语义不变的引号规范化）；保留一个核心 Dataset 对应一条外部 Dataset，包括未引用者。query SQL 的物理表名不随 Dataset 改名替换；只有字段/指标内已绑定的逻辑引用按 AST 重写。

字段、指标有多种 dialects 时，优先选择与已绑定引擎一致的表达式，其次选择可在该引擎白名单内验证的 ANSI_SQL；选择结果和被省略变体逐项报告。字段仍受同行标量边界约束，不能因支持方言就允许字段内 JOIN/聚合。导出实际方言名须是官方 Schema 允许的非空 dialect 字符串，并以适配映射表明确 mysql/doris/postgresql 的名称；绝不把方言专属函数伪装为 ANSI_SQL。query 的 source 字符串没有 dialect 槽位，引擎定位仍由平台匹配，扩展可携带引擎提示但不是授权或凭据。

### 9.2 跨数据集指标的机械转换

只用 semantic_model.relationships，不从本体 LinkType 或两个字段同名猜连接。relationships 是**导入转换的证据**，不成为核心数据集关系。流程为：

1. 解析所有逻辑字段、最终物理来源、公式与外部字段类型；限定同一连接及可执行方言。
2. 对公式实际涉及的数据集找唯一连接路径，完整对齐复合 from_columns/to_columns；存在多个路径、自连接角色不明或断路则待补全，不能选第一条。
3. 核对每条“一端”完整唯一键和 SQL 粒度，证明不会放大当前算法；同时核对连接类型、缺失匹配、过滤、NULL、时间范围。仅有 PK 不证明引用完整。
4. 可以证明转换保留原算法时，生成输出所需明细列的 query Dataset，以及引用该 Dataset 输出别名的原指标（simple 或 expression，仍只一个 dataset_id）。生成 id 沿适配器的 workspace+外部作用域+原指标定位的确定性规则，不按随机名称建立重复来源。完全相同的来源 AST、连接和输出投影才可复用，不能因“都叫销售额”就合并。
5. 两者组成待审阅依赖组，报告 RT-69 converted，展示生成 SQL、原公式、连接证据和别名对照；然后进入同一来源登记、探测、风险确认机制，不自动接受。

正向可转换例：mist_lines 每行一条销售明细，product_no 非空，已登记且数据库强制的外键指向 mist_products.product_no 主键；外部 relationships 指向同一列组，公式 SUM(lines.quantity * products.unit_price)。两条明细数量 2、3，价格 10、20，得到 80；转换为逐明细 total_amount 列的来源查询再 SUM(total_amount)，仍为 80。连接不存在缺失匹配且目标唯一时，INNER/LEFT 在此输入范围等价；缺这类证据不能自行承诺等价。

需要新增的外键观察是数据库元数据，不强制所有来源声明外键才能人工建模。没有约束证据时，外部 relationships 仍保留供人审阅，自动转换标待补全。§13 U-02 明确这种默认保守程度。

一单 100 对两退款 10/20 的连接聚合、两个独立事实的 SUM 比、存在不明期间/快照选择、额外 SELECT 作用域无法无损移入数据集的指标，都保留原文及定位，标 completion_status=available，不生成假完整核心指标。**不能把原公式的 JOIN 自动改成 UNION ALL、SUM 改成 DISTINCT SUM、或先聚合后连接并声称原算法未变**；这些是人工/Agent 提出的业务改写，需理由和审阅。独立合法项继续导入。

若原指标已经是明确 SELECT，只有能完整分离“来源结果集”和外层单数据集算法且证明输出粒度、分组和时间不变时才转换；否则按 RT-69 待补全，不把 SELECT 塞进 Metric.expression。

### 9.3 datatype、dimension.is_time 与 label

> 2026-10-21：导出推导保持不变；导入核对作废，改为逐字段报告 RT-46“声明不保存，以登记列类型和指标时间字段为准”，不比对、不提示冲突。

导出每个 Field 的 datatype：有直接属性绑定时优先取有效属性基础类型（值类型实现后取其基础类型），无绑定时从已登记/探测的物理列类型推导；多个属性对同一字段推导冲突，或与已知列类型不兼容时报告待核对，不任取第一项、不擅 CAST。核心七类型映射为 Ossie String/Integer/Decimal/Float/Boolean/Date/DateTime；已知物理 Time、DateTimeTz 按其真实类型输出，不能有损并入 DateTime；未知类型省略并提示，不以 String 填空。完整 SQL 类型精度/时区文本仍不能由逻辑 datatype 保证往返。

Field 对应的列被 Metric.time_field 或 Dataset.snapshot_date_column 使用时输出 `dimension: {is_time: true}`；ratio 使用分量时间字段。仅日期类型但无已声明时间用途，明确输出 is_time=false，避免官方 Schema 的日期类型默认 true 把审计时间误当业务时间。只按声明推导，不因列名含 date 就选择它。其他维度属性不新建核心开关。

导入 datatype 与已知属性/列类型核对，is_time 与已声明用途核对；冲突逐字段提示。单文件中的 is_time=true 只能说明时间维度角色，不能唯一确定快照列或某指标 time_field，不自动回填二者。逻辑 datatype 不伪装成数据库探测结果，类型未知仍可保留核对提示。字段 label **继续 dropped 并逐项 RT-46**，不自动转中文名称/同义词。未用 unique_keys 的现有损失边界保留。

### 9.4 扩展文件与核心字段往返

延续纯 Ossie JSON + ontofoundry-extension.json ZIP，version=core-1。dataset_metadata 用外部作用域和数据集名定位，写 snapshot_date_column、connection_name；metric_metadata 保存 simple/expression 的 time_field；角色名、display_names 沿用现有扩展。读取检查定位唯一、字段引用闭合；连接名称仅用于匹配提示。连接 id、凭据、业务行、实例、证据不导出。

这些字段读回核心，无需额外持久化。不保存不支持的 Ossie 原形；一元按布尔属性、多元按重化结构导出，按 RT-21/26/27/28 报告已转换或不支持。纯文件 is_time 不能唯一还原快照和指标时间字段，仍报告 RT-60；ZIP 可准确回读。

### 9.5 例外表和逐条 RT 修订清单

本表是实施时对主设计 §5–§7 的增量，本文不修改原文件。无新增 RT 编号，避免与并行值类型设计争用；每项差异仍落现有 RT。纯文件与带扩展 ZIP 必须分别列结果，不能把“原文在报告里”称为核心无损。

| RT | 本次变更与保留边界 |
|---|---|
| RT-03 | 扩展允许上述三项及 dataset 显示名定位；旧扩展块仍只导入兼容，非法/未知字段继续报告 |
| RT-13 | 保留引号规范化，扩大 query 中已解析标识；不能重写字符串字面量 |
| RT-21 | 二元角色名随扩展往返；值角色及一元/多元原形不保存。 |
| RT-26 | 一元转布尔属性，规范导出并报告结构差异；不保存原形。 |
| RT-27 | 多元转重化对象和关系，规范导出并报告结构差异；不保存原形。 |
| RT-28 | 仅转换可表达的标识和规则，其余待补全；不保存原形。 |
| RT-40、RT-41 | 字段名/分组仍可规范化；扩展定位跟随确定性对照重写，不能因 query 名相同合并不同作用域 |
| RT-43 | 从“只有 ANSI_SQL 的字段”扩大为匹配引擎的同行表达式；嵌套 referent、多层 children、字段内聚合/子查询等其余例外保留 |
| RT-45 | 匹配引擎的方言表达式可用并正确导出，删除“一律只留 ANSI”的说法；其他未选择变体仍逐项说明损失 |
| RT-46 | datatype、is_time 改为导出推导、导入核对提示，不再一概 dropped；不能恢复的独立声明及类型/用途差异仍报告。label、未用 unique_keys、其他未承载 Field 元数据继续 dropped |
| RT-47、RT-49、RT-50、RT-51 | 保留已解析字段重写、单数据集算法与去重含义及辅助字段规则；适用于 query 输出列，不因新增来源改变 COUNT/NULL 语义 |
| RT-52、RT-53、RT-54 | 既有映射折叠、歧义、拼接后同行作用域例外保留；显式 query 已把行集合闭合时按 query 处理，不能宣布所有旧多来源计算已无损 |
| RT-55、RT-56、RT-58 | 原同数据集比率/拼接去重及逐分量执行规则保留；不为跨表输入偷偷制造若干分量或改变过滤 |
| RT-60 | ZIP 结构化保存快照和指标时间字段，取消该情形的损失；纯文件只有 is_time/说明仍无法精确回读，继续逐项报告 |
| RT-61 | 核心指标单数据集不变；query 输出列未闭合、来源未完成或统计来源无法合法导出仍 error，不交付缺必要指标的伪有效文件 |
| RT-62 | table/query 一一登记和导出，作用域/同名消歧、未引用 Dataset 保留 |
| RT-63 | 合法只读 query 不再因不是表位置而 error；来源多语句、写操作、不可定位/未登记、连接待匹配等继续本项 error/待补全，不塞进 table_name |
| RT-64 | 主键顺序、冲突、快照时点唯一性例外保留；query 不因叶子表有主键就自动拥有主键，输出键须由既有映射和完整证明处理 |
| RT-66 | datatype 与引擎提示缩小部分损失，但逻辑类型不恢复完整物理精度、元数据采集身份和凭据；未能结构恢复部分仍报告 |
| RT-69 | 可证明等价且安全者 converted 为 query Dataset + 单数据集指标；连接歧义、放大、时间/NULL 口径不明或不能分离查询作用域者 error 待补全，保留完整原文和定位 |

主设计 §7 支持表需同步：Dataset 行改为表/视图/query；字段方言、datatype、is_time 拆开；跨数据集指标改“安全转换待审阅”；一元/多元保留转换差异，时间字段标出 ZIP 条件。例外索引“映射表达范围”移除一概拒绝 query，“字段元数据”保留 label 等余项，“指标”保留不安全/不明转换；值类型的 RT-23/24/35 等完全由并行设计维护。其他 RT 不变，不能顺带扩大映射、规则或导出空本体的范围。

## 10. 四个 MCP 工具的增量

工具数量、名称、只读性质、协议版本协商、serverInfo 版本及服务端发布/固定版本选择机制沿用现状；不新增 query_dataset、查表或同步工具，不加 version_id 入参。DS-08 的“只改 Schema 和说明”指 Agent 接入面，不排除使返回结果实际生效所需的 lookup、搜索、投影及分页实现；问数提示词文件保持不动。

search_ontology.kinds、get_ontology.kinds 的 Kind 增 dataset。搜索 dataset 时匹配 name、display_name、description、表来源 table_name 或 query 叶子表名；不对整段 SQL 字面量做全文搜索。默认不指定 kinds 时包括授权数据集。无 can_read_mappings 时，dataset 名称、描述、表名命中、数量、SQL、列和引用清单全部隐藏；ids 直查沿现有 missing 行为，不能通过错误泄露存在性。

get_ontology 不传 ids 只给轻量目录及真实数量；传 ids 且 include 含 physical 才返回 Dataset 来源详情。include 默认仍 semantic，不因请求 dataset 自动泄露物理 SQL。adjacency 请求时返回实时推导的 referenced_by，限当前授权/固定模型作用域；UI 详情使用同一推导服务。指标和对象原物理投影中的 Dataset 也加 source_kind/query_sql，避免只改独立详情后消费方还以 table_name 拼 SQL。

响应沿现有 envelope 和 definition，示意为一个授权查询结果元素（分页和 UUID 值省略）：

```json
{
  "kind": "dataset",
  "id": "<数据集 UUID>",
  "name": "trade_events",
  "description": "销售及退款事件，每行一个事件",
  "binding_status": "bound",
  "definition": {
    "source_kind": "query",
    "dialect": "mysql",
    "schema_name": null,
    "table_name": null,
    "query_sql": "SELECT ... UNION ALL SELECT ...",
    "snapshot_date_column": null,
    "columns": [{"name": "amount", "physical_type": "decimal", "comment": "事件金额"}]
  },
  "source": {"database": "mist_dw", "schema": "mist_dw"},
  "referenced_by": {
    "object_mappings": {"total": 0, "items": [], "next_cursor": null},
    "relationship_mappings": {"total": 0, "items": [], "next_cursor": null},
    "metrics": {"total": 3, "items": [], "next_cursor": "<引用分页游标>"}
  }
}
```

示意中的省略 items 仅为文档缩写，真实响应不能返回虚假空页。definition 实际含完整已授权 Dataset 字段。table 分支返回位置及登记 kind=table/view，query 分支只把 schema 解释为执行默认命名空间。来源方式是 table/query；引用列表条目至少含 kind/id/name、可用的 display_name、映射定位和引用原因，列表按对象 type_id、关系 id、指标 id 分别去重。对象含主/附/成员来源，关系含继承的本地绑定；ratio 从同数据集分量推导并计入自身，不能只列直接 simple。

columns、referenced_by 三个集合继续分页，SQL 大字段继续 field_segments，不超 256 KiB 总 wire 预算；返回可标识的完整分段，不静默截断 SQL 后仍供执行。SQL 参考只有定义、来源、登记、白名单就绪才返回；query 来源放入子查询，缺字段/权限时解释未就绪，无 SQL 旁路。版本固定不代表元数据永久不变，外部 DDL 后可返回不就绪原因，但不能跳到另一发布版查替代 SQL。

## 11. 全部消费方统一使用结果集

建议在服务层形成唯一 `resolve_dataset_relation`：根据绑定和 source_kind 返回已校验的表关系或子查询 AST、输出列、执行连接和来源诊断。实例计划的 SQLAlchemy Selectable、指标编译器和 SQL 参考从同一来源规范得到各自适配结果，不能维护三份 SQL 安全检查。

| 消费方 | 处理方式 |
|---|---|
| 实例浏览、关系实例和数据映射预览 | query 作为带唯一别名的 Selectable；映射键/属性只引用输出列，继续按既有逻辑校验重复实例键、分页、成员及继承条件 |
| 指标总值、趋势、ratio | 外层对该结果集应用指标固定过滤及各分量 time_field，分别聚合后相除；不会把 SELECT 带入 Metric.expression |
| 快照 | 在**完整 query 结果集**上找 snapshot_date_column 的整体最新日/周期末日，再处理外层时间；不把叶子快照自动注入分支，避免改写数据集定义 |
| MCP SQL 参考 | 返回外层参考 SQL，query 原算法保持；同一引用多次时别名/CTE 命名去冲突，参数仍只用于外层过滤 |
| 问数 Agent | 通过工具说明和授权来源字段理解 query 是结果集，在自己的查询工具中嵌入子查询；不修改问数系统提示词，不让模型从无权限 SQL 文本推来源 |

外层示意：`SELECT SUM(events.amount) FROM (<query_sql>) AS events WHERE events.event_kind = 'sale'`。销售/退款 UNION ALL 数据集里，分子过滤 refund 并按 business_date，分母过滤 sale 并按 business_date；销售 100、退款 30，得到 30%。若不同日发生，分别归各自事件日期，不按销售日强行回填退款。分支原有 LIMIT、过滤、窗口及聚合都属于来源定义，外层不能为了“更快”随意推入条件改变行集合。

## 12. 界面与技能设计

### 12.1 使用者、布局和五个目录页签

使用者是登记数据来源并审阅建模结果的空间成员，目标是区分底层表与语义数据集、理解表达式行集合和风险后接受。采用现有操作型界面，保留应用框架、元素详情页和新工作区页签导航；不增加另一套 SQL 工作台或视觉风格。

目录顺序固定：**实体类型 | 值类型 | 关系 | 指标 | 数据集**，各显示真实总数（含 0），不把搜索命中数当类型总数。catalogTab 继续保留 entities/relations/metrics，加 value_types/datasets，旧 URL 保留；值类型内容由并行设计提供。导入、导出、发布仍在页头右侧，各 Tab 新建在当前 PanelToolbar。关系名称仍为“关系”，列及 display_name 以最新名称统一设计为准，不沿用目录旧文档“关系没有中文名”的过时表述。

数据集目录为紧凑单行 Table：名称链接、英文标识（U-01）、来源方式、来源位置摘要、列数、快照日期列、被引用数量、来源校验、描述。位置列 table 显示 Schema.表（标注视图种类），query 显示“表达式 · N 张表”，不在目录塞 SQL。筛选来源方式/连接，搜索名称、英文标识、描述、表名；N、列数、引用数按授权实时推导。新建数据集打开稳定的新建详情页，来源方式用 Ant Design Radio.Group 选择；保存后同一页签换新元素地址，取消关闭新建页签。

### 12.2 数据集详情、新建与编辑

复用 PageHeader/PageBody + 单个 Panel fill，标题、页签固定，正文独立滚动；右上编辑原位切取消/保存。目录、搜索、引用进入稳定 elements/dataset/<id> 详情工作区页签，同元素去重；图上和构建/发布任务内继续按既有详情弹窗范围，复用相同内容组件，弹窗内引用进入详情页而不叠窗。切页签保留未保存编辑，离开工作空间/关编辑页按现有保护处理。

| 详情 Tab | 内容与组件 |
|---|---|
| 基本信息 | 无边框 Descriptions / Form：名称、英文标识、来源方式、连接、描述、是否快照及日期列。FormRow 对齐；引擎由连接决定，只读显示，不让用户重复选一个冲突方言 |
| 来源 | table：连接→Schema→已登记表/视图，直接展示位置。query：Input.TextArea 编辑/只读展示 SQL 原文，下方“校验并探测列”“预览数据”，诊断 Table 按级别和位置列出，重复计算用就近 Alert + 明确勾选确认。禁止引入手写 SQL 控件或新的编辑器依赖 |
| 列 | 完整宽度紧凑 Table：列名、类型、注释、用途（快照/指标时间，从定义推导），显示探测前后差异；输出名由 SQL 别名决定，不在此处单独改名造成不同步 |
| 数据预览 | 显式点击后才取少量行；Table + 页内说明，无全表计数。未校验/权限不足/超时有明确原因；无权限不发业务行请求 |
| 被引用 | 三个分区：对象映射、关系映射、指标，各显示数量和紧凑列表，名称文字链接。指标含 ratio；没有引用显示 0 与静态空说明，不新增模型字段 |

新建默认在基本信息，完成来源方式/连接后配置来源；query 必须经探测才能保存。来源方式/SQL/连接变化即使未点保存，也将旧校验与预览标为失效，禁用旧确认。连接或来源方式切换若会丢弃已编辑 SQL/表选择，先就地确认并清除失效配置；保留其他基本信息及稳定 id，不自动转换为不同业务数据集。已有映射/指标受影响时进入原 affected_items 保存预检，列不兼容阻断，不静默删依赖。

校验耗时中仅禁用冲突动作，不冻结浏览整个目录；请求乱序按候选指纹过滤，旧 SQL 的结果不能覆盖新输入。字段错误留 Form.Item；操作失败用浮动 message；业务风险保留在来源旁，不能只用一闪而过的 Toast。

### 12.3 数据管理与审阅交互

数据管理是**数据表 | 文档**，不再列本体 Dataset，不提供表达式新建或“登记数据集”操作。数据表页连接/Schema 筛选、名称搜索，右侧“同步全部”“同步指定表”；列表只展示已登记的表/视图、列数、最近成功观察时间、结构变化及同步状态。实时未登记库存仅在同步选择区出现，不能混进可选业务来源。文档继续使用现有 DocumentMaterials。

同步进度放在同一 Panel 内分割线分区，用 SectionTitle、细 Progress、StatusMark 和可展开 Table；不增加进度卡片。用户离开页面后任务继续，再进入恢复进度；失败显示可用成功部分及失败批次重试。数据集创建时的表选择器只读登记目录；缺表引导去数据管理，不在选择时悄悄同步。

提案列表在现有 pending 决策状态旁显示派生“表未同步”或其他阻塞数，详情来源区逐表列“去同步”“修改连接和表”；依赖映射、指标的错误在对应提案字段定位。接受按钮可触发预检并列出阻塞原因；服务端无论 UI 是否禁用都拒绝未解决组。重检不关闭当前详情、不重置用户选中提案、不让未同步错误消失后自动接受。

### 12.4 视觉规范与截图验收

只用 components/layout/ 与 Ant Design 5，Tailwind v4 排布。画布→面板最多两层，表格首列、PanelToolbar、SectionTitle 在 16px 内线对齐，页头/面板外框在 24px 线上；复用 12/14/16px 字号和既有紧凑密度。状态走 StatusMark，Tag 仅作中性来源分类/用途；长 SQL 用滚动正文/换行和 tokens 中的既有预览尺寸，不写零散 CSS、内联样式或任意值。

“来源 SQL 编辑与诊断”“后台同步进度分区”“五 Tab 数据集目录”若现有 §4 未覆盖，实施前将本节对应模式补入视觉一致性文档第 4 节并随本设计确认；不另加容器模式或在本轮改该文件。窄容器沿用 FormRow/DetailWorkbench 的切换，工具栏不能挤掉保存和页签，长列名允许表格横滚。

实施后统一在 1440×900 与改前/基准截图比对：①五 Tab 目录，数据集的 0/有数据/搜索；②表/表达式详情五 Tab 及查看/编辑，长 SQL、重复计算警告、列缺失、预览无权限/超时；③新建表/表达式；④数据管理的发现中、处理中、部分成功、重试后成功；⑤提案未同步、去同步返回、修改表及依赖重检；⑥对象/关系映射的数据集选择器及表达式标签；⑦指标预览与 Ossie 导入待补全界面。检查容器层级、对齐、字号、状态、表格密度，并运行 npm run test:visual；前端 id 只用 newId()，还需局域网 IP 的 HTTP 访问验证。此轮不截图、不更新基准、不运行测试。

### 12.5 技能仅追加正例与方法章节

实施时在 harness 最终技能结构上**新增示例/方法章节**，不重写系统提示或问数提示，不通读/复制另一份完整 Schema，不引入反例目录。查写法沿 harness 已确认 target_kind/operation 入口检索最小正例；服务端仍是最终裁决，不复制平台数据库校验到本地检查器。

| 追加正例 | 应呈现的合法结构和数值 |
|---|---|
| 表来源 Dataset、query 来源 Dataset | 来源互斥形状、平台绑定请求包与核心定义边界，字段注释和快照配置 |
| 销售/退款事件 UNION ALL + 指标 | 销售 100、退款 10+20，同结果集分子 30、分母 100，30%；各保留业务日期与事件类别 |
| 两事实先聚合再连接 | 同客户销售 100+50、退款 10+20，各先按客户汇总再连接，仍为 150 与 30；明确共同期间，20% |
| 事实只向一端查维度 | 两销售 100、50 查唯一客户地区后合计 150，展示完整主键匹配和输出列 |
| 依据材料提议未同步表 | 合法 pending Dataset 候选、reason/evidence，说明需人工同步；没有同步调用或伪造 columns |
| Ossie query 与安全跨表转换 | 外部 source、字段方言、生成单数据集公式及 RT 报告定位 |

方法章节补：先说明行粒度和分支范围；判断多事实是纵向事件还是横向补属性；保留每个分量业务时间；分析一对多金额复制（100 对两退款会变 200）与如何选安全方案；先聚合的期间/空值语义；只向一端查维度；登记与材料证据不同；静态“未知”不等于安全；Ossie 不明转换写待补全而不硬转。业务坑用方法论中的数字解释，不提供可被当模板的错误 JSON/错误 SQL。只在实现完成、合并验收获授权后按 README 同步技能并重启，本轮修改技能源码，不生成 dist，不调用 DataAgent。

## 13. 已确认边界

DS-13 确认 Dataset.name 为 ASCII 英文标识、display_name 可选；DS-14 确认跨数据集指标只有证据足够才机械转换，否则待补全；DS-15 确认仅非递归 CTE。DS-11 不保存不支持的原形；DS-12 采用进程内后台任务；DS-16 连接直接进入 Dataset；DS-17 首轮阅读总量不超过 22 KB。批量大小、超时、预览行数为执行参数，不新增业务概念。

## 14. 实现时文档同步与验收边界

本次同步更新：

| 文档 | 必须同步的说明 |
|---|---|
| datasets-and-binding.md | 表登记与语义 Dataset 分层，两种来源、平台连接绑定、输出列、表未同步审阅、引用推导，删除“任意查询不接受”的旧说明 |
| metrics.md | 单数据集原则保留，query 解决跨表；UNION ALL 数字示例与粒度方法，不扩展 Metric.expression 边界 |
| query-semantics.md | dataset 工具类型/权限/分页、子查询消费、原文分段、登记门槛、无新增 MCP 工具 |
| time-and-snapshots.md | query 输出整体选快照日；叶子表快照不自动传播，事件日期和分量时间保留 |
| formats.md、ossie-compatibility.md | query source、匹配方言、datatype/is_time、ZIP 时间字段及连接提示往返，RT 更新和纯文件限制 |
| identifiers.md、README.md | U-01 确认后的 Dataset 命名；概览索引及两层数据入口 |

实现前确认并同步主设计相关段落、第 49 项输入适配说明、目录/数据管理/UI §4；harness 仅增量衔接正例与方法，不推翻其 §11 已确认预算和退出机制。值类型文档到位后合并目录及属性基础类型推导；不在本设计代写值类型内容。

验收必须同时覆盖契约、真实数据库的只读/方言/列探测、任务持久化及重启恢复、权限与版本隔离、提案原子接受及重检、Ossie 纯文件/ZIP 的逐 RT 往返、实例与指标实际数值、1440×900 视觉和局域网 HTTP。离线检查不能冒充真实建模成功。

**用户已决定的交付节奏：数据集与值类型都实现完成后，与 token/harness 合并做一次真实建模验收。** 此前可按计划做确定性离线和数据库验证，不分阶段调用模型做“试跑”。本轮完成离线实现；真实数据库、视觉、局域网及联合模型验收交由 Claude 后续执行。
