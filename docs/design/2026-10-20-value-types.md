# 值类型（Value Type）设计

日期：2026-10-20。状态：已按第 1 节实施；2026-10-21 简化 VT-10、新增 VT-15。本文只提出设计，不代表代码、契约、技能或界面已支持。第 1 节是用户已经确认的范围；其余为实施建议，其中业务取舍集中在第 12 节，不能视为已确认。

## 1. 已确认决定

| 编号 | 决定 | 确认日期 |
|---|---|---|
| VT-01 | 新增元素“值类型”，首版包含名称（name 必填 ASCII 英文标识、display_name 可选中文名称）、基础类型（Ossie 七种内置类型之一）、约束、描述；不带关系和标识。用于统一金额、会员等级、手机号等值的业务口径。 | 2026-10-20 |
| VT-02 | 定位为本体层的“属性类型库”，不是与对象、关系、指标并列的业务实体。属性可选择七种内置类型或本空间的值类型，选择值类型时继承其基础类型与约束。 | 2026-10-20 |
| VT-03 | 本体对象目录为“实体类型｜值类型｜关系｜指标｜数据集”五个页签。值类型列表包含名称、英文标识、基础类型、约束、使用属性数、描述；不设详情页，列表展示全部信息，新建和编辑用弹窗。“使用属性”数字可展开使用属性列表，点击属性进入所属实体类型详情页。使用关系实时推导，不入模型；图谱不画值类型节点，只在属性上显示类型名。 | 2026-10-20 |
| VT-04 | Ossie 导入 ValueType 不再拆散到每个属性，RT-23/24 的大部分损失消失；导出恢复为 Ossie ValueType。值类型关系、identify_by、多级继承等首版不能承载的部分继续报告。 | 2026-10-20 |
| VT-05 | search_ontology / get_ontology 增加 value_type；属性详情包含引用的值类型。调整工具 Schema、输出和说明，不改问数提示词。 | 2026-10-20 |
| VT-06 | 建模 Agent 优先复用已有值类型，只有材料明确给出一类值的统一规则时才提议新建；技能增加正例和方法章节，只用正例，业务坑写成方法论。 | 2026-10-20 |
| VT-07 | 与数据集来源一起，在真实建模验收之前完成。 | 2026-10-20 |
| VT-08 | Q1：首版不开放值类型继承值类型，各类型直接选择内置基础类型；Ossie 多级值继承导入时折叠并按 RT-24 报告。 | 2026-10-20 |
| VT-09 | Q2：已被使用的值类型允许提出基础类型或约束变更，提交前做使用影响预检和完整候选校验，冲突属性须在同一批提案中一起修订；不自动转换或过滤数据。 | 2026-10-20 |
| VT-10 | Q3（2026-10-21 简化）：平台不证明约束是否互相矛盾，原“可证明的空值域阻断保存”作废；矛盾的约束由实例校验和人工审阅发现。**查看规则时同时显示自身规则和继承来的规则**：属性的规则列表同时列出自身约束和其值类型的约束；继承来的约束整行置灰、不可编辑（无编辑/删除入口），标明“继承自值类型 金额”，点击来源可跳到值类型；自身约束正常显示和编辑；实体类型和属性继续显示从父实体类型继承的规则（标明来源，只读）；来源与列表从定义实时推导，不复制规则。 | 2026-10-21 |
| VT-11 | Q4：值类型与实体类型共用忽略大小写的英文标识命名空间，与 Ossie concept 对齐；中文名称可重复。 | 2026-10-20 |
| VT-12 | Q5：删除使用中的值类型时阻断，并列出使用它的属性；用户需显式提交改绑或局部规则与删除的依赖组。 | 2026-10-20 |
| VT-13 | 不考虑旧数据：与名称统一、数据集来源同批上线，部署时本体内容已按 20261020 迁移清空。§10 的哈希兼容规范化（省略空 value_types、省略 value_type_id=null、旧样本金样回归）全部取消；新字段按普通默认值参与哈希，不保留任何旧草稿、旧提案或旧版本的兼容路径。 | 2026-10-20 |
| VT-14 | 实现偏差：属性的 `value_kind` 保持必填，引用值类型时由图校验要求它等于值类型的基础类型（UI 和建模助手自动填写），而不是设计 §3.2 的“二选一、value_kind 可空”。原因：全部消费方（实例校验与显示、成员条件、MCP、Ossie、前端）都直接读 `Property.value_kind`，改为可空影响面过大；这样仍只有一个权威来源（值类型），不一致时拒绝保存。修改值类型基础类型时，使用它的属性须在同一批里一起修改（与 VT-09 一致）。 | 2026-10-21 用户确认 |

| VT-15 | Ossie 导出不再为内置类型的标识属性生成 `{对象}_{属性}_value` 辅助 ValueType，标识直接引用内置类型；扩展文件不再有 generated_value_types，导入不按名称模式猜测并删除任何 ValueType（与 §7 RT-23 一致）。 | 2026-10-21 |

实施计划见 [值类型实施计划](../plans/2026-10-20-value-types-plan.md)。本轮只新建本文及该计划；不修改下述依据和并行任务文件，不运行 DataAgent 或模型，不提交代码。

## 2. 依据、来源与概念审查

### 2.1 核对基线

