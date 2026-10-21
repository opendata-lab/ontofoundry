# 数据集两种来源实施计划

日期：2026-10-20。状态：按 DS-01–DS-17 执行离线实现。依据：[数据集来源设计](../design/2026-10-20-dataset-sources.md)。不调用外部服务，不 commit/push，不运行 Playwright。

## 1. 实施约束

先统一设计和计划。保留名称统一、token/harness 的既有未提交编辑；只为值类型加空页签。Dataset 直接保存 connection_id，所有导出剥离 id，只带连接名称提示。不保存不支持的原形，不加绑定上下文。同步任务使用进程内执行，启动标记中断，人工重试，不做租约或多 worker。无旧数据兼容；必要清理通过新增迁移说明。全部编辑后集中运行用户指定离线检查，真实数据库、视觉及局域网留待 Claude。

## 2. 阶段一：后端模型、来源校验与消费方

目标：Dataset 能表达表或 query，显式平台绑定一个连接；所有平台查询共用只读校验与来源构造。映射、simple/ratio/expression 的单数据集合同不变。

| 工作 | 涉及文件（未存在者为建议新增） |
|---|---|
| 两来源互斥、query_sql、条件 table_name、可选命名方案 | apps/api/src/ontofoundry_api/domain/core.py、core_canonical.py、canonical.py、validation.py、dependencies.py；仅在本任务所需边界增量修改 |
| Pydantic/JSON Schema/前端类型一齐生成，提案允许结构合法但物理未就绪候选 | contracts/ontofoundry.core-1.schema.json、contracts/proposals.py、ontofoundry.proposals.v1.schema.json、read_models.py、建议 dataset_sources.py 契约、apps/web/src/api/core.generated.ts、types.ts、scripts/generate_core_types.mjs |
| 平台绑定、SQL AST/函数白名单、登记解析、血缘与 fanout 检查、LIMIT 0、预览 | services/dataset_sources.py、readonly.py、建议 dataset_validation.py、dataset_query.py、dataset_lineage.py、errors.py；API 新路由只校验与授权，建议 api/datasets.py、main.py 路由注册 |
| 连接随 Dataset 流转 | Dataset.connection_id 随现有 JSON 复制；导出移除 id，原生及 Ossie 扩展保留 connection_name；导入按名称唯一匹配 |
| 未同步提案派生诊断、接受前重检与确认、依赖闭包 | services/core_validation.py、model_result.py、proposals.py、model_review.py、element_save.py、api/proposals.py、相关读写契约；不新建 proposal.status，不要求 harness 把未同步当格式错误修复 |
| 实例、关系、指标和 SQL 参考消费 query | services/instance_plan.py、instance_query.py、instance_neighborhood.py、metric_query.py、metric_preview.py、ontology_query.py、physical_projection.py、public_projection.py；删除业务使用路径中仅物理 Table 的假设 |
| 实时发现与业务登记隔离 | api/connections.py 的 /tables 与 table-material、services/table_material.py 等；读表材料必须使用已登记来源，人工发现只供同步选择，固定工作包不因审阅同步而改变 |

核心 JSON 增字段无需新增列。新增任务/批次表和清理旧内容使用 Alembic；不新增来源上下文或交换原形。

先使用现有登记快照完成来源门槛，阶段二再替换同步产生机制。SQL 解析不执行网络；探测必须在平台数据库写事务外，短事务复核 revision/授权/元数据指纹后提交，避免锁住草稿等待业务数据库。

统一测试：扩展 test_core1_models.py、test_core1_dependencies.py、test_core1_metric_preview.py、test_core1_instances.py、test_core1_lifecycle.py、test_element_save.py、test_t4_proposal_decisions.py；新增 test_dataset_sources.py、test_dataset_sql_validation.py、test_dataset_proposals.py（建议名）。至少覆盖：

