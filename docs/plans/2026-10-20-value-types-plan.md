# 值类型实施计划

日期：2026-10-20。状态：待 Claude review、用户确认后实施。本轮只新建本文和[值类型设计](../design/2026-10-20-value-types.md)，没有代码、契约、技能、提示词、测试或现有文档修改，也不调用 DataAgent/模型、不 commit/push。

## 1. 前置条件与完成口径

按设计已确认决定 VT-01–07交付最小值类型库。开工前完成 Claude review 和设计 Q1–Q5 的用户取舍，更新决定表；当前推荐是 Rule.owner=value_type、属性互斥选择内置类型/类型引用、无值类型继承、影响预检后统一传播、可证明矛盾阻断、引用未解除不可删除。未确认项不由实现者自行拍板。

以名称统一后的 core-1 为实现基线，不恢复 technical_name、旧 ai_context 内嵌扩展或值概念折叠。实施前重读生效设计及并行任务最终文件；本轮工作树已有大量他人未提交修改，不能覆盖、回滚、格式化或整理它们。

下文阶段按“模型与契约 → 校验 → 提案/发布 → MCP → Ossie → 技能 → 前端”顺序列出文件和测试。**测试先编写/补齐，全部编辑完成后统一执行一次验证批次**，遵守 AGENTS.md；不是每个阶段结束就运行一遍。文档、fixture和测试数据全部使用虚构空间与业务表名，代码注释英文、文档与界面中文。

## 2. 分阶段工作

### 阶段一：模型与契约

涉及文件：

- `apps/api/src/ontofoundry_api/domain/core.py`、`models.py`：ValueType、value_types、Property.value_type_id与可空value_kind、RuleOwnerKind、ElementKind/ELEMENT_MODELS/COLLECTIONS；互斥字段本地校验。
- `domain/graph.py`：类型索引、引用使用属性解析；`domain/core_canonical.py`、`canonical.py`、`snapshot.py`：类型感知的默认省略、稳定哈希、旧快照默认读取。
- `contracts/export_core_schema.py`、`export_schema.py`、`proposals.py`及生成的 `ontofoundry.core-1.schema.json`、`ontofoundry.proposals.v1.schema.json`、必要的 `ontofoundry.api-read.v1.schema.json`等。均在 API 包内的 contracts/，不是仓库根目录。
- `scripts/generate_core_types.mjs`（只在生成器确有适配需要时改）、`apps/web/src/api/core.generated.ts`、`api/types.ts`：权威生成类型和显式读投影分开，更新 TargetKind/ElementSaveKind。

实现要点：ValueType只有id/name/display_name/value_kind/description/evidence；不存constraints、使用数或复制基础类型。字段一侧非空另一侧null/省略，Schema oneOf 与 Pydantic检查完全一致；提案after的UUID引用可接受client_ref。跨字段validator不会自动导出为Schema，权威生成路径须显式输出类型二选一、值类型Rule只能constraint的限制，after引用转换亦须保留。CoreDraft缺value_types默认空、旧属性缺value_type_id默认null。core-1/v1标签建议不变，和数据集来源合评后统一定案。

不考虑旧数据（设计 VT-13）：新字段按普通默认值参与哈希，不做省略规范化，也不做旧样本金样回归。

计划补齐的测试：`apps/api/tests/test_core1_models.py`、`test_core1_schema.py`、`test_t1_proposal_contract.py`、`test_core1_native_roundtrip.py`，必要时新增 `test_value_types.py`。覆盖七基型、名称/保留概念名、未知字段、选择互斥、client_ref、新类型修改改变哈希。前端 `src/test/core1Fixtures.test.ts`检验生成契约。此阶段不新增迁移，不改历史JSON。

### 阶段二：语义校验与公共解析

涉及文件：

- `domain/validation.py`、`expressions.py`、`dependencies.py`、`graph.py`；可新增一个纯领域 `value_types.py`集中effective_value_kind/约束解析，避免API服务/UI各有一套逻辑。
- 原先读取Property.value_kind的消费者，重点 `domain/instance_validation.py`、`instance_display.py`、成员条件和实例相关服务；实施时用rg全量查调用点，不顺带重写指标类型逻辑。
- `services/errors.py`及调用边界：领域抛结构校验错误，服务层转ServiceError英文code/中文message；api只路由、校验、权限，不从服务抛HTTPException。