- [核心模型与格式适配器](2026-10-14-core-model-and-format-adapters.md)：§3.3 属性、§3.5 规则、§3.8–3.9 顶层与校验、§4.5 导入匹配、§5.2 值概念折叠、§6.2/6.4 导出、§7 例外与 RT、§13 技能、§14 MCP。
- [概念文档](../concepts/README.md)，尤其 properties、rules、inheritance、identifiers、formats、ossie-compatibility、query-semantics；本轮不改概念页。
- [名称统一](2026-10-20-display-name-unification.md)、[视觉一致性](2026-10-17-ui-visual-consistency.md)、[ToB 界面原则](2026-10-19-tob-ui-design-principles.md)、[引用导航](2026-10-19-element-reference-navigation.md)、[本体对象目录](2026-10-19-ontology-catalog-navigation.md)。名称统一覆盖较早文档里的 technical_name 和“关系没有中文名称”等旧描述。
- 只读检查 `domain/core.py`、`validation.py`、`expressions.py`、`dependencies.py`、`core_canonical.py`，`adapters/ossie/`，`contracts/proposals.py`，`services/mcp_ontology.py`、`ontology_query.py`、`element_save.py` 及目录和属性组件。当前 Property.value_kind 必填，Rule.owner_kind 只有 object_type/property/link_type，MCP Kind 只有五类，目录只有三个页签，均是待改点。
- 仓库的 `adapters/ossie/assets/vendor/apache-ossie/ontology/ontology.json` 与 PROVENANCE.md 对齐提交 `88e0011148283302c9a04cd0287e00e0b9d87354`、`0.2.0.dev0`。仓库未收录 ontology.md，核对的是[同提交官方 ontology.md](https://github.com/apache/ossie/blob/88e0011148283302c9a04cd0287e00e0b9d87354/ontology/ontology.md)，不顺带升级上游格式。

### 2.2 为什么增加值类型

Ossie 的 ValueType 表达具有附加语义的值域；requires 给出值域条件，extends 最终落到内置值类型。JSON Schema 还允许填写关系、派生和标识字段，是否有效须结合文档和语义校验判断，不能仅因 schema 接收就宣称支持。参见上述固定提交的 Concepts、Extends、Requires、Identifying relationships。

Foundry 将 value type 定义为基础类型上的语义封装，可跨属性复用元数据与约束，且限定在定义它的空间内；本设计参考这层定位。[Foundry 值类型概览](https://www.palantir.com/docs/foundry/object-link-types/value-types-overview)。Foundry 另有约束执行和独立类型版本能力；本平台继续用整份本体版本管理，只保存语义声明，不照搬其执行器、独立版本和权限资源。[Foundry 类型版本](https://www.palantir.com/docs/foundry/object-link-types/value-types-versions)。

| 审查问题 | 结论 |
|---|---|
| 来源是什么 | 概念来自 Ossie ValueType；属性类型库与空间内复用参考 Foundry。UUID、扁平集合、Rule 归属和提案组织沿用本平台。不是 Fabric IQ 专属概念。 |
| 是语义还是执行优化 | “手机号是一类 11 位数字字符串”“会员等级只有普通/银卡/金卡”是业务值域。没有数据库 DDL、CAST、精度配置或过滤优化。 |
| 删除会失去什么 | 会失去共享定义的稳定身份、未使用类型、中文名称与说明、按引用统一调整约束、直接检索及 Ossie 类型往返。复制几条属性规则无法保留这些信息。 |
| 已有结构能否表达 | value_kind + 属性 Rule 可表达一个属性的局部条件，不能表达多个属性在引用同一个类型。对象类型会错误引入实例、身份、关系和图节点；tags/description 也不能承担类型引用。 |

金额“最多两位小数”在这里表示业务允许的数值集合，例如 12.34 属于、12.345 不属于；不表示数据库必须采用 DECIMAL(p,2)，也不表示展示固定两位或查询时自动 ROUND。后面三项仍交查询 Agent 按问题和引擎处理。

### 2.3 与并行任务的边界

建模 harness 正在修改 `integrations/dataagent/skills/`、`services/dataagent.py`、`services/modeling_input.py`，本轮只读、不修改。未来值类型接入应叠加在其最终工作包、摘要索引、定点回读和离线检查机制上，不恢复长提示词，不增加一次模型调用。

数据集来源设计由另一任务编写 `docs/design/2026-10-20-dataset-sources.md`；撰写本文时该文件尚未出现，本文不预设它的字段或确认状态。数据集仍负责物理来源与列，值类型只服务 Property；不把值类型挂到 Dataset.columns、Metric 或来源表达式上。五页签及共享契约由两项设计确认后统一接入，具体交接见计划第 3 节。

## 3. 核心模型与契约建议

### 3.1 ValueType

CoreDraft 新增扁平集合 `value_types: list[ValueType]`，缺省为空。值类型与属性、规则同样按稳定 UUID 寻址；工作空间由草稿确定，不重复保存 workspace_id。

| 字段 | 类型与默认 | 来源、必要性 |
|---|---|---|
| id | UUID，必填 | 平台既有元素身份，用于引用、提案与改名；不使用名称作外键。 |
| name | Identifier，必填 | Ossie concept；复用名称统一的 ASCII 语法 `^[A-Za-z_][A-Za-z0-9_]*$` 及 240 字符限制。 |
| display_name | str/null，默认 null | 平台已有展示元数据，可选中文名称，NFKC/去首尾空格，空时显示 name；不参与唯一性。 |
| value_kind | ValueKind，必填 | Ossie 七种内置基础类型，沿用 string/integer/decimal/float/boolean/date/datetime，不另建 base_type 枚举。 |
| description | str，默认空串 | Ossie description；复用现有 8000 字符限制。 |
| evidence | Evidence[]，默认空 | 平台既有证据机制，供建模提案追溯材料；沿用证据权限和 50 条上限。不是新的业务配置项。 |

约束不再在 ValueType 内保存第二份列表，统一存在 rules 集合（§4）。首版不加 synonyms、tags、单位、precision、scale、格式化、关系、identify_by、derived_by、extends、状态、类型版本、usage_count 或 property_ids。类型的约束列表和使用计数均可推导。

推荐值类型英文标识在空间内忽略大小写唯一，并与 ObjectType 共用概念英文命名空间（待确认 Q4）；中文名称可以重复。值类型不得取 Ossie 内置概念名（含 Any），避免把名为 String 的自定义类型误当内置类型；不增加 SQL 保留字限制。对象已有内置名冲突仍按现有导出错误处理，不顺带清理旧数据。

### 3.2 Property 的类型引用

保留 value_kind 供直接选择内置类型；新增 `value_type_id: UUID/null`，默认 null。value_kind 扩为可空，默认 null。**恰好一个非空**，JSON Schema 用 oneOf 表达非空分支，Pydantic 用同等校验，前端用对应联合类型。

| 选择 | 持久化 value_kind | 持久化 value_type_id | 有效基础类型 |
|---|---|---|---|
| 内置 Decimal | decimal | null/省略 | decimal |
| 金额 money | null/省略 | money 的 UUID | 从引用的 ValueType.value_kind 推导 decimal |
| 两者均非空或均为空 | 非法 | 非法 | 不猜优先级、不默认 string |

旧属性 `{"value_kind":"decimal"}` 仍合法。引用必须落在当前草稿的 value_types 集合，不能跨空间，也不能用对象、指标或同名类型代替。提案 after 中同批新建引用可用既有 `{"client_ref":"money"}`，落库后只保存 UUID。

新增领域只读解析函数 `effective_value_kind(draft, property)` 及等价前端函数。所有原来直接读 Property.value_kind 的消费者统一接入：PathCondition、规则类型检查、文档事实标量校验、实例格式与筛选、绑定结果类型、direct 连接类型提示、MCP、图属性和导入导出。指标自己的 value_kind 及 Dataset.columns.physical_type 不改，物理列类型不匹配仍交查询 Agent。

不同时保存“引用 id + 复制来的基础类型”，也不把有效约束复制到属性 rules。只读 API 的有效类型与原始 definition 分开（§7），不能把读投影原样当提案 after 提交。

### 3.3 不开放值类型继承

推荐首版 ValueType 只选择七种基础类型，不提供 ValueType extends ValueType（待确认 Q1）。例如“正金额”可直接选 Decimal，声明 `positive_money > 0`；无需再建立“正金额 → 金额 → Decimal”的编辑和传播层级。

这满足本轮三类统一口径，同时避免多层约束合并、父类型变更传播和继承编辑权限进入最小版。代价是正金额与金额之间的类型包含关系不入模型；Ossie 输入的多级继承只能报告后按明确规则折叠，不能声称保留祖先身份关系（§8）。未来若有真实材料要求类型层次，再单独设计，不能偷偷把 extends 填进 description 当作已支持。

## 4. 约束表达、生效与冲突

### 4.1 采用现有 Rule，扩展 owner_kind

Rule.owner_kind 新增 value_type；owner_id 指向 ValueType，rule_kind **只允许 constraint**。其余 id/name/display_name/description/expression/evidence 沿用既有规则字段、长度和归属内忽略大小写唯一性。不加 constraints 字段或 constraint_ids。

| 方案 | 评估 |
|---|---|
| 复用 Rule，owner=value_type（推荐） | 与 Ossie requires 一一对应，直接复用证据、规则提案、哈希、差异和审阅；只需增加标量上下文。 |
| ValueType 内嵌约束列表 | 少一个 owner 枚举，却要再定义约束身份、证据、表达式、差异和提案方式；与现有 rules 成为两个约束入口。首版不选。 |

值类型编辑弹窗可把类型与归属规则作为一个编辑单元；底层仍是 value_type 和 rule 的多条提案，依赖组统一接受，不新增嵌套提案协议。

### 4.2 标量上下文和三个正例

复用受限 SQL 表达式解析、AST、引用跨度和按 UUID 改名机制。值类型规则中，类型的 name 是**唯一可引用的当前标量变量**，例如 `money >= 0`。解析为值类型 UUID 引用；不新造 `$value`、`self` 或伪属性。类型名作为裸变量被优先识别，不因恰好是 SQL 保留字而禁用，必要时由渲染器引用标识符。

| 值类型 | 基础类型 | 约束 Rule.expression | 解释 |
|---|---|---|---|
| money／金额 | decimal | `money >= 0`；`money = ROUND(money, 2)` | 非负且数值最多两位小数；12.30 与 12.3 数值等价，不规定显示位数。 |
| member_level／会员等级 | string | `member_level IN ('普通', '银卡', '金卡')` | 列出实际业务字符串，不额外创造枚举编码表。 |
| mobile_phone／手机号 | string | `REGEXP_LIKE(mobile_phone, '^[0-9]{11}$')` | 完整匹配 11 位 ASCII 数字，保留前导零；不转换为 Integer。 |

现有标量函数白名单已有 ROUND、CHAR_LENGTH 等，**没有 REGEXP_LIKE**。手机号正例因此要求显式补充该语义函数的解析白名单、参数/返回类型和测试；不是声称当前已支持。首版接受的正则限定为常量模式的字符/字符类、连接、分组、选择、次数与首尾锚点；不接受反向引用、环视、内联模式开关。REGEXP_LIKE 的语义是按模式匹配，未加锚点不冒充完整匹配；示例用锚点保证完整匹配。跨引擎执行翻译仍由查询 Agent 决定，不往核心写某方言的正则 SQL。

每条约束必须引用当前类型并返回布尔条件；允许现有标量、比较、IN、布尔组合、算术、CASE 及受限函数。不能引用其他值类型、对象路径、物理列、材料、查询参数、外部变量、聚合、窗口、SELECT、子查询、关系导航或 EXISTS。值类型不拥有实例集合、关系或派生行为。表达式文本保存；AST、UUID 依赖和可读摘要只在读取/校验时生成，不持久化。

### 4.3 与属性自身规则的关系

对非空属性值 p，生效条件是：引用值类型的全部约束（将其标量变量按 AST 绑定为 p）AND 属性自身的 constraint Rule。对象和关系规则仍保持自己的上下文，不改归属；derivation Rule 也不变成值域条件。

例如订单.amount 和退款.refund 同引 money，只保存两条 money 约束；退款本地再有 `refund_record.refund > 0`。订单金额 0 满足 money，退款金额 0 不满足局部约束。修改 money 的上限，两个使用点都读取新定义，无需生成两套属性规则。

类型规则仅约束“有值时什么值有效”，不声明属性必须存在。required、identifier、unique 仍只在 Property 上，不从值类型推导或提升。缺值/null 与空字符串分别处理：null/缺值不参与值域判断，空字符串仍是字符串值；手机号空字符串不满足模式，但是否必填由属性决定。值类型规则不得用 IS NULL/IS NOT NULL 取代 required；需要复杂业务可空条件时用对象/属性规则。

实体继承属性继续沿用原属性 UUID、owner_type_id 和 value_type_id；不为每个子类复制引用或类型规则。使用数按属性定义 UUID 去重，例如父“客户”有 phone、三个子类继承 phone，使用属性数仍为 1。

### 4.4 校验边界与冲突处理

服务端在完整候选图上检查：类型选择互斥、引用存在、基础类型合法、规则归属与布尔结果、常量和运算类型兼容、函数参数及受支持表达式。不能只靠前端或离线脚本。

推荐对**能明确证明的空值域**阻断保存/接受/发布（待确认 Q3），范围限于同一标量上的 AND 常量比较、范围、IN/NOT IN 及其交集。例如 money>=0 与 money<0、等级集合为普通/银卡/金卡而局部规则只准铂金，均报中文原因并列出相关规则 UUID。局部集合为金卡/铂金时交集是金卡，不是冲突；局部更宽松不会覆盖共享约束。

不引入通用约束求解器。复杂 CASE、算术或正则交集无法证明时给出“未自动证明约束一致，请核对”提示并保留原表达式，不谎称已证明可满足，也不把每次普通简单表达式都标成故障。此提示从表达式推导，不新增核心状态。基于物理类型的可执行性不属于定义冲突。

沿用“规则不执行”的现状：不扫描业务库、不为文档事实新建通用规则执行器、不因值域约束自动拒绝材料中的异常值；事实仍按有效基础类型做既有标量校验。缺 required/identifier 值的事实处理不变。结构不相容和可证明的定义矛盾可阻断；数据是否满足声明没有被平台证明。查询/数据质量检查是另一个任务，不能把导入成功当作数据已合规。

## 5. 提案、引用依赖与发布

### 5.1 提案契约

ElementKind、ELEMENT_MODELS、COLLECTIONS 新增 `value_type → ValueType → value_types`。提案沿用 `ontofoundry.proposals/v1`、before/after 全量元素与 expected_target_hash，不另建值类型专用协议。

| operation | value_type 行为 |
|---|---|
| create | before=null，after 为不含服务端 id 的完整 ValueType；服务端分配 UUID，同批 property.value_type_id / rule.owner_id 可引用 client_ref。 |
| update | target_id、完整 before、expected_target_hash 与 after；id 稳定。增删改约束是 owner=value_type 的 rule create/update/delete，不能在 after 里传 constraints。 |
| delete | after=null；必须显式处理引用属性和归属规则，最终图不得悬空。导入仍只新增/修改，不生成 delete。 |

JSON Schema 同步 `contracts/ontofoundry.core-1.schema.json`、`ontofoundry.proposals.v1.schema.json`，Pydantic 同步 core.py、models.py、contracts/proposals.py，前端同步 core.generated.ts 和 api/types.ts。api-read Schema、导入/导出报告种类、保存请求允许种类及读投影也须一并检查。所有 contracts 路径均位于 `apps/api/src/ontofoundry_api/contracts/`。

Pydantic 的跨字段 validator 不会自动生成 JSON Schema 的互斥条件；必须在权威 Schema 生成路径显式输出 oneOf/条件约束，并确保提案 after 的 client_ref 改写后仍保留这些条件。除 Property 的二选一，还要输出 owner_kind=value_type 时 rule_kind=constraint 的限制。Schema、服务端解析和前端类型分别验证同一合法/非法输入矩阵，不能仅添加 Python validator 后声称契约同步完成。

服务端先解 client_ref、重写 UUID 引用，再按最终图校验，不能要求新建类型一定排在使用属性之前。创建类型及其约束的 UI 编辑组原子保存；批量 Agent 提案依据实际引用生成依赖。拒绝类型 create 时，依赖它的属性和规则不能单独接受；不相关提案仍可接受。保留现有 depends_on、原子组、撤销和重放机制，不新增依赖状态枚举。

### 5.2 引用和变更传播

新增引用边 `Property → ValueType`、`Rule(owner=value_type) → ValueType`，并记录表达式标量 UUID 引用。反向依赖沿 ValueType → 使用属性 → 成员条件/属性规则/标识/实例等重算；指标仍只依赖数据集，不因值类型变动重写指标定义。

| 变更 | 处理建议 |
|---|---|
| display_name、description | 引用 id 不动；目录、属性类型标签、MCP 下次读取显示当前文本。 |
| name | 引用 id 不动；归属类型规则中的标量变量按已解析 UUID 重建文本。字面量 `'money'` 绝不替换。需重写的 Rule 必须在同批提案中显式列出，沿用现有“批次外自动改写拒绝”约定。 |
| 约束增删改 | 当前草稿所有引用属性实时使用新约束；发布前显示影响清单。不制造内容未变的属性 update，已有发布版本保持原定义。 |
| value_kind | 推荐允许在影响预检并确认后修改，相关规则、条件、文档事实等全部重校验（待确认 Q2）；不 CAST 存量值、不改物理列。不能闭合者须同组修订/改绑，否则阻断。 |
| 删除 | 使用属性不为零则阻断，列出使用点。用户先显式改绑到另一类型或内置类型，或删除属性，再删除归属规则和类型；可同批形成依赖组。没有自动降级、级联删属性或复制旧约束。 |

删除 money 的例子：订单.amount 和退款.refund 都引用 money，单独 delete money 拒绝；同组把两属性改绑到另一已确认等价类型，并 delete money 的两条规则及类型，最终合法后方能接受。改成内置 Decimal 会失去共享非负/两位小数限制，影响清单必须明确；若想保留，用户另显式提出属性规则，平台不暗中复制。

### 5.3 element_hashes、并发与差异

value_types 按 id 排序参与 canonical，类型、类型规则分别有 element_hashes；属性哈希只包含实际定义及 value_type_id，不混入推导基础类型、有效规则、摘要或使用数。约束变更使 Rule 哈希及草稿哈希改变，**不会伪造 ValueType/Property 本体字段变化**。

因为类型哈希不包含归属规则，UI 弹窗保存必须带现有完整草稿修订/哈希并覆盖类型和规则编辑范围；Agent 的 source_session_revision/source_draft_sha256 同样不可省略。不能仅比 expected_target_hash 就认定约束没有并发变化。不另加 read_set 哈希字段。

发布/单元素保存预检分别展示“定义修改”与“使用影响”。例如 money 的规则从 >=0 改为 >0，差异是一条 Rule 修改，归组显示“金额的约束”，使用影响列出订单.amount、退款.refund；不是三条定义修改。value_type create/update/delete、属性改绑、规则增删均能比较，并显示前后基础类型、约束和名称。

三方合并除同元素字段冲突外还检查语义依赖：一方修改 money、另一方新增引用属性或修改其局部规则，合并预览必须按 latest 与最终 merged 重算使用范围、一致性和影响清单。新增的使用点不能漏报。预检凭据沿用会话修订、当前发布版本和合并哈希，变化后重新预检；接受、撤销、重放和发布均使用同一引用闭包规则。已有发布快照不可被草稿改动回写。

## 6. 问数与查询语义

值类型帮助 Agent 理解筛选值及类型含义。例如属性 membership 引用会员等级，枚举规则给出普通/银卡/金卡；问“金卡会员有多少”时可据此把金卡理解为实际筛选值。类型名和描述提供共享上下文；不存在“贵宾=金卡”的明确材料时不能自造同义映射。

值域是声明，不证明数据库实际没有脏值。普通金额求和不能因为 money>=0 就偷偷追加 WHERE amount>=0；遇到 -5 不能默默丢弃，12.345 也不能自动四舍五入后计入。用户要求检查异常时可依据约束组织检查查询，执行方言、NULL 处理与结果说明由 Agent 负责。类型规则不生成公共固定过滤，不改变指标算法、成员条件、快照范围或来源权限。

数值“两位小数”不规定 SQL 精度、显示格式、自动舍入、单位换算。枚举没有默认顺序，普通/银卡/金卡不能据此推导大小比较；手机号按 String 保留前导零，不做数值运算。

本功能不改 `integrations/dataagent/agents/agent_ontofoundry_qa.md`、问数轮次提示词或数据库查询工具。通过工具 Schema、工具说明和结构化语义使现有 Agent 读到新类型。是否正确使用须在后续获授权的真实问数验收中验证，本轮不调用模型。

## 7. MCP 输出建议

search_ontology.kinds、get_ontology.kinds 加入 value_type。保持原四工具及版本解析：建模读取固定基线、问数读取当前发布版本，客户端不新增 version_id 入参。目录、检索、批量读取、规则读取和缓存统一覆盖新类型。

- 搜索按 name/display_name/description 匹配值类型，结果 kind=value_type；不加 synonyms 字段。轻量目录增加值类型条目及相应计数，不嵌入全量规则。
- get_ontology 指定类型 id 时，definition 是核心 ValueType；`include=rules` 返回归属该类型的规则，继续分页。单个 Rule 也可检索、按 id 读取，其 owner_kind=value_type。
- 指定 Property 或返回对象的嵌套属性时，semantic 投影始终返回有效 `value_kind`、`value_type_id` 以及只读 `value_type` 摘要（id、name、display_name、value_kind、description）。直接内置类型时 value_type_id/value_type 为 null。
- include=rules 时，属性的 `rules` 仍是局部规则；另有只读 `value_type_constraints` 分页段引用原类型规则。类型约束表达式保持 `money >= 0` 的原文，不伪装为归属于订单.amount 的新 Rule。表达式的标量绑定由 value_type_id 与当前属性上下文明确。
- semantic 中的类型摘要不塞全量约束、使用属性列表或物理来源；需要约束用 include=rules 或批量读取值类型。避免每个对象携带一份大规则库。

下例只示意属性元素的新增投影，省略原有 envelope、分页同级字段和其余属性定义，不能作为完整提案 after：

```json
{
  "id": "00000000-0000-4000-8000-000000002012",
  "kind": "property",
  "name": "amount",
  "display_name": "金额",
  "value_kind": "decimal",
  "value_type_id": "00000000-0000-4000-8000-000000004001",
  "value_type": {
    "id": "00000000-0000-4000-8000-000000004001",
    "name": "money",
    "display_name": "金额",
    "value_kind": "decimal",
    "description": "业务金额，非负且最多两位小数"
  },
  "value_type_constraints": {
    "total": 1,
    "items": [{
      "id": "00000000-0000-4000-8000-000000005001",
      "name": "non_negative",
      "owner_kind": "value_type",
      "owner_id": "00000000-0000-4000-8000-000000004001",
      "rule_kind": "constraint",
      "expression": "money >= 0"
    }],
    "next_cursor": null
  }
}
```

原始 definition 在该属性引用值类型时仍为 value_kind=null、value_type_id=UUID；顶层只读 value_kind 是解析值，两者不能混淆。该示例为仅有非负约束的简化类型；完整金额正例应返回两条规则。

类型及规则依现有本体定义权限可读；evidence 仍按 can_read_instances 裁剪，不从类型摘要泄露证据。物理投影仍受 can_read_mappings 控制，类型没有数据集、连接、表、列或 SQL。使用属性数和使用清单均按当前授权视图实时推导，不把不可见属性数量暴露给读者。

保持默认 limit=20、上限100、ids 上限100、线级响应预算256 KiB（当前内部 BUDGET=110000 同时为 text/structuredContent 留空间）。新增约束段沿用签名 cursor，绑定版本、筛选、投影及权限；发布/权限变化不能拼接旧页。长字段与超大规则集必须分段并告知 total/next_cursor，不无标识截断。

## 8. Ossie 导入、导出与往返

### 8.1 导入

1. 先校验 vendored schema 与语义 lint，建立 EntityType/ValueType/内置类型独立索引。为每个可支持的显式 ValueType 建核心元素，即使没有任何属性使用；类型名称、description 和共享 UUID 得以保留。
2. 单父直接 extends 七内置类型之一时，映射 ValueType.value_kind；规则按变量绑定转为 owner_kind=value_type 的 Rule，每条只保存一次。属性 role 指向此类型时存 value_type_id，直接指向内置类型时存 value_kind。多元重化的值角色、参与方标识生成属性同样保留类型引用。
3. Ossie requires 使用当前类型名作为标量，沿用 AST 转换；不得替换字符串字面量。同一值类型用于多个角色时只共享类型定义，角色独立名的原有 RT-21 边界保留。
4. 多级或多父值继承在核心没有 extends。推荐能唯一确定兼容基础类型且完整绑定相关 requires 时，导入各显式类型为直接基础类型，将祖先约束按源位置去重后实例化到**子值类型**（不是每个属性），逐项 RT-24 报告继承结构丢失。不能绑定的整条约束 error 待补全，其余独立项可继续；不取第一父忽略其他父。无基型、循环或不兼容基型按 RT-35 拒绝相关类型及无法闭合依赖。折叠策略随 Q1 确认。
5. 值类型上的 relationships、derived_by、identify_by 单独报告，原文、源位置和依赖留材料/报告。requires 依赖未承载关系时整条不导入，不裁剪表达式。identify_by 在本地语义 lint 已是 `IDENTIFIER_ON_VALUE_TYPE` 错误，保留该错误，不为导入放宽校验；报告仍说明未承载部分，不能把它描述为合法但无损转换。
6. 无法转换的约束保留整条原文和补全状态，不在核心加“partial”字段，也不把同一失败复制为 N 个属性失败。用户在导入审阅中明确看到规则缺项。AI 补全应修订/新增类型约束；属性局部规则仍只归属性。不能因有报告原文就宣称全部类型语义已恢复。

临时 id 沿用 uuid5(workspace_id, `ossie:` + source_key)：类型键建议 `value-type:{原concept}`，规则键 `rule:value-type:{原concept}:constraint:{来源约束定位}`；折叠祖先规则键同时包含目标类型与来源约束定位，避免同名 constraint_1 冲突。导入合并仍由平台统一处理：Ossie 按英文标识和种类匹配已有类型，沿用已有 id；属性的 value_type_id、Rule.owner_id 及表达式引用同步重写。原生导入先 UUID+kind 锁定再名称匹配，异种 UUID 冲突不得误合并。

### 8.2 导出

| 核心内容 | 纯 Ossie 输出 |
|---|---|
| ValueType | ontology 中一条 `concept=name, type=ValueType, extends=[对应内置类型]`，原生 description。包含未使用类型。 |
| 类型约束 | 此 ValueType 的 requires，保持类型变量，按 AST 输出；不展开为每个使用属性的 requires。 |
| 引用类型的 Property | 对应实体 relationships 的 roles[0].concept 指向共享类型 name。identifier/unique/required 继续各自映射，不由类型推断。 |
| 直接内置类型的 Property | roles[0].concept 直接为 String/Integer/Decimal/Float/Boolean/Date/DateTime。 |
| 属性局部规则 | 继续放属性 relationship.requires/derived_by，不提升到类型。 |

推荐取消旧 §6.2“为每个内置标识属性自动生成辅助 ValueType”的规则：identify_by 引用的是对象上的二元属性关系，vendored schema/现有语义校验并不要求该关系的值角色必须为自定义类型。直接内置类型照样输出 identify_by 与属性基数；显式类型直接复用，避免导入后凭空出现 order_order_no_value。实施必须增加官方 schema+语义 lint 及标识/映射往返测试验证此调整，不通过时回到设计评审，不能先引入一套“生成类型”核心状态来绕过。

类型和实体统一分配导出概念名称，冲突显式报错；不按属性复制或偷偷加后缀掩盖已发布名称冲突。只含值类型的非空模型也满足 schema 的 ontology.minItems=1，应允许导出；现有“必须有业务对象”的导出守卫需改为“至少一个可输出的实体或值类型”。空模型或仅数据集/指标仍报原来的空本体错误，不生成假概念。

名称统一的 ZIP 约定继续有效：纯 Ossie JSON 只放官方字段，中文 display_name 在独立 `ontofoundry-extension.json` 的 display_names，以类型 name 定位；类型与实体共享命名空间不会互撞。类型规则的英文标识/描述沿用 rules 映射，owner 路径为类型 name、种类 constraint、数组位置，中文名称沿用 `rule:` 路径。无扩展单文件只保留 Ossie 原生名称/描述/约束，不宣称中文名称或规则身份无损。不把实例/证据塞进 Ossie 扩展。

### 8.3 RT 与例外表的逐项调整

RT 编号稳定，不重排、不挪给无关含义；下表是实施时对主设计 §5–7、§13 同步修订的清单，本轮不改主设计。

| 条目 | 当前行为 | 本设计后的行为与例外 |
|---|---|---|
| RT-23 | 值概念折叠、引用改为内置；标识生成辅助值概念 | 支持范围内停止发生，编号保留为历史条目；类型与属性引用原样承载，也不再自动生成标识辅助类型。旧外部文件中的显式辅助 ValueType 若无可信来源标记，按普通类型导入，不凭名称猜测删除。 |
| RT-24 | 类型约束复制到每个属性；独立域多数丢失 | 不再为名称、描述、未使用类型、共享身份和可解析 requires 报损失；保留编号用于多级/多父值继承折叠、值类型 derived_by/identify_by 等未承载构造及约束不能完整绑定的条目。关系损失主报 RT-29，不双重计数。 |
| RT-25 | 并入 RT-23，保留不用 | 仍保留不用，不复用。 |
| RT-35 | 无唯一兼容七内置类型则相关属性/依赖不导入 | 保留并明确以 ValueType 为首要失败目标；受影响属性及依赖仍不生成非法定义，不降级 string。循环/缺基型的输入错误保留原语义 lint，涉及无法闭合基型同时报告 RT-35。 |
| RT-29 | 值概念关系和 Any 关系不承载 | 保留。值类型基本信息已保留不代表其关系已支持；依赖该关系的 requires 按 RT-24/31 定位整条失败。 |
| RT-31 | 不能完整解析的表达式待补全 | 保留并涵盖类型规则；解析失败一条整项 error，原文和定位保留；不因共享引用报 N 条同样失败。 |
| RT-34 | 实体多父按首父 | 实体行为不变；不借此对值继承取首父。值继承完整折叠/无法闭合分别归 RT-24/35。 |
| RT-21 / RT-22 | 值角色独立名称、多值属性边界 | 均保留，值类型没有扩大 Property 单值边界，也没有保存角色名。 |
| RT-27 / RT-28 | 多元重化、决定角色构键与约束改写 | 保留；生成值属性改为引用 ValueType，类型约束不再复制到属性。多元结构仍不还原。 |
| RT-30 / RT-32 / RT-33 / RT-68 | 标识不闭合、关系成员、单项唯一、子类身份 | 保留；显式类型引用不改变对象标识行为。值类型自身没有 identify_by。 |
| RT-10 / RT-11 / RT-12 | 排序、空字段、英文标识规范化 | 保留并覆盖 value_types 及其规则；按 UUID 重写引用，不能只改类型名字。 |
| 其他 RT-01–69 | 文档、读法、映射、指标、时间与元数据边界 | 不因值类型改变；数据集来源任务另行修订属于它的 RT，不能在本设计中预先承诺。 |

本设计不申请新的 RT 编号，避免与并行数据集来源设计冲突。主设计“独立值类型语义域”例外应拆为“值类型继承结构/派生成员”“值类型关系”“值类型非法标识输入/其他未承载字段”“不能解析的 requires”，分别注明 RT-24、29、31、35 及适用的输入错误；从例外里移除已承载的名称、description、未使用类型、共享引用与直接基型规则。总表 ValueType 行改为“直接七基型的独立类型及约束可往返，剩余结构按例外报告”。

## 9. 界面布局与交互

### 9.1 目录

本体对象是管理入口，沿用 PageHeader/PageBody → 一个 Panel，目录页签、搜索、当前页签新建放 PanelToolbar 同一行。页头保留刷新、导入、导出、发布。页签固定顺序“实体类型｜值类型｜关系｜指标｜数据集”，使用计数真实展示 0，不靠隐藏零值缩短工具栏。catalogTab 建议沿用 entities/relations/metrics，新增 value_types/datasets；切换保留 session 与预览上下文，清理不适用筛选。

值类型表的业务列严格为名称、英文标识、基础类型、约束、使用属性数、描述；最右仅放紧凑编辑/删除操作。名称是普通文本，不出现详情页链接。基础类型显示 Decimal 等七种类型标签文本，不做状态色。约束逐条展示可读表达式和已有说明，长内容自然换行；描述完整换行阅读，不把关键信息只藏在悬停里。不用“查看详情”承接剩余字段，不另建值类型路由或工作区页签。

搜索匹配名称、英文标识、描述和约束文本；不套用值类型不存在的标签筛选。表格使用既有紧凑密度、数量列收紧、英文标识保持完整；长行允许自然增长，列表仍是一行一个类型。不添加外层卡片、彩色约束胶囊或统计卡。

### 9.2 使用属性展开

选择 Ant Design Table 展开行，点击“使用属性数”数字展开，同一表内呈现名称/英文路径/所属实体类型；0 显示为非交互数字。计数按 Property.id 去重，只数直接保存 value_type_id 的属性定义，继承使用不另计；例如 customer.phone 被 premium_customer 继承仍只列 customer.phone。

属性名称为普通文字链接，调用现有 useElementDetail 进入 owner_type_id 的实体详情新工作区页签，并带 initialPropertyId 定位属性；继承项跳定义所属实体。沿用 session/preview 参数和同元素页签去重，不跳到单独属性页。原目录的搜索、滚动和展开状态保留。未发布草稿中的引用不与发布版混数，删除或失权后刷新/报错，不显示伪零。

### 9.3 新建/编辑弹窗

这是已确认“不设详情页”的例外，覆盖 UI-024 中所有元素都走详情页的一般规则。实现前在视觉设计 §4 补充“目录类型编辑弹窗”模式，在引用导航设计中记录此例外。这里只设计，不在本轮修改那两篇文档。

使用 Ant Design Modal + Form/FormRow + SectionTitle：第一行“名称（可选）/英文标识（必填）”，下一行“基础类型”，随后“约束”列表、描述；已有规则行复用名称、英文标识、表达式和说明的编辑逻辑，不增加第二种约束存储格式。约束表达式直接可编辑，有金额、会员等级、手机号正例；没有规则时显示“未设置约束”。值类型不显示关系、标识、唯一、必填、来源或实例页签。

取消/保存放标题右侧，正文独立滚动，复用既有弹窗尺寸和 token；不另开固定高度的空白详情框，不套 Panel/Card。新建/编辑期间外框和动作位置稳定，错误贴近字段；保存失败用既有 message 反馈并保留输入。关闭有修改时沿用未保存保护，保存期间禁用重复提交。只读角色可展开使用属性，不显示新建/编辑/删除。

类型与规则一起提交保存/提案；有使用点时，基础类型或约束变化沿用保存影响预检展示使用清单和前后口径，确认最终图后生效。发现图已变更要求重新预检，不用用户刚打开弹窗时的旧使用数。删除已有引用类型只展示阻断原因和使用入口，用户显式改绑后再删除。

### 9.4 属性类型选择和属性详情

PropertyMappingTable 的类型 Select 分组“内置类型”“值类型”，前组七项，后组当前空间值类型；选项展示“金额 money · Decimal”，支持搜索中文名/英文标识。选择内置类型时清 value_type_id，选择值类型时清 value_kind；前端临时选项用带前缀的键区分 UUID 与内置值，不存到模型。没有值类型时不伪造选项，提示“可在本体对象的值类型页签维护”。首版不在属性编辑弹窗内叠加新建类型弹窗。

属性列表类型列显示“金额”；详情基本信息显示“类型：金额”“基础类型：Decimal”。约束区在 required/identifier/unique 之外，分清“来自值类型金额”的只读规则与本地属性规则；不把共享规则显示为可就地编辑的属性副本。可提供“在目录中定位金额”的文字链接，定位值类型目录行，不生成值类型详情页；未保存编辑仍按现有导航保护处理。

原对象详情继续 DetailWorkbench 的属性列表/配置区，在窄容器上下排列，继承属性只读；图谱、实例字段标签、全局搜索和构建草稿中的属性类型名称使用同一解析函数。语义图、对象关系图均不增加值类型节点或边。值类型搜索结果定位目录；构建草稿和发布变更中需要阅读类型时使用只读信息块或同一弹窗（预览态禁用保存），也不提供“打开详情”。

### 9.5 视觉和状态验收要求

采用 Operate 场景的紧凑信息组织，保留既有视觉语言。视觉数值只取 tokens.css：字号12/14/16，页面24与面板16对齐线，已有间距/控件/表格档位，状态只用 StatusMark；不用新 CSS 文件、任意尺寸或手写控件。错误、加载、空列表、无搜索结果、使用数0、长约束、长中文名称、只读、并发变更均需有明确表现。展开按钮、编辑动作、类型 Select、表单字段提供可访问名称和键盘焦点，表单失败定位到错误字段。

后续在1440×900截图并与改前/既有基准逐页对比：

| 页面/状态 | 比对重点 |
|---|---|
| 本体对象五页签，实体/关系/指标/数据集回归 | 页签与搜索同行、页头操作不挤压、名称/英文标识分列；数据集布局由其设计提供。 |
| 值类型目录（0条、正常、长规则）及使用属性展开 | 一行一个类型、完整信息、0/无值、计数和链接、展开后首列对齐。 |
| 新建/编辑弹窗（空规则、三类正例、校验错误、影响预检） | 两层以内容器、标题动作与滚动、规则行密度。 |
| 实体详情属性查看/编辑，类型选择下拉，继承属性 | 基础类型与来源约束分层、分组选项、DetailWorkbench 对齐。 |
| 语义图属性、构建草稿、发布预览与差异 | 没有值类型图节点，名称一致，规则改动与使用影响不混数。 |

实现编辑全部完成后统一运行 `npm run test:visual`，并用局域网 IP 的 HTTP 地址验证新建类型、添加规则、属性改绑与使用点跳转；UUID 使用 lib/id.ts 的 newId()，不能依赖安全上下文 crypto.randomUUID。本轮不截图、不启动浏览器、不跑测试。

## 10. 迁移、版本与兼容

现有 core-1 草稿/版本没有 value_types 和 value_type_id；读取默认空集合/null，旧 value_kind 属性仍合法。**不做数据迁移，不清空、不回填、不从散落规则猜测生成类型**。历史复制到属性的约束保留为属性规则，来源文字不能证明共享类型身份；需要复用时由后续显式提案处理。没有新表/列/数据库枚举，现有种类登记为字符串、快照为 JSON，不为本功能新增 Alembic。实施核对若发现真实表结构限制须回到设计并按仓库要求新增迁移，不能悄悄迁数据或加临时读取分支。

建议保持 core-1 和 ontofoundry.proposals/v1，作为可读取旧文档的增量扩展；保持现有原生包及 Ossie 扩展版本标签。新前后端、Schema、技能同步发布。旧严格消费者不能读取非空 value_types/新引用，部署须协调升级，不把“新端读旧”说成双向兼容；向旧端交换须明确不支持，不能静默折叠以通过校验。与数据集来源若共同引入破坏性格式调整，版本策略应在两项设计合评时统一，不能各自发布同名不同含义的 Schema。

**VT-13 取消哈希兼容。** 不考虑旧数据：新字段按普通默认值参与哈希，不做省略规则、旧样本金样回归或任何兼容分支。

## 11. 建模技能与概念文档的后续更新

在 harness 完成的结构上，quick-reference 增加值类型元素路由；core-model 解释基础类型与值类型引用、Rule owner 与组合；类型抽取方法章节增加“先查现有类型 → 比较值域/说明/材料依据 → 复用或提议 → 单列局部约束”。材料明确“所有金额非负且两位小数”才建 money；只有某字段叫金额或物理列是 DECIMAL(18,2)，不足以提议共享业务规则。材料给出“仅普通/银卡/金卡”时建会员等级，手机号11位规则按材料建 String 类型。业务坑写成正向判断方法，不新增可阅读反例章节；自动化非法输入测试不受“只用正例”限制。

受测正例至少覆盖 value_type create/update/delete、同批类型+规则+属性引用、复用已有类型只新增属性、属性局部约束叠加、改名规则引用重写及显式改绑后删除。工作包摘要索引加 value_type 的名称、基础类型、使用数和约束回读 pointer；完整 draft、element_hashes 和 Schema 仍是权威。不能为增加示例恢复按字段解释的长提示词，不能修改问数提示词。技能源码将来按 integrations/dataagent/README.md 复制到 SKILLS_ROOT_DIR 并重启；本轮不生成分发包、不访问后台。

实施时同步概念文档，本轮只列清单：

| 文件 | 更新内容 |
|---|---|
| 新增 docs/concepts/value-types.md | 类型库定位、字段、三类正例、引用与约束组合、变更/删除、首版例外。 |
| README.md | 元素集合/导航及概念关系图加入 ValueType 和 Rule 归属；说明文档关系图不等于产品图节点。 |
| properties.md | 互斥类型选择、有效类型、共享约束、本地规则、移除引用的影响；删除“金额约束复制到每个属性”旧说法。 |
| rules.md | value_type owner、当前标量语法、布尔/类型检查、合取、定义矛盾与不执行边界。 |
| formats.md、ossie-compatibility.md | 类型独立往返、未使用类型、扩展显示名、RT-23/24/35及例外、仅值类型可导出。 |
| query-semantics.md | 两工具新种类、属性类型摘要与规则分页，枚举理解、不能自动过滤脏值。 |
| inheritance.md、identifiers.md、object-types.md | 区分实体继承与不开放的值继承；属性标识可引用值类型，但值类型不拥有标识/实例/关系。 |
| datasets-and-binding.md、metrics.md、evidence-and-instances.md | 仅补边界交叉引用：数据集列/指标不引用值类型，事实有效基础类型解析及规则不执行；来源字段由并行任务维护。 |

同时定点更新主设计 §3.1/3.3/3.5/3.8/3.9、§5.2–5.4、§6.2/6.4/6.6、§7/7.1、§13/14及其已确认决定表，标明替代旧值类型折叠决定；例子08与多元例子03在实施时改为共享类型引用。名称统一和UI三份导航规范记录本轮确认带来的例外与五页签，不以本文未确认建议直接覆盖它们。

## 12. 需要用户取舍的点

**2026-10-20 已全部确认，结论见 §1 VT-08–VT-12（Q3 增加了规则来源展示要求）。** 下表保留原始选项供追溯。

| 编号 | 问题与具体结果 | 推荐与替代 |
|---|---|---|
| Q1 | 是否允许值类型继承值类型？金额>=0，正金额>0：直接基型方案各自选 Decimal；继承方案正金额自动获得金额以后新增的上限。Ossie money→positive_money 的祖先结构是否必须可编辑保留？ | 推荐首版不开放，导入折叠到各类型并明确报告 RT-24；替代是开放单父值继承，但需扩展模型、传播和编辑范围，不能仍称最小版。 |
| Q2 | 已使用类型能否改基础类型/收紧约束？会员编号 String 的值“001”改 Integer 会与现有事实不符；金额>=0 改>0会影响订单金额0。 | 推荐允许提出变更，经使用影响预检和完整候选校验后确认；冲突项须同组修订，不自动转换或过滤数据。替代是有使用点时禁止基础类型/约束破坏性修改，要求新建类型并显式改绑；需要另定“破坏性”的可判定范围。 |
| Q3 | 可证明的矛盾如何处理？等级仅普通/银卡/金卡，某属性局部规则仅铂金，组合后没有合法非空值。 | 推荐阻断能证明的空值域；复杂表达式只提示未证明、交用户核对。替代是全部只警告，会允许明确不可满足的类型/属性定义发布。两者都不扫描业务数据。 |
| Q4 | 类型与实体英文标识是否共用空间？已有实体 money，再建值类型 money：共享命名空间立即提示冲突；分开命名空间则两者可建，但 Ossie 导出必须改名或报错。 | 推荐共用忽略大小写的概念命名空间，与 Ossie concept 对齐；替代是核心分开，导出显式拒绝冲突，不静默重命名。中文名称仍可相同。 |
| Q5 | 删除使用中的类型是否自动解除引用？money 被订单.amount和退款.refund使用，降为 Decimal 会让共享非负/两位小数约束消失。 | 推荐阻断并列使用属性，用户显式提出改绑/局部规则及类型删除依赖组；替代是提供“解除并保留为局部规则”批量动作，会产生规则副本和后续维护成本，首版不做。 |

## 13. 评审与交付条件

Claude review 应重点检查：双契约互斥校验、类型规则上下文、空值语义、静态矛盾可判定范围、批次与发布依赖、哈希旧样本兼容、MCP 分页/权限、Ossie 标识直接用内置类型与仅值类型导出、RT 是否重复计数、UI 例外、与数据集来源契约和 harness 的合并边界。

当前只完成方案，不表示 Claude 已评审或用户已确认技术建议。后续先记录 review 结论与 Q1–Q5 的决定，再按计划实现；值类型和数据集来源均通过离线与界面验收后，才进入另行授权的真实建模/问数验收。本轮不调用 Claude 或其他模型来完成 review。