- table/query 字段互斥，旧外部表形状规范化，源类型变化稳定 id，生成类型与 Schema 同步。
- 多语句及空语句、写 CTE、SELECT INTO/锁、恶意函数、参数、系统目录、隐藏子查询/UNION 分支、CTE 遮蔽、部分复合键、全限定及带引号列；既有字符串里的占位符不误拒。
- “只有同名另一连接登记”“只在 /tables 发现”“已有自报 columns”“表已移除”“旧登记刷新失败”分别断言登记结果与 reason code。
- LIMIT 0 的 MySQL/Doris/PostgreSQL 类型码、CTE 嵌入、输出别名/重名/未知类型、外层限制、超时取消；真实数据库执行才能证明支持，mock 仅用于故障分支。
- 销售 100、退款 10/20 的 fanout 警告；UNION ALL 30%、两事实先聚合 20%、维度连接保持 150；SQL 仅输出明细时，外部指标仍能触发风险检查。
- 无映射权限不得泄露 SQL/表名，无实例权限不能预览；表单输入改变使旧探测/确认失效。
- 未同步候选可保存为 pending，接受失败不写草稿；同步后列错定位到对应映射/指标；相关组原子失败、独立项继续；ratio 间接依赖重新校验。
- 会话修改连接不覆盖已发布版，合并/撤销/幂等重放保持来源上下文，数据库凭据不进入核心/MCP/导出。

完成标准：在同一虚构来源上，表与 query 均可驱动实例和指标，所有执行入口遵守同一登记/只读/权限规则。未完成前不接 Agent 实测。

## 3. 阶段二：持久化后台同步任务

目标：去掉全 Schema 200 张/15 秒总限制，已完成部分马上登记，进程内执行，重启标为已中断并可重试。

| 工作 | 涉及文件 |
|---|---|
| jobs/batches、索引、状态与查询契约 | db_models.py、alembic/versions/ 新增结构迁移、建议 contracts/metadata_sync.py 及对应 API Schema |
| 分离同步业务、逐表观察/检查点事务、全量库存/指定表、漂移合并 | api/assets.py、建议 services/metadata_sync.py、metadata_registry.py；保留 schema_diff/retain_schema_changes 行为但移出路由业务 |
| 进程内后台任务、连接/Schema 串行、启动中断标记 | 建议 services/metadata_worker.py、main.py 生命周期、config.py；使用 BackgroundTasks；重启不自动重领 |
| 202 创建、轮询与失败批次重试，/assets 分页 | api/assets.py、api/connections.py、相关 OpenAPI/读写 Schema；refresh 的调用方后续一次切到任务协议 |
| 同步完成触发审阅重检 | 来源诊断缓存失效服务、提案批量校验 API，模型上下文只消费登记结果，不改运行中工作包 |

迁移只因新增表/索引，不迁移本体内容。登记表的 kind、主键顺序、外键、逐表 observed_at/存在性观察在现有 JSON 内增加，由真实同步观察填入。建议批量 20 张、每批 15 秒；枚举/单表超时独立记录；全量总表数不限，指定表同机制，空 selected 拒绝。

统一测试建议新增 test_metadata_sync.py、test_metadata_sync_postgres.py，扩展原 assets/connections 覆盖位置（实施时按测试目录实际文件归并，不假设已有同名测试）：

- 虚构 Schema 245 张以上含视图，成功分页分批无 200 限制，批次 duration/attempt 可追溯；单表指定同步只观察该表，不先枚举全库。
- 枚举失败不作删除；全量完整库存才观察移除；部分同步不影响未选对象；一个批次某表失败时成功表立即可用，首次失败表不登记。
- 服务重启后 queued/running 任务和批次标为 interrupted，重试不重复成功成员，成功部分仍已登记。
- 同进程同连接/Schema 串行；连接删除后任务明确失败；读取业务库期间不持平台写锁。
- schema_diff 的未处理漂移保持，表级新鲜度如实显示；主键顺序、同名不同 Schema、view 无主键都正确。
- API 响应与平台数据库 jobs/batches/快照同时断言；异步等待使用有上限的重试和诊断，不在测试源码启动/重启容器。

完成标准：重启后展示已中断任务，人工重试完成原 job，已登记成功部分不回退；用户返回页面可通过 job_id 恢复进度。

## 4. 阶段三：MCP dataset 类型与 SQL 参考

目标：两工具能搜索/读取数据集，保留四工具、只读、现有协议版本和固定本体版本机制。

文件：services/mcp_ontology.py（Kind、lookup、搜索、definition 与引用分页）、services/ontology_query.py、physical_projection.py、dataset_sources.py、api/mcp.py（工具说明）、相关工具读模型/Schema。明确不改 integrations/dataagent/agents/agent_ontofoundry_qa.md，不新增查询或查表工具，不加 version_id 入参。