实现要点：值类型引用存在且本空间；共享概念命名空间按Q4；Rule.owner_kind=value_type只允许constraint，以当前类型name为唯一裸标量变量。表达式解析保持UUID与字面量边界，要求布尔结果，禁止跨元素/物理列/关系/聚合/查询参数。REGEXP_LIKE显式扩展语义白名单，限定常量正则子集，不进入数据库执行白名单。

约束按非空值语义AND，空值不改变required，局部更宽不能覆盖共享条件。Q3确认后实现有限范围/枚举交集矛盾检查；复杂表达式无法判定只作派生提示，不增加solver和核心状态。基础类型用于既有事实校验，不新增规则执行器或业务库扫描。

计划测试：`test_core1_expressions.py`、`test_core1_dependencies.py`、`test_core1_instances.py`、新增 `test_value_types.py`。覆盖金额12.34/12.345的声明表达、手机号ASCII数字与正则语法、枚举文字、空字符串与null边界、布尔表达式、非法路径/参数/函数、字面量改名保护、实体继承沿用同属性id及使用数去重。定义冲突用领域输入测试，不把对表达式的人工期望写成已存在的数据执行结果。

### 阶段三：提案、保存、发布与影响展示数据

涉及文件：

- `contracts/proposals.py`、`services/proposals.py`、`model_result.py`、`model_review.py`：接纳新种类、client_ref解析、依赖组、修正回读；harness相关共享改动须等其收口后由指定负责人接入。
- `domain/dependencies.py`、`services/element_save.py`、`element_diff.py`、`publish_preview.py`、`version_diff.py`及已有接受/撤销/重放逻辑；`api/proposals.py`等入口和保存请求类型只补必要Schema/权限。
- `services/import_matching.py`、`imports.py`及统一引用重写：原生先UUID锁定、Ossie按name/kind匹配；类型引用和归属规则同步重写。
- `services/ontology_context.py`、提案上下文和`element_hashes`路径，完善空值类型快照及全量集合遍历。

实现要点：类型及归属规则组成编辑范围；同批创建不依赖输入顺序，拒绝上游不能接受悬空下游。类型改名显式携带Rule重写提案，value_kind变化重检下游，不转换事实。删除必须先显式改绑/删除引用及归属Rule，沿最终图判断；撤销亦重算依赖。

纯约束修改显示Rule差异及类型使用影响，不为未改属性制造提案。类型哈希不含规则，因此UI保存和Agent均必须校验完整草稿修订/哈希。发布三方合并按latest和merged重算影响，新引用、新局部约束、并发Rule修改不能漏报；旧发布快照不动，预检过期重新生成。

计划测试：`test_t1_proposal_contract.py`、`test_t3_proposal_results.py`、`test_t4_proposal_decisions.py`、`test_proposal_undo.py`、`test_element_save.py`、`test_element_diff.py`、`test_t6_publish_preview.py`、`test_core1_import_matching.py`；真实事务保障使用已有disposable PostgreSQL用例。覆盖create/update/delete/拒绝/撤销、before/hash过期、归属规则变了但类型hash没变、名称互换组、类型删除与属性改绑组、并发新增引用、两边不同元素修改后产生类型冲突、发布diff不出现N个伪属性修改。

### 阶段四：MCP与问数语义投影

涉及文件：`services/mcp_ontology.py`、`ontology_query.py`、`ontology_context.py`、`api/mcp.py`的工具说明/Schema，以及API-read Schema与相应前端读类型。缓存、cursor与resource_items新种类统一接入，不新建第五个工具。

实现要点：两工具kinds加value_type；按名称/标识/描述检索，目录/批量详情含新类。Property和对象嵌套属性semantic投影给有效value_kind、value_type_id与类型摘要；definition保持核心输入形状。include=rules返回局部rules和分页value_type_constraints，原Rule id/owner保留，不复制为属性规则。类型没有物理来源；证据、数量和使用清单按原权限过滤。工具说明解释声明不是自动过滤，不改问数提示词。

计划测试：`test_core1_mcp.py`、`test_core1_permissions.py`、`test_ontology_query.py`、`test_session_read_cache.py`。覆盖kinds筛选、目录0、独立类型/属性/对象嵌套一致性、规则owner、引用与直接内置类型两支、include组合、无证据/物理权限、100条与256KiB预算、规则多页与长字段、权限或发布变化cursor失效、旧固定版与当前发布版隔离。只在测试内直接调用服务或本地HTTP，不调用DataAgent/模型。

### 阶段五：Ossie与原生格式

涉及文件：

