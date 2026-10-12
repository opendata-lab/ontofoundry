# 语义层编辑原型 · 阶段 1

本次只有两份独立 HTML 原型与本说明，没有业务源码、接口、数据库或依赖清单的修改。双击 HTML 可打开，CSS、SVG 图标与数据均内联，不依赖服务或网络。右上角始终显示「原型 · 非实现」。所有演示修改只保存在页面内存中，刷新恢复初始数据；两个页面之间可以通过导航链接切换。

## 1. semantic-model.html

采用「目录 + 详情」工作台，与现有浅灰画布、白色卡片、蓝色强调、紧凑字号一致；使用 tokens.css 的 token。选择这一方案是因为用户要在大量字段中定位和编辑，完整图谱会挤占字段表空间，平铺卡片又难以比较表达式。

| 区域 | 内容与交互 |
| --- | --- |
| 顶部概览 | 模型技术名称、说明摘录、AIContext 提示；数据集、关系、指标、概念映射数量可以跳转到相应目录。 |
| 四个目录页签 | 数据集 / 数据集关系 / 指标 / 概念映射；各自保留搜索和新增入口，当前对象在右侧查看。 |
| 数据集目录 | 依据概念映射树对数据集的实际引用，分为已关联概念、待关联概念；支持技术名、物理表、数据集同义词搜索。 |
| 数据集详情 | source、原生主键、字段表；每页 10 个字段。展示表达式、实际方言、datatype、时间维度、同义词；下方概念映射、指标、连接可直接跳转。 |
| 数据集关系 | 两个数据集的小型连接示意；from_columns / to_columns 按原数组顺序成对展示，多键为 AND。编辑抽屉可增删键对。 |
| 指标详情 | 技术名、中文同义词、说明、类型、原方言表达式、数据集依赖、推导出的概念候选、可编译性、连接与快照约束。SQL 预览抽屉可切换方言、分组字段、日期等值 / as_of。 |
| 概念映射 | 对象根与关联分支分别展示；多根、children、referent_mappings 用可折叠树组织。抽屉可编辑表达式、概念与关系，增加对象根、关联根、子节点、标识引用，或删除节点。 |
| 编辑与删除 | 数据集、字段、关系、指标、概念映射均有新增 / 编辑 / 删除入口。被引用对象的删除先显示引用清单；名称变动涉及引用时需要影响预览，原型会给出反馈。 |

### 数据与边界

- 嵌入 `apps/api/tests/fixtures/ossie_real/architecture-governance.ossie.json` 的完整原文件内容：**41 datasets、371 fields、14 relationships、27 metrics、21 concept_mappings**。目录和详情由这些数据渲染，不只截取几个示例。
- 顶部短说明是原描述的摘录，原描述及模型 AIContext 均保留在内嵌数据中。模型 AIContext 的快照 / 滚动 / 事件说明通过 ⓘ 展示。
- B 的数据集没有声明 `primary_key`，显示「未声明」，没有根据字段名推断主键。编辑字段也不会推断维度、datatype 或同义词。
- 「核心服务数」搜索会出现 `core_service_count`，也会出现包含该词的「非核心服务数」候选；目录不强行消除匹配歧义。
- 指标目录中的执行信息是原型级依赖展示；单数据集并不保证可执行。提示中明确需要连接、安全编译和时间约束，跨数据集给出查询解释。
- SQL 抽屉明确标为「SQL 生成示意 · 未执行」；浏览器内的示例替换不是 sqlglot 的替代品，正式实现必须复用后端编译器与参数绑定，不执行前端生成的 SQL。
- 原文件中的方言、表达式、数组与字段缺省在内嵌数据中保留。尚未编辑的对象不会因展开、分页或切换目录而补出缺省字段。原型并不生成 Ossie 导出文件。

### 建议评审路径

打开页面 → 选择 `component_snapshot` → 下一页查看 `snapshot_date` → 点击引用指标「核心服务数」 → 查看表达式与快照提示 → 预览 SQL 并切换 as_of → 选择「数据集关系」中的 `deployment_to_component`，查看两个键对 → 选择「概念映射」中的 `component`，展开多个关联分支 → 编辑抽屉增加对象根 / 标识引用。