统一扩展 test_core1_mcp.py，必要时拆 test_dataset_mcp.py：

- 按名称、英文标识（U-01）、描述、table/query 叶子表名搜索，目录 0 与有值计数准确。
- get_ontology(ids,kinds,include) 的 semantic/physical/adjacency 边界；无映射权限连命中/计数也不泄露，直查沿既有 missing 规则。
- query 原文分段、列和三类引用分页，总 wire 预算不超过 256 KiB；游标包含模型版本、权限和投影。
- 映射/指标的嵌套 Dataset 同样有 source_kind，不再从 table_name 拼 query；simple/ratio SQL 参考嵌入子查询，分量过滤与时间保持。
- 发布切换的 cursor_invalid、建模 pinned_version_id、旧版不可用错误、权限变化缓存失效；业务元数据变化不使固定版本偷偷跳至新模型。

完成标准：现有工具名、协议协商和客户端接入保持，工具响应足以供既有问数 Agent 选择并嵌入来源，无需提示词变更。

## 5. 阶段四：Ossie query、跨数据集转换与往返

目标：直接 query 对应；可证明安全的跨表指标生成待审阅依赖组，不安全/不明项继续待补全；类型、时间和扩展字段的保存边界可逐 RT 核对。

文件：adapters/ossie/mappings.py、metrics.py、export_mappings.py、export_metrics.py、importer.py、exporter.py、extension.py、translation.py、ids.py，adapters/base.py、exporting.py 的来源上下文，services/imports.py、import_matching.py、import_completion.py、exports.py，以及原生完整包读写与平台 exchange_shapes 流转。vendored 上游 Schema 不修改；扩展读取白名单显式增加新字段。

先做 table/query 分类和匹配引擎方言，再做字段 datatype/is_time，随后接 relationships 转换和时间字段回读。外部适配器不访问业务库；连接匹配、注册核对和探测通过阶段一共用服务。不为自动转换新增核心 relationships，不从本体推指标 JOIN。

统一测试扩展 test_core1_ossie_import.py、export.py、roundtrip.py、test_synthetic_ossie_roundtrip.py、rt_cases.py 和纯虚构 fixtures；新增测试文件按需要拆分，不改既有预期掩盖差异：

- 单表、视图、query、非递归 CTE、JOIN、UNION ALL、UNION 的合法 source 往返；多语句/写语句/未匹配连接/未登记叶子保留原文与定位，不能伪表名。
- 一条销售明细对应唯一且完整产品外键的 80 元案例，生成 query Dataset + 单数据集指标的原子待审阅组；歧义路径、缺失键、缺匹配、fanout 15%/30% 不硬转。
- 字段和指标选择引擎匹配方言，省略其他变体报告；未知引擎不猜 mysql，专属函数不标 ANSI_SQL；字段同行边界仍生效。
- datatype 属性/列类型一致、冲突、未知、DateTimeTz/Time；is_time 按已声明用途而非日期类型自动选择；label 确实 dropped 并有 RT-46，不暗转显示名。
- 快照/指标时间 ZIP 恢复，纯文件不从 is_time 猜 time_field；扩展坏引用、过期原形、角色重排、多作用域同名数据集的定位和指纹拒用。
- 一元、多元完整时间字段回读；编辑/外部新增引用后安全回退规范形状并逐项报告；无溯源的新建中间对象不能猜原多元；原生完整包仅保留连接名称提示。
- 每份输出经过 vendored 官方 Schema 和语义校验，每一处往返差异都有设计 §9.5 的 RT；支持 query 不放宽空 ontology 等其他边界。

文档同批更新主设计 §5–§7、Ossie 支持表/例外表、格式说明；RT 编号保持，不能覆盖值类型负责的 RT-23/24/35 等。完成标准：带扩展 ZIP 和纯文件分别有准确的恢复/损失报告，不能只测 ZIP 宣称标准文件无损。

## 6. 阶段五：技能新增正例与方法章节

目标：在并行 harness 已完成的结构上增加来源写法与粒度方法，不重构 harness，不修改问数提示词。