- `adapters/ossie/importer.py`、`exporter.py`、`rules.py`、`translation.py`、`ids.py`、`extension.py`；`mappings.py`、`export_mappings.py`核对标识/多元值角色使用类型，指标文件只回归不扩功能。
- `adapters/ossie/validator.py`只调整本功能必要衔接，保持IDENTIFIER_ON_VALUE_TYPE等输入错误；**不修改vendored schema及PROVENANCE所锁上游版本**。
- `adapters/native/importer.py`、包读写及统一导入引用匹配；报告类型Schema和前端标签随新种类同步。
- 主设计§5–7/RT表和例子03/08：实现时同步，本轮不改。

实现要点：导入全部显式类型含未使用者，共享规则一次、属性引用UUID；多级/多父值继承按Q1方案，不能任取首父，能闭合者报告结构损失，不可解析整条规则留原文。导出直接七基型ValueType及requires、共享roles.concept，局部Rule仍在属性关系。取消内置标识属性辅助类型、允许仅值类型模型导出，均须用官方Schema和本地语义lint证明合法。

ZIP显示名/规则身份用现有独立扩展映射；不添加“生成类型”核心字段。纯文件中文名不恢复须明确，原生完整包含类型/规则及证据材料。RT逐条按设计§8.3更新，不新占RT编号，避免与数据集来源冲突。

计划测试：`test_core1_ossie_import.py`、`test_core1_ossie_export.py`、`test_core1_ossie_roundtrip.py`、`test_core1_translation_report.py`、`test_core1_native_import.py`、`test_core1_native_roundtrip.py`，同步`tests/rt_cases.py`和相关fixture。最低矩阵：

| 场景 | 必须证明 |
|---|---|
| 一份money被两个属性使用、一个未使用会员等级类型 | 类型各一份，money规则不复制，引用和未使用类型往返保持。 |
| 金额/枚举/手机号正例、局部属性更严规则 | 两级规则归属分开，REGEXP_LIKE表达式能合法交换；不可承载项明确报告。 |
| 直接内置类型标识、显式类型标识、多元值角色、标识复制属性 | 官方Schema/语义校验通过，不生成伪用户类型，角色生成属性保留引用，原映射/标识仍闭合。 |
| 多级/多父/菱形值继承、冲突基型/循环 | 祖先规则按来源去重，结构损失RT-24；不可闭合RT-35，整条失败不半句转换。 |
| 值类型关系/derived_by/identify_by、依赖关系的requires | RT-29/24/31和原语义lint定位准确，不丢原文，不重复计数。 |
| 仅值类型、空本体、仅数据集指标 | 前者可导出，后两者无假概念；不要求必须EntityType。 |
| ZIP/纯Ossie、原生完整包/缺材料单文件、跨空间匹配 | 显示名与规则元数据边界准确，证据权限/报告不变，所有类型引用正确重写。 |

### 阶段六：建模技能与harness衔接

仅在harness改动收口后改其最终结构，不并发覆盖当前源码。预计文件：

- `integrations/dataagent/skills/ontofoundry-modeling/references/quick-reference.md`、`core-model.md`、`extract-types.md`或harness最终确定的方法章节、`reading-ossie.md`及`references/examples/`正例/索引。
- 技能`SKILL.md`只加路由和必要入口，不复制核心规则全文；`scripts/check_result.py`、`prepare_result.py`、`read_input.py`、`show_example.py`等按收口后的实际职责适配，避免另写新检查协议。
- `apps/api/src/ontofoundry_api/services/modeling_input.py`只扩value_type摘要、计数、规则回读pointer；`services/dataagent.py`如确须更新工具/契约动态说明，由harness负责人接入，不增加类型教学长段落。
- `integrations/dataagent/README.md`后续写技能复制/重启步骤，保持现有Agent不创建/修改、问数提示词不动。

只加正例和方法：先检索已有类型，比较规则与业务域；明确材料证据才能建统一类型，列物理precision不等于业务两位小数；局部例外留局部规则，共享收紧列使用影响。复用例不新建重复money，不能仅按类型显示名相同推断等价。

计划测试：技能既有`tests/test_check_result.py`、`test_workflow.py`及harness新增离线fixture/预算用例，增加值类型create/update/delete和复用、批内client_ref、局部叠加、改名及删除依赖正例经真实服务端parse_result通过的覆盖。非法输入是程序测试mutation，不扩展教学反例目录。offline_budget核对新路由/示例不突破harness已定预算，不生成dist、不启动DataAgent、不调用模型、不把离线大小当usage。

