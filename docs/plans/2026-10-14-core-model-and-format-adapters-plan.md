# core-1 实施计划

基线：main `a39e3d2`（已合并设计 PR 21 与 AGENTS.md）。设计文档：`docs/design/2026-10-14-core-model-and-format-adapters.md`。核对日期：2026-10-16。

本文只安排后续实施。本次没有修改仓库、执行迁移、运行测试或创建提交。以下文件路径均相对仓库根目录；文中“新增”“删除”均是给实施者的任务。所有业务数据使用设计中的虚构示例，不把实际工作空间、业务库表、连接凭据写进代码、夹具、说明或测试日志。

## 1. 交付范围与阶段

规范来源为 `docs/design/2026-10-14-core-model-and-format-adapters.md`，尤其 §3–10、§13–14；已通读 `docs/concepts/` 13 页和 `docs/design/core-1-examples/` 的 README 与 13 份 JSON。主设计的决定表包含被后续修订取代的历史项，实施以当前 §3.6、§5.6、§6.5 和决定 49–51 为准，不能恢复对象指标、跨数据集指标表达式或数据集关系树。

建议仍分成六阶段。§9 第一部分较大，拆成“基础件”和“一次切换”；第二部分拆成“机械翻译”和“进入提案”；第三部分单独交付。P0 最先接入前端基础设施，再核对三个交互；基础设施进入后续实施代码，原型产物不提交。

| 阶段 / PR | 对应 §9 | 目标与交付物 | 前置依赖 | 合并与上线边界 |
|---|---|---|---|---|
| P0 前端基础设施、原型与准备 | 第一部分准备 | Ant Design 5 + Tailwind v4 接入、主题/测试/规则；三个交互与字段、路由、夹具核对 | 设计基线与已确认 UI 技术栈 | 基础设施可独立 PR，保持现有业务可用；原型不进 Git |
| P1 核心基础件 | 第一部分前半 | core-1 模型、校验、表达式解析、依赖和生成契约的基础设施 | P0 字段约定；前端验证依赖 P0-FE，不等视觉确认 | 可独立合并；新模块尚不接生产读写，现有运行仍完整；不接收或转换旧模型 |
| P2 全链路切换 | 第一部分后半 | 清空旧本体；读写、提案、发布、前端、实例、指标预览、四 MCP 工具、两类 agent 全部 core-1 | P1；新交互在实施前完成原型确认 | 必须一个完整集成 PR；可分内部提交，不可把半切换状态部署。此时导入、导出暂时下线 |
| P3 机械导入器 | 第二部分前半 | FormatAdapter 基础、报告、Ossie 和原生单文件导入器、RT 定向输入夹具 | P2 | 可独立合并；纯服务/库，导入入口仍关闭 |
| P4 导入提案流程 | 第二部分后半 | 预览/确认、材料与报告持久化、匹配和引用重写、会话提案、导入弹窗与待补全 | P3；导入原型 | 独立 PR，完成后开放导入；不增加发布通道 |
| P5 导出与往返 | 第三部分 | Ossie、原生单文件导出、官方校验、导出报告、RT 往返回归 | P4 | 独立 PR，完成后开放导出 |

P1 临时与旧实现共存的是未接入的开发模块，不是兼容运行：不写 core-1→v3 或 v3→core-1 转换器。P2 合并时删除旧运行模型和全部版本分支。不能把 P2 拆成“后端已换、前端继续转 v3”的可部署 PR。

以下不在这六阶段交付内：原生 ZIP 完整包、自动检测与完整适配器注册系统、完整自动 diff 分类器、导入后 AI 补全运行、数据集三类引用计数。P4 保存可补全清单和定位，提供人工选择/修改入口；真正的“用 AI 补全 N 项”执行按钮等后续能力完成后再启用，不能放一个会调用普通建模却不携带清单的假入口。单文件原生导出不得标为无损备份。

### 1.1 现有代码与工作的对应关系

| 当前实现 | 现状与必改点 |
|---|---|
| `domain/models.py`、`models_v3.py`、`snapshot.py` | 一个 OntologyDraft 混合 v2/v3；多父、角色、动作、语义树均在运行。新建唯一 core-1 定义后整条切换，非只改 schema_version |
| `services/workspaces.py::publish_draft` | 强制 as_v3_dict，compile_ossie、validate_ossie；版本表必存 ossie_json。发布须改为核心校验，Ossie 生成仅留在 P5 导出 |
| `domain/semantic_views.py`、`runtime_views.py`、`semantic_edit.py` 等 | 语义树与旧映射之间的投影/回写。替换为 Dataset + DataMapping 有效绑定解析 |
| `contracts/proposals.py` | models_for、_after_schema、parse_result 都含版本/角色分支；target_kind 没有可直接编辑的 core Metric/Dataset |
| `services/instance_query.py` | 强读 v3，document_object 保留 name，db_ref 把键转字符串，文档邻域使用 role_values。必须分离文档 UUID 与数据库 typed tuple |
| `services/metric_query.py` | MetricCompiler 读取 semantic_model/dataset_fields；存在 AST 白名单和只读执行，可保留能力、重写输入模型 |
| `api/mcp.py` | 当前 13 个工具，tool_schema 自动给全部工具加 version_id；source=database、query_metric 仍可执行数据库查询。需收敛为四个语义/文档事实工具 |
| `api/semantic_editing.py::sql_preview` | 当前只编译已存在 metric_id，不执行；不能作为新建指标数值预览直接复用 |
| `apps/web/src/api/types.ts`、`lib/nativeDraft.ts`、`draftView.ts` | LegacyDraft / NativeDraft 双结构；client.hydrateNativeResponse 注入 _legacy_form，保存又拆出 legacy_mappings/legacy_joins。全部移除 |
| `ElementInspector` / `InspectorDialog` / 映射表组件 | 保留组件职责、路由与保存流程；改到时将原生 dialog/表单/表格换成 antd Modal/Drawer、Form、Table，布局改 Tailwind。新增指标、数据集内容 |
| `OssieImportDialog`、`api/modeling.py::import_ossie_document` | 当前 merge/replace 导入直接写会话草稿，首次导入可直接发布。P4 改为先报告、确认后创建 pending 提案 |
| `integrations/dataagent`、`services/model_result.py` | 技能面向 Ossie，收集器还认 model-result/v1。改为只消费核心模型提案，并保留运行恢复、幂等与租约处理 |

### 1.2 已确认的前端 UI 边界

- 控件统一 **Ant Design 5**，布局、间距、排版统一 **Tailwind CSS v4**；中文 `zh_CN`，React 19 引入 `@ant-design/v5-patch-for-react-19`。关系图保留 `@xyflow/react`，图标保留 lucide-react。
- `apps/web/src/styles/tokens.css` 是唯一设计变量来源：主色 `#0061ef`、标准圆角 `6px`、字体以 `PingFang SC` 开头，同时映射 Tailwind `@theme` 与 ConfigProvider token；不在 TS 或页面内再维护一套字面量主题。
- Tailwind 关闭 preflight；仅导入 theme/utilities。antd 用 `@ant-design/cssinjs` 的 `StyleProvider layer`，统一层序 `theme, base, antd, components, utilities`。
- 当前 `apps/web/src/styles/*.css` 共 7,924 行（含 tokens），承载几乎全部页面布局。**用户决定（2026-10-16）：P2 逐页用 Ant Design + Tailwind 重写布局，P2 结束时删除全部旧页面 CSS 与过渡分层**；P0 的分层只是 P2 之前保证现有页面可用的过渡措施。P2 验收：`apps/web/src/styles/` 只剩 `tokens.css` 与入口 `index.css`（可改为引入 Tailwind preflight），ESLint 原生控件豁免清单清空。新指标表单/预览、派生条件编辑器、导入对话框和语义视图指标/数据集两类直接使用新栈；不新增零散页面 CSS，不覆盖 `.ant-*` 内部类。
- 仓库外已验证原型仅是交互结论的背景；本计划和实施代码不引用其路径、源码、截图或资源，也不从它建立运行/测试依赖。UI 技术栈已确认，无需重新选型。

## 2. 全阶段共用的数据与契约

### 2.1 Pydantic、JSON Schema 与 TS 的唯一来源

1. P1 新增 `apps/api/src/ontofoundry_api/domain/core.py`：唯一的 `CoreDraft` 与元素定义。P2 把 `domain/models.py` 改成这些定义和请求类型的公开入口；可保留 `OntologyDraft = CoreDraft` 这一同模型名称别名，不能保留旧字段或旧解析器。类型定义不在两个文件重复。
2. `Strict` 使用 `extra='forbid'`。草稿固定 `schema_version='core-1'`、workspace_id 与九集合；服务端空草稿函数始终补齐九集合。只有可空/有默认值的元素字段允许省略。旧版本、旧字段和只读派生字段作为输入均拒绝，不静默忽略。
3. 新增 `contracts/ontofoundry.core-1.schema.json`，从 Pydantic 生成 Draft 2020-12 schema。`contracts/export_schema.py` 扩为同时输出核心与提案 schema，并增加 `--check` 只比较、不写文件。P1 可先加入独立导出入口；P2 统一 CLI。JSON Schema 管结构；`validate_graph` 和语义解析管跨元素关系，不能声称 schema 单独证明图合法。
4. 新增 `scripts/generate_core_types.mjs`，使用固定 devDependency `json-schema-to-typescript` 从核心 schema 生成 `apps/web/src/api/core.generated.ts`。P1 同时更新 `apps/web/package.json`、根 `package-lock.json`，提供 `generate:core-types` 和 `check:core-types`（检查输出差异，临时文件放系统临时目录）。生成文件进 Git；`api/types.ts` 只 re-export 核心类型并手写 REST/MCP 的读投影与请求 envelope。
5. 不从读取响应反推存储类型。`MetricRead`、`MaterialObjectRead`、有效继承项和 BindingStatus 等单独定义；value_kind、ratio.dataset_id、display_text、inherited_from、metadata_snapshot_id、binding_status 都不写回 CoreDraft。OpenAPI 输出服务请求/响应；生成核心 TS 不必顺带把所有旧 REST 类型迁成代码生成。
6. 更新 schema 的固定顺序：Pydantic → schema 生成 → TS 生成 → 提案引用 schema → 更新技能引用表。阶段最后用 check 模式及漂移测试验收，禁止手改生成文件后忘记源模型。

### 2.2 要落地的核心数据结构

| 模型 | 字段/实现要求 |
|---|---|
| ObjectType | `id,name,technical_name,description,synonyms,tags,extends: UUID|null,title_property_id,derived_by: DerivedBranch[],evidence`；单父，只有本地定义 |
| Property | `id,owner_type_id,name,technical_name,description,value_kind,required,identifier,unique,synonyms,evidence`；七标量。删除 value_concept、角色、属性 multiplicity、verbalizes |
| LinkType | 通用名/说明、inverse_name、synonyms、source_type_id、target_type_id、三基数、tags、DataJoin|null、evidence；删除关系 identifier，source 为定义归属 |
| Rule | 归属仅 object_type/property/link_type；constraint/derivation，expression、元数据和证据；不加工作空间 owner，不执行规则 |
| Path / PathCondition | 有方向的 `{link_type_id,direction}` 列表、property_id；运算符与 values。只用于本体成员和规则，不用于指标 |
| DerivedBranch | `kind=simple` + 非空 conditions（AND）或 `kind=expression` + 非空 expression；互斥。多分支 OR，逐级先限父范围，再与 membership_source_id 取交集 |
| Dataset | `id,name,dialect?,schema_name?,table_name,description,snapshot_date_column?,columns?`；columns 项只有 name/physical_type/comment。没有连接别名、query、field 节点或用户填写的采集时间 |
| MappingSource / DataMapping | source 为局部 id、dataset_id、有序 key_columns；mapping 为 id/type_id/binding_mode/sources/fields/membership_source_id/inherited_link_bindings。independent 固定 main；shared_parent 仅存新增来源 |
| FieldBinding | column：source_id/column；expression：同行标量文本。不得引用另一个计算属性、其他对象、聚合、窗口或子查询 |
| DataJoin | direct：两组有序属性 UUID；mapping_table：dataset_id、两端列组、两端 mapping_key 或 properties 键引用。mapping_table 两侧键宽可以不同，各侧独立对应，不错误要求 source_columns 与 target_columns 等长 |
| SimpleMetric | 通用元数据，kind/dataset_id/aggregation/measure?/filters/time_field?；count 仅行数，measure 必须为空；其他六聚合必有列。输入不收 value_kind |
| RatioMetric | 通用元数据，kind/numerator_id/denominator_id；两者是同数据集数值型 simple；输入不收 dataset_id、time_field、value_kind |
| ExpressionMetric | 通用元数据，kind/dataset_id/expression/value_kind?/time_field?；全部列属于本数据集，不接受 SELECT/FROM/JOIN/其他作用域；外部未给类型可空并待补全 |
| Condition / ColumnReference | 条件引用 dataset_id+column，AND；运算符 eq/ne/gt/ge/lt/le/in/not_in/between/is_null/not_null，核对数量与类型，not_in 不含 null |
| MaterialObject / MaterialLink | 对象只存 id/type_id/values/evidence；链接只存 id/type_id/source_id/target_id/evidence。values 为属性技术名到标量，显示名为读取投影 |

业务标识按有效 identifier 属性的 UUID 字节序排序；来源逻辑键和 JOIN 列组保留声明次序。标识、来源键、元素 UUID 和事实 UUID 不能合并。任何地方都不能用分隔符字符串拼复合身份。

### 2.3 表达式与依赖：先统一内核，再接各入口

新增 `domain/expressions.py`、`domain/dependencies.py`、`domain/bindings.py`、`domain/validation.py`（可按体量拆分）。明确三个解析上下文：Rule/DerivedBranch 的本体路径、FieldBinding 的局部来源列、Metric 的本数据集列，禁止共用一个“凡是 a.b 就合法”的校验。

建议内部结构为 `ResolvedExpression(text, ast, references)`；reference 持上下文、元素 UUID 或 dataset UUID+column、路径方向及 AST 位置。它是由草稿生成的内部编译投影，不给九集合添加 AST/依赖字段，也不把 AST dump 写入原生文件。改名前先解析旧图并保留已解析引用，在候选图内按 UUID 重建文本，再校验；缓存以草稿哈希为键。这样可以保存稳定 id 依赖，又避免另建一份易失同步的持久化依赖集合。