建议涉及 integrations/dataagent/skills/ontofoundry-modeling/references/examples/ 下新增来源/指标正例；在 references 的数据集/指标/映射抽取方法章节追加粒度、时间和安全连接方法；沿 quick-reference/既有示例 catalog 接入 target_kind/operation 查询入口。确切文件名按 harness 合并结果确定，不提前触碰并行路径。SKILL.md 仅在需要索引新增章节时作最小链接调整，不另建反例目录或完整 Schema 副本。services/dataagent.py、modeling_input.py 的契约衔接只在对方完成后增量集成。

正例至少包含：table/query 的最小结构；UNION ALL 销售退款 30%；先聚合后连接 150/30=20%；事实到唯一维度保持 150；未同步表可提议但由人去同步；Ossie query/安全转换。业务坑在方法章节用数字说明，不生成错误提案供 Agent 阅读。

统一离线校验：每个正例通过当前契约和 harness 既有 check_result/prepare_result 流程；模型字段与平台绑定 envelope 不混淆；可从查写法入口找到，不增加共同必读预算。错误构造仅在测试中验证诊断路径/期望/实际值。记录新增材料字节预算，遵守 harness §11 的 ≤8,200 B 共同必读与 ≤22,000 B 首轮总量、两轮修复共享预算等已确认决定；以最终合并的预算脚本输出为准。

本阶段不调用 DataAgent/模型试跑。后续部署按 integrations/dataagent/README.md 复制至 SKILLS_ROOT_DIR 并重启；平台只引用已有 Agent，不创建/修改 Agent，不生成要提交的 dist。若本任务仅增加工具说明和技能内容，不顺带发布系统提示词改动。

## 7. 阶段六：前端目录、详情、同步与审阅

目标：在现有布局内使数据表登记、本体数据集和表达式来源各有明确入口。

| 工作 | 文件 |
|---|---|
| 五 Tab 及数据集目录、实体类型改名，保留关系名 | pages/TypeCatalogPage.tsx、目录参数类型与路由/页签状态；值类型内容由并行任务接入 |
| 数据管理改数据表/文档，后台任务进度/重试 | pages/MappingsPage.tsx、components/DatasetPicker.tsx 拆分现有“同步与登记”职责，建议 TableSyncPanel.tsx；不再从管理页创建 Dataset |
| 数据集详情五 Tab、表/表达式新建编辑、校验预览 | components/elements/DatasetPanel.tsx、DatasetLocationFields.tsx、DatasetSnapshotFields.tsx、ElementInspector.tsx、ElementDetailPage 现有页面框架、lib/datasetEditing.ts、elementInspector/elementModel/coreModel 相关来源展示 |
| 数据集选择器及所有映射/指标消费标签 | ObjectTablePicker、PropertyMappingTable、RelationMappingTable、LinkMappingPanel、MetricForm、MetricPreview 等现有组件；表/表达式数据集均可选，不再假设 table_name 非空 |
| 提案派生诊断、精确“去同步”、修改连接/表、依赖重检及风险确认 | components/proposals/ProposalCard.tsx、ProposalDetail.tsx、ProposalPanel.tsx、reviewMeta.ts、FieldDiff.tsx；ImportDialog/补全区域复用诊断结构 |
| API、布局和视觉规则 | api/client.ts 统一调用；api/types.ts 与生成类型；仅 components/layout/ + Ant Design 组装，视觉值只用 styles/tokens.css，需新模式先补 UI 文档 §4 |

表单使用 Ant Design Radio.Group、Form、Input.TextArea、Select、Checkbox，输出/引用使用紧凑 Table；不引入手写 SQL 编辑器、新 CSS 或 Pro 控件。所有前端 id 使用 lib/id.ts 的 newId()。查看/编辑沿顶部统一取消/保存，预览显式触发，切页签不改变框架尺寸，不把业务警告只做浮动消息。

统一前端测试扩展 TypeCatalogPage.test.tsx、MappingsPage.test.tsx、元素/提案/指标相关 Vitest；新增数据集来源表单和同步进度测试，覆盖：五 Tab 与旧链接、同元素页签去重、未保存编辑保护、source_kind 切换/连接切换失效、校验结果乱序、旧风险确认失效、无权限不预览、任务重返恢复、指定表只提交一张、同步后列错误回到对应提案、计数 0/未知/失败区分。

功能编辑全部完成后统一更新视觉用例：apps/web/e2e/visual/lists-settings.spec.ts、mappings.spec.ts、elements.spec.ts、publish-proposals.spec.ts、imports.spec.ts，按需要新增 dataset-sources.spec.ts，fixtures 只用虚构工作空间与表。