### 阶段七：前端与概念文档

涉及文件：

- `apps/web/src/pages/TypeCatalogPage.tsx`，可新增`components/elements/ValueTypeDialog.tsx`，复用Ant Design Form/Modal、layout/FormRow/SectionTitle和现有保存预检。名称普通文本，五页签及catalogTab兼容既有三项。
- `components/elements/PropertyMappingTable.tsx`、`ElementPanels.tsx`、`ElementInspector.tsx`必要分派、`pages/ElementDetailPage.tsx`的属性定位；值类型不接入独立详情路由。目录定位与已有引用导航hooks配合。
- `lib/coreModel.ts`、`elementModel.ts`、`objectMapping.ts`及实例格式、图谱属性标签消费者，共用有效类型函数；`components/OntologyGraph.tsx`、本体视图和构建结果只更新属性类型/类型阅读入口，不画新节点。
- `components/proposals/elementMeta.ts`、`reviewMeta.ts`、`FieldDiff.tsx`、提案/发布组件，显示值类型与归属规则差异、使用影响；不产生未改属性的差异。
- `api/client.ts`统一调用；`styles/tokens.css`只在确需新视觉变量时变更，禁止新增手写控件/零散CSS。`docs/design/2026-10-17-ui-visual-consistency.md`§4先补目录编辑弹窗模式；引用导航和目录/UI-019/UI-024记录五页签与值类型例外。
- 概念文档与主设计按设计§11清单更新；新增`docs/concepts/value-types.md`。数据来源相关页面/概念段落交其负责人合入，不顺带改语义。

界面行为：列表完整业务信息，使用数展开实时去重属性列表，点击属性到owner实体详情并定位；弹窗编辑类型+归属规则，不做查看详情页。类型Select分组且切换互斥；属性上只读展示基础类型和共享规则。无权限/0/长表达式/失效引用/未保存/并发预检覆盖完整，value_type入口不落到通用详情路由。新id使用newId()。

计划测试：`TypeCatalogPage.test.tsx`、`PropertyMappingTable`对应测试（可新增）、`ElementInspector.test.tsx`、`test_element_save_navigation.py`及提案/发布组件测试。新增值类型对话框测试、实际展开与跳转、选类型互斥、继承只读、保存影响、只读与0状态、没有详情链接/图节点。

视觉fixture使用虚构空间“青岚演示”，金额/会员等级/手机号三类型、两个直接使用属性、一个继承使用、一个未使用类型、长约束行。截图覆盖设计§9.5矩阵，并更新`e2e/visual/lists-settings.spec.ts`、`elements.spec.ts`、`builder-canvas.spec.ts`、`publish-proposals.spec.ts`及相关fixtures；数据集页签截图由来源任务提供后合测，不盲目批量更新所有golden。截图对比容器层级、24/16对齐线、12/14/16字号、状态、表格密度，1440×900固定视口；另用窄容器检查属性布局与键盘操作。

## 3. 与数据集来源及harness的实施顺序

撰写时 `docs/design/2026-10-20-dataset-sources.md`尚未出现；下表是交接约定，不推定其模型和RT变化已经确认。来源设计完成后，两项一起review字段和排期，本计划按确认结果调整，不编辑对方设计文件。

| 共享改动点 | 顺序与归属 |
|---|---|
| harness的skills/、dataagent.py、modeling_input.py | 当前harness先收口；值类型阶段六再基于最终文件加种类、摘要、正例和方法。不得覆盖其预算/工作包/修复机制，不把本功能塞入正在进行的实现。 |
| core.py、models.py、Schema及TS生成文件 | 推荐先落值类型模型/互斥类型及哈希策略，再由来源实现接其自己的字段；若来源已先落地，值类型重读后叠加。指定一位契约负责人维护两项最终Schema与生成类型，收口后统一再生成，不各交一份不同基线。 |
| validation/dependencies/canonical、proposal解析与发布 | 值类型只增Property→ValueType及类型Rule上下文；来源保留Dataset/Metric自己的依赖。避免新增全局规则将两者错误连起来；合并候选图同时验证。空默认哈希策略须评估两项组合，禁止各自无迁移却重算旧基线。 |
| ontology_query/mcp_ontology/API-read | 合并值类型语义投影与来源物理投影，复用授权/分页。类型不接来源，Dataset/Metric不因value_type改变算法；两项分别可测试，最后组合验证。 |
| Ossie importer/exporter及主设计RT表 | 适配器先接稳定核心模型；指定一人串行合并共享文件。值类型只改本设计列出的RT，不占新编号；来源任务负责它的新格式边界。统一再跑官方校验和往返矩阵。 |
| TypeCatalogPage、目录catalogTab和视觉fixtures | 数据集来源负责人实现datasets列表及入口；值类型负责人实现value_types列表/弹窗。由一个目录集成者合并为已确认顺序五页签，实体标签统一“实体类型”，不能各自新增第二个本体目录。 |
| 主设计/概念README/格式说明/技能速查 | 各提供自己范围的补丁清单，由最终集成者串行合入；不还原对方已确认内容，不把新类型加到Dataset.columns。 |