技术名可为 SQL 保留字。本体路径需要专用标识符解析，不能直接把对象名 `order` 当 SQL 关键字拒绝。EXISTS 仅用于成员表达式的显式关系存在性，解析 forward/reverse/self/平行关系；不能借此允许 SQL 子查询。标量路径按方向和声明基数判断，不把集合当单值。

依赖图区分：(a) 对象/属性/关系/规则/成员/绑定；(b) Dataset/列→Metric→ratio。对象改名、删对象、改基数、改 derived_by 不产生指标修订。Dataset 删列/删登记/位置与快照变化须列直接和 ratio 间接影响；位置变化展示语义风险，确认等价的搬迁只更新 SQL 参考，不强造算法修改。

### 2.4 提案契约 `ontofoundry.proposals/v1`

保留合同名 v1；这是设计已确定的切换，不另设 v2，也不接受旧 v1 内容。旧会话和运行随 P2 清空/失效，DataAgent 技能须同时更新。

- `target_kind` 精确为 `object_type/property/link_type/rule/metric/dataset/mapping/material_object/material_link`。删除 action、value_type；Metric/Dataset 正式作为提案目标，不再藏在语义编辑 API。
- 保留 run_token、workspace/session、base_version_id/hash、source_session_revision/draft_hash、before/after、expected_target_hash、evidence、depends_on、reason。create 的 agent after 无自身 id，client_ref 必填；update/delete 指向既有 UUID，继续验证 before/hash。
- 改 `_after_schema`、`result_schema`、`parse_result`：只从 core 模型生成；删 models_for/draft_version、native binary、角色与 concept_context 的特殊路径。
- 统一 reference walker 覆盖 extends、title_property_id、端点、归属、ratio 分量、ColumnReference、sources.dataset_id、mapping_table.dataset_id、direct 属性组、derived Path、inherited_link_bindings 的 UUID 字典键及值、事实端点。不只替换标量字段。局部 sources.id、column、values、quote、SQL 字面量不是 UUID 引用。
- 创建批次可用 UUID 或 `{client_ref: ...}` 指向同批次新元素。对于以关系 UUID 为 key 的 inherited_link_bindings，agent 输入使用明确的条目数组 `{link_type_id: UUID|ClientRef, data_join}`，解析后转存储字典；不把 client_ref 猜作 JSON key。新建目标技术名可在同批次 expression 文本出现，待完成 id 分配/引用解析后统一解析候选图；改名只动解析后的引用。
- 自动依赖从最终引用图计算，显式 depends_on 只增补。名称交换、删除依赖修订、跨元素规则改名必须能原子接受；不要为了原子组造 depends_on 环。新增内部 `atomic_group_id`（ProposalItemRecord 可空列及读响应），组整体校验后一次写入；依赖图在组层压缩为 DAG。接入 decide 的选中组扩展、拒绝/撤销和幂等，前端显示组内联动数量。
- 原生导入 create 需保留文件 UUID，不能直接喂给当前会重铸 create_target_id 的 agent parse_result。新增可信平台构造入口 `build_import_batch`：使用匹配完成的最终 UUID，复用同一元素校验、依赖、fingerprint、store_batch、decide；不得通过放宽 agent target_id 规则实现。
- 材料证据继续验证工作空间、哈希、行号和 quote；agent 不能伪造人工证据。原生导入是独立可信来源，允许保留原 manual.created_by/created_at，不被手工编辑的服务端盖章逻辑覆写。证据按自身 UUID 保持归属，不因相同 quote 移动或合并。
- Dataset/Mapping 按设计没有 evidence 字段，导入证据放 ProposalItemRecord.evidence_json；不得为统一提案显示而给它们私加持久化字段。

### 2.5 MCP 四工具输入输出

实现放在 `api/mcp.py`（协议/分发）及新增 `services/mcp_ontology.py`、`services/cursors.py`（语义服务/分页）。保留当前 JSON-RPC、请求头与协议协商测试；工具重构不是删除协议传输能力。

统一 envelope：`workspace_id,version_id`，列表含 `total,items,next_cursor`；对象批量含 elements 和 missing（未授权与不存在采用同一不泄露身份的策略）。返回结构通过 Pydantic/JSON schema 固定，`structuredContent` 与 text 内容一致。

| 工具 | 输入（所有对象 extra forbid） | 输出及调用边界 |
|---|---|---|
| search_ontology | query 必填；kinds? 为 object_type/property/link_type/rule/metric；cursor?；limit=20，1–100 | id、kind、name、technical_name、摘要、命中 synonyms；本体有归属；指标仅授权数据集信息，不带对象 owner |
| get_ontology | ids 可省略，非空时 1–100；kinds?；include 默认 semantic，可加 physical/rules/adjacency；cursor?、limit 同上 | 不传 ids：授权轻量目录和数量；传 ids：定义、有效继承项、直接子类型、binding_status、授权 Dataset/来源/列/JOIN、元数据采集标识/时间、指标定义及可用 sql_reference。dataset/mapping 仅在 physical 授权范围读取，不变成独立工具 |
| search_objects | type_id?、q?、cursor?、limit | 只读选定发布/固定版本内已接受的文档事实；UUID、实际 type_id、display_text、属性摘要，total 按事实 UUID；无 source、无 db ref，不访问业务连接 |
| get_object | id 为事实 UUID；include?（properties/evidence/adjacency，默认 properties）；cursor?、limit | 该事实的只读 display_text、属性、可见证据；直接邻接带 link_type_id、方向和端点 UUID，按关系/方向分段，不递归塞邻居全文 |

四工具全部拒绝 version_id；不能像当前 tool_schema 那样统一注入。建模 Principal 的 pinned_version_id 由服务端使用；空基线提供空核心目录，不能偷偷切当前发布版；问数 Principal 每次解析工作空间 current_version_id。返回 version_id 供追溯；已清理固定版报 `version_unavailable`。

cursor 签名绑定 workspace、解析版本、工具、filters、projection、权限指纹及页内 section/偏移；发布或授权变化后报 `cursor_invalid`。嵌套属性/规则/邻接均提供 total/items/next_cursor；同工具用 section 编码续取，超大 expression/description 提供字段分段游标与明确分段信息。总响应 256 KiB，在元素边界分页；不能用字符串硬截断冒充完整值。

权限由 `services/access.py` 统一：无 can_read_mappings 不返回 Dataset 名称、描述、数量、列、SQL/参数、物理表达式、JOIN、元数据采集信息；含数据集名称的指标表达式也裁剪；semantic 部分可保留授权摘要并写 forbidden。无 can_read_instances 不返回事实、证据、quote。目录、搜索摘要、全局数量、嵌套项和 read_cache 均使用同一授权投影。内部 connection identity 只用于判断同连接，所有层级不输出 connection_alias。

## 3. P0：前端基础设施、原型与实施准备

### 3.1 前端基础设施（最先实施）

**P0-FE-01 依赖与固定版本。** 修改后续实施中的 `apps/web/package.json`、根 `package-lock.json`：运行依赖加入 `antd`（限定 5，至少支持 layer 的 5.17）、`@ant-design/cssinjs`（与所选 antd 兼容并去重）、`@ant-design/v5-patch-for-react-19`、`dayjs`（直接使用日期值/语言配置）；开发依赖加入 `tailwindcss` 与 `@tailwindcss/vite`（均为 v4，同一发行版本）。实施当天确认 peerDependencies/Node 与现有 React 19、Vite 6、Vitest 的兼容性，用 `--save-exact` 保存每个新依赖的确切版本，不用 `latest`、`^` 或 `~`；记录解析版本、提交 lockfile，并以 `npm ci` 验证可重建。保留现有 UI 外依赖，不顺带升级 React/Vite；不引入第二套控件库。本次修订仅安排安装，不执行安装或虚构已验证的版本号。

**P0-FE-02 Vite 与 CSS 入口。** 在 `apps/web/vite.config.ts` 保留 react 插件、代理和 jsdom 配置，加入 `@tailwindcss/vite` 插件。新增集中入口 `apps/web/src/styles/index.css`，`main.tsx` 只导入它；它是基础设施入口，不是页面 CSS。顺序示意：

```css
@layer theme, base, antd, components, utilities;
@import "tailwindcss/theme.css" layer(theme);
@import "tailwindcss/utilities.css" layer(utilities);
@import "./tokens.css";
/* 此后集中导入现有 global/reference/页面样式和 @xyflow/react 样式，均明确归层。 */
```

所有 `@import` 放在普通声明前；禁止 `@import "tailwindcss"`、`tailwindcss/preflight.css` 和额外的 `antd/dist/reset.css`。把散落在组件与 main 的旧 CSS 导入集中到此入口，避免未分层副本。将 `global.css` 里 html/body/root、基础字体与必要 box-sizing 等最小基础规则放 `base`；旧控件/页面类放 `components`，逐项收窄到旧页面已有容器，禁止泛化的 button/input/select/table 或 `.button` 规则命中 antd 控件。仅分层仍不足：components 在 antd 之后，旧通用选择器必须隔离/收窄。`@xyflow/react/dist/style.css` 放 `components` 并保留其布局规则，utilities 最后。保留未改页面所需规则，不以接入为由重写全部样式；后续按 §5.4 / §9.2.1 缩减。

**P0-FE-03 单一 tokens 与主题映射。** 在现有 `tokens.css` 保留自有 CSS 变量，并在同文件用 `@theme inline` 映射语义别名，如 `--color-primary: var(--color-accent)`、`--font-sans: var(--font-body)`、标准圆角及间距/排版变量；避免同名自引用。颜色、圆角、字体、间距及弹层层级的设计取值只在这里定义。新增 `apps/web/src/theme/antdTheme.ts` 作为适配器，入口 CSS 加载后从根元素 `getComputedStyle` 读取变量，给 ConfigProvider 生成合法 token 值：`colorPrimary` 读取现有 `--color-accent`（#0061ef），`borderRadius` 将 `--radius-sm` 的 6px 转为数字 6，`fontFamily` 读取 `--font-body`（PingFang SC 等），并映射文字、背景、边框、状态色及 `zIndexPopupBase`。颜色按 antd 所选版本支持格式规范化，派生色交由其算法；不把要求数字的 token 传成 `var(...)`/带 px 字符串，不复制 hex/font/radius 常量或添加第二份 tokens 文件。

**P0-FE-04 根 Provider、中文与 React 19。** 在 `main.tsx` 最先导入 React 19 patch，保留 StrictMode、React createRoot 和对话 SDK 注册；根部结构为 `StyleProvider layer` → `ConfigProvider locale={zh_CN} theme={...}` → antd `App` → 现有应用。antd App 可别名以避开现有 App；组件通过 `App.useApp()` 调用 message/notification/modal，避免静态方法脱离主题/locale 上下文。同步 dayjs `zh-cn` locale。`InspectorDialog` 等保持业务 API，具体 Modal/Drawer 在 P2 对应任务替换；P0 仅以基础冒烟验证新控件和旧页面共存，不全量替换页面。

**P0-FE-05 Vitest/jsdom。** 扩 `src/test-setup.ts`，补足 antd 实际用到的 `window.matchMedia`（含 matches、media、监听/事件 API）、`ResizeObserver`、必要的 `scrollTo`/`scrollIntoView`；保留现有 React Router/Node AbortSignal 兼容；测试入口同样加载 React 19 patch，不依赖只在 main.tsx 执行的副作用。测试辅助 `src/test/renderWithProviders.tsx` 复用同一 Provider/主题入口。暂保留未迁移原生 dialog 的 polyfill，最后一个引用退役后才删。避免全局 mock antd 或吞掉 console 错误；测试按 role/name 访问 portal 到 body 的内容，用异步查询等动画结束，并正确清理弹层。新增 `src/test/uiFoundation.test.tsx`：验证中文日期/校验信息、可搜索 Select 的键盘选择、Modal/Drawer 打开关闭与焦点恢复、主题适配器读取/数值转换及表单提交。jsdom 不验实际 CSS 层叠/遮挡，这部分交真实浏览器验收。

**P0-FE-06 ESLint 与渐进迁移规则。** 在 `apps/web/eslint.config.js` 使用 JSX `no-restricted-syntax`（或等效规则）禁止新增原生 `<select>`/`<dialog>`；现有存量按明确文件登记临时豁免，迁移一个文件删一个豁免，新文件不能豁免。评审清单同时检查新增 Form/Input/Table/DatePicker 等使用 antd、无新页面 CSS、无 `.ant-*` 选择器覆盖、无重复主题常量和动态拼接导致 Tailwind 扫描不到的类名；测试夹具中的原生元素单独说明。不能为了 lint 一次重写所有旧页面，也不能永久全局关闭规则。

**P0-FE-07 局域网 HTTP 非安全上下文。** localhost 和真实局域网 IP 的 HTTP 地址都验收（开发/生产预览各一次），记录 `window.isSecureContext`；不得把 localhost 结果视为 IP 验证。检查 `crypto.randomUUID`、`crypto.subtle`、clipboard 等能力依赖；所需普通 UI 临时 id 使用可在目标环境运行的方案，缺少受限能力时提供明确降级，不能令应用白屏，也不以浏览器安全开关或全局伪装 secureContext 通过。核验 Modal/Drawer、Select 搜索、TreeSelect、DatePicker 中文、上传选择、路由/API 代理与关系图；P2/P4/P5 再补各自业务入口。此项是部署访问能力检查，不要求给普通 UI 强行增加 HTTPS 前置条件。