截图清单：五 Tab 目录；table/query 新建与详情五 Tab 的查看/编辑；长 SQL/风险/列错误/无权限预览；数据管理发现中/进度/部分失败/重试；未同步提案到同步和重检；表达式数据集的对象与关系选择器、指标预览、Ossie 待补全。固定 1440×900，与改前/基准比较容器、对齐、字号、状态和密度；审核差异后才能更新基准，不能自动全量接受截图。

完成标准：运行 npm run test:visual，并通过局域网 IP 的 HTTP 验证新建数据集、选择来源和预览，确认非安全上下文中 newId() 可用。窄容器只核对现有布局折叠，不扩展额外产品需求。

## 8. 统一验证和执行记录

以下是实施后的命令模板，本轮未执行。最终命令以合并后的脚本/测试名为准，执行记录给出原始命令与 Tests run/Failures/Errors/Skipped，环境不可用或 skip 如实记录，不称为通过。

```sh
cd apps/api
uv run --python 3.13 pytest -q
uv run --python 3.13 ruff check src tests
```

```sh
cd apps/web
npm run check:core-types
npm test -- --run
npm run lint
npm run build
npm run test:visual
```

另跑仓库 test-pg 的既有发布/决策/指标回归，并纳入新增同步并发恢复、来源上下文版本隔离测试。业务引擎 MySQL、Doris、PostgreSQL 分别跑受控集成套件，SQLite 不替代 CTE/白名单/类型探测支持证明。运行前核对测试库可达与只读账号权限，使用独立虚构命名空间和预置数据；环境启动/worker 终止恢复由外部操作执行，测试代码不重启容器。并行负载和超时故障与业务数值测试分开记录。

真实数据库测试只读业务数据；平台 jobs/版本/提案等允许在隔离测试平台库写入。清理脚本幂等并容忍半完成夹具，不能误删用户连接/表；真实建模任务不能复用错误构造夹具。优先断言数值、来源 lineage、诊断和平台持久化结果，而非只断言 HTTP 200 或 SQL 字符串含关键字。

全部阶段集成后统一更新 concepts：datasets-and-binding、metrics、query-semantics、time-and-snapshots、formats、ossie-compatibility、identifiers、README；内容见设计 §14，本轮不改。设计冲突、实际不支持的方言和未覆盖的风险应留在执行记录，不临时降低校验通过门槛。

## 9. 一次联合真实建模验收与交付

**用户决定：数据集与值类型都实现完成后，与 token/harness 合并做一次真实建模验收。** 等四项共同就绪、离线/数据库/前端检查完成，且实际模型调用进入用户授权实施范围后，再执行这一次；不在上述各阶段单独触发 Agent 试跑。本轮不调用模型，也不代 Claude 执行 review。

验收材料使用虚构空间“雾岭商贸”和 mist_sales、mist_refunds、mist_products、mist_lines 等表，包含两事实、不同业务日期、共享值类型、一张仅材料提到而未同步的表，以及明确 Ossie query/可转换与待补全片段。期望：

- Agent 用既有 harness 查最小正例并输出 query Dataset + 单数据集指标及证据，未同步项保留待审阅且运行中不调用同步；不可表达项按 harness 退出约定说明，其余合法项继续。
- token/工具调用和修复轮次可追溯，未反复枚举 Schema、未把未同步当格式修复，新增示例没有挤爆已确认阅读预算；值类型复用正确，目录五 Tab 协同工作。
- 人工在审阅页只同步缺失表，依赖自动重检；错误列留在对应提案，解决后原子接受；销售退款实际算出 30%，高风险连接不会默默变为 15%。
- 接受后的实例/指标预览、MCP dataset/SQL 参考、Ossie ZIP/纯文件报告均与该版本一致；问数 Agent 使用子查询的证明可在同次联合验收后续步骤收集，不为此修改问数提示词。

交付时给出两份设计的确认版本、实施差异、迁移结构清单、离线/数据库/视觉结果和唯一真实任务的结果及用量。没有真实验收证据则明确写未验收。仅在用户另行明确要求时 commit/push；不提交 .claude/、原型、评审报告或 integrations/dataagent/dist/，文档不链接原型。