新增一个不被引用的数据集，再新增、编辑、删除字段，可以检查完整 CRUD 反馈；删除现有 `component_snapshot` 会先展示引用清单。

## 2. relation-editor.html

使用 **860 × 560** 的紧凑居中元素窗口，标题和页签固定、内容区域独立滚动，保存按钮位于标题右侧。实体 / 值概念是中性描边 chip + 图标，用户标签使用蓝底。没有「只读」或「暂只读」的界面状态标签。

初始关系来自 A 的真实 `manages_settle_sub_account`，与提供的关系卡片截图对应：所属概念 `dedicated_settlement_account`，附加角色依次为 `settlement_member`、`settle_account`；保留两条原语义描述、原说明、原约束。原生附加角色均没有 name，打开原型不会自动命名。中文 chip 文字仅是展示别名。

| 页签 | 内容与交互 |
| --- | --- |
| 基本信息 | 技术名称、显示名称、说明、用户标签。显示名称的提示明确其属于平台扩展。 |
| 角色与语义描述 | 隐含首角色 owner 单独标注；附加角色可新增、删除、上下移动。概念按实体、值概念、内置类型分组选取，角色名可空。 |
| 多重性 | 未声明 / ManyToOne / OneToOne。ManyToOne 约束末角色；OneToOne 只在二元情况下可选，不扩展成不存在的 n 元双向唯一规则。 |
| 语义描述 | 可直接编辑语义描述；点击角色 chip 在光标处插入真实占位符。未知占位符、遗漏角色、重复引用即时提示并阻止保存。显式角色名变化或概念变化同步对应占位符，保留其余语义描述文字。 |
| 映射 · 数据集连接 | 按附加角色分别编辑 owner 数据集 → role 数据集的有序复合键；列明确为 owner_columns / role_columns。角色切换后保存各自键对，换序不会把键对绑定到另一个角色。 |
| 映射 · 概念映射 | 左侧选择对象根 / 角色节点，右侧编辑完整表达式及多字段 referent 引用；支持新增对象根、添加 / 删除引用。 |
| 规则 | 保留原 requires 表达式，支持新增、编辑、删除，不截断内容。 |

A 原文件没有语义层，此弹窗中的数据集连接和复杂映射被明确标为「映射示例」。`Amount` 是值概念选择的示意项；正式实现必须从当前空间真实值概念目录加载，不自动创建此概念。用户标签与中文展示别名同样为界面示意，不改写 A 的原生定义。

n 元关系并不对应一条拥有 n 个端点的 `dataset_relationship`。后者仍连接两个 dataset；每个角色绑定及组合事实保存在 `concept_mappings` / `mapping_nodes` 的原生树中，不能将它们压平成二元兼容端点。

### 建议评审路径

在「角色与语义描述」中交换两个附加角色 → 为其中一个明确填写角色名，观察占位符同步 → 清空角色名，恢复概念技术名占位符 → 添加内置 String 角色 → 点击 chip 将其补入两条语义描述 → 删除角色并检查旧占位符报错 → 在语义描述中键入 `{unknown_role}`，保存应被阻止。

「映射」→ 增加第三对键并切换角色，检查各自条件 → 切换「多字段 / 表达式」→ 选择资金明细账户，编辑 CONCAT 和两个标识引用 → 新增对象根。

## 3. 正式实现需要的后端路径

`models_v3` 的数据结构能承载这些编辑，**现有保存服务尚不够用**。不能仅移除前端状态文字或把干净目录投影当作可直接回写的草稿。

以下现有接口均以 `/api/v1/workspaces/{workspace_id}` 为前缀。