接入依据：[Ant Design 样式分层](https://ant.design/docs/react/compatible-style/)、[Ant Design 5 的 React 19 补丁](https://5x.ant.design/docs/react/v5-for-19/)、[Tailwind 的 Vite 插件](https://tailwindcss.com/docs/installation/using-vite)、[Tailwind 关闭 Preflight](https://tailwindcss.com/docs/preflight)。采用本文已确认的 v5/v4 范围，官方文档中的其他主版本配置不自动纳入。

### 3.2 交互与夹具任务

**P0-01 交互原型（已确认，不提交）。** 用户已在原型中确认三个新交互，实施按以下结论执行：

- **新建指标**：右侧抽屉；数据集下拉可搜索，选中后显示“一行代表什么”、物理表、是否快照，选项标出每日快照、无连接、无映射权限。计数不选列；求和、平均、中位数只列数值列。比率只选同一数据集的简单指标，分别显示分子、分母的时间口径并给出“比率 = 分子 ÷ 分母”。写表达式时下方列出可点击插入的列，引用其他数据集的列或含 SELECT/FROM/JOIN 时当场报错。无日期列时时间字段禁用。数值预览手动触发，总值与按月趋势并排并说明算法；表单修改后旧结果标“已过期”；无连接、无权限、表达式不支持时显示“无法预览”及原因。
- **子对象派生条件**：只有一层条件，全部同时满足；同一字段的“或”用“属于”运算。字段下拉分“属性”“关联”两组，关联的运算只有“有 / 没有”。不同字段之间的“或”、关联对象的属性筛选等复杂情况，切换到与“按条件”平级的“写表达式”。父对象的继承条件只读显示。没有条件时提示“该对象没有实例，不会等于父对象全部实例”。底部一行显示“当前满足 N 个”，可展开查看。成员扩展表在数据映射页配置，不在此处。存储不变：按条件保存为一个 simple 分支，表达式保存为 expression 分支。
- **导入**：三步对话框（选择文件 → 转换报告 → 确认）。选择文件时选格式（Ossie / 原生单文件）并说明“只新增和修改，不删除”。报告顶部汇总已转换、有提醒、未导入、错误、待补全数量，按标签页分组；每条有原文行号、说明，可展开原文与规则编号；`COUNT(*)` 可当场选数据集，其他待补全写“原文保留，进入会话后手动改写”。文件级错误整份停止，与条目级错误区分。确认页显示将生成的新增、修改提案数，无变化和待补全不生成提案；进入会话审阅，不提供直接发布。

**P0-02 既有页面的小范围核对。** 只确认语义资源管理器四类筛选及指标/数据集弹窗、规则回归所属弹窗、数据集登记与绑定总览两个标签、全局分层数量导航。保留路由与页面骨架，不另做整站设计。对象详情的“相关指标”首版默认省略；若原型认为必须增加，仅按 dataset 绑定推导，不存对象归属。数据集引用计数明确后续。

**P0-03 夹具静态差异登记。** 当前设计 JSON 尚不是可执行合同验收。已发现：

- `06-inheritance.json` 的 devices/vehicles 已给非空 columns，却缺其绑定使用的 device_name/vehicle_name、responsible_id。
- `12-snapshot-and-trends.json` 的 component_state_daily 已声明 snapshot_date_column，却在非空 columns 清单缺 snapshot_date。

P1/P2 的夹具准备应按已写明的虚构业务语义补齐这些元数据，并同步最小示例修正说明。不能降低已知列引用校验、把已知不存在当 unknown，或伪称原始 13 文件全量已通过。保留原始错误变体作为负向测试。此为文档数据一致性修正，不是新增业务决定。

### 完成标准与阶段检查

前端基础设施可单独合并，未改页面业务仍可用；三个交互已有确认结论或完成必要的呈现确认，九集合与提案引用格式清楚。原型不纳入 Git。业务边界与 UI 技术栈已定，不再请求用户确认清空、继承模式、指标归属或选型。

P0 基础设施全部编辑完成后执行（从仓库根目录；此处命令是后续实施验收，不是本次运行记录）：

```sh
npm ci
npm ls antd @ant-design/cssinjs @ant-design/v5-patch-for-react-19 dayjs tailwindcss @tailwindcss/vite --workspace apps/web
(cd apps/web && npm test -- --run)
(cd apps/web && npm exec -- tsc -b)
(cd apps/web && npm run lint)
(cd apps/web && npm run build)
```

本阶段须新增上述 UI 基础冒烟测试，不跑后端测试。浏览器人工检查需另启长期服务，开发与预览分开运行，检查后停止对应进程：

```sh
npm run dev --workspace apps/web -- --host 0.0.0.0
npm run preview --workspace apps/web -- --host 0.0.0.0
```

使用服务实际输出的端口访问 localhost 与本机局域网 IP；后端代理另按现有配置准备，预览模式的 API 需由实际部署反向代理或同源测试环境提供，不假设 Vite dev proxy 会在 preview 中生效。记录页面/弹层计算样式的层归属、关闭 preflight、中文与焦点、HTTP 能力降级、构建 JS/CSS 原始和 gzip 体积；jsdom 通过不代替这些检查。

## 4. P1：核心模型、表达式、依赖与生成基础

### 任务

**P1-01 建核心类型。** 新增 `domain/core.py`，按 §2.2 实现 Strict、九元素集合、四个判别联合（derived、join、field、metric）、条件与引用。不要从 models_v3 继承，不 import ossie/adapters。P2 仍需的 PublishRequest/WorkspaceCreate 暂留原入口，P1 不替换现有运行模型。

**P1-02 图与继承校验。** 新增 `domain/validation.py`、`domain/bindings.py`：实现 `validate_core_graph`、`effective_properties/effective_links/effective_rules`、`resolve_binding`、`binding_readiness`。检查全局 id/技术名、共享命名空间、单父环/遮蔽、标题和父标识沿用；父有绑定仅 shared_parent；虚拟父的具体子类可绑继承属性/关系且保留 id；虚拟父不可直接事实；无绑定叶类型 unbound。binding readiness 与结构合法分离：空键/无列清单/未知类型可保存，已知不存在引用必须修正。

**P1-03 表达式解析。** 新增 `domain/expressions.py`：分别提供 `resolve_rule_expression`、`resolve_derived_expression`、`resolve_field_expression`、`resolve_metric_expression`、`render_references`。用 sqlglot 辅助受限 SQL AST，规则路径和 EXISTS 另做语义解析。覆盖 CASE、字符串/参数不替换、反向、自环、平行边、标量/集合边界与 SQL 保留字。引用可闭合不等于当前引擎可执行；预览白名单不作为语义保存的通用函数白名单。

**P1-04 依赖与变更分析。** 新增 `domain/dependencies.py`：`reference_index`、`reverse_dependencies`、`rewrite_references`、`affected_metrics`、`validate_candidate_graph`。规则/派生条件改名基于旧图 id；Dataset 改名重建 metric 文本引用，不碰字面量；Dataset/列/快照变更沿 ratio 传影响；普通本体操作不依赖 metric。

**P1-05 哈希基础。** 新增独立 `domain/core_canonical.py`，实现规范化并在 P2 替换 canonical 入口。明确九集合/证据按 UUID；sources 按局部 id；columns 按 name；tags/synonyms 规范化为集合；key_columns、JOIN 属性/列组、Path.links、between.values 等保序；用户 values 中的 null/0/false 保留。其他条件数组先保序，避免未经定义去重改变文本。新增字段必须登记策略；核心不再持 hash_algorithm 字段。报告 content_sha256、原始上传字节 hash 与草稿语义 hash 分开。

**P1-06 生成契约与跨语言夹具。** 新增核心 schema、TS 生成器及 check 命令（§2.1）。新增 `apps/api/tests/core1_fixtures.py` 直接读取 docs 的 13 文件，不复制一套长期漂移的 JSON。修正 P0 已登记的虚构列清单缺口；增加 `apps/web/src/test/core1Fixtures.ts` 读取同一来源，映射为 UI 的读投影时保持 UUID 和表达式。

### 完成标准、风险与验收

- 13 份 draft 在元数据缺口修正后通过 core schema 与图校验；09 空模型、08 缺列清单可保存；缺证据材料不在纯模型测试中伪验完整性。
- 定向负例：旧版本/动作/角色字段，ratio 携带只读字段，count 带 measure，SUM 文本，其他数据集列，SELECT/JOIN，not_in null，继承遮蔽/环、子对象独立父外绑定、非法 direct 键、交换复合键列序。
- §14.6 对应：来源绑定、继承、计算列、指标、本轮语义边界的静态部分。示例主要 01–13；多层 OR/AND/EXISTS、20+来源另造最小变体。
- 风险：AST/路径解析最容易把引用改坏；生成 schema 必须保持判别联合与禁止只读输入，不能退回 TS 可选字段大对象。P1 不改变现有 API 输出，现有测试保持可用。

阶段全部编辑结束后统一执行（均从仓库根目录）：

```sh
(cd apps/api && uv run --python 3.13 pytest -q tests/test_core1_models.py tests/test_core1_expressions.py tests/test_core1_dependencies.py tests/test_core1_schema.py)
(cd apps/api && uv run --python 3.13 ruff check src tests)
(cd apps/api && uv run --python 3.13 python -m ontofoundry_api.contracts.export_core_schema --check)
npm run check:core-types --workspace apps/web
(cd apps/web && npm test -- --run)
(cd apps/web && npm exec -- tsc -b)
(cd apps/web && npm run lint)
(cd apps/web && npm run build)
```

P1 前端不迁移页面控件或删除页面 CSS；共用 P0 Provider 的 13 例 loader/类型回归，不另加原生控件。

上述 `test_core1_*.py` 和 `export_core_schema` 是本阶段新增；不是声称仓库已有命令。P2 会把独立核心 schema CLI 并入 export_schema。

## 5. P2：一次完成内部运行切换

本阶段是主要工程量。按下列顺序全部完成编辑，再统一测试；不是每项一边改一边跑全套。将 schema、服务、前端、清理分成内部提交便于审阅，合并/部署边界仍为整个阶段。

### 5.1 后端存储、读写、提案与发布

**P2-01 核心入口与快照。** 改 `domain/models.py` 为 core 公开入口；`domain/snapshot.py` 只留 empty_snapshot/read_snapshot/read_snapshot_json/哈希边界，缺版本和非 core-1 一律拒绝。将 core_canonical 接入 `domain/canonical.py`，删除旧哈希算法分支。调用者统一，不能再传 target_version。移除 models_v3/legacy_v1（删除清单见 §9）。

**P2-02 提案全链路。** 改 `contracts/proposals.py`、`contracts/export_schema.py`、`services/proposals.py`、`api/proposals.py`，按 §2.4 接入九种目标、引用 walker、原子组与最终图校验。保留 parse 的整批拒绝、run context 固定、before hash、幂等、superseded、undo 与事务并发。组内无需每应用一条就校验图；全部应用到副本后一次验证。`effective_statuses/dependency_map` 从当前草稿实时算依赖阻断，历史报告不变。

**P2-03 保存范围与影响。** 改 `services/element_save.py::element_scope/scoped_draft`：对象聚合只包括本地对象/属性/所属规则和自身绑定；关系、指标、数据集分别有作用域，不能顺带覆盖不相关集合。Dataset 影响组或技术名引用改写必须显式带受影响项/校验 hash。改 `api/modeling.py::save_element/save_session/revise/session_data/_derived_views`，删 LegacyFormRequest、legacy mapping 回写；改 `api/semantic_editing.py` 去掉语义树 change API，Dataset/Metric/Mapping 通过同一 core 保存服务，迁走预览后删除旧模块/路由。

**P2-04 发布脱离外部格式。** 改 `services/workspaces.py::publish_draft`、`api/modeling.py::validate_draft/preview_definition/publish_session`、`services/publish_preview.py::three_way/impacts`、`services/merge.py`、`element_diff.py`、`version_diff.py`、`identities.py`：仅核心校验与实例值校验；合并九集合，删除 roles.position 合并、ontology_requires 比较、Ossie 校验器依赖。保留 revision/current_version/hash 三重防陈旧及行锁/CAS。09 空核心、13 仅数据集指标均可正常发布。

**P2-05 版本记录与清空迁移。** 改 `db_models.py::OntologyVersionRecord` 去掉 ossie_json；版本 snapshot_json/validation_json/sha256 保留，sha256 用核心发布 envelope。新增紧接 `20261009_000001` 的 Alembic revision（名称建议 `20261016_000001_core1_cutover.py`）：

1. 在停掉旧写入/运行同步的部署步骤后执行。先清 current_version_id。
2. 按 FK 顺序删除 proposal_decision_items、proposal_item_dependencies、proposal_items、proposal_batches、proposal_decision_requests，然后删除携旧草稿的 modeling_sessions、ontology_element_identities、ontology_versions；旧导入内容当前无独立 ORM 表，若部署库有历史表按 schema 检查清理，不能假称已有 import_records。选择删旧建模会话整行，不保留悬空的 topic/run/候选记录。
3. 保留 users/workspaces/workspace_members、materials/material_chunks、data_connections、service_tokens/scopes、metadata_snapshots；不清空业务数据库、不删磁盘材料。
4. 去版本表 ossie_json；为 ProposalItem 加 atomic_group_id。SQLite 用 batch_alter_table，PostgreSQL 保持 FK 顺序；脚本重入辅助函数幂等。down revision 不承诺恢复清掉的数据。
5. 特别处理 `20260930_000001_proposal_first_lifecycle.py` 的旧数据 backfill：它在运行时 import as_v2_dict、snapshot_sha256、element_kinds，删除旧实现后 fresh upgrade 会失败。保留该历史 revision 的 DDL，去除最终会被 core-1 清空的旧数据转换 backfill，写明清空切换原因；不要把 v2 转换器搬到运行路径。已有已升级库不会重跑旧 revision；新库从 base 升 head 和旧 head 升新 head 都必须验收。
6. 旧 run grant 随会话删除立即失效，服务令牌保留但清空后按无发布版本响应。清应用 read_cache；阻止旧 DataAgent 回调复活已删会话。

**P2-06 初始化与周边读服务。** 改 `services/demo.py::build_demo_draft`、`main.py` demo 初始化、`services/ontology_query.py::snapshot_of/query_view/workspace_overview/get_type/type_graph`、`ontology_context.py`、`public_projection.py`。demo 用通用虚构 core 模型直接构造（P5 后才可从新适配器重导）；数量覆盖指标/数据集/文档事实且权限一致。`api/workspaces.py` 只保留会话发布的用户通路，删除绕过会话的 `/{workspace_id}/publish` 旧公共路由及 `PublishRequest`，内部 publish_draft 继续被会话和测试初始化调用。发布页本身保留。

### 5.2 来源解析、数据库实例和指标预览

**P2-07 来源解析。** 新增 `services/dataset_sources.py::resolve_dataset/authorized_dataset_projection`，把 `api/connections.py::resolve_alias/query_mapping/connect_readonly` 中的来源选择与只读连接能力解耦。按 Dataset.dialect/schema_name + 服务端连接配置解析唯一连接、database/schema，空 schema 用配置默认值，多连接歧义明确失败。模型和 MCP 不带 connection_alias；连接管理内部 name/凭据字段不因此删除。`api/assets.py` 提供授权目录/元数据；登记 Dataset 复制已采集列元数据，采集 id/时间由服务端投影附带。

**P2-08 对象实例编译。** 改 `api/connections.py::PreviewRequest/query_mapping`、`api/instances.py::NeighborhoodRequest/database_object/related_rows/database_neighborhood`、`services/instance_query.py::mapping_for/db_ref/parse_ref/search_objects/get_object/object_neighborhood`、`join_validation.py`；新增 `services/instance_plan.py`：

- 用有效 DataMapping 按 main 实例集合 LEFT JOIN 普通附表；成员扩展用 EXISTS 或等价半连接避免凭空增实例；支持 main 不在 sources 首位、20+来源、有序复合键、计算列。
- shared_parent 逐层限父范围，加本层 derived 分支并集及成员来源交集，继承列/关系仍取祖先绑定。虚拟父递归展开具体绑定来源，只对相同 `(具体 type_id, typed key tuple)` 去重，不把同局部键的两个子类型合并。
- direct、mapping_table 正反向、多对多、自关联/平行边、unique 非物理主键均按明确列组。对象查询保留未匹配行；关联浏览仅列匹配。缺键/跨连接/缺列给状态，不执行伪 JOIN。
- 各 Dataset 独立选全表最大快照日期（先取日期再加成员/属性筛选），指定日期精确使用当日；主附不强加同日，不能由主来源决定附表日期，不能把每个实体最近一行混成当前快照。
- 数据库 ref 改编码为具体 type_id + 有序带类型 key tuple；值参数化，绝不 str(key) 或分隔符拼接。保持 REST 实例页数据库浏览能力，MCP 只保留文档路径。
- 复用已有只读超时/行数/注入防护。模型声明唯一性不触发数据扫描/自动去重；实例定位发现多个匹配可报定位不唯一，不能扩张成全库基数验证器。

**P2-09 文档事实投影与审阅。** 新增 `domain/instance_display.py::document_display_text/database_display_text/business_identity`；改 instance_query、instance_validation、ontology_query 中 name 依赖。标题→完整标识→可见 quote 前 80 字→UUID；0/false 有值，缺任一标识跳过整组，引文按 evidence UUID 稳定选首个，manual.note 不代替 quote。MaterialObject 不存 display_text。提案读取增加同类型同完整标识的 duplicate_candidates 提示，只提示；缺完整标识不猜。ProposalDetail 提供“改为更新已有事实并追加证据”的显式修订入口（可新增 `POST /proposal-items/{id}/revision`），沿用当前 revision/target hash 并重建依赖组；不原地悄悄改 accepted 项。两条都接受时仍按两个 UUID 检索、分页、保留各自属性与邻接。

**P2-10 指标编译和基础 SQL。** 重写 `services/metric_query.py::MetricCompiler/connection_for/metrics_for_draft/query_metric`，新公开函数建议 `compile_metric_reference`、`compile_metric_preview`、`execute_metric_preview`。删除 semantic_model/fields、vendor_parameters、隐式 snapshot_date 猜测、rolling 逻辑；保留 sqlglot 解析、安全 AST 和 connect_readonly 超时能力。simple 按本数据集列和固定条件，ratio 两侧独立过滤与归时间、非整数截断、NULLIF 零分母；count_distinct 忽略 null，SUM 空集 null、COUNT 空集 0。median 在支持引擎编译，其他引擎解释无法预览，不把 median 模型拒绝。

**P2-11 当前表单预览 API。** 新增 `api/metrics.py` 并在 main 注册，建议 `POST /api/v1/modeling/workspaces/{workspace_id}/metrics/preview`：

- 请求 `{session_id?,expected_session_revision?,expected_current_version_id?,metric:<完整未保存的 Metric>,components?: SimpleMetric[],time_range?:{start,end},trend_grain?:'month'}`。范围采用半开区间；ratio components 必须覆盖引用且校验同数据集；仅允许临时覆盖本次引用分量，不接受任意客户端表、连接或 SQL 查询。
- Dataset 来自服务端当前会话/发布快照，不从 metric 反查对象。预览前在内存构造完整候选定义、解析引用和权限；不写会话/版本/提案。字段和算法合法但执行不支持时返回 unable 原因，不否定已保存语义。
- 返回 `{definition_hash,context_version/session_revision,status,reason_code?,reason?,value,value_kind,total_query,trend_query?,trend?,snapshot_dates,warnings}`；query 含 SQL/params/dialect/database。实际执行就是展示的 SQL 和参数；总值一条聚合 SQL，月趋势另条 SQL，不遍历实例分页或前端聚合。
- 快照的周期末选日范围以数据集为单位，不能被 metric 固定条件缩小；总计在整个范围重算，月趋势逐周期重算，不加总月均值/去重/比率。ratio 两分量可不同 time_field，分别归月后计算。缺时间字段不声称生成月趋势。
- can_read_mappings 与实例/数据读取授权按现有服务路径共同检查，超时/失败有稳定 reason code，失败不返回伪 0。禁止把整个编译出的 SELECT 再作为无约束的用户 SQL 执行。MCP 不开放该执行接口。

### 5.3 MCP 与 DataAgent

**P2-12 四工具与授权分页。** 按 §2.5 重写 `api/mcp.py`，新增 mcp_ontology/cursors；改 `services/access.py/read_cache.py/ontology_query.py/public_projection.py` 与 `api/auth.py` pinned 版本解析。删除旧工具分发和工具 schema 的 version_id。绑定状态统一为 bound/unbound/virtual/missing_key/cross_connection/metadata_stale/forbidden 等读投影。缓存 key 必含授权指纹，不能先缓存高权限结果再给低权限复用。

**P2-13 建模技能和结果接收。** 改名 `integrations/dataagent/skills/md2ossie` 为 `ontofoundry-modeling`；新增 references/core-model.md、modeling-patterns.md、reading-ossie.md、import-completion.md 与 `scripts/check_result.py`、对应测试。check_result 使用轮次提供的 JSON Schema、client_ref 唯一与引用闭合，不用 Ossie 校验器。Ossie 的 roles 等只在 reading-ossie 解释外部材料，其余技能核心输出指导不出现旧合同。

改 `services/dataagent.py::proposal_instructions/build_turn_prompt`，只给合同、schema 路径、材料清单、MCP 配置、结果路径；改 `api/agent_conversation.py` 上传 schema/skill 名、run manifest；改 `services/model_result.py::reconcile_run/_consume_proposals` 仅接 proposals/v1，删除 model-result/v1 的完整 Ossie 分支及相关修复 prompt，保留 lease、下载失败重试/恢复、幂等入库。`services/model_review.py` 只留有实际调用的核心提案修复。改 agents/agent_ontofoundry.md、README、Makefile 的 ZIP 名称及安装配置。

**P2-14 问数提示词与部署说明。** 重写 `integrations/dataagent/agents/agent_ontofoundry_qa.md`，用四工具读语义后调用 DataAgent 自有 mysql.query/doris.query；禁止 version 入参、connection_alias、翻页明细做数据库统计。固定指标过滤、ratio 分量时间、快照独立末日、继承范围及跨连接风险按 §14.4。所有示例改通用虚构销售，不引用现有真实环境名称或业务库。

部署手册明确：安装新技能 ZIP、更新 agent skill 配置、重启 DataAgent，然后 core-1 应用/迁移切换；不在自动测试中启动/重启外部系统。应用切换窗口禁止旧 agent 结果继续进入。外部管理台操作列为发布操作，不假称改了仓库提示词就已生效。

### 5.4 前端数据层与界面

前置为 P0-FE 全组。以下纯数据层任务不引入 UI/CSS；有界面修改的任务均在该次业务改动中同步换控件、迁布局并删除失效规则，文件级清理见 §9.2.1。保留页面职责与路由，控件实现按新技术栈交付。

**P2-15 TS/HTTP 切换。** 改 `api/types.ts`、`api/client.ts::request/draftRequest`，删 hydrateNativeResponse、_legacy_form、legacy_mappings/legacy_joins；Draft 唯一 core-1。新增预览 DTO、MetricRead、Dataset 读投影、duplicate candidates、四工具服务说明相关类型。删 nativeDraft.ts 与 fixture/test，调用点全部直接读 core；draftView.ts 改成纯 UI 选择器，不把 Rule 折叠为字符串再猜 id，不把 derived_by 与 derivation Rule 混用。

**P2-16 编辑器和映射数据层。** 改 `lib/elementModel.ts`（ElementType、PanelProps、objectLineage、relationsFor、rulesFor）、`lib/objectMapping.ts`（objectMapping/sourceColumns）、`objectMappingEditing.ts`（stageMapping/propertyEntryChange/relationEntryChange/chooseIdentifier/mappingChangesForSave）、`relationEditing.ts`、`elementInspector.ts`、`instanceGraph.ts`、`instanceHints.ts`、`graphLayout.ts`。都使用有效 core 定义和来源引用，删 semantic tree/native entry 回写。继承只读展示来源；通过虚拟父具体绑定配置继承关系，不复制定义。

**P2-17 改造既有详情弹窗与映射表。** 改 `components/elements/ElementInspector.tsx::KINDS/resolve/Inspector`、`ElementPanels.tsx::BasicPanel/RulesPanel`、`PropertyMappingTable`、`RelationMappingTable`、`LinkMappingPanel`、`ObjectTablePicker`、`RelationCards`、`IdentifierBar`、`ElementInstances`，保留 InspectorDialog 的业务封装和调用接口。对象面板加入 synonyms、title、单父/派生；关系加入 inverse_name、三基数、direct 或 mapping_table；主附/关系表均只选择 Dataset。属性 unique 与复合标识独立编辑，计算绑定与列绑定可选；description 直接展示，去“上下文说明”和读法/角色。

控件替换：`InspectorDialog` / `ElementInspector` 的原生 dialog 改 antd `Modal`/`Drawer`（按详情与编辑交互选用，不叠套原生 dialog）；`ElementPanels`、`IdentifierBar`、`RelationCards` 的输入/复选/描述/页签改 `Form`、`Input`/`Input.TextArea`、`Checkbox`、`Tabs`；`MappingWidgets` / `ObjectTablePicker` / 各映射表的原生 select 改有 `showSearch` 的 `Select`（按 label 搜索并保留 UUID/列值），层级定义选择用 `TreeSelect`；手写映射/规则/实例 table 改 `Table`，状态用 `Tag`/`Alert`。迁移 `element-inspector.css`、`object-mapping.css` 对应规则为 Tailwind；关系图专用规则和其他消费者仍保留，无引用后才删整文件。

**P2-18 新做派生编辑器。** **2026-10-18 优先级更新：用户确认结构化 OR 多分支和多跳路径编辑属于后续便利性优化，不阻塞 P3～P5；当前复杂成员条件继续使用表达式编辑。** 新增 `components/elements/DerivedConditionEditor.tsx` 和 `lib/derivedEditing.ts`；按 P0 原型处理分支、路径、值类型、方向、EXISTS、表达式切换。上下文只选直接父的有效定义，不选物理列。错误定位具体分支/条件，保存走正常 element save 和最终图校验。直接使用 `Form.List` 表达 OR 分支/AND 条件，`Segmented` 切 simple/expression，`TreeSelect` 选择有方向的本体路径，`Select` 搜索运算符/定义，按类型用 `Input`/`InputNumber`/`DatePicker`/`Switch`，表达式用 `Input.TextArea`，错误用 Form 校验/`Alert`。替代 `ElementPanels` 内相应手写输入与 `ExpressionsEditor` 涉及的编辑控件；不改变本体条件与指标过滤的语义边界。布局直接用 Tailwind，不新增 derived 页面 CSS；清除原 element-inspector/object-mapping 中派生编辑规则，完整文件按 §9.2.1 判定。

**P2-19 新做指标/数据集弹窗与预览。** 新增 `components/elements/MetricPanel.tsx`、`MetricForm.tsx`、`MetricPreview.tsx`、`DatasetPanel.tsx`、`lib/metricEditing.ts`。MetricForm 覆盖 simple/ratio/expression、全部条件运算符、列/日期列筛选、类型推导；ratio 不提交三项派生字段。预览点击时发送完整表单与分量，不要求先保存。definition_hash/请求序号匹配才显示返回；表单改变或取消请求时旧结果失效，展示“需重新预览”，不让慢响应覆盖新口径。SQL 与总值/趋势结果一同显示；失败给原因。Dataset 表单可无列清单保存，但不能手工伪造元数据采集记录。直接用 `Modal`/`Drawer`、`Form`/`Form.List`、`Segmented`、可搜索 `Select`、`Input`/`InputNumber`、`DatePicker.RangePicker`、`Button`；预览值/状态/查询用 `Statistic`、`Spin`、`Alert`、`Tabs`、`Table` 与保留格式的 SQL 文本。此处 DatePicker 仅填写需要的条件值和预览范围，不新增采集时间字段。Dataset 列清单用 Table；替代旧 `SemanticModels` 中指标输入、原生表格和 `semantic.css` 的编辑样式，不复用旧语义树 UI。表单/预览测试覆盖搜索、校验、过期响应和提交定义；布局直接 Tailwind，无新 metric/dataset CSS。

**P2-20 四类资源与页面小改。** 改 `lib/semanticExplorer.ts`、`components/SemanticView.tsx`、`OntologyGraph.tsx`、`pages/OntologyViewPage.tsx`：对象/关系/指标/数据集四类，指标不画图节点，规则回归所属弹窗；筛选指标时有新建入口。改 `pages/MappingsPage.tsx`、DataAssets、DatasetPicker：只留数据集、本体映射，数据目录选择用于登记同一 Dataset；删除 SemanticModels/MappingTreeEditor/SemanticObjectForm。改 OntologyOverview/WorkspaceTabs/pageTabs/workspacePages 等：原页结构保留，全局层级不画连线，按权限计数和导航。

控件替换：`SemanticView` 四类筛选用 `Segmented`、搜索用 `Input.Search`、资源层级用 `Tree`，新增指标/数据集列表用 `Table`，详情接 P2-19；替代手写搜索框、筛选按钮和列表样式。`MappingsPage` 的双标签用 `Tabs`，`DataAssets`/`DatasetPicker` 的原生筛选、搜索、目录 table 换可搜索 `Select`/`TreeSelect`、`Input.Search`、`Table`，登记操作用 `Modal` + `Form`。`OntologyOverview` 的统计/导航使用 `Statistic`/`Card`，`WorkspaceTabs` 的页签/关闭确认使用 `Tabs`/`Modal`；图仍用 xyflow。布局/间距/排版改 Tailwind，逐步清理 `semantic-view.css`、`object-mapping.css`、`ontology-reading.css`、`ontology-overview.css`、`page-tabs.css` 及 reference 的对应规则；`semantic.css` 随旧语义树消费者移除而删除。

**P2-21 建模、发布与文档事实。** 改 hooks/useModeling/useSnapshot、BuilderPage/ModelResults、proposals/elementMeta/FieldDiff/ProposalDetail/ProposalPanel、publish/PublishPanel/ConflictResolver、ReleaseReview、InstancesPage/ObjectDetailPage：九类提案、组内联动、Dataset/metric diff；删除 actions 和 workspace requires；事实用 display_text，无独立 name 输入。重复事实提示与显式修订为更新按 P2-09。保留普通发布面板、冲突解决、版本历史；P2 暂时移除 Ossie 导入/下载按钮和后端旧路由，不留点击后 500 的入口。旧导入对话框可删除后 P4 以通用新组件恢复。`ProposalPanel`/`ProposalCard` 的手写搜索、筛选/勾选换 `Input.Search`/`Select`/`Checkbox`；`FieldDiff`/`ProposalDetail`/`ModelResults` 的手写差异表换 `Table`/`Descriptions`，分组状态用 `Tag`/`Alert`，`ReviewOverlays` 的 dialog 用 `Modal`/`Drawer`。`PublishPanel` 发布确认/注释与 `ConflictResolver` 输入改 `Modal`、`Form`、`Input.TextArea`；保留冲突选择和三方合并行为。`ReleaseReview`/`InstancesPage`/`ObjectDetailPage` 的筛选/日期/实例 table 改 `Select(showSearch)`/`DatePicker`/`Table`，不让 UI 替换改变事实 UUID 定位。涉及的 `BuilderPage` 输入和 `SessionPicker` 搜索/会话表同次换 Input/Form/Table/Modal。用 Tailwind 替代对应布局，清理 `proposals.css`、`publish.css`、`ontology-reading.css`、reference/global 中失效规则，仍有消费者的文件继续保留。

### 5.5 完成标准与统一测试

交付必须能从空工作空间手工建模或 AI 提案→审阅→接受→发布→读取 core-1；发布不 import 适配器，09/13 可发布。旧模型输入明确拒绝。§14.6 的来源、继承、计算列、指标、平台预览、时间、MCP、本轮语义边界均完成；示例 01–13 全部参与，导入/往返行留 P3–P5。前端采用当前页面结构与 Ant Design + Tailwind，不恢复已从 main 删除的编辑页面。

风险最高的验收：三方合并/undo 丢规则 id；atomic_group 与 DAG 冲突；虚拟父重复/漏实例；快照按过滤后取末日；ratio 分母过滤错误；权限从 expression/计数/缓存泄露；新 schema 使历史 Alembic import 断掉。通过下列新增/改写测试直接覆盖，不以截图替代数据断言。

前端回归新增/改写 `DerivedConditionEditor.test.tsx`、`MetricForm.test.tsx`、`MetricPreview.test.tsx` 与现有 Inspector/SemanticView/Mappings/Proposal/Publish/Instances 测试：覆盖可搜索选择器、表单字段错误、Tree/TreeSelect 方向与继承只读、Modal/Drawer 焦点/取消、DatePicker 区间、Table 分页/选择，以及真实提交 payload。统一通过 P0 测试 Provider；portal 用 screen/body 的 role 查询，不依赖旧 dialog.open、DOM 层级、hash 类名或全量快照。删除纯样式快照前保住业务断言；布局与弹层遮挡在浏览器验证。

新增建议测试：`test_core1_lifecycle.py`、`test_core1_cutover.py`、`test_core1_bindings.py`、`test_core1_instances.py`、`test_core1_metric_preview.py`、`test_core1_mcp.py`、`test_core1_permissions.py`、`test_core1_architecture.py`、`test_core1_metric_postgres.py`。原有 t1/t3/t4/t6 等有效行为迁为 core-1 夹具，不按前缀全删。

阶段全部编辑结束后统一执行：

```sh
(cd apps/api && uv run --python 3.13 python -m ontofoundry_api.contracts.export_schema --check)
npm run check:core-types --workspace apps/web
(cd apps/api && uv run --python 3.13 pytest -q)
(cd apps/api && uv run --python 3.13 ruff check src tests)
(cd apps/web && npm test -- --run)
(cd apps/web && npm exec -- tsc -b)
(cd apps/web && npm run lint)
(cd apps/web && npm run build)
(cd apps/api && uv run --python 3.13 pytest -q ../../integrations/dataagent/skills/ontofoundry-modeling/tests)
make -C integrations/dataagent zip
```

可用外部测试库在批次开始前配置 `ONTOFOUNDRY_TEST_POSTGRES_URL` 和 `ONTOFOUNDRY_TEST_MYSQL_CONFIG`，然后同一批 pytest 会跑相应集成测试。专项复现命令：

```sh
(cd apps/api && uv run --python 3.13 pytest -q tests/test_core1_cutover.py tests/test_t0_postgres_publish.py tests/test_t4_postgres_decisions.py tests/test_core1_metric_postgres.py tests/test_stage_a_mysql.py)
```

这些测试自身建立可丢弃库/虚构表及数据并幂等清理。未提供外部环境导致 skipped 时记录数量和原因；“单元测试通过”不代替 PostgreSQL 并发/迁移、真实引擎预览或 DataAgent 问数验收。现有 `make test-pg` 只跑 t0_postgres_publish，应在 P2 扩为包含迁移/决策/预览，不能误称覆盖全部。

人工/API 验收集中在批次末：复用 P0 的 dev/preview 启动命令，在 localhost 与局域网 IP HTTP 检查迁移页面、Modal/Drawer 内 Select/DatePicker 叠层、xyflow 缩放/拖动和未迁移页面；重新记录包体积与 CSS 删除/保留清单。另验三个新交互、样例 06/12、13 未保存预览总值 10、通用销售最高客户由数据库聚合返回；留查询日志证明没有 MCP 数据库执行和实例分页聚合。记录 Tests run / Failures / Errors / Skipped 与外部配置状态。

## 6. P3：机械导入适配器

2026-10-18：P3 已在 `codex/core1-remaining` 工作树实施，验证完成并进入 PR/CI 交付流程；范围、验证和外部环境跳过项见 `2026-10-18-core1-p3-import-adapters-progress.md`。导入 API/界面已在 P4 接通，导出与定向往返已在 P5 接通。

本阶段完成纯翻译，不创建或合并草稿，不发布。纯输入错误与局部不支持不同：局部错误只暂停本条及无法独立成立的依赖；文件无法解析/版本不支持阻止整份，报告仍可显示。

### 任务

**P3-01 适配器与报告。** 新增 `adapters/base.py`：FormatAdapter Protocol、ImportContext/ImportResult、ExportContext/ExportResult、TranslationIssue/Report/RoundTripDiff，字段严格按 §4.1–4.2。Export 方法暂显式未启用；只有硬编码 id→实现的最小选择，不扩成插件框架或自动识别系统。outcome 仅 converted/dropped/error；completion_status 仅 not_needed/available。Report.content_sha256 对确定性转换产物和输入 artifact 身份取 hash，不能仅 hash 文件名。历史报告不可被实时阻断覆盖。

**P3-02 原生单文件。** 新增 `adapters/native/importer.py`：校验四字段 envelope 与内部 core-1，目标 workspace_id 采用 ImportContext，跨空间保留元素 UUID。材料证据解析不硬塞 DB 到 domain：ImportResult 内部允许返回证据待解析清单，由 P4 material resolver 按目标 SHA 处理，产出的最终导入模型要再经 core 校验。单文件无材料时找不到相同 SHA 的证据 dropped，manual 保留；不把全部实例丢弃。ZIP 在本轮明确不支持，不宣称完整备份可用。

**P3-03 Ossie 基础与身份。** 新增 `adapters/ossie/importer.py`、`extension.py`、`ids.py`、`translation.py`；将当前 `ossie/validator.py`、固定 vendor assets/PROVENANCE 移到 adapters/ossie（license/notice 保留），validator 的引用只指适配器公共工具。仅 ontology 文档 0.2.0.dev0 + 内嵌 ontology_mappings；OSI standalone、独立 mapping documents 报 error。UUID5 按 §5.8 完整作用域和源定位，dataset 不按重名后缀造身份。只读取 core-1 平台扩展块，旧 1–4 块整体 dropped。

**P3-04 对象、属性、继承和规则。** 先建符号/类型图，再映射 id、单父首选（文件顺序）、七基础类型、identify_by 整组、RT-68 父身份；继承标题/同义词/描述与 RT-59 instructions 合并。值类型沿完整祖先图求兼容基础类型，不任选首个、不默认为 string。可改写自身及祖先 requires 按值变量绑定实例化到每个实际属性，含多元值角色，来源去重，不覆盖原属性规则；不可转换整条保留报告。Rule 和成员由核心解析器闭合，derived_by 全定义完整转换或整项 error，不导残分支、不另造同义 Rule。

**P3-05 关系重写。** importer 拆小函数 `import_property/import_binary_link/reify_nary/import_unary`。一元→布尔；二元 name/inverse 从首条合形读法提取、尾部与其余读法报告；多元按 owner+roles 次序生成中间对象、编号属性和 direct，构键角色按 ManyToOne 去最后/无基数全部，含值角色。缺决定角色标识整组未完成，缺最后实体角色单独报告；外键未证明业务编号对应时不绑编号，不覆盖原角色映射。多元 OneToOne、实体 extends 值类型为非法输入，不转换、不给 AI 补全任务。

**P3-06 扁平数据集与映射。** 新增 `adapters/ossie/mappings.py`：所有 dataset 一一登记（含未使用/纯关系表/纯指标）；source 只拆可确定的表位置，不接收任意查询。logical field→物理列解析后再创建 main、唯一星形附表、column/expression、direct/mapping_table。一层 referent 支持完整复合业务标识；来源主键与业务标识分开，物理 to_columns 按所引键重排 from。平行边按业务关系+目标身份+精确列组唯一匹配，歧义只丢该绑定。父绑定+独立子表保留定义/Dataset、暂不接子绑定，RT-65；快照/成员绑定往返限制另报，不能由 ANSI_SQL 猜 mysql。

**P3-07 数据集指标。** 新增 `adapters/ossie/metrics.py`：先解析全部列的最终数据集来源与额外作用域，再固定形式识别。支持 §5.6 所列五聚合/median、列去重、限定 CASE、精确行计数规范式和同数据集 CAST/NULLIF ratio。两遍导入：先登记 simple，再匹配 ratio 的已有分量；找不到则保留单条 expression，不生成分量指标。COUNT(nullable_col)/条件 COUNT(nullable_col) 保留 expression；拼接去重、OR/ELSE 0/多个 WHEN 保算法。裸 COUNT(*) 留原文/候选待用户选来源，不从对象映射猜；跨数据集/SELECT/JOIN/其他查询作用域按 RT-69，不进入 CoreDraft.metrics。非 ANSI 指标保留原表达式和来源方言说明，只有引用/边界能闭合才形成核心指标；不能闭合时留待补全，不能把未知方言标成 ANSI_SQL。

**P3-08 定向 RT 夹具。** 新增 `tests/test_core1_ossie_import.py`、`test_core1_native_import.py`、`test_core1_translation_report.py`、`tests/fixtures/core1_ossie/`、`rt_cases.py`。保留 A=`fixtures/ossie_synthetic/storybook-lending.ossie.json`、B=`library-lending.ossie.json`，重写原 AST 无损断言为机械支持子集和 RT 报告快照；不把 A/B 预处理成只有容易转换的内容。输入缺口、非法输入、RT-68、RT-69 单列。P3 的 RT 测试验导入；对应往返断言 P5 补齐，不提前声称完成。

### 完成标准与统一测试

§14.6 导入和本轮语义边界的适配器部分完成；核心 01–13 用于 native 输入，03/06/07 的源 Ossie 另造定向夹具，不把已重化 JSON 当多元输入覆盖。每个 outcome 带真实可取得定位、原文和最终可用 target id；源解析失败不伪造 JSON pointer。ImportResult.model 是独立合法核心子图，不把坏条目塞半成品元素以求 counts 好看。

阶段全部编辑结束后统一执行：

```sh
(cd apps/api && uv run --python 3.13 pytest -q tests/test_core1_ossie_import.py tests/test_core1_native_import.py tests/test_core1_translation_report.py tests/test_core1_architecture.py)
(cd apps/api && uv run --python 3.13 pytest -q)
(cd apps/api && uv run --python 3.13 ruff check src tests)
```

P3 只改适配器，不新增页面/原生控件/CSS，不重复跑前端；若契约变化牵动前端，则补 P2 的 check:core-types、vitest、tsc、lint、build 与相关浏览器验收。vendor schema 校验从测试调用固定版本 validator，不下载新 upstream，也不根据上游变化修改已定范围。

## 7. P4：导入报告、匹配、提案与弹窗

2026-10-18：P4 已在 `codex/core1-remaining` 实施，验证完成并进入 PR/CI 交付流程；验证、迁移与局域网验收见 `2026-10-18-core1-p4-import-workflow-progress.md`。导入只生成待审提案，开发/生产迁移和 DataAgent 部署仍单独执行。

### 任务

**P4-01 导入记录与材料。** 新增 `ImportRecord`（建议表名 ontology_imports）及 Alembic revision：workspace/user、adapter、filename、raw artifact/hash、formatted material/hash、report_json、converted core artifact、content_sha256、preview base version/hash、session_id/batch_id、确认幂等信息。Report 保存原始 target ids；最终 id 对照单独保存/读投影，不原地篡改历史报告。确认后的报告挂会话可重新打开。

新增 `services/import_materials.py` 复用 materials 上传/切分/按 workspace+SHA 去重。原上传字节 artifact 保留，JSON 以两空格缩进且保持键序生成作为可引用材料，JSON pointer→格式化行范围由解析器/格式化器实际产生；上传 SHA、格式化材料 SHA 分别标识，不能混用。格式化会改变字节哈希，提案 evidence 必须用实际材料 SHA 与行号。JSON 解析失败只保原 artifact 和实际文件/行列信息。

**P4-02 统一匹配。** 新增 `services/import_matching.py::match_import/rewrite_import_ids/build_candidate_graph`：

1. 原生：先对全部元素按 UUID+kind 锁定，再对双方未锁定项按自然技术键；未匹配保留文件 UUID。外部：按技术键。
2. 对象技术名；属性/关系按所属对象+技术名；规则按归属+技术名；指标 technical_name；Dataset.name。先重写对象，再以 type_id 一对一匹配 Mapping。UUID 已锁定不能被自然键覆盖。
3. 事实/链接/证据只有 UUID，没有业务编号/quote 自然匹配；证据归属不可搬移。
4. 九集合全部引用重写，含 ratio、Dataset、MappingSource、Path 和 inherited_link_bindings 字典 key；expression 用 AST 重建引用，不改字面量。
5. 以 base + 导入 create/update 构候选最终图，先统一检查身份注册表跨种类复用和名称/引用；名字合法交换放同原子组。冲突及不能独立成立的反向依赖闭包阻断，其他提案继续。
6. 文件外元素保持不动；失败条目对应已有定义保持不动。无论空工作空间或重复导入，从不生成 delete。相同内容为 no-op；空文件不能清空已有工作空间。

**P4-03 两步 API 与哈希。** 新增 `api/imports.py`、`services/imports.py`：

- `POST /api/v1/modeling/workspaces/{id}/imports/{adapter_id}` 接收文件 bytes，默认 preview；返回 import_id/report/content_sha256、候选提案摘要和 completion 列表，不写正式会话草稿。
- `POST .../imports/{adapter_id}/{import_id}/confirm` 收 `{content_sha256,expected_current_version_id,idempotency_key}`；重新校验权限、报告/产物哈希与预览基线。head 改变时回 409 要求重新预览，不偷偷基于新 head 生成用户没见过的结果。
- 确认在同事务创建基于当前发布版的新会话（草稿仍等于 base）+ pending 批次，调用 build_import_batch/store_batch；producer 为 `{kind:'import',adapter,report_id}`，task_id 可空，不伪造 DataAgent run。响应 session_id/batch_id/report_id；重复确认返回同结果，不重复建会话。
- `/imports/ossie` 保留为 ossie-0.2 别名，只保留地址，不接受旧 merge/replace/publish 行为；新文档写完整实际 prefix。route 不是 `/api/v1/workspaces`，避免照设计简写注册错前缀。

**P4-04 待补全与实时阻断。** 保存 completion_status=available 的整条原文、依赖原因和候选来源；新建 `services/import_completion.py` 仅提供确定性选择/重新校验能力：裸 COUNT(*) 选 Dataset、补已登记列/方言或修正定义后生成新提案，沿正常 revision/hash/审阅。原历史报告不改；当前阻断从会话候选图重新计算，补完依赖立即解除。不得自行提关系/改变指标统计范围；需要业务改写时由用户明确审阅该修改提案。AI 运行能力后续独立交付。

**P4-05 导入 UI。** 删除旧 `OssieImportDialog` 的 replace/firstImport/publish/publishError/published/publishApi 分支，新建 `components/ImportDialog.tsx`、`TranslationReport.tsx`、`ImportCompletionList.tsx`；client/types 新接口。Ossie/native 单文件二选一；上传、预览、取消、重试、新文件重置、确认幂等、过期重预览、报告中原文/材料定位均有状态。条目级 error 不把所有合法提案按钮锁死；文件级 error 禁止确认。确认后跳 `builder?session=...` 提案页；没有直接发布、跳转 delivery 三方合并入口和文件 diff 页面。Builder/SessionPicker/ProposalPanel 能识别 import producer、打开报告、人工处理待补全列表。新 UI 直接用 `Modal`/`Drawer`、`Steps`、`Form`、`Radio.Group`/`Select`、`Upload`（受控文件列表，禁止默认自动上传，沿 client 显式 preview/confirm）；报告用 `Table`、`Tag`、`Alert`、`Collapse`、`Typography`，待补全来源用 `Select(showSearch)`/`TreeSelect`。替代 `OssieImportDialog` 原生 dialog、文件/模式输入、报告 table，以及 `reference.css` 内专属导入规则；布局全用 Tailwind，不新建 import/report CSS，不删除仍用于其他页面的 reference。

**P4-06 API 与 UI 完整回归。** 新增 `test_core1_import_matching.py`、`test_core1_import_flow.py`、`ImportDialog.test.tsx`、`TranslationReport.test.tsx`。UI 复用 P0 Provider，覆盖 Upload 选文件不自动提交、报告展开/筛选、合法项可确认、确认 loading/防重、关闭重开重置、待补全搜索选择与焦点恢复。验 UUID 锁定 alpha/beta 反例、原子交换名、同名不同 map Dataset UUID5、Mapping UUID 已锁定他对象、同号事实/同 quote 证据不合并、反向依赖闭包、补齐后解阻断、证据行号/hash、重复 confirm、head 变化、空文件不删。首次/非首次导入都等用户接受，接受前已发布内容不变；接受后还必须正常发布。

### 完成标准与统一测试

§14.6 导入整行及 MCP 的事实审阅、部分本轮语义边界全部闭环。13 份 native 文件均能预览→提案→接受→发布；缺材料证据逐项 dropped，人工证据原作者保留。A/B 导入机械结果与 P3 一致，不把 AI 补全结果算机械成功。

阶段全部编辑结束后统一执行：

```sh
(cd apps/api && uv run --python 3.13 pytest -q)
(cd apps/api && uv run --python 3.13 ruff check src tests)
(cd apps/api && uv run --python 3.13 python -m ontofoundry_api.contracts.export_schema --check)
npm run check:core-types --workspace apps/web
(cd apps/web && npm test -- --run)
(cd apps/web && npm exec -- tsc -b)
(cd apps/web && npm run lint)
(cd apps/web && npm run build)
```

同批包含新 Alembic 的 PostgreSQL 升级测试（需预配 disposable URL）；没有环境就记录未覆盖，不能只用 create_all 证明导入表迁移。集中手工走三个文件：A/B 之一、07 缺证据材料、13 无对象指标；确认直接发布入口消失；复用 P0 dev/preview 命令在局域网 HTTP 验 Upload/报告 Modal 与嵌套选择器，检查主题/层叠、焦点、文件重置和包体积变化。

## 8. P5：导出、官方校验与往返

2026-10-18：P5 已在 `codex/core1-remaining` 工作树实施，验证完成并进入 PR/CI 交付流程。范围与验收见 `2026-10-18-core1-p5-export-workflow-progress.md`；开发/生产数据库切换和 DataAgent 部署仍是单独事项。

### 任务

**P5-01 原生与导出服务。** 新增 `adapters/native/exporter.py`，只输出 format/schema_version/exported_at/draft，保留 UUID、规则名、映射、指标、事实、人工证据；报告单文件不含材料，不写“完整备份”。新增 `api/exports.py`、`services/exports.py`，从明确选定的发布快照输出，不从旧 ossie_json 读。沿设计 GET exports/{adapter_id} 提供报告/产物描述，另给同一 hash 产物下载资源；不为 GET 写入本体或新版本。参考字段：report、content_sha256、filename、media_type、download_url。下载再核权限，不能以下载 URL 绕过实例/映射读取授权；完整模型导出仅满足所需权限者可取，不静默给半文件冒充原生完整模型。

**P5-02 Ossie 本体导出。** 新增 `adapters/ossie/exporter.py`：对象/单父/有效标识/规则/RT-67 成员、七值类型、自环 related 正反读法；标识值概念预留所有对象与内置名、忽略大小写碰撞并稳定分配后缀。对象与内置名同名明确报 error。规则按 id 重建现名引用，不导出规则名/技术名/描述；成员条件与说明性 derivation Rule 不能混写。空 ontology（09/13）提前 error，不造假对象通过校验。

**P5-03 Dataset 与绑定。** 扩 `adapters/ossie/mappings.py` 双向翻译：每个 Dataset 恰好一个外部 dataset，所有对象/附表/关系/指标共用；merge 属性 field、物理键/JOIN 辅助 field、登记列。名称冲突稳定后缀并重写引用。一个主身份 object_mapping + 平铺 children 指各来源字段 + 唯一星形物理连接；复合业务标识一层 referent，物理键独立。支持 direct/映射表/unique 非主键，业务目标身份不能由引用列直接表达时只丢业务子节点，仍导物理连接/unique_keys 并报告。

快照历史键加本数据集日期，不能把时点键当整表 PK；同一 Dataset 来源键冲突省略而不任选，RT-64。成员扩展/虚拟并集按 RT-57/65；跨来源计算 RT-54；快照和指标时间写描述并 RT-60；来源方言/列类型/采集元数据无法同构按 RT-66，不从说明机械恢复。

**P5-04 指标一一导出。** 扩 metrics.py：每核心 Metric 一条 OSI metric，不造辅助指标、不复制 Dataset；simple 固定聚合与 CASE，ratio 展开两个完整分量，小数除法与 NULLIF；expression 仅重写已解析列引用、保留拼接常量/NULL/算法。COUNT 行规范式精确为带本数据集任意登记列的 `COUNT(CASE WHEN ds.f IS NULL THEN 1 ELSE 1 END)`，条件版外套限定 CASE；不能改 COUNT(ds.f)。含 COUNT(*) expression 可只规范其中行计数保来源，不能抹去其余算法。无可用登记列/来源不能表达/核心指标非法 RT-61 error，保留核心定义、整份不交付缺必需指标文件。ratio 涉及分量过滤/时间时逐项 RT-58 converted+warning。

**P5-05 交付文件合法性。** 每份将交付的 Ossie 跑固定官方 schema 和 semantic validator；失败 report error、不返回下载。预检已知边界与编译 bug 区分，均留定位。Ossie 不导证据、事实、规则元数据的报告粒度按 §6.7；ai_context.ontofoundry 仅 core-1 显示名/反向名/同义词/标签/必填/标题等，不私藏整个 core 模型。

**P5-06 导出 UI。** 新增 `components/ExportDialog.tsx`，复用 TranslationReport，格式选择、损失、逐指标约定与同产物下载。改 DeliveryPage、ReleaseReview/HistoryComparison 和 client.exportUrl 对应入口，移除旧版本直接下载 ossie_json 的假设。09/13 展示 error 和可用原生单文件选项，不能自动切格式后标成功。直接使用 antd `Modal`/`Drawer`、`Form`、`Select`/`Radio.Group`、`Alert`、`Button`，报告复用 P4 的 Table/Collapse；DeliveryPage/ReleaseReview/HistoryComparison 的相关版本选择、手写导出表格替换为 `Select(showSearch)`/`Table`。布局用 Tailwind，清理 reference/publish/ontology-reading 中对应旧下载与版本比较规则，无新 export 页面 CSS。新增 `ExportDialog.test.tsx` 覆盖格式/版本选择、错误无下载、权限、报告与下载 hash 一致和关闭状态。

**P5-07 RT 往返与清扫。** 新增 `test_core1_ossie_export.py`、`test_core1_native_roundtrip.py`、`test_core1_ossie_roundtrip.py`；重写 `test_synthetic_ossie_roundtrip.py`。每个已支持 RT 最低定向往返断言同时存在。用 `rt_cases.py` 中明确源路径、预期目标/损失和变换断言检查差异；不能仅断言 report 有某 RT 就让任意字段变化通过。A/B 样例所有语义差异必须对应 RT，RT-10 排序可忽略。完整通用 diff_roundtrip 分类器后补，但不允许整文件差异一律盖 RT-20 或 RT-47。最后删除 scripts/ossie_coverage_matrix.py 的调用与旧覆盖率断言，保留 RT-25/42/44 等停用编号，不重用。

### 完成标准与统一测试

§14.6 往返整行完成。01–08、10–12 的 Ossie 文件全部通过官方验证；09/13 完整 Ossie 导出稳定 error 且无 artifact。13 的 metric 定向互译用另一个有已定义业务对象的测试容器，不往原 13 JSON 偷加占位对象。native 单文件除了缺失材料证据的明确损失外保留定义及 UUID；ZIP 无损不在本轮验收。

阶段全部编辑结束后统一执行：

```sh
(cd apps/api && uv run --python 3.13 pytest -q)
(cd apps/api && uv run --python 3.13 ruff check src tests)
(cd apps/api && uv run --python 3.13 python -m ontofoundry_api.contracts.export_schema --check)
npm run check:core-types --workspace apps/web
(cd apps/web && npm test -- --run)
(cd apps/web && npm exec -- tsc -b)
(cd apps/web && npm run lint)
(cd apps/web && npm run build)
```

同批使用已配的 PostgreSQL/MySQL 复算导出再导入后的可执行指标，不只比较 SQL 文本。人工集中核查导出报告/不可导出、历史版本选择、权限、下载哈希及文件名；用 P0 dev/preview 命令复验局域网 HTTP 下载和报告弹层，记录 JS/CSS 体积变化与最终 CSS 清理清单。

## 9. 删除与替换清单

### 9.1 后端代码

| 时机 | 文件/内容 | 处理 |
|---|---|---|
| P2 | `domain/models_v3.py`、`domain/legacy_v1.py` | 删除文件，models.py 的 v2 定义/版本联合全部删除 |
| P2 | `domain/snapshot.py` | 删除 normalize_v1/as_v2_dict/normalize_v2_to_v3/as_v3_dict/legacy_rule_id 等；保留仅 core 边界 |
| P2 | `domain/runtime_views.py`、`semantic_views.py`、`semantic_authoring.py`、`semantic_edit.py`、`semantic_fields.py`、`role_join.py`、`fact_views.py` | 旧语义树/角色/二元兼容投影删除；有效绑定与事实逻辑由新模块承担，不留转 v2 的 helper |
| P2 | 旧 `ossie/native.py/extensions.py/importer.py/compiler.py/mappings.py/coverage.py` | 删除。schema/validator/license 先移动到适配器目录供 P3 使用；domain 与发布不 import 它。sha256_json 若仍需要改为核心通用实现 |
| P2 | `api/semantic_editing.py` 的 SemanticChange 和树编辑、旧 metric_id sql-preview；`api/modeling.py` semantic-models/published-legacy-form、旧 imports/ossie | 删除/下线；metric preview 移新接口，P4 恢复导入别名 |
| P2 | `api/mcp.py` 旧工具名（四工具之外）与 source=database | 删除旧注册/参数/分发，只保留四工具；旧 get_object.ref 换 id，search_objects 删 source |
| P2 | `services/model_result.py` 完整 model-result 分支、旧 candidates 接受流程及对应 API | 删除并同步候选 UI/类型，保留 proposals 接收和普通运行恢复，不把整个 model_result 文件误删 |
| P2 | `actions`、ActionParameter/Effect、owner_kind=action、ontology_requires | 全面删除模型、提案/schema、diff/hash/merge/发布/图/提示词字段；不写迁移报告 |
| P2 | `OntologyVersionRecord.ossie_json`、旧独立 `/workspaces/{id}/publish` 用户入口 | 删字段/路由；内部发布服务保留；不删正常会话发布与三方冲突解决 |
| P2/P5 | 版本兼容测试和 coverage 脚本 | 先拆有效验收，再删纯旧合同文件；脚本最迟 P5 删除，第一部分不运行旧覆盖率脚本 |

`domain/` 不 import adapters/ossie；api/services 可依赖 domain 和 adapters，但导入合并归 services，不归 adapters。新增架构测试检查 import graph，不能仅搜索一个字符串漏掉相对 import。

### 9.2 前端与 DataAgent

- 删除 `lib/nativeDraft.ts`、nativeDraft.fixture.json、nativeDraft.test.ts、api/client.native.test.ts 的旧协议断言；新的 core 保存不经双向转换。
- 删除 `components/VerbalizationEditor.tsx` 及测试、`lib/verbalization.ts`、`components/RelationshipRoles.tsx`、`components/elements/ElementActions.tsx`；删所有 actions tab、路由参数、计数、帮助文字和动作规则分支。
- 删除 `components/SemanticModels.tsx` 及测试、`components/semantic/MappingTreeEditor.tsx/SemanticObjectForm.tsx`、`lib/semanticEditing.ts`；改写 objectMapping 系列，不留下引用树类型。
- 改写 draftView、elementModel、semanticExplorer、图与实例层；删除 value_type/builtin/role 图节点、旧 NativeFields/ConceptRef/presence/position/owner_ref/RoleJoin/LegacyDraft/NativeDraft 类型。Dataset 新扁平类型必须保留。
- 删除 MaterialObject.name 表单/读字段；属性技术名恰为 name 仍可合法存在，不能全局删除 `name` 字段。
- 删除 OssieImportDialog 首次直接发布、replace、跳 delivery 三方合并；正常发布页和冲突面板保留。P2 隐藏旧 export，P5 恢复新导出。
- 不重建 main 已删除的 AdvancedMappingDialog、MappingStructure、NativeMappingEditor、MappingForm、ObjectEditorPage。
- `md2ossie` 目录改名改写；删 scripts/validate_ossie.py、tests/test_validate_ossie.py、template.ossie.json 和核心建模用 vendor 校验依赖。reading-ossie 保留规范参考与必要 NOTICE/PROVENANCE；API 适配器自己的固定 schema/校验器不能一起误删。
- 两份 agent 提示词、DataAgent README/Makefile、capabilities.skills、上传 schema manifest 一起改；旧合同 B、旧名称和旧轮次建模规则删除。

### 9.2.1 前端 CSS 清理与控件替换台账

路径均相对 `apps/web/src/styles/`。每个前端 PR 记录迁移的组件/规则、已删行数、仍保留的消费者；删整文件前用 `rg` 核对 TSX/className 与集中入口/测试引用均归零，不能只检查 CSS import（P0 已集中导入）。

| 时机与文件 | 对应迁移 / 可删除条件 |
|---|---|
| P0 `tokens.css`、`global.css` | tokens 永久保留为唯一设计源；global 的最小 base 与旧组件规则分层隔离，后续删已替代的按钮、输入、弹窗、表格样式。global 不在 P0 整删 |
| P2 `semantic.css` | 删除 SemanticModels/MappingTreeEditor/SemanticObjectForm 并移除其唯一消费者后，删除整个文件及入口 import；新指标/数据集不再依赖它 |
| P2 `element-inspector.css` | Inspector/ElementPanels 用 Modal/Drawer/Form/Tabs + Tailwind 替代后，删对应规则；全文件无消费者则整删 |
| P2 `object-mapping.css` | MappingWidgets/各映射表/DatasetPicker/实例表用 Select/Table 等替代后删其规则；xyflow/关系图专用规则与其他仍用消费者保留至迁移完成，不能按文件名直接整删 |
| P2 `semantic-view.css` | SemanticView 用 Segmented/Input/Tree/Table + Tailwind 后删除旧资源列表/筛选规则；两类旧资源也迁完且无消费者时整删 |
| P2 `ontology-overview.css`、`page-tabs.css` | Overview/WorkspaceTabs 的统计导航、Tabs/Modal 与 Tailwind 完成后，各自无消费者即可整删 |
| P2–P5 `proposals.css`、`publish.css` | Proposal/ReviewOverlays/Publish/ConflictResolver 改 Table/Checkbox/Modal/Drawer 等后删对应规则；保留仍使用的差异/冲突展示或历史页规则，最后消费者迁完后整删 |
| P2–P5 `ontology-reading.css`、`reference.css` | DataAssets/实例/ReleaseReview/Delivery/导入导出按任务逐段清理。reference 还服务连接/成员设置等未改页面，不作为本轮必须整删的目标；P2 删除旧导入专用块，P4/P5 不添回 |
| 持续保留 `index.css` 与第三方 xyflow CSS | index 只保留层序、imports 与集中基础设施配置；xyflow 的必要图样式不计入手写控件重写目标 |

未涉及的 AppShell/DataConnections/Settings/WorkspaceDirectory 等保持已有业务与存量豁免；当 core-1 实施确实改其控件时，同次以 Form/Select/Table/Modal 等替代并撤销豁免，不借 CSS 清理扩大成全量重写。新页面不继承存量豁免。

### 9.3 测试处理，不按前缀批量删

| 测试组 | 操作 |
|---|---|
| test_p0_v3_contract、p1_native_roundtrip、p1_roles、m7_optional_role_names、p3_verbalization_retype | 纯旧结构/语法树保真断言删除，新增 core static/RT 测试替代 |
| p1_legacy_form、p3_semantic_views、p3_semantic_integration、test_semantic_editing | 旧表单回写/树编辑删除；有效列绑定、授权、变更预览迁到 core bindings/element save/metric preview |
| p1_mcp_roles、p2_mcp_synonyms、t7_mcp_elements、p2_m4_compact_projection | 角色/旧工具断言删除；同义词搜索、协议、权限、分页/内容预算改为四工具断言 |
| p2_extensions、旧 extension v1–v3 fixtures、ossie_name_description | 不再测试旧扩展回读/还原；留最小旧块输入仅证明 RT-03 dropped；名称取工作空间/核心元数据改为 adapter 测试 |
| t1_v2_model、t2_postgres_migration、t8_switch、m6_session_cleanup | 纯 v1→v2/v3 兼容删除；fresh migration、清空保留范围、run context 固定/失效迁到 core1_cutover/pinned tests |
| t0_characterization、t1_proposal_contract、t2_pinned_context、t3_proposal_results、t4_proposal_decisions、test_proposal_undo、t6_publish_preview | 保留业务行为，换 core 夹具，增加 dataset/metric/原子组；不能因 P/T 前缀删除 |
| test_instance_queries、stage_a/boundaries/mysql、p3_owner_join_replay、m8_binary_facts_replay、p4_metric_query/postgres | 来源/键参数化/只读/复合键/分页行为改写；删角色兼容、强制同日及父来源决定日期旧断言；真实查询回归保留 |
| test_model_result/run_sync/agent_conversation_bff/dataagent_client | 删除旧合同结果消费断言；保留错误恢复、租约/幂等、运行状态等，与 core proposals 联动 |
| 现有前端 ElementInspector/ElementInstances/SemanticView/MappingsPage/ProposalPanel/PublishPanel/ReleaseReview/BuilderPage tests | 改为同一核心 fixture 与 P0 Provider，适配 antd portal/异步交互；保留并发/导航/编辑/提交结果，审阅快照变化；新增 UI foundation、三交互与导出行为测试 |

历史 `real_runs/` 夹具如含真实名称/表位置，不直接复制到新测试或计划中；以通用虚构 replay 保留运行恢复断言，旧 v3-only replay 随对应测试退役。auth/static/app/settings 等无关有效测试不改语义。

10-08 主计划、P1–P4 进度、coverage matrix 共 6 份文档在 P2 顶部标“已被 core-1 主设计取代”。引用设计链接，不重写历史结论来冒充当时已经实现。

## 10. 十三个示例作为可执行夹具

### 10.1 夹具规则

- 唯一 JSON 来源是 `docs/design/core-1-examples/`；Python/TS loader 直接读取。每例单独隔离工作空间，不能把多例同名对象、复用 UUID 直接拼一起。
- 四层分别断言：schema/图；生命周期/读投影；虚构物理行查询；adapter/报告。模型解析成功不等于证据或查询验证成功。
- 原生导入测试使用完整 envelope；模型单测只取 draft。workspace_id 以目标环境替换，其他 UUID 保持，除非匹配规则明确要求复用目标 id。
- 03/06/07 的演示材料哈希/行号没有附原文：机械单文件导入须测缺失证据 dropped。另建短小虚构材料文件，填到指定行，用真实 SHA 重写测试内 evidence 验 quote 与标题回退；不要假造原材料存在，也不修改示例哈希来逃过检查。
- 非空 columns 缺列按 P0 问题修正后再验；保留修正前负例。08 columns 缺省是未知元数据，合法但未完成，不补假证据或自动推断列真实存在。
- 虚构 SQL seed 放 `apps/api/tests/fixtures/core1_data/`；只用于 disposable 数据库，声明表/行/预期。派生变体用 deepcopy，不写回设计文件。前端必要 fixture 通过 loader 引用，不抄新一套 13 JSON。

### 10.2 示例与阶段验收表

| 示例 | P1/P2 核心、UI、查询/MCP | P3/P4 导入 | P5 导出/往返 |
|---|---|---|---|
| 01 basic-sales | synonyms/标题、关系表复用；金额 100+200+50=350；一完成一取消完成率 0.5；median；半开季度区间 | 固定 CASE/可空 COUNT/列去重/ratio、复杂 OR 和拼接 expression | 一指标一 OSI；COUNT 行锚定、ratio 分量、字段重写仅标识符；RT-47/49/50/55/56/58 |
| 02 many-to-many | 无成绩纯配对与带成绩中间对象分离；成绩 90/70→均值80、行数2；不同端键宽合法 | 纯映射表识别、业务边唯一匹配 | mapping_table、复合根身份；不合并两种业务模型 |
| 03 n-ary-reified | 三实体编号复合标识/direct；数量10/20→30、供应商去重2；属性约束共存 | 另造源多元输入验角色顺序、缺决定/最后角色、值约束祖先传播 | 输出普通中间对象，不还原多元；RT-24/27/28/31 |
| 04 composite-key | UUID 标识顺序与物理 key 顺序独立；qty2/3/4→9，单价10/20/30→金额200；发货4含孤儿仍4 | to_columns 反序时 from 随完整键重排，不能只验长度 | referent 身份、计算列回读；逻辑/辅助 field |
| 05 self-and-parallel-links | 正反/自环/买卖方向；交易100/200→300、员工2、工位3（含未分配/脏关联） | 平行边按业务关系+身份+列组匹配，歧义报缺绑定 | self.related 正反读法、精确列组保留 |
| 06 inheritance | 三建法；父3/个人1/VIP1；虚拟资产设备+车辆并集；同局部键不误并；derived 改动不改 VIP metric | 首父/完整派生/RT-68 另源变体；不猜独立子表覆盖 | RT-57/65/67/68；本体与绑定损失分别报 |
| 07 instances-and-evidence | 缺标识保存；标题/完整键/可见 quote/UUID，0/false；同号两事实按 UUID 返回 | 缺材料 dropped、人工保留；引用/归属不按 quote 合并 | 实例/证据丢失报告，原生单文件不称无损 |
| 08 rules | 三归属规则/路径重命名、计算 CASE，不重复保存 derivation；本体无绑定规则仍合法 | 值类型>=0、子类型>0传播且保原规则，字符串不替换 | 规则表达式保留、名字/说明损失；同行 CASE 回读 |
| 09 empty | 核心合法、空会话/发布/MCP 目录 | 空导入不删既有模型，不生成 delete | Ossie error 无下载；native 成功 |
| 10 partial | 城市/关系 unbound；默认 database/schema 服务端解析，缺连接状态明确 | 部分条目未转换时已有定义保持、独立提案可接受 | 定义保留、映射损失列报告，不能造占位表 |
| 11 multi-source-and-unique-link | main+amounts LEFT JOIN，附表孤儿不造对象；unique 非主键 direct；指标100+900=1000 | RT-52 星形绑定、RT-53 业务目标身份不能凭编码猜 id | 物理关系和 unique_keys 保留，缺业务 link 子节点单独报告 |
| 12 snapshot-and-trends | 11月末14、12月末10、精确12-29为16、按组件分组仍12-31；状态/仓库独立12-30；成员筛选不改末日 | 不从描述恢复快照或猜引擎 | RT-60 时间、RT-64 历史键、RT-66 元数据；native 保留声明 |
| 13 dataset-metrics | 无对象照样建指标/预览；提交10、core8、ratio0.8、仓库2、行3；按日去重1/2但全周期2 | 原生无对象提案与发布完整；不反查对象补来源 | 完整 Ossie error；指标定向另配已有对象容器，不改本例 |

### 10.3 §14.6 验收矩阵归属

| §14.6 行 | 必须收口阶段 | 附加负向/边界 |
|---|---|---|
| 来源绑定 | P1 结构，P2 真实读取，P3/P5 外部互译 | main 顺序、20+来源、缺附表、缺键、空清单、unique 非主键、两侧键宽不同 |
| 继承 | P1 静态，P2 UI/事实/数据库，P3/P5 派生与绑定报告 | 多层虚拟、父有绑定后代、成员表交集、保留关系 id、不扫覆盖 |
| 计算列 | P1 解析，P2 读取/MCP，P3/P5 单来源回读 | 乘法/CASE、跨对象/计算属性/窗口禁止，跨来源导出风险 |
| 指标 | P1 结构/依赖，P2 预览/编辑，P3/P5 OSI | ratio 跨集、只读输入、NULL/空集、复杂本数据集 expression、删列/快照组 |
| 平台预览 | P2 | 未保存定义、慢响应过期、权限、引擎不支持、白名单失败、总值趋势分别执行 |
| 时间 | P2，P5 验损失 | 数据集全局末日、不同来源日期、事件整体去重、ratio 不同分量时间；空周期不新增核心默认 |
| MCP | P2，P4 回归导入后事实 | 4 工具、无 version 输入、空 pinned、清版/改发布/改权限游标、256 KiB/超大单字段、授权摘要/缓存 |
| 导入 | P3 翻译，P4 提案闭环 | 无 delete、UUID 锁定、交换名、反向依赖、原文/定位/待补全、报告 hash |
| 本轮语义边界 | P1/P2 + P3/P4 | 对象成员与指标独立、多元键/值约束、映射锁定、事实仅 UUID、通用 error 无 RT |
| 往返 | P5 | 09/13 error、RT-61/69、COUNT 空列/行、裸 COUNT 来源选择、无列 expression 不能丢来源 |

额外固定数值验收：`COUNT(amount)` 与 `COUNT(CASE WHEN flag='Y' THEN amount END)`，两行 flag=Y、amount=NULL/10，都为1；行计数为2，空集为0。原式保留 expression。COUNT DISTINCT CASE 单独证明忽略 NULL；SUM ELSE 0 不能误结构化成 ELSE NULL。此组必须在 P3 输入分类与 P5 往返同时存在。

## 11. 规模、顺序与可并行工作

估算含代码/测试/生成文件增删，不是只算新增行。大文件 v3/语义树删除较多，文件数各阶段可重叠，不能直接求和当净文件数。实际实现完成每阶段后更新估算。

| 阶段 | 预计涉及文件 | 大致手写增改/删除量（行） | 主要工作量 |
|---|---:|---:|---|
| P0 | 10–16 个前端配置/基础设施/测试文件，另有仓库外演示 | 增改600–1,200，原型另计且不提交 | 依赖固定、Vite/CSS 层、tokens/Provider、测试/lint、HTTP 验收与交互核对 |
| P1 | 18–28 | 增改3,000–5,000；生成 schema/TS 另计 | 表达式/继承/依赖及类型统一 |
| P2 | 105–150 | 增改11,000–19,000；删除11,000–18,000 | 前后端 core 切换、查询/预览/提案/MCP/技能；对应 UI 换 antd/Tailwind 与局部 CSS 退役 |
| P3 | 18–28 | 增改3,000–5,000 | 确定性 Ossie 转换、报告与定向夹具 |
| P4 | 20–32 | 增改3,500–6,000；删旧对话框约300 | 两步导入、匹配/id 重写、材料证据、提案组与 UI |
| P5 | 16–26 | 增改3,000–5,000 | 外部合法输出、报告下载、RT 语义往返 |

推荐执行顺序：最先完成 P0-FE 基础设施；交互核对可与 P1 核心基础实现并行，P1 前端检查须基于 P0-FE；P1 合并后集中 P2；P2 全阶段通过后 P3→P4→P5。若需要缩短单 PR，P2 只能拆成同集成分支上的内部子提交/审阅单元，不部署半切换、不为拆 PR 引入兼容模型。

契约固定后的可并行部分（这里只列分工机会，不要求实际启用多个 agent）：

- P1：模型/schema、表达式解析、fixture/依赖测试可分别准备，共同依赖 core.py 字段约定。
- P2：后端生命周期、实例/指标预览、MCP/权限、前端数据层、DataAgent 技能可并行；api/types 与模型入口由一处统一改，避免多人各写一套。原子组/保存接口必须先定后接 UI。迁移与部署清单可并行编写，执行要在整个切换就绪后。
- P3：Ossie 关系/规则、映射、metric、native importer 可并行；共用 id 对照、报告和符号表，不各自重复匹配。
- P4：匹配/提案服务、材料/报告持久化、UI 可按已定 API 并行；确认事务依赖三者完成。
- P5：本体 exporter、mapping/metric exporter、native/download UI 可并行；官方校验与全部 RT 收口统一完成。

真正需要用户参与的只有 P0 的新交互确认，以及导入某条内容无法等价转换时的业务改写审阅。类型命名、文件拆分、分页实现、哈希、删除旧测试、清空范围等工程工作按本计划执行，不重复发起产品确认。若选择增加对象详情“相关指标”，须在原型里确认其价值；默认不增加，且永不持久化对象指标关联。

### 11.1 前端专项风险与收口

| 风险 | 处理与验收归属 |
|---|---|
| 包体积增加 | P0 安装前记录现有 production build JS/CSS 原始及 gzip 基线，接入后及 P2/P4/P5 再比较；使用 antd ESM 的命名导入，避免全量 locale/图标/重复 cssinjs，日期只取 zh-cn。检查构建输出的 chunk 与首屏加载，确有增长瓶颈再按路由懒加载；不凭开发模式体感声称 tree shaking 生效 |
| antd 与现有 global/reference CSS 冲突 | P0 先做层序与旧样式隔离；未分层正常声明高于所有 layer，components 也高于 antd，故收窄旧通用规则是必做项。关闭 preflight，禁止内部类覆盖和 `!important` 堆叠；P2 迁移页与未迁移页在浏览器逐项验控件、字体、边框、焦点和滚动 |
| DOM/测试快照变化 | antd portal、Table 结构、动态样式和动画会改变旧断言。P0 建 Provider/polyfill，P2/P4/P5 改 role/name 与业务 payload 断言，审阅每项有意义快照差异，不批量接受快照或全局 mock 组件；jsdom 不承担布局验收 |
| xyflow 与 antd 弹层 z-index/裁剪 | P0 在 tokens 统一图/导航/遮罩/弹窗/下拉/提示层级，映射 `zIndexPopupBase`；P2 验图拖动、缩放/transform、Drawer 内 Select/TreeSelect/DatePicker 与工具提示。Modal/Drawer 保持合适的 body portal，子 popup 按滚动容器选择 getPopupContainer，不用全局一刀切父节点；必要的层级值来自 tokens。存量原生 dialog 属浏览器 top layer，不能靠调高 antd z-index 跨越：同一已迁移交互链的 dialog 必须一起改为 Modal/Drawer |
| 局域网 IP HTTP 与 localhost 行为差异 | P0-FE-07 建立真实 IP 非安全上下文记录，P2/P4/P5 验编辑/预览/上传/下载和受限能力降级；浏览器不支持目标 CSS 能力时明确记录，不以修改安全开关验收 |

## 12. 发布操作与阶段记录

每阶段开始记录基线 commit、依赖阶段版本、变更文件和外部环境是否可用；全部编辑结束再集中跑该阶段命令。失败时针对失败根因改完再跑受影响检查，不在尚未完成阶段编辑时反复跑全套。阶段结束保留命令、Tests run/Failures/Errors/Skipped、手工验收结果、未覆盖条件，不能把 skip 写成通过。前端阶段另记录新依赖确切版本、构建体积基线/差值、CSS 退役台账和 localhost/局域网 HTTP 开发与预览结果；纯后端 P3 若未动前端注明不适用。

P2 数据清空仅在后续实施的切换部署执行，本次计划没有执行。清空前沿正常运维保留数据库备份，停止旧建模任务和结果同步，执行 Alembic，再启 core-1；保留范围有表级测试证明。不可恢复旧内容由备份处理，down migration 不伪造旧本体。P4/P5 加表/字段同样先在 disposable PostgreSQL 验迁移，不拿本地真实工作空间试删。

P2 导入/导出暂下线由能力接口和 UI 控制；旧路径返回明确不可用/不存在，不携带旧实现依赖。P4 开导入、P5 开导出各作为阶段交付行为。新的原生完整包实现之前，备份依赖数据库/材料常规备份，单文件仅用于定义查看与交换。

## 13. 执行检查表（逐项勾选）

- [ ] 确认基线 b8ac8c0、工作树状态，引用当前设计决定 49–51；只用虚构名称/表。
- [ ] P0-FE：新依赖确切版本/peer 兼容已记录，package-lock 固定，npm ci/npm ls 通过，保留 React 19/Vite 6。
- [ ] P0-FE：Vite 插件、集中 CSS 入口、theme/base/antd/components/utilities 层序完成；无 preflight/reset、散落未分层 import 或旧通用样式污染。
- [ ] P0-FE：tokens 唯一来源，Tailwind @theme 与 ConfigProvider 映射一致；#0061ef、圆角6、PingFang SC、z-index 生效。
- [ ] P0-FE：React 19 patch、StyleProvider/ConfigProvider/antd App、zh_CN/dayjs 中文与 useApp 上下文完成。
- [ ] P0-FE：matchMedia/ResizeObserver 等 polyfill、测试 Provider、基础冒烟、ESLint 存量豁免/无新增 select/dialog 与评审规则完成。
- [ ] P0-FE：vitest/tsc/lint/build 通过；安装前后包体积、旧页共存、localhost/局域网 IP HTTP dev/preview、弹层与安全上下文检查有记录。
- [ ] P0：完成指标预览、派生条件、导入三个交互确认；原型未进入 Git，计划/代码不引用仓库外原型产物。
- [ ] P0：记录 06/12 元数据缺口，默认不加对象相关指标入口，后续扩展不混入首版。
- [x] P1：九集合与四判别联合完成，核心无 adapters/ossie 依赖。
- [x] P1：三种表达式上下文、稳定 id 引用、继承/键/指标边界、依赖组完成。
- [x] P1：核心 schema→TS 生成与 check 可用，13 例夹具及负例就绪；共用 P0 Provider，含 build 的阶段统一测试通过并记录。
- [ ] P2：切换 snapshot/canonical/models，删除 v1/v2/v3 运行分支和转换器。
- [ ] P2：提案九目标/client_ref/原子组/undo/幂等、element save 与三方发布完成。
- [ ] P2：发布与 Ossie 脱钩，09/13 可发布，导入导出暂时下线。
- [ ] P2：清空迁移覆盖 FK 顺序、保留表、旧回调失效；fresh base→head 与旧 head→head 均通过。
- [ ] P2：Dataset 来源唯一解析、主附/继承/多对多/复合键/独立快照和只读实例查询完成。
- [ ] P2：事实 display_text、同号提示、人工改更新追加证据、UUID 分页完成。
- [ ] P2：未保存指标完整定义只读预览，总值10、ratio0.8、月趋势/失败/过期状态完成。
- [ ] P2：四 MCP 工具、授权裁剪、无 version 参数/连接别名、签名分页和缓存隔离完成。
- [ ] P2：前端唯一 core 类型/读写，三新交互、四类资源、动作/语义模型/事实名删减完成。
- [ ] P2：指标表单/预览、派生编辑器、指标/数据集资源直接 antd + Tailwind；既有 Inspector/映射/提案/发布/实例页面按任务同步换控件。
- [ ] P2：semantic.css 随旧页退役；其他 CSS 按 §9.2.1 清理、记录剩余消费者；无新页面 CSS/原生 select/dialog，已迁移文件撤销 lint 豁免。
- [ ] P2：antd portal/异步/可访问性与业务提交断言通过；快照已审阅；xyflow 弹层/焦点/裁剪、局域网 HTTP、包体积回归有记录。
- [ ] P2：建模技能与问数提示词、结果收集器、部署技能 ZIP 配置同步完成。
- [ ] P2：阶段全部编辑后统一 pytest/vitest/tsc/eslint/ruff/build/schema 检查；外部 skip 如实记录。
- [x] P3：两导入器仅翻译独立合法核心子图，RT 与原文/真实定位完整，A/B 支持子集验收完成。
- [x] P3：值约束/多元完整键/RT-68/COUNT 分类/RT-69 负例通过，统一测试已记录；未动前端则标不适用，若动契约补前端整组检查。
- [x] P4：preview/confirm 同 hash、基线过期/幂等、材料 SHA/格式化行号、历史报告保存完成。
- [x] P4：UUID 两轮匹配、映射一对一、所有引用重写、名字交换和依赖闭包完成，永不生成 delete。
- [x] P4：确认只建 pending 提案，空空间也进入会话审阅；人工待补全和实时解阻断完成。
- [x] P4：新导入 Modal/Drawer/Upload/Form 与 Table 报告直接用 antd + Tailwind，无替换/直接发布/新页面 CSS；专属旧导入样式已删。
- [x] P4：13 原生示例与 A/B 导入验收；含选择文件不自动提交/防重/重置的 UI 回归和阶段统一检查完成，局域网上传/弹层/包体积已记录。
- [x] P5：原生单文件/Ossie exporter、逐项报告、每 Dataset/Metric 一一输出与官方校验完成。
- [x] P5：01–08/10–12 合法导出；09/13 Ossie error 无 artifact；native 不宣称材料无损。
- [x] P5：每支持 RT 定向往返、A/B 差异归类、行 COUNT/可空 COUNT/裸 COUNT 来源/ratio 无分量回读完成。
- [x] P5：ExportDialog 与复用报告直接 antd + Tailwind；旧版本选择/下载控件及对应 CSS 按任务替换，无新页面 CSS。
- [x] P5：下载同产物 hash、权限、版本选择；含 ExportDialog 的全阶段统一回归与局域网 HTTP 下载/报告/包体积/最终 CSS 台账已记录。
- [ ] 收尾：旧代码/工具/测试逐项清理，10-08 文档标取代；无原型、真实名称、凭据或临时夹具进入提交。

## 修订记录

### 2026-10-16：纳入 Ant Design 5 + Tailwind CSS v4

- 按已确认决定补 §1.2，并将 P0 最前置任务组改为“前端基础设施”：固定依赖、Vite/CSS 分层与关闭 preflight、唯一 tokens 到两套主题的映射、根 Provider/中文/React 19 补丁、jsdom polyfill、lint/评审规则和局域网 HTTP 验收。
- 修订 P2-17～21、P4-05～06、P5-06，逐项明确 antd 组件、被替换的现有原生控件/手写表格/弹窗，以及 Tailwind 布局边界；纯数据层和纯后端任务不扩大 UI 范围。
- 新增 §9.2.1 CSS 退役台账与 §11.1 风险表，说明 semantic.css 的删除时机、共享 CSS 的条件清理，以及包体积、旧全局样式、快照、xyflow/antd 弹层风险。
- 同步六阶段交付表、执行顺序与规模估算、P0/P1/P2/P4/P5 检查命令和人工验收、P3 不适用条件、阶段记录及执行检查表；移除“P0 不改运行代码/不跑前端测试”和“继续使用原生弹窗实现”的旧表述。
- 原地更新本计划文件；本轮未修改仓库、安装依赖、运行应用测试/构建、执行迁移或创建提交。仓库外原型不作为计划、实现或测试的可引用资源。


### 2026-10-16：P1 后端基础件实施完成

在 `9375ed3` 基础上完成 P1-02～06，补充 P1 模型约束与回归。实现、统一检查、外部服务跳过项和阶段边界见 [P1 后端实施记录](2026-10-16-core1-p1-backend-progress.md)。前端本轮只有生成契约和共享夹具，页面交由 Claude；P2～P5 仍未开始，不部署半切换系统。未创建提交、推送或 PR。