推荐关键路径：两项设计review和用户确认 → harness收口 → 两项模型/契约统一 → 各自校验/提案/MCP/Ossie → 技能一次合入 → 五页签及属性界面合入 → 全部编辑完成后统一离线/事务/视觉验证 → 双功能准备就绪 → 后续真实建模验收。阶段内可开发独立模块，但共享文件和生成产物串行交接，不要求另启并行Agent。

真实建模验收前，两项必须均可从材料形成合法提案、审阅/接受/发布、MCP读取；值类型三个正例和来源设计自己的必验来源场景都可追溯。离线验证不替代真实建模和问数语义验收，但本轮不请求/执行真实运行。

## 4. 统一验证批次与部署交接

以下是将来实现后的命令计划，本轮不执行。若并行任务变更实际命令，以收口的Makefile/README为准，不为凑通过跳过检查。

| 检查 | 建议执行方式 |
|---|---|
| Schema权威生成与漂移 | 在apps/api运行export_core_schema和export_schema相应生成/检查命令；apps/web执行`npm run generate:core-types`后用`npm run check:core-types`验证。生成在全部契约编辑后统一做。 |
| 后端 | 在apps/api用既有uv Python3.13环境统一运行`pytest -q`；重点观察上列类型/哈希/依赖/发布/MCP/Ossie用例。 |
| 事务 | 通过仓库已有测试入口提供显式disposable PostgreSQL URL，覆盖接受/撤销与发布事务；不能指向开发业务库。无环境则如实记录未验证，不能声称通过。 |
| 技能 | 运行README中的离线技能测试及offline_budget，不调用模型；服务端parse_result fixture与新Schema相符。 |
| 前端 | apps/web统一执行`npm run test -- --run`、`npm run build`、`npm run lint`，失败定位修正后再跑相关检查。 |
| 视觉 | 1440×900检查改前/改后截图，统一执行`npm run test:visual`；基准变化须说明并供人工review，不能只用更新快照消除失败。 |
| 局域网HTTP | 在实际局域网IP地址验证类型创建、规则保存、属性Select、使用属性定位和发布，核对非安全上下文id生成；记录访问地址和结果，文档只用虚构业务数据。 |

本任务不重跑名称统一的数据清空迁移。后续部署由发布人员同步前后端、Schema与技能，替换整个技能目录到SKILLS_ROOT_DIR并重启DataAgent，平台应用重启清缓存；不新建或修改既有Agent，不更新问数提示词，不修改共享模型参数。若本功能未改任何Agent提示词，就不为它重复后台发布提示词。

回退时保留备份与原生完整包；旧严格程序不能读取已发布值类型文档，不通过清空/折叠新类型实现无损回退。需要回退到不支持值类型的软件时先确认可用旧发布版本/备份与部署兼容范围；这是后续部署交接条件，本轮不部署。

## 5. 验收清单与本轮交付

- 第1节七项已确认能力全部有实现证据；Q1–Q5形成明确决定，不把推荐当确认。
- 新旧草稿哈希、Schema/Pydantic/TS、提案依赖及并发发布一致；无数据库迁移和隐式数据改写。
- MCP读到共享定义，Ossie保留支持范围内类型/引用，剩余RT和非法输入清楚报告。
- 五页签、完整值类型行、编辑弹窗、使用属性导航、属性类型分组及共享约束符合视觉/权限规范；图上没有值类型节点、没有值类型详情页。
- 主设计/概念文档/方法与正例同步；数据集来源和harness共享改动完成交接，统一测试有实际结果，真实运行留在后续授权阶段。

本轮交付为两份待评审文档。没有运行测试、浏览器、DataAgent或模型，没有代码/技能/提示词/测试编辑，也没有commit/push。Claude review尚未执行；由用户安排评审并确认后再进入实施。