| 已有入口 / 服务 | 可复用部分 | 需要补齐 |
| --- | --- | --- |
| `GET /semantic-models?session_id=…` → `semantic_catalog()` | 模型、dataset、fields、relationships、metrics 的干净目录，以及指标归属候选。 | 当前不返回完整 concept_mappings / mapping_nodes，也没有 dataset → 概念 / 指标的引用详情与删除影响清单；需补充干净树投影、节点稳定 ID、关联索引和当前版本 / 会话 revision。 |
| `domain/semantic_edit.py::apply_semantic_form()` | 单表对象映射、字段生成、连接别名 ONTOFOUNDRY 扩展、owner / role 的复合键连接写入。 | 目前遇到复杂映射会拒绝；不是 dataset / field / metric CRUD，也不是多根、referent、n 元映射树的通用编辑器。保留给现有简单表单，新增原生节点编辑服务。 |
| `POST /element-saves` + `services/element_save.py::scoped_draft()` | 不可变版本保存、expected_current_version_id、可选 session revision CAS、范围隔离、三方合并、证据处理、校验。 | `modeling.py::save_element()` 仍拒绝多元 / 非实体二元关系；`scoped_draft()` 拒绝语义层集合变化。需允许完整 RoleRef 编辑、稳定角色 ID / 顺序，并将当前关系的映射树纳入明确范围；不得顺带覆盖其他元素。 |
| `PUT /sessions/{session_id}`，`POST …/preview`，`POST …/publish` | 完整 v3 草稿保存、revision CAS、预览、校验和发布；可作为建模会话中的保存路径。 | 不宜由干净目录投影重建完整 draft，否则会丢保真元数据。应由后端在原快照上应用显式编辑，再走现有事务。 |
| MCP `list_metrics` / `query_metric`，`services/metric_query.py` | 已发布指标的可执行性、安全编译、方言与快照约束。 | 当前入口面向已发布版本，`query_metric` 可能实际执行。需新增 draft-aware 的 **compile-only REST 预览**，禁止 SQL 预览顺带执行查询。 |

### 建议新增的接口形态（仅设计，没有实现）

1. `POST /semantic-saves`：`target_kind` 为 dataset / dataset_field / dataset_relationship / metric / concept_mapping，携带 `target_id`、新增 / 修改 / 删除操作，以及 `expected_current_version_id`、可选 `session_id` / `expected_session_revision`。保存语义与现有元素卡片一致：校验、合并后产生立即生效的不可变版本；会话模式同时只回写当前聚合，保留其他草稿工作。
2. `POST /semantic-change-preview`：返回删除引用、改名 / 移动影响、键对和映射树校验结果。改名不能只修改 name 留下失效的字符串引用；受影响引用应显式纳入同一聚合和事务。
3. `POST /metrics/{metric_id}/sql-preview`：接受版本 / 会话引用、目标方言、group_by、结构化 filters 与 as_of；调用现有编译器但不访问执行路径，返回 SQL、绑定参数、可执行性 / 原因、快照要求。多 dataset 只解释依赖和连接路径。
4. 扩展 `/element-saves` 的关系聚合：角色 concept/name/multiplicity/verbalizes 与所属概念、选中概念映射树的编辑一起校验；owner_columns / role_columns 始终按 Ossie 角色解释。存在对应表结构时，保存前校验物理列。

### 保存不变量

- 后端从完整原快照开始，按显式操作修改；缺少字段代表不修改，明确删除用删除操作，不用空值模拟缺省。native_presence / origin / position 由保存服务维护，不由干净对外投影重建，也不在界面暴露。
- 角色、对象根、children、referent、复合键键对和方言项保留稳定 ID 与顺序；角色内容与角色顺序按现有合并合同分别处理。
- 原生 Ossie 字段不被表单默认值填充。角色名称只在明确输入时设置；展示名走现有平台扩展，字符串 AIContext 不被无意转成对象。指标或 dataset 的执行策略仅放 `custom_extensions(vendor_name=ONTOFOUNDRY)`。
- 发布沿用现有 Ossie / 领域校验，导出仍必须 A/B 0 差异；完整编辑能力不等于跨 dataset 或复杂映射的实例查询自动可执行。

## 4. 检查记录

两个原型已通过 **20 项离线 DOM / 交互检查**：完整目录计数、字段分页、同义词候选、SQL 示意及 as_of、CRUD 与引用删除保护、复合键顺序、映射树编辑、角色换序与空名称、显式名称占位符同步、未知占位符保存拦截、chip 插入、多重性边界、角色间独立键对、复杂表达式和多根编辑，以及界面标签 / 外部资源检查。两份内联脚本均可解析，运行无脚本错误。

浏览器工具的安全策略拒绝 `file://` 地址，因此本次没有浏览器截图或像素级视觉核验，也没有为规避策略启动预览服务。尚需评审方直接打开 HTML，确认布局、密度与交互方向。本阶段未运行 API / web 全量业务测试，因为未修改业务代码。
