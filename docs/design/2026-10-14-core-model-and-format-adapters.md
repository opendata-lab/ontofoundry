# 核心模型与格式适配器设计

日期：2026-10-14 · 修订：2026-10-16（第 19 轮）· 状态：设计定稿，待实施

本文**取代** `docs/plans/2026-10-08-ossie-native-lossless-plan.md` 及其 P1–P4 进度文档、
`docs/design/2026-10-08-ossie-coverage-matrix.md` 中“Ossie 是模型规范层、必须无损承载”的原则。
为避免与已有的草稿 schema v2 / v3 混淆，本文的模型称为**核心模型（Core Model）**，
存储标识 `schema_version: "core-1"`，不再沿用数字版本号。

---

## 1. 背景与结论

10-08 方案把 Apache Ossie 定为模型的规范层，要求平台原生、无损地承载 Ossie 的全部构造。落地结果是草稿 schema v3
（`domain/models_v3.py`）实质上成了 Ossie 文档的语法树：每个节点记录字段是否出现（`native_presence`）、数组位置（`position`）；
关系是 `owner_ref + roles[]` 的 n 元结构；值类型是独立概念；语义层照搬用于交换语义定义的开放语义交换规范 OSI（Open Semantic Interchange）的 dataset / field / mapping 递归树；
平台扩展还要记录“导出时改了哪些 JSON 位置”以便撤销（`export_edits`）。
发布时所有草稿都会先转成 v3（`services/workspaces.py`），编辑、提案、合并、前端、agent prompt 都被迫围绕这套结构工作。

Ossie 在概念上是合理的。本体与数据集分层并用映射连接、指标可以是表达式、给 AI 的说明、规则挂在具体元素上，这些我们最终都采用了。不适用的是结构：Ossie 面向交换，使用树形嵌套，一份文件完整描述，表达面宽；我们是编辑与问数平台，需要扁平集合和 id 引用、逐元素提案，以及便于校验和 agent 理解的较窄表达范围。v3 的问题是把交换格式当成了内部存储。本设计是把 Ossie 放到适配器的位置，不是否定它。上游也在把映射拆成独立文档，原内嵌入口仍接受但已弃用（见 §5 的范围说明）。

建模方式随之确定（2026-10-20 补充）：由基于整份文件的全量建模改为**基于已有元素的增量建模**：AI 与人每次只提交对具体元素的新增、修改或删除提案，引用元素 UUID、基准哈希和材料证据，而不是每轮生成或比对整份 Ossie 文件。这样输出只含改动、遗漏不会变成删除、并发修改可检测、每条改动可逐条审阅；核心模型与 Ossie 解耦，上游调整文件结构只影响适配器（2026-10 上游拆分文档的跟进见[待办](../plans/2026-10-20-ossie-upstream-alignment-todo.md)）。复杂 Ossie 构造用等价的较窄结构表达（多元关系转中间对象、一元关系转布尔属性），无法等价的列入 §7。对外表述为“以 Ossie 为语义基准，支持导入导出，支持范围与差异公开列明”，不称完全兼容，并注明对齐的上游提交；说明见[与 Ossie 的关系](../concepts/ossie-compatibility.md)。

本设计的结论：

1. **核心模型是平台唯一的真相**。建模、编辑、提案、合并、发布、查询、MCP 都只面向核心模型。
2. **外部格式只通过适配器进出**。Ossie 是第一个适配器，以后可以加 Palantir Foundry、Microsoft Fabric IQ、OWL 等。
3. **以 Ossie 为语义基准，尽量无损保留它能表达的语义**。首版未承载的能力集中列在 §7 的例外表；成功完整等价转换的条目才算 converted，未完成的条目保留原文并待补全，不静默丢弃或猜测。
4. 核心模型的形状参考 Palantir Foundry 和 Microsoft Fabric IQ 的共同做法：**关系只有二元**；
   多元事实建成中间对象；关系绑定区分“直接属性关联”和“使用映射表”。
5. **只提供语义**。对象、属性、关系、指标和绑定是核心；物理类型适配、单位、精度、时区、运行时基数校验和完整查询编译交给执行查询的 agent。

---

## 2. 原则

| # | 原则 | 含义 |
|---|---|---|
| P1 | 核心模型优先 | 核心采用平台需要的编辑结构，以 Ossie 为语义基准；不能承载的语义集中列明，不能把结构简化当作语义已完整保留。 |
| P2 | 适配器隔离 | `domain/` 不得 import 任何适配器；适配器只依赖核心模型的公开类型。外部格式专用的角色、presence 等语法不出现在适配器之外；数据集方言是平台自己的来源信息。 |
| P3 | 有损可见 | 导入、导出都产出转换报告，逐项列出“结构改写、丢弃、错误”。 |
| P4 | 不猜测 | 不擅自解释无法确定的业务含义。指标表达式保留原文，引用或统计数据集不明时报告待补全，不能因无法结构化而丢弃；其他不支持的构造逐项报告。 |
| P5 | 无损只靠原生格式 | 平台自己的完整备份和搬迁用 OntoFoundry 原生格式的**完整包**（§4.6，含材料），无损；不含材料的单文件形式会丢失证据，导入报告逐项说明。外部格式只保留其可表达的业务结构和命名，语法合法不等于执行语义等价；逐指标报告比率分量过滤与时间约定（§6.5）：核心模型 → 外部格式 → 核心模型时，规则名、实例、证据等可能丢失。外部格式 → 核心模型 → 外部格式**不保证**还原原文，但每处差异都必须能归到一条编号规则（§7.1），并在导入报告里逐项列出。 |
| P6 | 导出必须合法 | 导出的文档必须通过目标格式的官方校验。缺的信息优先省略或由模型推导，不往受校验的字段里塞占位字符串（见 §4.4）。 |

---

## 3. 核心模型 core-1

按概念阅读的中文说明、建模建议和例子见[概念文档](../concepts/README.md)，字段与行为以本设计为准。

以现有 v2（`domain/models.py` 中的 `*Definition` 类）为基础做减法和少量加法。所有元素都有稳定 UUID，集合扁平、按 id 寻址，
所属关系用引用表达，这些都沿用 v2。

2026-10-20 命名与交换修订以[名称统一设计](2026-10-20-display-name-unification.md)为准：五类元素 name 是必填英文标识，display_name 为可选中文名称，名称不参与唯一性。Dataset 不变。数据库旧内容清理，不做读取转换。

### 3.1 元素一览

| 集合 | 元素 | 说明 |
|---|---|---|
| `object_types` | 业务对象 | |
| `properties` | 属性 | 对象 → 一个值 |
| `link_types` | 关系 | **只有二元**：源对象 → 目标对象 |
| `rules` | 规则 | 约束或派生，SQL 表达式，属于某个具体元素 |
| `metrics` | 指标 | **新增**，优先结构化，复杂口径用 SQL 聚合表达式保存，见 §3.6 |
| `datasets` | 数据集登记 | 扁平登记物理表、方言、schema 和可选的快照日期列，不建字段节点或语义模型树 |
| `mappings` | 数据映射 | 对象 → 主、附数据集引用；属性 → 来源列或计算列 |
| `material_objects` / `material_links` | 材料实例 | 对象事实只保存 id、type_id、values、evidence，显示文本读取时推导；`material_links` 只有 source / target。保留用于后续的实例图谱（Palantir 的对象和链接实例也是同样用途） |

**删除**：v2 的 `ontology_requires`（工作空间级约束）。规则必须归属具体元素，不再有不属于任何元素的约束。

**对象、属性、标识、关系各自分开定义**，以订单明细为例：

| 概念 | 订单明细 | 说明 |
|---|---|---|
| 对象 | 订单明细 | |
| 属性 | 订单号（映射 `order_id` 列）、行号、数量、单价 | 表里的列都可以建成属性，外键列也一样 |
| 标识 | 订单号 + 行号 | 只由属性组成，组合起来唯一 |
| 关系 | 订单明细 属于 订单 | 单独定义，`data_join` 写明用 `order_id` 列连接；关系不参与标识 |

订单号既是属性（有值、可以显示和过滤），连接时用到的 `order_id` 列又出现在关系的 `data_join` 里，两者各管各的，互不替代。

### 3.2 业务对象 `ObjectType`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID | |
| `display_name` | str / null | 可选中文名称，空时显示 name，不参与唯一性 |
| `name` | str | `^[A-Za-z_][A-Za-z0-9_]*$`，工作空间内唯一（忽略大小写） |
| `description` | str | 业务说明及供 agent 理解的上下文。外部 `ai_context.instructions` 并入这里，不新增独立字段 |
| `synonyms` | list[str] | **新增**（取代 v3 `extension_v4.concept_context.synonyms`），供问答和 MCP 检索 |
| `tags` | list[str] | |
| `extends` | UUID / null | 单父对象；只存本地新增定义，继承定义按祖先链解析 |
| `title_property_id` | UUID / null | 实例标题属性，允许继承属性；文档事实按标题、完整标识、证据引文开头、UUID 回退；数据库实例按标题、完整标识、物理键回退 |
| `derived_by` | list[DerivedBranch] | 默认空数组，非空时必须有 extends；定义本层成员条件，分支取并集，形状见下 |
| `evidence` | list[Evidence] | 沿用 v2 |

#### 继承的定义与绑定

单父 `is-a` 表达实例包含关系，属性、普通关系和规则沿祖先链全部继承，保留原 id 和归属对象。子对象只存本地新增定义，界面只读展示继承项并标注来源，不复制、不覆盖，也不重复建立父关系。关系端点允许兼容的子类型实例。对象自身的描述、同义词和标签各自维护。

建模必须在以下三种建法中选择，不能把完整的父表与父表之外的独立子表混用。

| 建法 | 绑定与查询语义 |
|---|---|
| ① 父对象有绑定 | 父绑定必须覆盖所有子对象实例；子对象共用父表并在 ObjectType.derived_by 声明派生条件，或共用父表并增加按标识关联的扩展表。扩展表有记录的父实例才属于该子对象，特有属性来自扩展表；继承属性和关系仍从父绑定取。查父对象只使用父表，实例集合天然完整且不重复 |
| ② 虚拟父对象 | 父对象没有 DataMapping，子对象各自绑定数据集，一个实例只属于一个具体子对象；查父对象列出所有具体子对象实例的并集。继承属性可在具体子对象上绑定，继承关系按同一关系 id 配置本地数据绑定；MCP 标明“无自己的表，实例来自以下子对象” |
| ③ 两个独立对象 | 不建 extends，各自定义属性、绑定和查询口径；共同字段不表示实例之间存在包含关系 |

**禁止父对象有绑定，但子对象实例另存在独立表、没有包含在父绑定中。** 这种情况应改为两个独立对象，或去掉父绑定，采用虚拟父对象。平台校验绑定结构和覆盖声明，不扫描数据库证明实例覆盖、互斥或唯一性；建模技能必须向建模者解释此约束。

① 使用 `binding_mode=shared_parent`。agent 从直接父对象的有效成员范围出发，逐层应用派生条件；同时有 membership_source_id 时还须在成员扩展来源存在，二者同时限定，不能取并集。两者都未声明时属于未完成绑定，不能把父表全部行当作子类。继承链继续沿用有绑定祖先的实例覆盖约束。

② 的无绑定父对象带有子对象时即为虚拟父对象，允许多层虚拟分类，查询递归展开至具体绑定的子对象；每个具体实例只出现一次。有绑定的子对象仍须遵守①对其后代的覆盖要求。父对象没有自己的数据库实例或直接文档事实；文档事实的父类型检索也按具体子对象展开，并保留实际 type_id。普通的无绑定叶对象仍是待补全对象，不能仅因没有表就宣称已有可查询实例。并集如何编排查询由 agent 处理，不增加通用纵向映射树。

父对象有标识时，子对象沿用该标识元组，不能增加标识属性改变它；父对象没有标识时，子对象可定义自己的标识。实例标题由 `title_property_id` 指定，允许引用继承属性。虚拟父对象查询保留具体类型和实例键，不能把不同具体类型中相同的局部键误认为同一实例。已定义的客户数等指标仍按其口径回答。

[Fabric 继承](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-inheritance)支持单父和父类型多态查询，但不继承普通关系与数据绑定；[Palantir 接口](https://www.palantir.com/docs/foundry/interfaces/interface-overview)提供跨实现对象的查询。这些是②的概念参考，不代表字段或递归行为完全相同。本平台选择完整继承属性、普通关系和规则；成员派生定义以 Ossie derived_by 为语义参考，不把其他产品的权限筛选视为同一能力。

#### 派生条件的形状与语义

`DerivedBranch` 是判别联合，一条分支只能使用一种表示：

```json
{
  "kind": "simple",
  "conditions": [
    {
      "path": {
        "links": [],
        "property_id": "<父对象有效属性 id>"
      },
      "operator": "eq",
      "values": [
        "VIP"
      ]
    }
  ]
}
```

或：

```json
{
  "kind": "expression",
  "expression": "EXISTS (person.earns)"
}
```

simple 的 conditions 非空，采用本节的 PathCondition 和值类型校验，分支内全部 AND；其路径必须指向标量。expression 与 conditions 互斥，表达式非空。数组内各分支取并集；需要同时满足的条件写在同一分支内。空数组表示本层没有派生条件，不表示成员已完整定义。表达式保存文本并解析 AST，按 id 记录引用依赖，与规则一样按引用存储，不另建依赖集合；改名按 id 重建显示，不替换字面量。

引用从直接父对象的有效属性和关系解析，可引用祖先定义且保留原 id。表达式支持 §3.5 的标量、比较、布尔组合、算术、CASE 和受限标量函数，另支持关系存在性 `EXISTS (对象.关系路径)`；路径每跳按关系 id 和 forward 或 reverse 方向记录，文字显示采用关系英文标识，反向显示为 `REVERSE(关系英文标识)`。同类不同角色以不同关系 id 区分，自关联同样保留方向。EXISTS 显式量化该路径的可达关联实例，找不到关联为 false；存在关联但某属性为空不等同不存在。它是本体成员语义，不接受任意 SQL 子查询、聚合、递归或未定义的角色变量量化。

每层先限定父范围，再判断本层分支的并集；有成员扩展来源时再取交集。多层不得漏掉祖先条件。语义引用不依赖物理列或父绑定就绪；缺绑定只影响问数就绪。普通 derivation Rule 是说明，不自动成为成员条件，同一条件不重复存 Rule。导入不能完整闭合时保留整个成员定义原文并待补全，不把可解析片段当成完整定义或覆盖已有定义。

**Path 与 PathCondition（仅用于成员派生和本体规则）**：Path 从上下文对象出发，使用 `{ "links": [{"link_type_id": "<关系 id>", "direction": "forward"}], "property_id": "<属性 id>" }`；links 为空时引用自身属性，每跳方向为 forward 或 reverse。PathCondition 是 `{ "path": <Path>, "operator": <运算符>, "values": [...] }`。operator 使用 eq、ne、gt、ge、lt、le、in、not_in、between、is_null、not_null；between 两个值，in/not_in 至少一个，is_null/not_null 零个，其余一个，not_in 不含 null，值须匹配属性 value_kind。关系导航必须解析为标量；涉及集合时使用受支持的显式量化（例如成员表达式 EXISTS），不能将集合当标量。指标不使用 Path 或 PathCondition。

#### 文档事实的显示与搜索

文档事实不保存独立事实名。读取时依次取有效 title_property_id 的值、按属性 UUID 顺序排列的完整标识元组、该事实可见的非空材料 quote 开头、事实 UUID。null 和空字符串无显示值，0 和 false 有值；标识任一项缺值就跳过整组。多个引文按证据 UUID 顺序取首个非空项，显示最多前 80 个字符，截断不修改原文；只有 manual.note 或缺少可见 quote 时继续回退 UUID。UI 和 MCP 返回只读 display_text，搜索覆盖推导显示文本及属性值，权限和分页保持一致。数据库实例没有材料证据时仍使用原有物理键回退。

### 3.3 属性 `Property`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id`、`owner_type_id`、`display_name`、`name`、`description` | | 同 v2 |
| `value_kind` | enum | `string / integer / decimal / float / boolean / date / datetime` |
| `required` | bool | |
| `identifier` | bool | 是否参与对象标识 |
| `unique` | bool | 属性值是否能唯一识别一个业务实例，例如身份证号。对象标识只含一个属性时，该属性必须 unique；复合标识的成员可以各自不唯一。快照历史中同一业务实例可跨日期重复，不能据此声明历史物理列整表唯一 |
| `synonyms` | list[str] | **新增**，业务别名，如“金额”的“销售额” |
| `evidence` | | |

类型仅为 Ossie 本体七种内置类型；核心不增加单位、精度、时区、Time、DateTimeTz、数组或结构体。物理列类型与语义类型不匹配由 agent 查询时调整，不要求核心执行转换。不支持的导入类型须报告并跳过，不能静默当字符串。

**删除**：`verbalizes`、`target_role_name`、`multiplicity`（由 `unique` 取代）、`value_concept`。

### 3.4 关系 `LinkType`

2026-10-19 已确认并实施：以 [关系标识、角色名与完整读法](2026-10-19-link-verbalizations.md) 为准，替代此前 name/inverse_name 截取动词方案。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id`、`description` | | 稳定身份及说明 |
| `name` | ASCII 标识符 | 对应 Ossie relationship.name，所属对象内唯一，例如 reports_to |
| `display_name` | str / null | 可选中文名称，空时显示 name |
| `verbalizes` | list[str] | 完整正反业务句式，使用 {source}/{target}，保留正文、尾部及列表顺序；默认空列表，最多 50 条，每条 4000 字符 |
| `source_role_name`、`target_role_name` | str / null | 两端在本关系中的角色名，可空；来源端下属、目标端主管。正向遍历显示目标角色，反向遍历显示来源角色。来源 Ossie roles.name，保留关系读法 |
| `synonyms` | list[str] | **新增** |
| `source_type_id`、`target_type_id` | UUID | 允许相同（自关联，例如 员工 汇报给 员工） |
| `multiplicity` | enum | `one_to_one / many_to_one / many_to_many`。没有一对多：一对多关系一律从“多”的一端建成多对一，例如订单 → 客户，多对一；完整读法“{source}属于{target}”“{target}拥有{source}”分别表达两个方向 |
| `tags` | list[str] | |
| `data_join` | DataJoin / null | 关系的数据绑定，见下 |
| `evidence` | | |

**删除**：关系旧动词短语 `name` 的语义、`inverse_name`（仅外部文件导入兼容，数据库不兼容读取），以及 v3 的 `owner_ref`、`roles`、`endpoint_direction`、
`owner_role_name`、`legacy_multiplicity`。

**`DataJoin`**：判别字段 `kind = direct | mapping_table`。参照 [Fabric “Use mapping table?”](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-create-relationship-types#create-relationship-type)（核查：2026-10-15）。

| 模式 | 字段 | 含义 |
|---|---|---|
| `direct` | `source_property_ids`, `target_property_ids`（有序 UUID 列表） | 两端属性逐对相等；目标必须为单个 `unique` 属性或目标完整标识，**不限物理主键**。一对一要求源端也声明唯一；多对多用映射表 |
| `mapping_table` | `dataset_id` | 引用登记的数据集，允许就是某一端来源的数据集；不在关系中重复表位置 |
| `mapping_table` | `source_columns`, `target_columns` | 映射表中分别指向两端引用键的有序列 |
| `mapping_table` | `source_key`, `target_key` | `{kind: mapping_key}` 指对象主来源的 `key_columns`；或 `{kind: properties, property_ids: [...]}` 指单个 unique 属性、完整标识。列数、顺序必须一致 |

`direct` 保存有效属性间的等值语义，具体 JOIN 就绪要求两端有列绑定；缺绑定时连接待补全，不给出伪 SQL。计算表达式不能作为首版关联键。关系可以跨 connection 保留语义，但 MCP 明示 `cross_connection`，不能在一条 SQL 中连接，不生成伪可执行 JOIN。映射表必须与两端在同一连接 才提供 SQL 参考。任意 SQL JOIN、范围 JOIN 留以后扩展。

例：订单外键无业务属性时，用订单表作映射表，`source_columns=[order_id]` 指源映射键，`target_columns=[customer_id]` 指目标映射键；订单客户编码已建属性时，可直接关联客户 `unique` 的编码属性。选课表用独立映射表；复合键按位置逐列 AND。

对象问数从查询对象出发保留未匹配对象，基础 SQL 参考默认 LEFT JOIN；浏览关联实例只列匹配关系。具体 SQL 的连接与过滤安排由 agent 保证语义等价，不把执行写法作为核心模型字段。按声明的基数给重复计算风险提示；数据库未声明约束、脏键或重复映射表行仍可能增行，平台不做运行时基数校验。

### 3.5 规则 `Rule`

同 v2：`id, display_name, name, description, owner_kind, owner_id, rule_kind (constraint | derivation), expression, evidence`。
`owner_kind` 为 `object_type / property / link_type`。**删除** `verbalizes`，自然语言说明写在 `description`。
v3 的规则引用列表不保留，普通规则只存在 `rules` 集合；ObjectType.derived_by 是成员判定定义，不是 Rule id 列表。

**表达式写法**：受限 SQL 表达式 + 本体路径，用文字路径引用：`对象.属性`、`对象.关系.属性`，第一段是规则所属的对象
（属性、关系上的规则，第一段是其所属对象），每一段按 §3.2 的 Path 解析。平台不执行规则，只检查路径中的对象、关系、属性都存在。
规则保留文本并解析用于识别表达式结构的抽象语法树 AST（Abstract Syntax Tree）及 id 依赖；不是任意 ANSI SQL。允许常量、比较、布尔组合、算术、CASE、受限标量函数及本体路径，不允许 SELECT、子查询、聚合或窗口。属性 owner 以属性所属对象为上下文，关系 owner 以源对象为上下文；继承规则沿用父上下文。规则描述业务条件，不自动变成属性计算绑定。改英文标识时按 id 依赖在同一提案组重写路径，不能全局替换字符串、字面量和参数；引用不能解析则拒绝规则。例：

```sql
-- 属性 sales_order.amount 上的约束
sales_order.amount > 0
-- 对象 sales_order 上的约束：华东客户的订单必须有销售员
sales_order.customer.region <> '华东' OR sales_order.salesperson.employee_no IS NOT NULL
```

不使用 Ossie 的角色写法（如 `Person.parent_of(descendant)`）。规则语法的关系导航按上下文和显式方向解析；涉及集合必须有显式的、后续语法支持的量化形式，不能把集合当标量。



### 3.6 指标 `Metric`（结构化与表达式）

指标是独立顶层语义元素，只挂在数据集上，与本体对象、属性、关系不建立关联。simple、expression 显式保存 `dataset_id`；ratio 不保存 dataset_id，读取时从两个 simple 分量解析，两者必须是同一数据集。指标在语义视图中查看；对象详情是否按数据集绑定推导展示“相关指标”，由工程实施和原型阶段决定，模型不保存或规定这种展示关联。

常见口径用 simple 或 ratio，复杂口径用 expression 保存一条 SQL 聚合表达式。**我们给的是语义**：模型校验引用，agent 负责完整查询与方言调整；平台数值预览另按 §8A 受限编译并只读执行。

#### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id`、`display_name`、`name`、`description`、`synonyms`、`evidence` | | 通用元数据 |
| `kind` | `simple` / `ratio` / `expression` | 简单聚合、比率或 SQL 聚合表达式 |
| `dataset_id` | UUID | simple、expression 必填，引用已登记数据集，说明唯一统计来源；所有列引用均限该数据集。ratio 输入不收此字段，读取时从分量解析 |
| `value_kind` | enum / null | simple、ratio 只读推导，原生输入不填：count、count_distinct 为 integer，sum、min、max 沿用度量值类型，avg、median、ratio 为 decimal。expression 声明七种语义类型之一，外部未提供时可空并待补全，不做 SQL 类型推断 |
| **simple** | | |
| `aggregation` | enum | sum / avg / median / min / max / count / count_distinct |
| `measure` | ColumnReference / null | count 不填，数数据集行；其他聚合必填，仅引用 dataset_id 所指数据集的列 |
| `filters` | list[Condition] | 本数据集列的固定条件，全部 AND，可空；不支持 OR，复杂条件用 expression |
| **ratio** | | |
| `numerator_id`、`denominator_id` | UUID | 两个数值型 simple，必须同一数据集；各自保留过滤和时间字段。小数相除，分母为零时为空，总计按分量重算。精度及物理类型交给 agent，不发生整数截断 |
| **expression** | | |
| `expression` | str | 一条 SQL 聚合表达式，只以 dataset.column 引用 dataset_id 所指数据集的登记列；保留算法、字面量与 NULL 行为，不使用本体路径，不接受 SELECT、FROM、JOIN 或额外查询作用域 |
| **时间字段** | | |
| `time_field` | ColumnReference / null | simple、expression 可选日期类列，包含快照日期列。simple、expression 均限 dataset_id 所指数据集；ratio 不保存，分别使用分量时间字段归周期，允许不同业务时间 |

**ColumnReference 与 Condition**：

```json
{
  "measure": {"dataset_id": "<数据集 id>", "column": "amount"},
  "filters": [
    {"column": {"dataset_id": "<数据集 id>", "column": "status"}, "operator": "eq", "values": ["已完成"]}
  ]
}
```

operator 为 eq / ne / gt / ge / lt / le / in / not_in / between / is_null / not_null；between 两个值，in/not_in 至少一个，is_null/not_null 零个，其余比较一个，not_in 不含 null。值类型按 Dataset.columns 登记元数据核对；清单空或类型未知时待补全，已知清单不存在该列时修订引用，不臆造列、属性或就绪 SQL。物理类型适配交给 agent。

比较遵循 SQL 三值逻辑，is_null 匹配列为空。count_distinct 精确去重且不计 null；SUM 空集为 null、COUNT 空集为 0。ratio 的过滤留在各自分量，不能把分子过滤放到公共 WHERE。

**所有指标只引用单个数据集**：simple 的度量、固定条件和时间字段，expression 的全部列和时间字段，以及 ratio 的两个分量，均限于自己的 dataset_id 所指数据集。expression 允许本数据集聚合、算术、CASE 和标量函数，不接受 SELECT、FROM、JOIN 或额外查询作用域；不能借同一数据集的不同角色绕过此边界。模型没有数据集之间的关系，指标也不引用本体，不能从本体关系推出指标的连接。

**需要其他数据集的条件在查询时处理**：例如只定义 orders 上的“订单金额” `SUM(orders.amount)`。用户问“华东区订单金额”时，agent 在查询时沿订单到客户的本体关系筛选客户地区，再按订单金额口径聚合。地区筛选和查询连接是 agent 回答问题时的行为，不是指标定义的一部分；有歧义或重复计算风险时由 agent 处理，必要时澄清。

expression 不套用 simple 的 AND 和聚合枚举。模型检查本数据集列引用及表达式边界，不验证函数执行、物理类型或公式等价性。保存文本并解析 AST，引用按 dataset id 与列名记录；数据集改名时只重建引用显示，不替换字面量。新建引用必须闭合；导入未闭合则保留原文待补全，数值预览另须通过执行白名单。

**依赖变更**：删除数据集、删除或改名列、调整来源位置或快照声明时，检查直接引用与经 ratio 分量间接依赖的指标，列出影响及原因；修订与数据集变更归同一依赖组，最终图合法才能接受。范围与含义保持的来源搬迁只更新 SQL 参考，无法确认等价时列潜在影响，不扫描数据库证明等价。本体对象、属性、关系及 derived_by 的变更不触发指标定义依赖检查。

ratio 例如退款率＝退款金额（按退款时间）÷销售金额（按下单时间），两个分量均在同一订单数据集，2 月值为 2 月退款除以 2 月销售。改变时间口径须换分量；分量时间字段变化时展示新口径，不自动改写另一分量。

#### 例子

以下数据集与列均为虚构登记；orders 每行是一张订单，包含 amount、status、customer_id、created_at，customers 每行是一名客户，包含 customer_id、region。

| 指标 | kind | 数据集 | 算法 |
|---|---|---|---|
| 订单金额 | simple | orders | sum(amount) |
| 订单数 | simple | orders | count，measure=null |
| 已完成订单数 | simple | orders | count，固定过滤 status='已完成' |
| 下单客户数 | simple | orders | count_distinct(customer_id)，示例外键有效 |
| 客户数 | simple | customers | count |
| 客单价 | ratio | 从分量解析为 orders | 订单金额÷下单客户数 |

```json
{
  "kind": "simple",
  "display_name": "订单金额",
  "name": "order_amount",
  "dataset_id": "<订单数据集 id>",
  "aggregation": "sum",
  "measure": {"dataset_id": "<订单数据集 id>", "column": "amount"},
  "filters": [],
  "time_field": {"dataset_id": "<订单数据集 id>", "column": "created_at"}
}
```

代码行日统计每行代表一个仓库一天的统计，提交数为 SUM(commit_count)；两行值为 3 和 5 时结果 8，COUNT(*) 则为 2。无需对象绑定，完整列条件、ratio 与 expression 见[示例 13](core-1-examples/13-dataset-metrics.json)。

#### 时间口径：快照与事件

时间只在两处声明：**数据集上的快照日期列**（§3.7）和 **simple、expression 指标上的可选时间字段**；ratio 使用两个分量各自的时间字段。

| 时间 | 回答什么问题 | 例子 | 声明在哪 |
|---|---|---|---|
| 快照时间 | 这一行是哪一天的状态 | 组件每日快照表的 `snapshot_date` | 数据集的 `snapshot_date_column`，只给每日全量快照表填写 |
| 业务时间 | 这件事什么时候发生 | 订单的下单时间、支付时间；组件的上线日期 | 对象的日期类属性，或数据集的日期类列 |
| 指标的时间字段 | 这个指标按哪个时间归到周期 | 订单金额按下单时间统计 | simple 或 expression 的 `time_field`，可选；ratio 读取分量定义 |
| 技术时间 | 数据什么时候被加载或更新 | `update_time`、`etl_time` | 可以建成属性，一般不选作时间字段 |

每日增量分区表（每行是某天发生的事，常见后缀 `_di`）的日期列只是业务时间，不声明快照。

**计算规则**：快照数据集（声明了 snapshot_date_column）每个周期取最后一个有数据的日期，其他数据集取周期内全部行；然后按指标自身算法在整个范围上重新计算，去重、均值、比率等不把每日结果相加。

“最后一个有数据的日期”以整个数据集为范围，同一数据集的所有行用同一天，不按实例、地区或子对象成员条件各取最近值。每个数据集按自己的声明独立选日期；对象有普通主表和快照附表时，各列按所在表的声明处理，不由主表统一决定选日。“当前”使用各数据集的最新日期，指定某一天就使用那一天；选定快照后，需要按业务时间分组的指标再按自己的 time_field 归组，没有时间字段就不按时间分组。不同数据集日期不一致时如何关联、空周期如何显示，由 agent 根据问题处理并说明所用日期，核心不规定。

快照表混有“当日调用次数”等事件列时，应把这些列移到每日增量表；模型不提供指标例外开关。取期末固定为周期内最后一个有数据的日期，不提供取期初。

**例子**：组件每日快照表

| snapshot_date | 组件 | 上线日期 |
|---|---|---|
| 12-30 | A | 10-05 |
| 12-30 | B | 12-20 |
| 12-31 | A | 10-05 |
| 12-31 | B | 12-20 |
| 12-31 | C | 12-31 |

- “组件数”，时间字段为快照日期：12 月取 12-31，结果 3。把两天加起来得到 5，是错误的。
- “截至 12 月底的组件按上线月份计数”，时间字段为上线日期：先取 12 月最后有数据的快照 12-31，再按上线日期归月，12 月为 2（B、C），10 月为 1（A）。不先取快照，A 会被数两次。

**实例浏览也使用数据集的快照声明**：对象绑定快照数据集时，实例浏览和 agent 查询明细默认只取最新一天，也可以指定日期查看当时的状态。

**和业界的对照**（核查日期 2026-10-15）：

| 产品 | 时间字段 | 时间聚合声明或显示设置 |
|---|---|---|
| [dbt 语义层](https://docs.getdbt.com/docs/build/semantic-models) | 模型的 `agg_time_dimension` 为默认时间轴，新版 simple metric 可覆盖 | 旧版 [measure](https://docs.getdbt.com/docs/build/measures#non-additive-dimensions) 和新版 [simple metric](https://docs.getdbt.com/docs/build/simple) 都有 `non_additive_dimension`；旧 measure 已弃用 |
| [Snowflake 语义视图](https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view) | 时间作为维度显式声明 | 在 metric 上写 `NON ADDITIVE BY`，按声明的排序取末值参与聚合 |
| [Tableau Pulse](https://trailhead.salesforce.com/content/learn/modules/tableau-pulse-fundamentals/create-metric-definitions) | 定义指标时必填 Time Dimension | `Show values to date as` 只控制图上各点的累计显示，顶部当前值仍为周期累计；此资料未证明等价的期末快照规则 |
| [Databricks 指标视图](https://docs.databricks.com/aws/en/uc-semantics/metric-views/advanced-techniques) | 时间作为维度声明，并可用作窗口的 order 字段 | measure 的 window 中声明 `semiadditive: first/last`，查询未按 order 字段分组时取首值或末值；不等同于整个数据集统一选日 |
| Fabric IQ、Palantir | 实体绑定时间序列来源、对象的时间序列属性，在数据一侧处理 | 未核实与本平台同构的指标级声明 |

我们的 time_field 与 dbt 的 agg_time_dimension 在归周期的用途上相近，core-1 允许不填，dbt 对定义指标的模型要求时间维度和默认时间轴。我们只在数据集上声明快照，不在指标上声明；dbt 在旧 measure 或新 simple metric 上、Snowflake 在 metric 上、Databricks 在 measure 的窗口中声明相应时间聚合规则。core-1 的数据集声明也供实例浏览使用，混入快照表的事件列应拆到每日增量表。

现有 `services/metric_query.py` 的 as_of 使用整张来源表中不晚于截止日的最大日期，相当于这里的“数据集最新日期”；现有代码尚未实现逐周期趋势和多数据集独立选日期，后续实现按本节验收。

#### 汇总表与窗口属性

汇总表登记成数据集，直接在其上建数据集指标；查询时用不用汇总表由 agent 决定，不在指标上保存执行来源提示。

例如销售额已有按日、地区汇总的金额表，可以在其上建销售额数据集指标，用于按月、地区求和；只有金额均值的表不能代替总体均值，只有去重数的表也不能随意把各日去重数相加。agent 选择来源时须保留固定过滤、分子分母和时间口径，不能因为有汇总表就改变算法。

1m、3m、6m、1y 等已计算窗口分别建为不同属性或不同来源，并在描述里说明统计时点、窗口起止和含义。这些窗口可能重叠，不能相加。表里已经算好的覆盖率、密度、百分比列是属性；需要总体比率指标时，建分子和分母再相除，不能把每行百分比简单求和或平均。

#### 为什么采用结构化与表达式并存

| 参考产品 | 已核实的形式 | 本设计的取舍 |
|---|---|---|
| [dbt MetricFlow](https://docs.getdbt.com/docs/build/about-metricflow)、[derived metrics](https://docs.getdbt.com/docs/build/derived) | simple、ratio、derived、cumulative、conversion 等类型；derived 用表达式组合已有指标 | 采用常见口径结构化、复杂口径用表达式的方向；不宣称 MetricFlow 的 derived 等于任意 SQL |
| [Cube measures](https://docs.cube.dev/reference/data-modeling/measures) | count、count_distinct、sum、avg、min、max 等类型结合 sql；number 可承载聚合表达式，number_agg 可用自定义聚合，但受引擎条件限制 | 使用 simple 和 ratio 提供清晰字段，用 expression 保存其余聚合口径；不假设 Cube 有内置 median 类型 |
| [LookML measure types](https://docs.cloud.google.com/looker/docs/reference/param-measure-types) | sum、average、median 等聚合类型结合 sql；number 可组合聚合值，median 受数据库方言支持限制 | 增加 median 语义，具体 SQL 由 agent 按引擎调整 |
| [Fabric Metric](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-metrics) 与 [Ossie OSI](https://github.com/apache/ossie/blob/main/core-spec/spec.yaml) | Fabric 的操作页展示源 DAX（Data Analysis Expressions，用于分析计算的数据分析表达式）measure，定义协议还支持顶层表达式 Metric；OSI Metric 以表达式保存计算 | 支持表达式承载口径，同时保留本平台便于编辑的结构化形式 |
| [Palantir 对象集合聚合](https://www.palantir.com/docs/foundry/api/ontology-resources/objects/aggregate)、[自定义 Function 聚合](https://www.palantir.com/docs/foundry/functions/create-custom-aggregation) | 对象集合可声明聚合与分组，复杂计算可写 Function 代码 | 保留语义定义，不引入 Function 运行环境 |

Fabric [新体验定义协议](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/ontology-definition)公开 explicit、enrichment、projected Metric；explicit 有自己的 expression，支持 SQL、KQL（Kusto Query Language，用于日志和分析查询的 Kusto 查询语言）等方言，另外两类依赖源 measure。以上核查日期为 2026-10-15。共同方向是聚合类型与表达式或代码配合；各产品的执行能力并不相同。

**MCP 契约**：返回指标定义和数据集列引用，不返回对象归属。simple、ratio 在数据集来源、列及权限就绪时可附基础 SQL 参考；expression 保留算法交给 agent。simple、ratio 可附只读推导 value_kind，ratio 可附从分量解析的 dataset_id，原生输入不收这些推导字段。分组、查询范围、其他数据集的筛选和物理适配由 agent 在查询时处理，不能改变固定算法与条件。

例如“完成率 = 已完成订单数 / 全部订单数”，一单完成、一单取消，结果是 0.5。不能把“已完成”移到公共 WHERE，否则分母也只剩完成订单而得到 1。各分量的过滤和时间口径分别保留。

### 3.7 数据集登记与数据映射

#### 数据集 `Dataset`

新增顶层 `datasets`，用轻量、扁平的登记表示可引用的数据来源。数据集是登记单位，背后可以是表或视图；指标只引用单个数据集的列，不关心其物理形态。同一数据集可以被对象主表、附表、关系映射表及数据集指标复用，位置和快照声明只维护一份。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | UUID | 稳定引用 id |
| `name` | str | 数据集名称，在本模型内唯一；不是对象英文标识，不要求与对象同名 |
| `dialect` | str / null | mysql、doris、postgresql 等引擎方言；导入材料无法确定时为空并标记待补全，不能把 ANSI_SQL 当成数据库引擎 |
| `schema_name` | str / null | 表的命名空间，按方言可含 database/schema 限定；MCP 结合服务端元数据解析 database 与 schema，空值使用来源默认值，无法定位则未完成 |
| `table_name` | str | 来源表名或视图名，不存任意 source query 或递归来源树 |
| `description` | str | 来源说明，也可承载供 agent 理解的上下文 |
| `snapshot_date_column` | str / null | 快照日期列。只给每日全量快照表填写（每行是某天的状态，常见后缀 `_df`）；每日增量分区表（每行是某天发生的事，常见后缀 `_di`）的日期列只是业务时间，不填。非空时，每周期按该数据集最后有数据的日期选行，实例浏览默认取最新一天（§3.6） |
| `columns` | list / null | 可选的元数据快照列清单，每项为 `{name, physical_type, comment}`；不是本体字段节点，不自动生成属性，空或缺省表示未提供清单 |

元数据快照的采集 id 和时间由服务端物理投影附带；列清单只是导出时可携带的元数据副本。没有列清单时只能检查已知元数据中的引用，未知列标记待补全，不伪装成已经验证存在。连接凭据和连接登记保留在平台配置中，不进入 Dataset 或 MCP 合同；平台根据方言和 schema 定位来源，歧义按 §14.3 处理。

快照日期列允许日期、日期时间，以及可按日期排序的文本或整数列（如 `2026-10-23`、`20261023`）；类型未知时仍允许登记。声明者须保证原值排序与日期顺序一致，平台不猜测或转换日期格式，默认用 `MAX` 选最新快照，指定快照时按原值比较；布尔、小数和浮点类型仍拒绝。指标时间字段的日期类要求不变；若已有定义以非日期类快照列作为时间字段，月趋势预览明确报错，提示先在数据源提供日期类列再作为时间字段，或关闭月趋势。

参考依据是分层方式，而非照搬外部模型：[Fabric 本体与 Power BI 语义模型](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview#alignment-with-power-bi-semantic-models)分层，并支持[实体绑定 Lakehouse 表](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-bind-data)；[Ossie](https://github.com/apache/ossie/blob/main/ontology/ontology.md)将 ontology 与包含 datasets 的 semantic_model 分开，用 ontology_mappings 连接；[Palantir 对象](https://www.palantir.com/docs/foundry/object-link-types/create-object-type)直接选择 backing datasource。本平台取“扁平数据集登记 + 本体引用它”，不恢复 v3 的 semantic_models、dataset_fields 或递归映射树。

#### 数据映射 `DataMapping`

一个对象最多有一个 DataMapping。主、附来源以 dataset id 引用登记，按键横向补充属性。D1 的同连接约束由服务端来源配置核对，不由对象各自重复保存表名或连接别名。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id`, `type_id` | UUID, UUID | 映射及对象 id |
| `binding_mode` | `independent` / `shared_parent` | 独立绑定或沿用有绑定父对象；虚拟父对象自身没有映射 |
| `sources` | list[MappingSource] | 每项为 `id, dataset_id, key_columns`，均为平铺引用；shared_parent 只列新增扩展来源，不重复父来源 |
| `fields` | {属性英文标识: FieldBinding} | 每个已绑定属性对应一个来源列或同行表达式；有绑定父对象的继承项不覆盖，虚拟父对象的继承属性可在具体子对象中绑定 |
| `membership_source_id` | str / null | shared_parent 的成员扩展来源，必须是本层 sources 的一项；该表中有记录的父实例才属于子对象 |
| `inherited_link_bindings` | {关系 UUID: DataJoin} | 默认空；仅虚拟父对象的具体子对象可为继承关系提供本地绑定，不创建新关系；有绑定父对象的继承关系沿用父绑定 |

独立绑定固定以 id=main 为主来源，不能按 sources 数组首项猜主表；shared_parent 沿用父主来源。`MappingSource.id` 是映射内局部来源名；扩展来源不能与有效祖先来源重名。`key_columns` 声明来源在所选业务时点上的有序逻辑键，不要求数据库已声明主键；非快照数据集上是整表逻辑键。主、附键逐对对应，连接呈星形；shared_parent 扩展表键按父主来源的标识键顺序对应。附表默认只补充属性，只有 membership_source_id 所指扩展表还限制子对象的成员集合。

主表决定对象实例集合，普通附表缺失不删除主实例，附表独有的键不创建实例；子对象扩展表只能引用父实例。空键可保留为未完成绑定，不能提供伪可执行 JOIN。平台校验键引用、列数和顺序，不运行唯一性或实例覆盖扫描。D1 的普通纵向合并和跨连接联邦继续延期，虚拟父对象的实例并集是 §3.2 的明确语义，不是任意表的 union 映射。

`FieldBinding` 是带判别字段的联合：

```json
{
  "kind": "column",
  "source_id": "main",
  "column": "amount"
}
```

或：

```json
{
  "kind": "expression",
  "expression": "main.quantity * prices.unit_price"
}
```

表达式只引用本对象来源表的物理列（`来源id.列`），对附表完成声明的横向拼接后的**同一行**求值；允许算术、CASE、受限标量函数，不允许聚合、窗口、子查询或其他对象。禁止引用另一个计算属性，避免派生依赖环。平台只解析、校验引用与同行边界，不执行、不校验物理类型转换；结果语义类型取 Property.value_kind。MCP 把表达式作为该属性的列绑定返回，agent 按查询引擎调整。

Fabric 的 [Overview](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview#alignment-with-power-bi-semantic-models) 明确新体验能保留源语义模型的 calculated columns；[源 CalculatedColumn.Expression](https://learn.microsoft.com/en-us/dotnet/api/microsoft.analysisservices.tabular.calculatedcolumn.expression) 是 DAX 表达式。本轮核查了新体验定义协议，但未确认独立编写本体计算列的专用字段；本设计对齐“逐行属性、聚合 Metric 分开”的概念，不宣称 SQL 绑定与 Fabric 内部结构相同（核查：2026-10-15）。

一个对象可能挂了二十多张汇总和快照表，不设置小于该规模的产品限制。不同窗口映射到不同属性，不能由多个来源争用同一属性。无法声明唯一拼接键时保留未完成绑定；跨连接联邦和普通多表纵向映射以后再扩展，虚拟父对象按 §3.2 展开。

#### 数据集快照与关联提示

快照只在 Dataset.snapshot_date_column 上声明；MappingSource 不再保存 snapshot。对象绑定快照数据集时，实例浏览和 agent 查询明细默认只取该数据集最新一天，也可以指定日期查看当时的状态。历史物理行常以实体键和日期共同唯一，但选定数据集日期后，实例关联键仍可使用实体键。不要把时点内唯一误写成历史全表唯一，也不要从逻辑键自动推导不同数据集日期相等。业务时间属性描述指标含义，数据集日期列描述来源快照，二者不必由同一物理字段承载所有来源的日期。

给 agent 的提示：历史表只连实体键可能让多天记录交叉配对，应先理解数据集日期和问题时点，避免把多个日期当成同一天。日期一致时可以同日关联；日期不一致时如何关联或说明、空周期如何展示由 agent 处理，核心不强制同日，不指定主来源决定日期，不增加自动回退规则。

#### 成员定义与物理绑定

成员条件保存在 ObjectType.derived_by，引用本体属性和关系；物理列改名或换绑不改条件的 id 依赖。成员扩展来源仍由 membership_source_id 声明。可能改变成员范围或属性、关系含义的换绑须展示对象语义影响；权限筛选不替代成员定义。指标独立引用数据集列，不随对象成员定义改变。

### 3.8 草稿顶层

```text
schema_version: "core-1"
workspace_id
object_types, properties, link_types, rules,
metrics, datasets, mappings, material_objects, material_links
```

**删除**的 v3 顶层字段：`hash_algorithm`、`ossie_version`、`ossie_name`、`ossie_description`、`ai_context`、
`native_presence`、`document_origin`、`core_version`、`core_presence`、`extension_v4`、`value_types`、`semantic_models`、
`dataset_fields`、`dataset_relationships`、`concept_mappings`、`mapping_nodes`；原 v3 的 datasets 结构删除，改用本节轻量 Dataset，不能沿用旧字段树。

### 3.9 校验

沿用 v2 `OntologyDraft.validate_graph` 的全部规则（同名、英文标识冲突、继承环、属性与关系共享命名空间、规则归属、实例类型、映射引用），
新增校验如下。它们检查语义声明和引用，不要求平台代替 agent 适配物理类型。

- 继承只能有一个父对象，且不能成环。标题属性必须属于本对象或其祖先，本地定义不能遮蔽继承定义；标识规则见 §3.2。Ossie 子类不同的首选标识不能给已有父标识增项，按 §5.2、RT-68 保留普通属性并报告原标识损失。
- Dataset id 和名称唯一；sources 及关系映射表的 dataset_id 必须存在；表位置仅在 Dataset 保存。可选列清单不作为已验证元数据的替代。
- 有绑定父对象的子对象只能 shared_parent，不允许 independent 子表；无绑定父对象的具体子对象可 independent 并绑定继承属性、关系；虚拟父对象不接受直接事实。共享父绑定须有 ObjectType.derived_by 或 membership_source_id 才算就绪，成员扩展表须属于有效星形来源且按父标识键关联；覆盖与互斥是建模约束，不扫描实例验证。
- `sources` id 不重复、独立主来源存在；fields 中 source / 列引用可定位；空键为未完成绑定，不拒绝概念模型；附表非空键与主键列数一致。表达式须通过同行引用检查。
- `data_join` 按 kind 校验：direct 两端属性引用有效、目标属性组为声明唯一键；具体 JOIN 就绪还需两端有列绑定；mapping_table 列数匹配引用键（mapping_key 或 properties）；任一端未映射时不得提供具体 SQL JOIN；可保留未就绪 direct 的有效属性引用，或保留语义关系并令 data_join=null。跨连接标记仅供语义，不提供单 SQL。

- inherited_link_bindings 只能引用本对象从虚拟祖先继承的关系 id，按本对象有效来源校验相应 DataJoin；有绑定父对象的继承绑定不得覆写，字段与关系的本地绑定不改变原定义归属。
- simple、expression 必须保存有效 dataset_id；ratio 输入不收 dataset_id，从两个同数据集数值型 simple 分量解析。simple 的 measure、filters.column、time_field 和 expression 的全部列引用及 time_field 均限本数据集列。
- count 不填 measure，其他聚合必填；sum、avg、median 要求数值，min、max 允许数值、string、date、datetime，不允许 boolean。列类型和结果类型按登记元数据，未知则待补全。ratio 分量必须同一数据集且是数值型 simple。COUNT 可空列不得误转行计数，条件值数量和类型须匹配运算符及列。
- expression 的全部列引用必须属于 dataset_id；不接受本体路径、SELECT、FROM、JOIN 或额外查询作用域，不推断 SQL 类型，不套用 simple 的 AND 限制。不能从本体绑定补出指标连接。
- 数据集改名按 id 重建指标引用显示。删除数据集或列、调整来源位置及快照声明须检查直接引用与 ratio 间接依赖，修订归同一依赖组，最终图须合法。本体增删改和成员变化不触发指标定义依赖检查。
- 数据集快照日期列和指标时间字段必须可定位，time_field 为日期类列引用；simple、expression 均限自己的 dataset_id 所指数据集列。ratio 出现 time_field 时拒绝，按两个分量各自时间字段归周期，允许不同。派生条件按 §3.2 校验，与指标独立。平台不检查数据集日期一致性或快照完整性。
- 关系 name 是所属对象内的 ASCII 标识；verbalizes 每条必须包含 {source}/{target} 两端，无未知或残缺占位符。
- `rules.expression` 中的路径必须从规则所属对象出发，每段都存在。
- **标识只由属性组成**：对象的标识是它全部 `identifier=true` 的属性（含从父对象继承的），组合起来唯一。关系不参与标识，只负责连接对象。
  标识只有一个属性时，该属性必须 `unique=true`；多个属性组成的复合标识不要求各自唯一。
  例：订单明细的标识是“订单号”+“行号”两个属性，行号在不同订单里会重复，`unique=false` 合法；
  “所属订单”关系另外存在，用于从明细走到订单。属性键与关系分开；复合业务标识是本平台明确支持的能力，不能等同 Palantir 当前单 primary-key property。
- 英文标识允许 SQL 保留字，例如 order；解析时按本体标识符处理，物理 SQL 标识符由 agent 按方言引用。
- 业务标识顺序按属性 UUID 字节序确定，Ossie 导出 identify_by 和原生引用使用同一顺序；不依赖 JSON 数组位置。物理 key_columns 顺序独立保持。元数据 UUID、文档事实 UUID、数据库 `(具体 type_id, 有序 typed key tuple)` 分开；不以分隔符拼接复合身份。文档事实缺标识仍保存并提示补全，不因 required/identifier 自动拒绝。

---

## 4. 适配器架构

### 4.1 接口

```python
class FormatAdapter(Protocol):
    id: str                      # 例如 "ossie-0.2"
    label: str                   # 界面显示名，例如 "Apache Ossie 0.2"
    file_extensions: tuple[str, ...]

    def detect(self, raw: bytes) -> bool: ...
    def import_document(self, raw: bytes, ctx: ImportContext) -> ImportResult: ...
    def export_document(self, model: CoreDraft, ctx: ExportContext) -> ExportResult: ...
    def validate_document(self, document: bytes) -> list[TranslationIssue]: ...  # 目标格式自己的官方校验
    def diff_roundtrip(self, original: bytes, exported: bytes) -> list[RoundTripDiff]: ...  # 仅测试使用，每处差异带规则编号，见 §7.2

@dataclass
class ImportContext:
    workspace_id: UUID

@dataclass
class ImportResult:
    model: CoreDraft             # 完整、已通过核心校验的独立模型
    report: TranslationReport

@dataclass
class ExportContext:
    workspace_name: str
    workspace_slug: str
    workspace_description: str

@dataclass
class ExportResult:
    document: bytes
    media_type: str
    filename: str
    report: TranslationReport
```

**合并不归适配器管**。适配器负责把外部文档翻译成独立核心模型并提供转换报告；怎么进入草稿由平台统一处理，见 §4.5。这样每个适配器都不需要重复实现合并和 id 保持。

### 4.2 转换报告

```python
class TranslationIssue(BaseModel):
    outcome: Literal["converted", "dropped", "error"]
    construct: str               # 外部格式里的构造名，例如 "Relationship(n-ary)"
    id: UUID
    rule_id: str | None         # Ossie 语义差异用 RT-xx；通用解析、版本、原生证据错误可空
    severity: Literal["info", "warning", "error"]  # 与 outcome 分开
    source_path: str             # 能解析时为元素路径；解析失败时用可取得的文件定位
    source_locator: dict        # material_id / sha256 / JSON pointer / 行号范围
    original: str | None        # 原表达式、完整片段，或材料 artifact 引用
    target_element_ids: list[UUID] # 无核心结果时为空
    completion_status: Literal["not_needed", "available"]
    target_path: str | None
    message: str                 # 中文说明

class TranslationReport(BaseModel):
    id: UUID
    content_sha256: str         # 预览和确认引用同一转换产物
    direction: Literal["import", "export"]
    adapter: str
    counts: dict[str, int]       # 各类元素的翻译数量
    issues: list[TranslationIssue]
```

| outcome | 含义 | 例子 |
|---|---|---|
| `converted` | 本条转换已完成；是否另有损失须逐项报告，不能以原文留存代替语义转换 | 可完整等价转换的派生定义、元组标识、值类型局部约束 |
| `dropped` | 丢弃 | 读法里的同义说法、字段的 `dimension.is_time` |
| `error` | 本条及无法独立成立的依赖暂停；文件级错误阻止整份导入或导出 | 文档不是 JSON、版本不支持、导出时模型为空 |

前端导入、导出对话框按 outcome 分组，另显严重度；语义风险可为 `converted + warning`，不冒充 dropped。报告随导入记录保存，平台维护临时 id → 匹配后的最终 id。行号针对 §13.4 保存的格式化材料，不声称是上传字节原行号。

### 4.3 目录与注册

```text
ontofoundry_api/
  domain/                  核心模型、校验、合并（不 import adapters）
  adapters/
    base.py                FormatAdapter、TranslationReport、注册表
    ossie/
      importer.py
      exporter.py
      mappings.py          ontology_mappings 的双向翻译
      extension.py         ontofoundry-extension.json 扩展文件读写（旧块只在导入读取）
      validator.py         官方 schema + 语义校验（沿用现有 ossie/validator.py）
      assets/vendor/       固定版本的 Ossie schema（沿用）
    native/                OntoFoundry 原生格式（§4.6）
```

API：`POST /workspaces/{id}/imports/{adapter_id}`、`GET /workspaces/{id}/exports/{adapter_id}`，
现有的 `/imports/ossie` 保留为 `adapter_id=ossie-0.2` 的别名。用一个测试保证 `domain/` 不 import `adapters/`。

### 4.4 缺失信息的处理

导出时目标格式要求、核心模型里没有的信息，按以下顺序处理：

1. **可选字段**：直接不写。
2. **必填字段，能从核心模型推导**：推导生成（例如未填写关系读法时，Ossie 的必填 `verbalizes` 生成最小关联句，不回填模型）。
3. **必填字段，推导不出**：本项报 error，不生成伪有效对象；若整份文件要求该项则不交付文件。

导入时明确不承载的构造报 dropped，无法完整转换的条目报 error，均保留原文、定位及原因。报告 completion_status 只说明有无可补全事项；当前是否阻断从候选图及实际依赖实时推导，不另存 blocked，也不篡改历史报告。缺依赖时仍可发起补全。无法解析 JSON 时仅记录实际可取得的文件或行列定位，不伪造 JSON pointer；通用解析、版本不支持、原生缺材料等问题的 rule_id 可为空，由适配器 message 说明。

### 4.5 导入走提案，复用本体构建的会话

本体构建支持两种场景，**都产出提案，后续流程完全相同**：

| 场景 | 输入 | 谁产出提案 |
|---|---|---|
| AI 构建 | 材料 + 对话 | 建模 agent |
| 文件导入 | 外部格式文件（如 Ossie） | 适配器 + 平台对比，确定性生成 |

两种场景共用同一个建模会话和同一套界面：**提案面板 → 会话草稿 → 发布面板（含冲突处理）**。
导入不单独做一套弹窗流程，弹窗只负责选文件、看转换报告，确认后进入会话。

**导入流程**：

1. 导入弹窗：选择格式和文件 → 适配器翻译 → 弹窗展示转换报告（按 outcome 分组）。
   导入只有一种方式：只新增和修改，文件里没有的已有元素保持不动；平台导入从不生成 delete 提案。要删除元素，用户在会话里手动删除，或让 agent 提出删除提案，走正常审阅流程。
2. 用户确认后，平台：
   - 把原文件保存为一份材料（§13.4）；
   - 新建一个建模会话，标题“导入 <文件名>”，基于当前已发布版本；
   - 把适配器产出的核心模型和会话草稿逐元素对比，找出每个导入元素对应草稿里的哪个元素，生成一批提案：
     对应不上的 → create；内容不同的 → update（含改名）；内容相同的不生成提案。匹配方式按格式区分：

     | 格式 | 匹配方式 |
     |---|---|
     | **原生格式** | 文件带着稳定 UUID，**分两轮匹配，结果必须一对一**：<br>① 先对**全部**导入元素按 UUID + 元素类型匹配，对上的双方都锁定；英文标识不同算改名（update）。<br>② 再在**两边都未锁定**的元素之间按英文标识匹配（规则见下行）；匹配上就沿用草稿里的 id，并把文件里对这个元素的引用改成该 id。<br>③ 仍对不上的保留文件里的 UUID 新建。<br>例：文件有 `alpha(id1)`、`beta(id2)`，草稿只有已改名为 `beta` 的 `id1`。第①轮 `alpha` 锁定 `id1`（改名回 `alpha`）；第②轮 `beta(id2)` 找不到未锁定的 `beta`，按③新建，最终状态为 `alpha(id1), beta(id2)`，合法；不按 id1 改名前的 beta 误判冲突，也不会把两个元素对应到 id1 |
     | **Ossie 等外部格式** | 文件里没有我们的 UUID（适配器生成的 id 只在本次有效），**按英文标识匹配**：对象按 `name`，属性按 `所属对象.name`，关系按 `来源对象.name`，规则按 `归属.name`，指标按 `name`，数据集按 `name` |

     英文标识匹配还包括：先重写对象 id，再按 type_id 一对一匹配未锁定映射，复用已有映射 id，不能为一个对象创建两份映射；UUID 首轮锁定不得被后续自然键匹配覆盖，冲突按候选最终图报告。文档事实、链接和证据没有自然匹配键，只按 UUID，不因业务编号或 quote 相同而合并，也不改变嵌套证据归属。

     转换不出来的条目保留原文、材料定位与待补全原因，等待用户选择或点击 AI 补全，满足核心校验后再形成新增或修改提案；对应已有定义保持不动。其他可独立成立的 create、update 照常生成。

     完成全部匹配和 id 重写后，先构造**候选最终图**，统一检查英文标识及引用。合法互换名字放在同一原子依赖组；不按草稿现状提前拒绝。证据、实例、Metric、Dataset、Mapping 均纳入重写，dataset_id 及继承关系的本地绑定也须重写。
     冲突不硬套，逐条报告，冲突元素及依赖它且无法独立成立的反向依赖闭包标记阻断，不生成悬空提案，由用户处理：
     - UUID 在本工作空间登记过、但类型不同（元素身份表规定 id 不跨类型复用）；
     - 按 UUID 对应后改出来的英文标识，或新建元素的英文标识，在候选最终图里仍与另一个元素冲突。
     元素身份按工作空间登记，同一个原生文件导入到别的工作空间时 UUID 可以原样使用。
   - 每条提案附材料证据，指向原文件里对应的行；
   - 提案批次的 `producer_json` 记为 `{"kind": "import", "adapter": "ossie-0.2", "report_id": "<转换报告 id>"}`，和 agent 产出的批次区分。
3. 跳转到该会话。用户在提案面板审阅：可以逐条接受，也可以用已有的“全部接受”；然后照常在发布面板发布。
4. 会话里显示“用 AI 补全 N 项”（§13.4），在同一个会话里发起一次建模运行，补全提案和导入提案放在一起审阅。

**文档事实是否合并由人审阅决定。** AI 从不同文档抽出同一业务标识的事实时，各自形成新建提案。审阅时，若已有同对象类型、同完整业务标识的事实，界面给出重复提示，只提示、不阻断、不自动合并；用户可以两条都接受、只接受一条，或把新建提案改为对已有事实的更新提案并追加证据。缺完整标识时不猜重复；更新保留已有事实 UUID，证据按自身 UUID 保存。原生导入仍按上面的 UUID 匹配规则处理，不把重复提示当成自然键匹配。

空工作空间也走同一流程，此时全部是 create 提案，“全部接受”后发布即可。
这样导入不需要自己的合并、冲突处理和发布逻辑，全部复用提案机制；现有导入弹窗里的“直接发布 / 跳转发布页三方合并”逻辑删除。

### 4.6 OntoFoundry 原生格式

适配器 `id = ontofoundry-core-1`，用于完整备份、在环境之间搬迁、平台之间交换。有两种形式：

| 形式 | 内容 | 用途 | 无损 |
|---|---|---|---|
| **完整包**（默认）`*.ontofoundry.zip` | `manifest.json` + `draft.json` + `materials/` 下被证据引用的材料原文件 | 备份、跨环境搬迁 | 是 |
| **单文件** `*.ontofoundry.json` | 只有核心模型 | 查看、比对、在同一环境内复制模型 | 否：证据引用的材料不随文件走 |

`manifest.json`：

```json
{
  "format": "ontofoundry",
  "schema_version": "core-1",
  "exported_at": "2026-10-14T08:00:00Z",
  "materials": [
    {
      "material_id": "mat_returns_jan",
      "name": "1月退货登记.md",
      "sha256": "3f1c…",
      "byte_size": 2048,
      "path": "materials/3f1c….md"
    }
  ]
}
```

单文件形式就是 `{ "format", "schema_version", "exported_at", "draft" }` 四个字段。

**导出**：核心模型原样写入 `draft.json`，包括规则名、指标、映射、实例、证据。完整包把**被任何证据引用**的材料（含导入时保存的原 Ossie 文件）
按原字节打进 `materials/`，文件名用 sha256，manifest 记录材料 id、名称、哈希和大小。没被引用的材料不打包。

**导入**（同样走提案，§4.5）：

1. 校验 `schema_version`；完整包逐个校验材料文件的 sha256 与 manifest 一致，不一致整包拒绝。
2. **重建材料**：按 sha256 在目标工作空间查找同内容的材料（材料表对 `workspace_id + sha256` 唯一），有就复用；没有就用包里的原文件新建，
   照常切分。得到“包内材料 id → 目标材料 id”的对照表。
3. **重写证据引用**：所有材料证据的 `material_id` 按对照表改成目标 id；`material_sha256` 不变，行号和原文不变（内容相同，行号仍然有效）。
4. 人工证据原样保留；`created_by` 是导出环境的用户 id，目标环境不一定有这个用户，界面按原值显示，不做映射。
5. 单文件形式没有材料：证据引用的材料在目标工作空间按 sha256 找得到就重写引用，找不到就丢弃该证据并报 `dropped`。

各种场景和边界情况的完整示例见 [`core-1-examples/`](core-1-examples/README.md)（每份是带 `draft` 的单文件原生包装）。

---

## 5. Ossie 适配器：导入

支持纯 Ossie JSON 或 ZIP（Ossie 文件 + ontofoundry-extension.json）。单个文件不推导中文名称，display_name 为空；旧 ai_context.ontofoundry 只在导入边界兼容读取，报告“旧版扩展块”。

适用入口是现有 `ontology/ontology.json` 中 version 为 0.2.0.dev0 的内嵌 ontology_mappings 文档，其他版本报 error。上游[现行说明](https://github.com/apache/ossie/blob/main/ontology/ontology.md#mapping-documents)已将内嵌形式标为弃用但仍接受；新的独立 mapping documents 不在本期适配范围，不能仅凭版本号相同就声称全部支持。
只包含 `semantic_model`、没有 `ontology` 的 OSI core-spec 独立文档：报 `error`（没有可导入的业务对象）。

### 5.1 文档层

| Ossie | 导入 | 说明 |
|---|---|---|
| `version` | 校验 | 不是 `0.2.0.dev0` 报 `error` |
| `name`、`description` | 不读，记入报告 | 模型名称取工作空间自身 |
| `requires` | `dropped` | 核心模型没有工作空间级约束；原文留在报告里，可由 AI 补全改写成具体元素上的规则（§13.4） |
| `ai_context`（字符串） | `dropped` | |
| `ai_context.ontofoundry` | 读取，见 §5.7 | 旧版平台扩展块（仅导入兼容；报告“旧版扩展块”） |
| `ai_context.instructions` | 能确定对应对象时并入该对象的 description，报 converted（RT-59） | 文档级说明没有明确归属时留报告待 AI 分配，不复制到每个对象（RT-02） |
| `ai_context` 其他键 | 未支持的内容报 dropped | 同义词可由后续 AI 补全分配，不能猜归属 |
| `ontology` | 见 §5.2–5.4 | |
| `ontology_mappings` | 见 §5.5–5.6 | semantic_model.datasets 一一登记为 Dataset，不保存 semantic_model 元素 |

### 5.2 概念

| Ossie | 导入 | 说明 |
|---|---|---|
| `EntityType` | → `ObjectType` | `concept` → `name`（不合规的字符替换为 `_`，冲突加后缀，报 `converted`）；`display_name` 只从扩展文件取，没有则为空 |
| `description` | → `description` | 与能够确定归属的 `ai_context.instructions` 合并，原描述在前，说明在后，以空行分开（RT-59） |
| `extends`（实体） | → 单个可空 `extends` | 按文件顺序只保留第一个，其余逐项 dropped（RT-34），报告额外父类及不能闭合的继承引用；原文保留。可建议改写成派生条件或关系，但这是需用户审阅的业务改写，不保证等价，不自动生成关系；不得先排序 |
| 实体 `extends` 值概念或内置值类型 | 输入 `error` | 非法 Ossie 输入，报告原文与定位；不转换、不进入合法能力例外表 |
| `identify_by` | 全部成员都是属性且不改变已有父标识时：这些属性 `identifier=true` | 标识**整组翻译或整组放弃**，不裁剪：只要有一个成员是关系（Ossie 允许用关系做标识）或引用不存在，整组标识都不导入，所有成员属性都不设 `identifier`、`unique` 保持原样，关系照常作为普通关系导入，报告“标识待补全”（RT-32）。否则裁剪后剩下的单个属性会被当成唯一标识，与它 `unique=false` 冲突。<br>只有一个属性成员时，该属性设 `unique=true`：Ossie 的 `identify_by` 本身就表示能用它唯一找到对象；原文的 `multiplicity` 不是 `OneToOne` 时报 `converted`（RT-33） |
| `requires` / `derived_by` | requires → 对象 constraint Rule；子概念 derived_by → ObjectType.derived_by（§3.2、§5.5） | 非成员派生说明按 §5.4 生成 Rule；成员条件不重复生成 Rule |
| `ValueType` | **不建元素**，折叠进属性 | 见下 |

**继承标识边界（RT-68）**：先解析父对象的有效标识。父对象已有标识时，子对象只能沿用完整父标识；子类自有的不同 `identify_by` 不设为核心 identifier，也不与父标识拼接。其编号属性照常保留，单属性编号保留为普通 unique 属性（原未声明唯一时按单属性标识语义补 true）；复合编号不把每项都擅设 unique。原首选标识按 dropped 逐项报告（RT-68），保留原文、定位和影响，不把普通属性的保留报成标识已完整转换。原映射若依赖子类首选标识，只有能等价转换为父标识时才转换，否则该映射 error 待补全，不能冒充已就绪。父对象没有标识时，子对象可按本表定义标识；仅重述同一父标识不算冲突。

**值概念折叠**：沿完整祖先图确定唯一兼容的内置基础类型（String、Integer、Decimal、Float、Boolean、Date、DateTime）。无支持类型或基类不兼容时，不取第一个，也不默认为 string，相关属性按 RT-35 报待补全，依赖重算。

可完整按具体值变量改写的 requires，连同祖先有效约束，分别实例化到每个使用属性，包括多元关系值角色生成的属性：owner_kind=property、rule_kind=constraint，description 注明来源值类型及约束。按解析后的变量绑定改写，不替换字符串字面量；同类型的多个角色按各自变量绑定处理。祖先约束按来源定位去重，原属性规则保留；继承属性不为每个子类再复制规则。

例：金额 extends Decimal 且金额>=0，订单.订单金额使用金额；正金额 extends 金额 且正金额>0，退款.退款金额使用正金额。生成订单金额>=0、退款金额>=0、退款金额>0 三条属性约束；退款值 0 不能绕过最后一条。约束不自动使属性必填。无法解析、依赖值类型关系或其他未承载构造的整条约束保留原文并待补全，不生成半条 Rule，其余独立约束照常转换（RT-24、RT-31）。

值概念不建核心元素，原名称、共享域身份、描述、未使用类型、继承结构及 derived_by、identify_by、关系等仍按 RT-23、RT-24 列为例外。来源说明不构成以后自动联动的类型继承。

### 5.3 关系分类

Ossie 的关系写在所属概念（owner）的 `relationships` 里，`roles` 是除 owner 之外的附加角色。按 owner 类型和角色情况分类：

| 情况 | 判定 | 导入为 | outcome |
|---|---|---|---|
| a. 属性 | owner 是实体，1 个角色，角色是值概念或内置类型 | `Property` | — |
| b. 二元关系 | owner 是实体，1 个角色，角色是实体 | `LinkType`（源 = owner，目标 = 角色概念） | — |
| c. 多元关系 | owner 是实体，≥2 个角色 | **中间对象** + 若干二元关系 / 属性 | `converted` |
| d. 一元关系 | owner 是实体，0 个角色 | 布尔属性 | `converted` |
| e. 值概念的关系 | owner 是值概念 | 不导入 | `dropped` |
| f. 引用 `Any` 或不存在的概念 | | 不导入 | `dropped` |

各情况共同的字段处理：

| Ossie 关系字段 | 导入 |
|---|---|
| `name` | 二元实体关系 → 核心 name；属性仍 → name，其 display_name 只从扩展文件读取，没有则为空 |
| `description` | → `description` |
| `requires` / `derived_by` | → `rules`（owner 为对应的属性 / 关系 / 中间对象） |
| `roles[].name` | 二元实体目标角色保存到 target_role_name，重化实体角色保存到生成关系的 target_role_name；源端从 link_role_names 扩展恢复；属性/值角色仍按 RT-21 报告独立名称不保存 |
| `verbalizes` | 二元实体关系保留完整列表，只转换端点占位符；属性见下方例外 |

**读法处理**：

- b：完整 verbalizes 原序保存，Ossie 源概念和目标概念/角色占位符转换为 {source}/{target}；不截取动词，不丢弃尾部或额外读法。导出反向替换，角色改名不破坏引用。
- d：一元读法不推导中文名称；display_name 只读取扩展文件，缺省为空。
- a：属性读法仍 dropped，导出时生成，按 RT-20 记录。

**multiplicity**：

| 情况 | `ManyToOne` | `OneToOne` | 缺省 |
|---|---|---|---|
| a. 属性 | `unique=false` | `unique=true` | `unique=false` |
| b. 二元关系 | `many_to_one` | `one_to_one` | `many_to_many` |
| c. 多元关系 | 除最后角色外的全部角色决定最后角色，按下文生成中间标识 | 输入 error 并报告：OneToOne 只允许二元关系，不转换、不设计补全 | 全角色元组组成中间标识 |

**c. 多元关系 → 中间对象**。

角色顺序为 owner 后接 roles 文件顺序。建立 `{owner}_{关系名}` 中间对象，到每个实体角色建立多对一关系，值角色成为同类型属性。为每个实体角色的有效完整标识逐项生成同类型编号属性，英文标识为 `{角色}_{标识属性英文标识}`，显示名如“起点仓库编码”；继承和复合标识均展开，角色同类型也不合并。生成的角色属性 required=true，表达角色必有值。

ManyToOne 的中间标识取除最后角色外的全部角色表示，包括非最后的值角色；无基数时取全角色元组。单属性键设 unique=true，复合键各项可 unique=false。不把随机 UUID 当业务标识，也不把相同元组解释成多次事件。决定角色缺完整标识时，不生成该角色编号属性，已有其他角色属性保留但都不设 identifier，整组中间标识待补全；ManyToOne 最后实体角色缺标识时，同样不生成其编号属性，但不妨碍前面角色生成完整中间标识，原角色关系保留。

生成编号属性就是角色关系 direct 的 source_property_ids，target_property_ids 是参与对象的完整标识属性组，复合标识逐项对应。关系由这组编号属性定义，天然一致，不另加编号与角色一致性 Rule。只有映射能证明外键列逐项对应业务标识时才绑定编号列；外键若指物理键或另一候选键，编号绑定待补全，角色关系仍按原映射保留，不能猜测或伪装为同行计算列。direct 引用可作为未就绪连接保存，缺列时不给伪 SQL；已有原映射不被未就绪 direct 覆盖。

其他约束先核对 §3.5 现有 Rule 语法；能完整表达才生成，不能表达的整项保留原文待补全，不扩充规则量化或类型系统。先建立角色、生成属性和关系的稳定对照，再按变量绑定改写原规则（RT-28、RT-31）。原多元读法不保留，导出按普通中间对象，不还原多元结构（RT-27）。

例：仓库.运往(终点仓库, 天数) ManyToOne，起点、终点仓库各有仓库编码。中间对象有起点仓库编码、终点仓库编码、天数，前两项构成标识，天数不参与；两条角色关系分别用对应编号 direct 连向仓库编码。同一仓库对的天数 2 与 5 不能作为两个不同元组存在。排班(医生, 日期, 科室) ManyToOne 的标识为医生编号加日期，科室缺标识只使科室编号待补全；医生缺标识则整个排班标识待补全。无基数的供货(供应商, 零件, 项目, 数量) 则四个角色表示都进入键。

[示例 03](core-1-examples/03-n-ary-reified.json)采用供货 ManyToOne，最后角色为数量，因此前三个实体编号组成标识；值角色数量继承的约束生成属性 Rule。



**d. 一元关系 → 布尔属性**。例：`customer` 上的 `{ "name": "is_vip", "verbalizes": ["{customer}是VIP"] }`
导入为属性 `customer.is_vip`，`value_kind=boolean`，名称“是VIP”。导出时按普通布尔属性导出，不还原成一元关系。

### 5.4 工作空间级约束和规则

- 文档 `requires`：`dropped`（RT-04）。
- 除 §5.5 的子概念成员派生定义外，各元素的 `requires` / `derived_by` → `rules`，无扩展时 display_name 为空，英文标识按 `constraint_1` 等生成；ZIP 从 rules 定位与 display_names 恢复英文标识、名称及描述。
- 元素变换和引用重写完成后，表达式里的引用能按 §3.5 的路径写法解析的导入；解析不了的（如 Ossie 角色写法 `Person.parent_of(descendant)`），本条报 error，不生成核心 Rule，原文、归属和定位保留待补全（RT-31）；对应已有定义不动，其他独立提案照常生成。
- 归属元素被 `dropped` 时，其规则一并 `dropped`。

### 5.5 数据映射

每个 semantic_model.datasets 条目一一登记为核心 Dataset，包括没有映射到对象、仅作关系表或用于数据集指标的数据集。name 保留原名，source 拆成 schema_name、table_name，description 保留；同名数据集跨 OntologyMap 冲突时以来源限定并按 RT-62 报 converted，不合并两个条目。方言仅从可确定的引擎信息或平台元数据补全，不能从 ANSI_SQL 猜 mysql；不明时保留为空并报告待补全。可表达的物理列进入可选列清单，逻辑 field 不升级成字段节点。任意 source query 无法表示为表位置时报告 error（RT-63），不静默丢数据集或把查询塞进表名。

OntologyMap 与 semantic_model 只是适配器作用域，不导入连接别名或模型树。建立外部 dataset → 核心 dataset id 对照后，下列对象、关系绑定均引用它。继承绑定必须符合 §3.2；外部独立子表与已绑定父对象冲突时保留继承定义和 Dataset，暂不接入子绑定并按 RT-65 报待补全，不能猜成父覆盖或虚拟父对象。

| 模式 | 判定及导入 |
|---|---|
| 单表对象 | 对象映射为 dataset.field，或一层 referent_mappings 对应完整 identify_by；source 拆 schema/table；主来源 id=`main`。key_columns 优先 dataset.primary_key；无声明时仅在对象身份字段是直接列且声明唯一时取该组列，否则为空并报告待补键，不擅猜数据库主键 |
| 多表同实体 | 单个主对象映射确定主 dataset，属于该对象的属性 children 可引用其他 dataset；每个属性来源到主 dataset 有唯一的声明唯一键星形连接，折叠为附表。多个 object_mappings 仅在同一主来源身份的等价写法时可规范化，否则 dropped，不猜成 union |
| 属性列、计算列 | link_mappings 根对应对象身份；一层 children 的属性映射指向 field。field.ANSI_SQL 为单列则 column，否则可解析为该对象来源的同行表达式则 expression；不支持的方言、跨对象、聚合、窗口、子查询 dropped（RT-43） |
| 直接关系 | 用业务 link_mapping 的 relationship、目标 concept 和身份字段联合物理 relationship.from_columns/to_columns 匹配；目标可为 unique 属性、完整标识（不必物理主键），能一一对应属性时为 direct |
| 映射表关系 | 独立映射表或某端来源表；source/target_columns 对齐各自 source_key/target_key。只存在物理连接而无法唯一定位业务关系时，仅该绑定 dropped（RT-53），业务关系仍保留 |
| 多对多 | 未映射概念的 dataset 有两条到两端唯一键的连接，且业务关系匹配唯一，转 mapping_table；不把关系表的重复配对当作已证明唯一 |

**列对齐**：先解析逻辑 field 到物理列，按被引用键的既定顺序重排 from_columns；to_columns 必须与该完整键同组、一一对应，不重复，不能只检查列数。例：目标 `[tenant_id, student_id]`、to `[student_id, tenant_id]`、from `[student_ref, tenant_ref]` 应变为 `[tenant_ref, student_ref]`。

**平台自导出固定形式**（RT-52）：每个核心 Dataset 一一输出为外部 dataset，名称使用数据集登记名，不按对象或 source_id 复制数据集。`concept_mappings` 保持一个主对象身份映射；`link_mappings` 根也使用主身份，平铺 children 分别引用各属性所属 dataset.field，不为附表重复创建对象身份映射。显式写附表到主表的等值物理 relationships（主、附表键均声明唯一）。这样主表由 object_mapping 的引用确定，不靠名字猜第一张表，业务标识与物理拼接键也不要求相同。读取时以属性 mapping 和唯一星形连接联合确认附表，缺少连接、声明键或有歧义则只丢该绑定，不能把属性来自另一个 dataset 就改成独立对象。来源 id 属局部名，外部格式允许规范化，完整保真仍用原生格式。这是适配器可识别子集，不是 Ossie 的原生多数据源对象 MDO（Multi-Datasource Objects，用于按列组合来源）定义。

计算表达式跨本对象多个来源时，Ossie field 没有本平台的“拼接后同行”作用域：可导出标量表达式，但不保证机械回读（RT-54）；平台自己导出的单来源同行表达式必须能够回读。主键和外键的辅助字段仅供键和 JOIN，不自动建属性；unique_keys 用于核实引用键和还原对应属性唯一性，未使用的键约束和逻辑 Field.dimension / label / datatype 按 RT-46 报损失。物理列清单可登记，但不声称保留所有逻辑 field 定义。

不支持的映射包括嵌套 referent_mappings、多层 children、身份不一致的多个 object_mappings、跨连接纵向合并、值概念映射和只有非 ANSI 方言的字段表达式。未支持的上下文和扩展逐项报告；能确定归属对象的 instructions 按 RT-59 合并到描述。指标表达式按 §5.6 保留，不沿用映射的丢弃规则。

#### 派生子概念与成员条件（RT-67）

Ossie derived concept 的成员从父范围导出，`Employee extends Person`、`derived_by: ["EXISTS (Person.earns)"]` 表示有薪酬关系的人。导入按 §3.2 转成 ObjectType.derived_by，不依赖父属性已有物理列绑定；简单条件用 conditions，复杂条件用 expression，保留分支并集、角色与方向，不重复生成普通 Rule。多层每层只保存自己的条件，extends 保持祖先逐级限定。

整份成员定义能够完整解析、绑定并等价输出时按 RT-67 converted。引用被裁掉的第二父、未承载关系派生、递归或未定义变量量化等无法闭合时，整项保留原文并 error 待补全，不导入残缺分支，不覆盖已有完整定义。语义已闭合但物理绑定缺失时仅问数未就绪，不把两类缺口混为一谈。

导出按 id 转回父概念有效属性与关系路径，保留所有分支及方向；无法完整输出时本项 error，不声称已无损转换。成员扩展来源及额外继承绑定的外部往返边界仍按 RT-57、RT-65 报告，不能因派生条件已转换就宣称绑定也已恢复。普通说明性 derivation Rule 不参与成员判定；若与对象成员定义不能在目标中区分，报告待补全，不能混写。

### 5.6 指标

只引用一个数据集且符合 §3.6 表达式边界的 OSI semantic_model.metrics 指标，与核心 Metric 一一对应，计算定义直接按该数据集的登记字段导入导出；不建立到本体对象或属性的映射。simple、ratio 是常见公式的可编辑写法，expression 承载其余本数据集算法。支持范围内保持算法与列引用，不承诺空白、大小写等原文格式。快照、time_field 和物理元数据等无同构字段的声明仍按 RT-60、RT-66 报告，不宣称完整核心模型无损往返。

导入统一使用 dataset_id，先检查全部字段的最终数据集来源及表达式边界。只引用一个数据集且没有 SELECT、FROM、JOIN 或额外查询作用域时才继续转换。超出该边界的 OSI 指标首版不承载：按 RT-69 本项 error，原文、完整片段、来源清单和材料定位保留在转换报告，completion_status=available，target_element_ids=[]，不形成残缺核心指标、不猜来源；用户可将其改写为本数据集指标后再提案，业务改写不称为等价转换。已有定义保持不动，其他独立提案照常处理。裸 COUNT(*) 没有列来源时保留原文与候选，待用户选择一个数据集；选定后转为该数据集的 simple count，导出沿用 §6.5 的行计数编译规范式，不根据对象绑定推测。

用 SQL AST 识别确定等价的固定形式。逻辑字段按其定义解析为登记数据集列，只改写已解析标识符并按 RT-47 报告，不改变运算、常量、分隔符或 NULL 行为。计算字段不能冒充物理列；不能按列结构化时保留 expression 及字段定义定位，待引用补全。列清单空或类型未知时待补全，不编造列或就绪 SQL。

| 外部表达式 | 导入结果 |
|---|---|
| SUM / AVG / MEDIAN / MIN / MAX(ds.f) | simple，measure 为 ds.f，MEDIAN 对应 median |
| COUNT(DISTINCT ds.f) | simple count_distinct，保持列去重及忽略 NULL（RT-50） |
| 上述五种聚合的单 WHEN、缺省或 NULL ELSE CASE | 条件为 AND 子集且全部引用同一数据集时拆为 measure、filters |
| COUNT(DISTINCT CASE WHEN 条件 THEN ds.f END) | 独立识别为 count_distinct 和固定过滤 |
| COUNT(CASE WHEN ds.f IS NULL THEN 1 ELSE 1 END) | simple count；两分支均为非空常量，等价行计数，不依赖 f 非空或唯一 |
| COUNT(CASE WHEN 固定条件 THEN CASE WHEN ds.f IS NULL THEN 1 ELSE 1 END END) | 固定条件属于同数据集 AND 子集时转 count 加 filters |
| 固定 CAST、NULLIF 比率 | 两侧对应已登记的同数据集数值型 simple 时复用其 id 转 ratio（RT-55）；否则保留一条 expression，不为一条外部指标额外生成分量指标 |
| 本数据集拼接复合去重、OR、ELSE 0、多个 WHEN、复杂函数 | expression，保持完整算法（RT-49、RT-56） |
| 裸 COUNT(*) | 选择来源后转 simple count，导出沿用 §6.5 的行计数编译规范式；不能凭对象键改成去重计数 |

COUNT(ds.f) 和 COUNT(CASE WHEN 条件 THEN ds.f END) 保留 expression，不能转行计数：两行列值为 NULL、10 时列计数为 1，行计数为 2。上表行计数规范形式须精确匹配两分支均为 1 的结构，不能扩大为所有 CASE COUNT。

所有导入指标同样遵守 §3.6 的单数据集边界，不能把不支持的算法直接放进 expression。原文留报告不等于核心承载。不创建 reference_bindings，不改成本体路径。非 ANSI 指标保留表达式及来源方言说明，不把未知方言标成 ANSI_SQL；引用未闭合时保留待补全，导出时报 error。字段类型不匹配仍按 D5 报告，不因此丢掉整条指标。

### 5.7 平台扩展文件

`ontofoundry-extension.json` 的 version=core-1，包含 rules、display_names、link_role_names、generated_link_readings、synonyms、tags、title_properties、required、unsupported。键使用对象 name、对象.name、metric:name 等英文路径。display_names 可包含关系。仅当 Ossie 原生位置不能放同义词时使用扩展 synonyms；Metric 等从 ai_context.synonyms 恢复。导入旧 ai_context.ontofoundry 块按同一字段读取并明确提示旧版扩展块。未导出清单保留损失定位，不承诺恢复未导出语义。

### 5.8 id

适配器按 `uuid5(workspace_id, "ossie:" + 键)` 生成确定性 id，键为 `object:{concept}`、`property:{concept}.{name}`、
`link:{concept}.{name}`、`reified:{concept}.{name}`、`reified-link:{concept}.{name}.{role}`、`rule:{归属键}:{kind}:{序号}`、
`mapping:{concept}`、`metric:{map}.{name}`。Dataset 键为 `dataset:{外部OntologyMap作用域}:{原dataset名}`，作用域优先唯一声明名，重复或缺失时用明确源定位或序号限定并报告消歧，不依赖临时核心名称后缀。生成编号属性键为 `reified-property:{原关系定位}:{角色定位}:{参与方标识属性定位}`；值角色属性用角色定位；实例化约束键为 `value-rule:{目标属性键}:{来源值类型定位}:{来源约束定位}`，不同来源不会共用 constraint_1 的身份。角色重排、复合列对齐先有稳定对照，不能靠显示名称串猜引用。合并到已有草稿时，平台按 §4.5 的英文标识匹配沿用已有 id。

---

## 6. Ossie 适配器：导出

交付 ZIP：一份通过 vendored 官方 schema 校验的纯 Ossie JSON，以及 ontofoundry-extension.json。不再输出 ai_context.ontofoundry；display_name 仅写 display_names；name 和 description 各自映射，互不拼接。支持 ai_context 的节点用规范 ai_context.synonyms；其他节点用扩展 synonyms。

### 6.1 文档层

| Ossie 字段 | 来源 |
|---|---|
| `version` | 固定 `0.2.0.dev0` |
| `name` | 工作空间名称 |
| `description` | 工作空间描述，空则不写 |
| `ai_context` | 只使用 schema 允许的规范字段，例如 synonyms；平台信息写独立扩展文件，见 §6.6 |
| `ontology` | 见 §6.2–6.4；模型没有任何业务对象时报 `error`（Ossie 要求至少 1 个组件） |
| `ontology_mappings` | 见 §6.5；没有映射则不写 |

### 6.2 业务对象和属性

| 核心 | Ossie |
|---|---|
| `ObjectType` | `EntityType` 组件：`concept = name`，`description`，`extends` = `[父对象英文标识]` 或省略；核心为单个 UUID，不是列表 |
| `identifier=true` 的属性 | 所属组件的 `identify_by` |
| 对象上的规则 | 组件的 requires 或说明性派生规则；ObjectType.derived_by 按 RT-67 输出成员定义，不混写冒充同一条件 |
| `Property` | 所属组件下的关系：`name = name`，`roles = [{concept: 值概念}]` |
| 值概念 | 普通属性直接引用内置类型（见下方“值类型翻译”）；标识属性生成一个 `ValueType`（`extends` 对应内置类型），名字按下方“生成名”规则分配 |
| 属性 `unique` | true 写 `OneToOne`，false 写 `ManyToOne` |
| 属性读法 | 生成 `{对象}的{属性名}是{值概念}` |
| `required`、`display_name`、`tags`、`title_property_id` | 写入独立扩展文件；标题转为属性英文标识 |
| `synonyms` | 支持 ai_context 的节点用 ai_context.synonyms；概念和本体关系使用扩展 synonyms |
| 属性上的规则 | 关系的 `requires` / `derived_by` |

**值类型翻译**：属性的 `value_kind` 对应 Ossie 内置值类型，导入导出按同一张表互译：

| `value_kind` | Ossie 内置类型 |
|---|---|
| `string` | `String` |
| `integer` | `Integer` |
| `decimal` | `Decimal` |
| `float` | `Float` |
| `boolean` | `Boolean` |
| `date` | `Date` |
| `datetime` | `DateTime` |

**生成名**：标识属性的值概念由适配器生成，名字不能和已有概念撞上：

1. 先预留所有对象的英文标识和 Ossie 内置概念名（`Any` 和上表七个），比较时忽略大小写。
2. 按“对象英文标识、属性英文标识”排序，依次为每个标识属性取候选名 `{对象}_{属性}_value`；已被占用就依次试 `_value_2`、`_value_3`……，取到即预留。
3. 关系的 `roles`、读法里的占位符一律使用分配到的名字。

**本期不支持**：业务对象的英文标识与 Ossie 内置概念同名（忽略大小写，如对象叫 `String`）。不做自动改名和还原：
导出时这种对象使 Ossie 官方校验失败，导出报错并指出是哪个对象，由用户改名后再导出。

例：对象 `customer_code_value` 已存在时，`customer.code` 的值概念名是 `customer_code_value_2`；`a_b.c` 与 `a.b_c` 都想用 `a_b_c_value`，
按排序 `a.b_c` 先取到，`a_b.c` 得到 `a_b_c_value_2`。顺序固定，同一模型每次导出的名字相同。

### 6.3 关系

| `multiplicity` | 写在谁下面 | `roles` | Ossie `multiplicity` |
|---|---|---|---|
| `many_to_one` | 源对象 | `[{concept: 目标}]` | `ManyToOne` |
| `one_to_one` | 源对象 | `[{concept: 目标}]` | `OneToOne` |
| `many_to_many` | 源对象 | `[{concept: 目标}]` | 不写（Ossie 中缺省即无唯一性约束） |

- 目标角色名写入 roles[0].name；自关联未填写时生成 related。源端角色名和精确空值由 link_role_names 扩展保留，生成占位符不回填为业务角色。详见角色名修订设计。
- 读法：完整 verbalizes 逐条机械转换稳定端点占位符，保留文本及顺序。空列表时输出最小关联句满足 Ossie 至少一条的要求，并由 generated_link_readings 扩展记录；原样重新导入恢复空列表，不将生成句持久化为业务定义。
- 关系上的规则 → 关系的 `requires` / `derived_by`。

### 6.4 规则

- 对象成员定义按 §5.5 的 RT-67 输出，不作为独立 Rule 重复输出。
- object_type、property、link_type 规则转对应 Ossie 元素的 requires 或 derived_by；由值类型约束实例化的规则导出到各属性关系的 requires，不恢复原 ValueType。
- 规则英文标识、名称和描述保存在独立扩展文件，rules 以归属英文路径、种类及数组位置定位原生匿名表达式。引用按 id 生成当前路径，不能把角色与方向丢失的文字当作等价规则；无法合法输出的本项报 error。
- 导出跑官方校验，但 schema 通过不证明规则语义等价。

### 6.5 数据映射和指标

**字段**：Ossie 的映射表达式和关系引用的是 dataset 的**逻辑字段名**，不是物理列名
（[Ossie 规范 · Object mappings](https://github.com/apache/ossie/blob/main/ontology/ontology.md#object-mappings)）。因此：

- 每个已映射属性在所属来源 dataset 中生成字段：字段名使用属性英文标识，column 绑定写物理列；expression 绑定写同行标量表达式（单来源去掉来源前缀，跨来源按 RT-54）。
- 主键列、外键列等**被键或 JOIN 用到、但没有属性映射到它的物理列**，声明为**辅助字段**：字段名 = 列名；
  与某个属性英文标识冲突时加后缀 `_col`（仍冲突再加序号）。辅助字段只为键和 JOIN 服务。
- 下文所有 `dataset.字段` 都指逻辑字段名。一个物理列由哪个字段代表，按“有属性映射用属性字段，否则用辅助字段”确定。

例：示例 01 的客户字段 `customer_no` 的 column 绑定为 `source_id=main, column=customer_id`，主键列 `customer_id` 由属性 `customer_no` 映射，
所以在示例 01 的 customers 数据集上，对象映射写 `customers.customer_no`；订单表的外键列 `customer_id` 没有属性映射，声明辅助字段 `customer_id`，
关系写 `from_columns: ["customer_id"]`。

**生成规则**：

- 每个核心 Dataset 恰好生成一个外部 dataset，包括未被本体引用的数据集；按服务端可确定的来源作用域组织 OntologyMap，不保存其原语法树。数据集使用登记名和描述，source 来自 schema_name 与 table_name，不再以对象英文标识命名或为共享绑定复制别名数据集（RT-62）。

**来源行键和业务标识分开处理**。核心模型不要求两者相同；来源键用于定位行，业务标识通过属性定义。

| Ossie 里 | 来自 | 说明 |
|---|---|---|
| dataset 的 `primary_key` | 可一致表达的来源行键 | 非快照来自 key_columns，快照历史键还包含本数据集的日期；不把时点内实体键当成历史整表主键 |
| 对象怎么被认出来（`object_mappings`、`link_mappings` 根节点） | 标识属性映射到的字段 | 业务标识，与 `identify_by` 一致 |

- 所有引用同一 Dataset 的对象、附表、关系和数据集指标共享同一个导出 dataset，fields 合并可表达的属性字段、键辅助字段及表达式需要的字段别名；无属性映射的登记列按单列字段输出，不自动变成本体属性。不同对象对同一物理列使用不同属性名时保留各自字段名；同一个字段名指向不同列时按稳定顺序加后缀并同步重写已解析引用，按 RT-40 报告，不覆盖字段。
- primary_key 来自可一致确定的非空来源键，快照数据集使用实体键加本数据集快照日期的完整历史键；同一 Dataset 的多个键声明冲突时不任取其一，省略该键并按 RT-64 报告依赖影响。附表星形连接只在键能合法表达时输出。
- ObjectType.derived_by 按 RT-67 输出父概念属性、关系路径，完整等价转换者报 converted。membership_source_id 成员扩展绑定和额外继承绑定按 RT-57 报损失；保留父子定义与全部 Dataset，不输出残缺条件或为子类复制 dataset。虚拟父对象无自己的 dataset，具体子对象可输出已绑定继承定义，多态并集约定按 RT-65 报告。

- 非快照数据集引用非主键 unique 属性时，可输出对应 dataset.unique_keys。快照时点内唯一不能当作历史全表唯一，完整历史键可由实体键和本数据集快照日期构成；不能据此自动给不同数据集的连接增加日期相等。时间选择、时点唯一性或连接无法按标准结构表达时按 RT-60、RT-64 报告，不伪造历史唯一键。
- 数据集引擎方言和元数据快照列类型未必有同构外部字段；能正确表达的照常输出，其余在 dataset 描述中说明并按 RT-66 报损失，不能从 ANSI_SQL 保证恢复引擎或元数据采集来源。
- `concept_mappings`：
  - 只有一个标识属性：`object_mappings` 为 `[{"expression": "dataset.标识属性字段"}]`。例如登记名为 persons 的数据集中写 `persons.id_card_no`，与 `identify_by: ["id_card_no"]` 一致。
  - 多个标识属性：`object_mappings` 为 `[{"referent_mappings": [...]}]`，每个标识属性一项，`relationship` 为该属性，`expression` 为它的字段。
  - 对象没有标识，或某个标识属性没有映射：认不出对象，该对象的 `concept_mappings` 报 `dropped`（dataset 照常导出，供连表和指标使用）。
  - `link_mappings` 根节点与 `object_mappings` 写法相同，`children` 每项 `relationship` 为属性英文标识、`expression` 指向该属性来源的 `dataset.属性英文标识`，允许附表来源（RT-52）。
- 直接属性关联或映射表恰为某一端来源表的外键关系 → `semantic_model.relationships` 一条，`from_columns` / `to_columns` 为对应字段名，
  多列时 `to_columns` 按被引用键（物理映射键或唯一属性组）的顺序、`from_columns` 按同样顺序（§5.5 列对齐规则）。这条只描述物理连接，同连接 且绑定完整时导出。
- 外键关系的业务子节点只有在引用列能表达目标完整业务标识时直接写出；目标仅是候选 unique 键时，保留物理连接及 unique_keys，业务链接映射不能凭空把编码改成 id，报 dropped。两者不能混称“绑定全部丢失”。
- 多对多 mapping_table 引用已输出的登记 dataset 并生成到两端引用键的物理 relationships；source_key/target_key 是 properties 时按该组顺序写，mapping_key 时按主来源 key_columns。业务 link_mappings 根与子节点同样需要两端完整业务标识可表达，否则只导出物理连接并报告业务映射缺失。
- 物理关系只在同一个 OntologyMap（同连接）内导出，跨连接只留本体关系定义并报绑定 dropped。平行边必须同时写对应业务 link_mapping 与精确列组以便 §5.5 匹配；缺少一一对应协议时不能承诺回读绑定。

**单个数据集上的指标一一导出**。每个核心 Metric 恰好输出一条 OSI semantic_model.metrics，不复制 Dataset，不创建辅助指标。simple 编译固定聚合与本数据集过滤；ratio 展开两个同数据集 simple 的完整公式；expression 保留算法、字面量与 NULL 行为，将已解析引用转换为同一登记 dataset.field（RT-47）；含 COUNT(*) 的表达式还可按下文等价规范化其中的行计数以保留来源。旧逻辑字段名可在同一 Dataset 内保留字段别名。导出前复查所有列及 time_field 均属于该指标数据集，且 expression 符合 §3.6；不合法核心输入报 RT-61 error，不交付伪有效文件，不从对象映射补连接。

| 指标 | OSI 表达式示意 |
|---|---|
| sum、avg、median、min、max | 对应函数，例如 SUM(orders.amount) |
| 带固定条件 | SUM(CASE WHEN orders.status='已完成' THEN orders.amount END) |
| count | COUNT(CASE WHEN orders.order_id IS NULL THEN 1 ELSE 1 END) |
| 带条件 count | COUNT(CASE WHEN orders.status='已完成' THEN CASE WHEN orders.order_id IS NULL THEN 1 ELSE 1 END END) |
| count_distinct | COUNT(DISTINCT orders.customer_id) |
| ratio | 各分量分别保留过滤，小数除法，零分母为空 |

count 的规范表达式通过任一登记列明确数据集来源，但不要求列唯一或非空；两分支均返回 1，保留 COUNT(*) 的行计数含义，不借业务对象键改算法。回读按 §5.6 精确识别。无列引用的 expression（包括原生输入）也必须在导出公式中保留 dataset_id 已声明的统计来源，不能直接输出无来源公式并算成功。含 COUNT(*) 的表达式可将其中的行计数等价规范化为上述带本数据集登记列的 COUNT(CASE WHEN … IS NULL THEN 1 ELSE 1 END)，保持其余算法、字面量与 NULL 行为，不创建辅助指标。没有可引用登记列、无法等价表达统计来源，或其他列、来源无法定位、引用无法合法输出时，按 RT-61 本项 error 待补全，保留核心定义；不静默丢指标，不交付缺少必需指标的文件。median 方言及小数类型由执行 agent 调整。

用户问题需要其他数据集的条件时，由 agent 在查询阶段沿本体关系组织筛选和连接；这些查询条件不写入指标，也不随指标导出。

**执行约定与逐指标报告（D6）**：只对实际涉及的情况附 RT-58 converted + warning：ratio 两个分量分别过滤、归周期并聚合后相除，零分母为空。算法、字面量和 NULL 行为必须保留，不为指标附加本体连接约定。

Ossie 没有快照字段。每个 Dataset 的 snapshot_date_column 和“各数据集独立取最新日或周期内末日，同一数据集所有行使用同一天”写入该 dataset 的 description；simple、expression 的时间字段写入指标描述。以上均按 RT-60 逐项列出结构化声明损失，保留原描述在前，不能宣称再导入能自动从说明文字恢复字段。

再导入按 §5.6 回读数据集列与算法；固定过滤、列去重、行计数及同数据集比率按固定形式识别，不能把列去重改成行计数。

### 6.6 平台扩展文件

交付 `qinglan.ossie.zip`，含 `qinglan.ossie.json`（纯 Ossie）和 `ontofoundry-extension.json`（如下）。

```json
{
  "version": "core-1",
  "display_names": {"sales_order":"订单", "sales_order.amount":"金额", "sales_order.customer":"购买客户"},
  "link_role_names": {"sales_order.customer":{"source_role_name":"订单", "target_role_name":"客户"}},
  "generated_link_readings": [],
  "synonyms": {"sales_order":["销售单"]},
  "tags": {"sales_order":["核心"]},
  "title_properties": {"sales_order":"order_no"},
  "required": ["sales_order.amount"],
  "unsupported": [{"source_path":"/material_objects", "construct":"material_objects", "message":"Ossie 不包含文档事实"}]
}
```

键一律用 name 英文路径（对象、对象.属性、对象.关系、metric:指标），不用 UUID。显示名不拼入 Ossie name/concept 或 description。Metric 等同义词放在规范 ai_context.synonyms，概念和本体关系无此原生位置才用扩展 synonyms。title_properties 解析为有效属性 id；规则英文标识及描述用 rules 关联匿名表达式，名称用 rule: 路径的 display_names；实例和证据不在扩展恢复，完整保留用原生完整包。旧 ai_context.ontofoundry 仅在导入接受，并报告“旧版扩展块”。

### 6.7 不导出

| 核心内容 | 原因 | 报告 |
|---|---|---|
| `evidence` | Ossie 无对应构造，且引用平台内部材料 | 不逐项报告，文档级说明一次 |
| `material_objects` / `material_links` | Ossie 没有实例数据 | `dropped` |
| 规则名、英文标识、描述 | Ossie 规则只有表达式 | ZIP 扩展 rules 与 display_names 恢复；单文件无法恢复 |
| 没有标识或标识属性未映射的对象的 `concept_mappings`；目标业务标识不能由引用列直接表达时的外键子节点；两端业务标识不能由映射表引用列表达时的多对多业务链接映射（物理连接照常导出） | | `dropped` |


Ossie 的必填字段优先从核心推导；无法推导或无法合法表达时按 §4.4 报 error，不交付无效文件。

### 6.8 校验

导出前检查目标格式可表达的最小结构：当前 Ossie ontology 数组要求至少一个元素。没有可导出本体元素时，包括只有数据集和指标的示例 13，导出报 error，不交付文件，也不为通过校验伪造对象；原生格式仍可完整保存。

每份可生成的导出都跑官方 schema 校验和现有语义校验（`ossie/validator.py`）。校验失败视为适配器 bug，报 error，不交付文件；目标格式已知无法表达的输入限制应在生成前报告。

---

## 7. 总表：Ossie 构造的支持情况

| Ossie 构造 | 导入 | 导出 |
|---|---|---|
| 文档 `version` / `name` / `description` | 校验 / 不读 / 不读 | 固定值 / 工作空间名称 / 工作空间描述 |
| 文档 `requires` | ❌ dropped | — |
| 文档 `ai_context` | 读取平台扩展文件；可确定归属的 instructions 并入对象描述（RT-59），其余 RT-02 | 规范 synonyms 写 ai_context；平台展示信息写扩展文件，说明写 description |
| EntityType | ✅ | ✅ |
| ValueType | 折叠基础类型并实例化可转换的有效 requires；独立值概念仍未承载 | 只为标识属性生成 |
| `extends`（实体 → 实体） | 首个实体父类；其余 RT-34 | 单元素列表 |
| `extends`（实体 → 值） | ❌ 输入 error（非法 Ossie 输入，不转换、不设计补全） | — |
| `identify_by`（全部成员是属性） | ✅，但不能改变已有父标识；子类自有首选标识按 RT-68 报损失 | ✅（只列有效核心标识属性） |
| 概念 / 关系的 `requires`、`derived_by` | requires 等转 Rule；子概念成员定义完整转换到 ObjectType.derived_by（RT-67），不重复建规则 | 规则按引用输出；成员定义按 RT-67 保留分支与路径，绑定例外 RT-57 |
| 属性型关系（实体 → 值） | ✅ | ✅ |
| 二元关系（实体 → 实体） | ✅ | ✅（三种基数） |
| 自关联 | ✅ | ✅（角色名 `related`） |
| 一元关系 | 🔁 布尔属性 | 不还原 |
| 多元关系 | 🔁 中间对象 | 不还原 |
| `identify_by` 含关系成员 | ❌ 整组标识不导入，报“标识待补全” | — |
| 值概念上的关系 | ❌ dropped | — |
| `roles[].name` | ❌ dropped | 只在自关联时生成 |
| `verbalizes` | 二元实体关系完整保留，转换端点占位符；属性读法仍按 RT-20 | 原文及顺序输出；空列表生成最小句并记录交换标记 |
| `multiplicity` | ✅（属性 → unique；合法多元 ManyToOne / 无基数按角色推导标识）；多元 OneToOne 为输入 error | ✅ |
| OntologyMap / SemanticModel | 只作适配器分组作用域，不建核心元素 | 按可确定来源作用域组织，RT-41 |
| Dataset（包括未被引用者） | ✅ 一一登记，无法表示表位置时报 RT-63 error | ✅ 一一输出，RT-62；快照声明按 RT-60 写描述 |
| Dataset 复合主键 | ✅ 有序键；对象身份可用一层 referent | ✅ |
| Dataset `unique_keys` | 引用键对应属性唯一性；其余 dropped | 被关系引用的候选唯一键 |
| Field（单列 ANSI 表达式） | ✅ | ✅ |
| Field 同行计算表达式 | ✅（§5.5 范围内） | ✅；跨来源作用域风险 RT-54 |
| 其他方言、`dimension`、`label`、`datatype` | ❌ dropped | — |
| OSI Relationship（外键） | ✅ → `data_join` | ✅ |
| 多对多 join 表 | ✅ | ✅ |
| `object_mappings`（单个、单列） | ✅ | ✅ |
| `link_mappings`（一层 children） | ✅ | ✅ |
| 一层 `referent_mappings`（对应 `identify_by`） | ✅ → 复合业务身份（物理键另取 primary_key） | ✅ |
| 多来源属性引用 | 主身份 + 属性来源 + 唯一键星形连接可折叠 | 一个主对象映射，children 引用来源字段 |
| 多个 object_mappings | 只接受同主来源等价身份的规范化，其他 dropped | 不生成多个对象身份映射 |
| 嵌套 referent、多层 children | ❌ dropped | — |
| Metric（单个 dataset 上的 SUM / AVG / MEDIAN / MIN / MAX / COUNT DISTINCT） | ✅ → 数据集列结构化指标 | ✅ |
| Metric 固定 CASE（SUM / AVG / MEDIAN / MIN / MAX，COUNT DISTINCT 独立处理）、行计数规范式、CAST-NULLIF 同数据集比率 | ✅ 按 §5.6；ratio 复用已登记分量，否则单条 expression | ✅，按 §6.5 报执行约定 |
| Metric 裸 COUNT(*) | 待用户选定来源后转 simple count（§5.6） | 按 §6.5 的行计数规范式保留来源；无法表达时 RT-61 error |
| Metric 其他本数据集表达式、拼接复合去重 | ✅ 本数据集 expression；来源或列引用不明时原文保留待补全，超出 §3.6 边界者按 RT-69 不承载，见下表 | 算法与统计来源保留，按 RT-47 转换已解析引用；含 COUNT(*) 的表达式可等价规范化行计数，无法合法输出时报 RT-61 error |
| 各处 `ai_context.instructions` | 能确定对应对象时并入 description（RT-59） | 不还原为独立 instructions |
| 其他 `ai_context`、`custom_extensions` | 未支持内容报 dropped | — |
| （平台）显示名、反向名称、同义词、标签、必填、标题属性 | 从扩展文件读 | 写入扩展文件 |
| （平台）规则名称与英文标识 | — | 写入独立扩展 rules 与 display_names，不进入纯 Ossie |
| （平台）证据、实例数据 | — | ❌ 不导出 |

✅ 支持　🔁 结构改写（报 `converted`）　❌ 不支持（报 `dropped`）

### 首版不承载的 Ossie 能力

下表是例外索引，细节以 §7.1 的 RT 为准。导入原文、完整片段和定位保存在材料及报告中；尚未进入核心的语义不能因材料留存而称无损。派生条件、元组标识、值类型约束已完整等价转换的条目不算语义损失，未转换个例列在对应行。

| 能力 | 未承载部分及方向 | 报告与原文处理 | RT |
|---|---|---|---|
| 多父继承、关系标识 | 导入仅首父；含关系的标识整组不导入，及相关继承引用 | 逐项报告，业务改写需审阅且不等价；原文留材料 | RT-30、RT-32、RT-34 |
| 子类自有首选属性标识 | 父对象已有标识时不能改选子类编号作为身份；依赖该身份且不能等价转换的映射 | 沿用父标识，子类单编号保留普通 unique 属性；原首选标识 dropped 并逐项报告、保留原文，不能转换的相关映射 error 待补全 | RT-68 |
| 文档级规则 | 导入没有工作空间规则归属 | dropped，不能擅改为单对象约束，原文供补全 | RT-04 |
| 独立值类型语义域 | 名称、共享身份、描述、未使用类型、祖先结构及 derived_by、identify_by、关系；未能实例化的 requires | 独立域 dropped；不能改写约束 error 待补全，成功的局部约束不算损失 | RT-23、RT-24、RT-35 |
| 未能解析的规则及成员派生 | 未定义角色变量、集合量化、递归及不闭合引用 | 整项 error，保留原文待补全，不生成残缺核心定义 | RT-31、RT-67 |
| 多元关系 | 原结构、读法不还原；缺完整构键角色、无法表达的额外元组约束 | 结构改写 converted，未转换约束或标识逐项待补全，原文保留 | RT-27、RT-28 |
| 一元及多值属性 | 一元转布尔不还原；无基数实体到值关系收窄为单值 | 报告结构或语义差异，原文保留；多电话号码不能称已完整保留 | RT-22、RT-26 |
| 读法、角色、通用端点 | 属性读法、属性/值角色名，值类型关系及 Any 端点 | dropped；角色参与表达式时先按绑定转换，不能转换的整项待补全 | RT-20、RT-21、RT-29 |
| 上下文及扩展 | 未归属说明、未承载上下文、非本期扩展及旧版本块；可归属 instructions 并入描述后不还原原字段 | 逐项报告，原片段保留 | RT-02、RT-03、RT-48、RT-59 |
| 映射表达范围 | 新独立 mapping documents、嵌套 referent、多层 children、非支持字段方言、值类型映射、歧义身份或业务边、多来源不能折叠、跨来源计算 | 不支持入口 error；绑定 dropped 或 error，任意查询来源 RT-63 error；保留定义、Dataset 及原文 | RT-43、RT-45、RT-52、RT-53、RT-54、RT-63 |
| 字段与物理元数据 | dimension、label、datatype、未使用 unique_keys、未承载逻辑字段及引擎元数据 | 报损失，说明文字不能自动恢复结构，原文保留 | RT-46、RT-66 |
| 成员、快照与继承绑定 | 成员扩展来源、多态并集、父覆盖不兼容子表、快照时间、时点键、跨期连接 | 逐项报告绑定及范围差异，不能因 derived_by 已转换而省略，原文保留 | RT-57、RT-60、RT-64、RT-65 |
| 指标 | 跨数据集（spanning datasets）的 OSI 指标，以及含子查询、显式连接或额外查询作用域的指标；来源/列未闭合、未承载时间和物理元数据 | 超出单数据集表达式边界者 RT-69 error，原文及来源清单保留报告并标待补全，用户可改写为单个数据集上的指标；其余逐项报告 | RT-47、RT-49、RT-50、RT-55、RT-56、RT-58、RT-60、RT-61、RT-66、RT-69 |

非法输入另行报告 error：多元 OneToOne、实体继承值类型均违反 Ossie 规范，不属于上表未承载的合法能力，不设计转换或补全分支。

反向边界另见 §6.6–6.7：核心的规则名和说明需要独立扩展；文档事实、证据及部分绑定不能由标准 Ossie 完整保存，完整备份使用原生格式。它们不属于 Ossie 导入能力缺口。

### 7.1 导入再导出的差异

Ossie 文件导入后再导出，**允许和原文件不同，但每一处不同都必须能归到下表的某条规则**。
规则编号 `RT-xx` 是固定的：Ossie 语义差异引用对应编号；通用解析、版本错误和原生缺证据等 rule_id 可为空，测试也按编号检查（§7.2）。

**文档层**

| 编号 | 差异 | 原文件 | 再导出 |
|---|---|---|---|
| RT-01 | 文档名称、描述换成工作空间的 | `"name": "library", "description": "图书馆"` | `"name": "<工作空间名称>", "description": "<工作空间描述>"` |
| RT-02 | 文档上下文没有明确对象归属时不自动分配；能够归属的 instructions 另按 RT-59 合并 | `{"synonyms": [...], "instructions": "...", "acme": {...}}` | `{"ontofoundry": {"version": "core-1", ...}}` |
| RT-03 | core-1 旧版扩展块仅导入兼容；不支持版本与字段报告 | 旧 version 或未承载内容 | dropped，原文留材料；只输出 core-1 命名扩展 |
| RT-04 | 文档级 `requires` 消失 | `"requires": ["COUNT(Customer) > 0"]` | 不出现 |

**格式规范化**（不改变含义）

| 编号 | 差异 | 原文件 | 再导出 |
|---|---|---|---|
| RT-10 | 数组按名称排序：`ontology` 组件、`relationships`、dataset、field（键和继承选择不按名称重排） | 原文顺序 | 值概念在前、实体在后，各自按名称排序 |
| RT-11 | 空值字段省略 | `"description": ""`、`"extends": []` | 不出现该字段 |
| RT-12 | 不合规的概念名、关系名被替换 | `"concept": "order-line"` | `"concept": "order_line"` |
| RT-13 | 列名的 SQL 引号规范化 | `orders."Amount"` 与 `orders.amount` 混用 | 只在需要时加引号 |

**概念和关系**

| 编号 | 差异 | 原文件 | 再导出 |
|---|---|---|---|
| RT-20 | 属性读法重新生成 | 属性的原始 verbalizes | 属性读法仍不独立存储；二元实体关系的完整文本、尾部、额外读法及顺序已保留，不再截取动词 |
| RT-21 | 属性/值角色独立名称暂不保存 | 属性或值角色的 roles[].name | 二元实体及重化实体角色已保存；值角色先按变量绑定保留可解析语义，无法转换的角色引用待补全 |
| RT-22 | 未写基数的实体到值关系收窄为单值属性 | 同一人可有多个电话链接 | 单个 Property 无法完整承载多值，明确报告损失 |
| RT-23 | 值概念被替换：属性改为引用内置类型，标识属性改为引用适配器生成的值概念（§6.2 生成名） | `"roles": [{"concept": "money"}]`，`money extends Decimal` | `"roles": [{"concept": "Decimal"}]`，`money` 不再出现 |
| RT-24 | 值类型有效 requires 实例化到使用属性；独立域的其他语义未承载 | 自身及祖先约束、多元值角色 | 能完整按变量绑定改写者 converted；不能转换的整条 error 待补全；未使用类型、描述、关系、identify_by、derived_by 等原文留材料 |
| RT-25 | （已并入 RT-23，编号保留不用） | | |
| RT-26 | 一元关系变成布尔属性 | `{"name": "is_vip", "verbalizes": ["{customer}是VIP"]}` | `{"name": "is_vip", "roles": [{"concept": "Boolean"}], "multiplicity": "ManyToOne", "verbalizes": ["{customer}的是VIP是{Boolean}"]}` |
| RT-27 | 多元关系重化且不还原 | 供货(供应商,零件,项目,数量) ManyToOne | 中间对象、编号属性和 direct 角色关系，前三角色组成标识，原结构与读法不还原 |
| RT-28 | 多元基数按角色元组生成标识，规则按角色绑定改写 | ManyToOne 除最后角色外决定最后角色；无基数全角色构键 | 完整者 converted；决定角色缺标识则整组待补全；最后角色缺标识不妨碍前项构键；其他无法表达约束 RT-31 |
| RT-29 | 合法但未承载的值概念关系、引用 `Any` 的关系 | | dropped，原文保留；实体继承值类型另按非法输入 error，不归入本项 |
| RT-30 | identify_by 引用无法进入核心的元素则整组待补全 | 标识中的某个二元属性类型不支持 | 不裁剪为较小键，原文和依赖原因留报告 |
| RT-31 | 无法完整解析的规则或成员定义保留原文待补全 | 未支持角色变量、递归或量化 | 本项 error，不生成非法核心规则或残缺成员定义；已有定义不动，独立提案继续 |
| RT-32 | 含关系成员的标识整组不导入 | 座位：`"identify_by": ["acct", "seat_nr"]`（`acct` 是关系） | 座位没有 `identify_by`；`seat_nr` 是普通属性，`acct` 是普通关系 |
| RT-33 | 单属性标识补上唯一性 | `identify_by: ["nr"]`，`nr` 的 `multiplicity` 为 `ManyToOne` 或未写 | `nr` 写成 `OneToOne` |
| RT-34 | 多父继承仅保留文件首父 | extends 多项 | 其余父类及不闭合引用逐项报告，原文保留；可建议派生条件或关系的业务改写，需审阅且不等价，不自动生成关系 |
| RT-35 | 不支持的值类型拒绝 | 找不到七种内置类型 | 属性及无法闭合依赖 dropped，不当字符串 |

**数据映射和指标**

| 编号 | 差异 | 原文件 | 再导出 |
|---|---|---|---|
| RT-40 | 字段按属性英文标识规范化，dataset 名按登记保留 | dataset ORD_T 的字段 AMT 映射到属性 amount | dataset 仍为 ORD_T，字段可为 amount；expression 所需旧字段名可在同一数据集内保留别名 |
| RT-41 | OntologyMap 和 semantic_model 分组及说明规范化 | 原 name / description | 按可确定来源作用域生成，不保存分组语法树 |
| RT-42 | （不再使用；dataset 描述由登记保留，快照说明追加按 RT-60） | | |
| RT-43 | 不支持的映射消失（§5.5 不支持清单） | 嵌套 referent、不支持的计算表达式等 | 不出现 |
| RT-44 | （不再使用；没有被本体引用的 dataset 也一一登记和输出） | | |
| RT-45 | 字段只保留 ANSI_SQL；指标非 ANSI 表达式保留并报告方言，不能误标 | `"dialects": [{"dialect": "ANSI_SQL", ...}, {"dialect": "SNOWFLAKE", ...}]` | 只有 `ANSI_SQL` |
| RT-46 | 字段的 `dimension`、`label`、`datatype`，未使用的 dataset unique_keys 丢失 | | 不出现 |
| RT-47 | 单个数据集内的指标登记字段引用规范化 | 同一数据集的逻辑字段或旧 dataset 名 | 仅重写解析后的列引用，保留算法、字面量和 NULL 行为；超出单数据集边界另按 RT-69 |
| RT-48 | 语义层未支持的上下文和扩展丢失；能够归属对象的 instructions 按 RT-59 合并 | | 不出现 |
| RT-49 | 单个数据集上的非固定形式指标转为 expression，报 converted；引用不明另报待补全 | `SUM(CASE WHEN ... THEN amount ELSE 0 END)` | 保持原算法；不涵盖 RT-69 不承载项 |
| RT-50 | 列去重保持列语义 | COUNT(DISTINCT ds.f) | 同数据集 count_distinct，不改成行计数，不依赖对象键 |
| RT-51 | 没有属性映射的键列、外键列以辅助字段出现，字段名 = 列名 | dataset 原有的字段名 | `{"name": "customer_id", "expression": …}` |
| RT-52 | 多来源按平铺协议改写 | 同实体星形多来源 | 一个主身份 + 跨来源属性 children + 唯一键星形连接；歧义绑定 dropped |
| RT-53 | 业务关系、物理连接匹配歧义 | 平行边、同表多对象无法唯一配对 | 只丢该绑定，不任取第一条 |
| RT-54 | 跨来源计算作用域风险 | 拼接后同行表达式 | 表达式可导出；回读不确定则 dropped，报告原文 |
| RT-55 | 固定过滤及同数据集比率规范化 | CASE、CAST/NULLIF | 分量已登记且同数据集时复用为 ratio，否则保留单条 expression；不额外造分量指标 |
| RT-56 | 拼接去重转 expression，不改变去重算法 | COUNT DISTINCT(a \|\| '::' \|\| b) | 保留原表达式，不再 dropped |
| RT-57 | 成员扩展来源及额外继承绑定无法机械往返 | membership_source_id、本地扩展绑定 | 派生定义可独立按 RT-67 转换；不等于外部已恢复扩展成员约束，逐项报告并保留全部 Dataset |
| RT-58 | 逐指标执行约定 | 同数据集比率分量的过滤与时间 | 保留指标，附 converted + warning，分别聚合后相除，零分母为空；不附指标连接约定 |
| RT-59 | 对象上下文说明并入 description，报 converted | 可确定归属的 `ai_context.instructions` | 原描述后附空行及说明；不再输出独立 instructions |
| RT-60 | 快照和指标时间字段无同构标准字段 | Dataset.snapshot_date_column、simple/expression 的 time_field | 快照写入对应 dataset 描述，其余写指标描述，逐项报告结构化声明损失，不自动回读 |
| RT-61 | 核心指标无法合法导出 | 来源/列未闭合、无可引用登记列、无列引用 expression 的已声明统计来源无法等价表达，或输入违反单数据集表达式边界 | 本项 error 待补全，核心保留，不交付必需指标缺项的文件；OSI 不承载项的导入另按 RT-69 |
| RT-62 | 数据集一一登记及名称冲突规范化 | 多个 OntologyMap 有同名 dataset | 每项各有核心 id，必要时限定名称；导出每个核心 Dataset 恰好一项，不按对象复制 |
| RT-63 | 数据集来源无法表示为表位置 | 任意 source query 或无法解析的来源 | error，不静默删数据集或冒充 table_name |
| RT-64 | 数据集键声明无法统一或时点唯一性无法按外部结构表达 | 同表键冲突、快照键与跨期连接 | 数据集保留，省略无法成立的键或物理连接并报告依赖影响，不强加日期相等 |
| RT-65 | 继承实例范围或绑定需补全 | 已绑定父对象与独立子表冲突，或虚拟父对象实例并集 | 导入冲突时保留定义和数据集、暂不接子绑定；导出说明虚拟父并集及继承绑定限制 |
| RT-66 | 来源引擎和物理元数据不能保证自动往返 | Dataset.dialect、元数据快照列类型及采集来源 | 无同构标准字段者写数据集描述并报告损失，不能从 ANSI_SQL 猜引擎或伪造元数据快照 |
| RT-67 | 成员派生定义按本体 id 转换 | 简单条件或关系 EXISTS，多分支并集、多层逐级限定 | 完整解析且等价输出者 converted；不能闭合的整项 RT-31 error 待补全，不取部分分支，不重复建 Rule |
| RT-68 | 子类首选属性标识不能改写已有父身份 | Person.person_no；Employee extends Person，identify_by 为 employee_no | Employee 沿用 person_no；employee_no 为普通 unique 属性，原首选标识 dropped，逐项报告且原文保留；依赖该标识且不能等价改写的映射 error 待补全 |
| RT-69 | OSI 指标超出单数据集表达式边界 | 引用多个数据集，或含 SELECT、FROM、JOIN、额外查询作用域 | 首版不承载；本项 error，原文、来源及定位保留转换报告并标待补全，不生成核心指标；用户可改写为单个数据集上的指标 |

**支持范围内保持不变的部分**：实体概念名（RT-12 除外）、实体继承（RT-34 除外）、实体描述（RT-59 合并说明除外）、属性和二元关系的名字与指向、二元关系的基数、
`identify_by`（RT-30、RT-32、RT-33、RT-68 除外）、可解析的规则表达式（RT-28 改写、RT-31 待补全、RT-67 转成员条件除外）、
dataset 的 source、登记名和描述（RT-62、RT-63、RT-60、RT-66 除外）、可一致表达的键（RT-64 除外）及物理列名。

### 7.2 让用户知道自己的文件哪里变了

不做“与原文件对比”的界面。用户看到的是：

1. **导入报告**：按文件逐项列出改写、丢弃及待补全条目；Ossie 语义差异标注 RT 编号，通用错误编号可空，记录可取得的原文路径与定位，原文件作为材料保存（§13.4）。
2. **规则表**（§7.1）：说明格式规范化这类全局差异（排序、空字段、读法重新生成等），不逐项列出。

**测试兜底**：每条适配器已支持 RT 至少有定向往返断言，随导入、导出交付；完整自动 `diff_roundtrip` 分类器可后补，只在测试里使用。对每份样例文件（含 A/B）执行“导入 → 导出 → 对比”，
断言**每一处差异都有 RT 编号**（RT-10 的排序差异不计）。出现无法归类的差异就是适配器 bug，测试失败。
新增 RT 规则必须同时更新 §7.1 的表格。

---

## 8. 存量数据：清空，不迁移

平台尚未正式就绪，现有的工作空间本体数据都是测试和演示数据，**不做迁移**：

- 上线 core-1 时用一个数据库迁移清空本体相关数据：草稿、已发布版本、提案、导入记录、元素身份表、建模会话中引用旧草稿的部分。
  工作空间、成员、材料、连接配置保留。
- 只读 core-1，不保留 v1 / v2 / v3 的任何读取或转换代码。
- 演示需要的数据，用新的 Ossie 适配器从样例文件重新导入。

这样第一部分不需要写任何兼容代码，`domain/legacy_v1.py`、`domain/snapshot.py` 中的版本转换、`models_v3.py` 可以直接删除。

---

## 8A. 界面结构

以下是用户已确认的内容结构，不规定像素、颜色或具体组件样式；标注“原型阶段确认”的项目仍需在原型中核对交互。

### 全局：分层概览

保留“全局”，一眼展示有哪些概念以及各有多少：对象、关系、指标、数据集、文档实例与材料、服务端点。不画连线，改用平台自己的立体分层表达，不沿用现有样式。点击某一层进入该层的具体内容，例如点击指标层，进入语义视图并筛选到指标。服务端点是平台服务入口的概览，不新增 core-1 元素集合。所有数量与内容均按权限展示。

### 语义视图：建模工作台

采用资源管理器加图，资源管理器包含对象、关系、指标、数据集四类，可筛选只看本体（对象和关系）、指标或数据集。指标不是本体元素，是与其并列的一类语义元素；关系图里不画指标节点。

点击元素打开对应弹窗，对象、关系、指标、数据集各有弹窗。指标在语义视图中查看；指标弹窗展示描述、同义词、数据集、算法、列、条件或 expression 全文、时间及授权 SQL 参考，不显示对象归属。ratio 展示分量数据集及各自时间口径。对象弹窗或详情是否按绑定推导展示“相关指标”，由工程实施和原型阶段决定，不在模型中存储或承诺入口。expression 能通过预览编译时展示参考 SQL，否则解释原因，不编造 SQL。

**新建指标（原型阶段确认）**

**数据集与算法。** 在语义视图筛选“指标”后使用“新建指标”。表单包含名称、同义词、数据集选择、计算方式、列、条件、SQL 参考和数值预览。数据集选择后按其说明展示“一行 = 一张订单”或“一行 = 一个代码仓库一天的统计”，只列登记列。计算方式含计数、求和、平均、最大、最小、去重计数、中位数、比率、写表达式；ratio 选择同数据集的两个 simple，expression 也只能从所选数据集的列中选择。

**时间。** simple、expression 的时间字段只列可引用的日期类列，含快照日期列，可以不选；simple、expression 均只列所选数据集的日期类列。ratio 不显示时间选择框，分别展示分量时间口径；改变口径就换相应分量。快照选行由数据集声明决定。

**维度。** 不另存可切分维度清单；表单只使用所选数据集登记列。用户问题涉及其他数据集的分组或筛选时由 agent 在查询阶段沿本体关系组织，不写入指标。

**预览。** 平台使用当前完整表单、ratio 分量、授权数据集及时间范围，编译并展示参考 SQL，使用数据集对应的已登记连接只读执行，不经过 DataAgent。有时间字段时再按月执行小趋势，ratio 分量各自归月。公式无法在支持的引擎中执行时显示“无法预览”及原因。预览不写模型，表单变更须重新执行，不能复用旧定义结果。

复用 `apps/api/src/ontofoundry_api/services/metric_query.py` 的编译、sqlglot 白名单检查和只读执行能力，改写为接受尚未保存的 core-1 完整定义；连接与权限沿用 `instance_query.py` 所用的路径及映射、实例读取权限。复用的是执行能力，不是实例分页明细；不能分页拉取实例再由前端聚合。表达式未通过白名单、引擎不支持、缺来源绑定或登记连接、列清单待补全、权限不足、查询失败时显示“无法预览”及原因，不伪造数值；不支持预览不等于否定已通过引用校验的 expression 语义。MCP 仍只提供语义和参考，agent 答题时自己写 SQL；平台表单自查预览是独立的界面能力，不增加 MCP 执行工具。

也可在本体构建中让 AI 产出相同指标提案，复用审阅与接受流程。

规则不作为资源管理器单独一类，在对象或关系弹窗中查看；这是“原型阶段确认”项。属性规则可在对象的属性上下文查看，不改变核心中的归属。

### 数据映射页

去掉“语义模型”标签。“数据源与资产”改名为“数据集”。数据集展示已登记的表或视图、快照日期列和说明，通过“浏览数据目录”登记新数据集；这部分标为“原型阶段确认”。“本体映射”标签保留为全部绑定总览，也标为“原型阶段确认”。两个入口引用同一份 Dataset 登记与核心绑定，不产生平行模型。

**数据集引用计数（后续功能，原型阶段确认）**：数据集页面分开显示“被 N 个对象、K 个关系、M 个指标引用”，三类可分别展开查看引用者。N 从对象绑定 DataMapping 的主来源、附表、成员扩展来源推导，按对象 type_id 去重；同一对象通过多个来源引用同一数据集时只计一次。K 从关系绑定中用作映射表的数据集推导（含继承关系的本地绑定），按关系 id 去重；同一关系在多个本地绑定中引用同一数据集时只计一次，不计入 N。M 从指标的 dataset_id 推导，ratio 沿用从两个 simple 分量解析 dataset_id 的规则，按指标 id 去重，ratio 本身也计为一个指标。数量与列表均按现有权限展示，从当前绑定和指标定义实时推导，不新增模型字段。

### 展示原则

真实内容不藏在 ⓘ 中，没有“高级”入口。上述设计原则用于指导产品实现，不作为界面文案展示。

---

## 9. 实施：分三部分

### 第一部分：核心模型、增删改查、MCP

目标：平台内部全部切到核心模型，建模、编辑、发布、问数都能用。

| 内容 | 说明 |
|---|---|
| 核心模型 core-1 | §3 的全部元素和校验：二元关系、`unique`、`synonyms`、关系 name/verbalizes 与两端角色名、复合主键、新 `data_join`、扁平数据集登记、多来源和计算列、三种继承建法、实例标题、描述合并、结构化及表达式指标、数据集快照与 simple、expression 的时间字段、成员派生的路径与引用检查 |
| 清空数据 | 数据库迁移清空本体相关数据（§8） |
| 增删改查 | 提案、草稿、合并、发布、元素编辑全部基于核心模型；前端删除角色、读法编辑器，增加反向名称、同义词、指标表单和数据集登记编辑，主附表、关系表统一选择 dataset；页面和弹窗结构遵守 §8A |
| 查询 | 实例浏览按新 `data_join` 生成 JOIN（含多对多 join 表、复合主键）；结构化指标提供基础 SQL 参考（改写 `metric_query.py`），完整查询由 agent 组装；父绑定完整覆盖、虚拟父实例并集及成员扩展表同时验收 |
| 指标数值预览 | 平台以当前表单完整定义和时间范围编译并展示同一份参考 SQL，经 sqlglot 白名单后，使用已登记连接只读执行总值，有时间字段时再按月执行小趋势；复用 metric_query.py 的编译与执行能力及 instance_query.py 的连接、权限路径，支持数据集指标，失败显示“无法预览”及原因，不经过 DataAgent，不使用实例分页聚合（§8A） |
| MCP | 精简为 4 个工具；`get_ontology` 返回授权物理绑定、结构化指标或 expression；绑定就绪的结构化指标可附基础 SQL 参考，授权 Dataset 提供方言与 database/schema，虚拟父列出实例来源（§14） |
| AI 建模 | 技能 `md2ossie` 改写为 `ontofoundry-modeling`；轮次提示词精简；提案合同 `target_kind` 调整（§13.3） |
| 问数 agent | 系统提示词按 §14.4 重写 |
| 删除旧代码 | v1 / v2 / v3 模型与转换、`ossie/native.py`、`ossie/extensions.py` 等（§11） |

现有的 Ossie 导入、导出依赖旧模型，第一部分期间在界面上**暂时下线**，由第二、三部分重新提供。

验收：在界面和 AI 建模里建出示例 01–08 及新增绑定示例的模型并发布；演示空间的问数示例全部答对，聚合在一次 SQL 内完成；
`domain/` 不 import 任何适配器。

### 第二部分：导入

| 内容 | 说明 |
|---|---|
| 适配器接口 | 只需导入函数：文件 → 核心模型与转换报告（§4.1、§4.2） |
| Ossie 导入 | 概念、属性、二元关系、值概念折叠、一元 / 多元转换、规则、扩展文件及旧块导入兼容（§5.1–5.4、§5.7）；映射：Dataset 一一登记（含未引用者）、对象、属性列、外键、多对多映射表、复合键、多来源、计算列、唯一属性键、派生子概念成员条件互译及继承绑定冲突报告（§5.5）；指标只引用自己的数据集，固定聚合、CASE 过滤和同数据集比率按列结构化，其余本数据集算法保留 expression；超出边界按 RT-69 留报告待补全（§5.6） |
| 导入走提案 | 新建会话、按英文标识对比生成提案、复用提案面板和发布（§4.5）；只新增和修改，从不生成 delete 提案，转换失败条目保留原文等待补全；原文件保存为材料，提案证据指向原文行号 |
| 导入报告 | 按条目列出改写和丢弃，标注 RT 编号、原文路径、行号 |
| 原生格式导入 | 单文件形式（§4.6） |

验收：Ossie 样例 A/B 可机械导入支持子集，原生示例逐个导入（见 README 矩阵）；导入报告做快照，固定 CASE、行计数与比率算法必须回读；比率无已登记分量时保留一条 expression，复杂指标原文必须保留；RT-69 不承载项不形成核心指标。AI 补全另期验收，不混作机械导入成果。

### 第三部分：导出

| 内容 | 说明 |
|---|---|
| 适配器接口 | 导出函数：核心模型 → 文件 + 转换报告 |
| Ossie 导出 | 概念、属性、关系、规则、扩展文件（§6.1–6.4、§6.6）；映射：Dataset 一一输出、逻辑与辅助字段、计算字段、多来源属性、复合键、唯一属性外键、多对多映射表，快照说明写入数据集描述、RT-67 可完整转换的派生子概念；单个数据集上的指标与 OSI 一一对应，按本数据集登记列编译，expression 保留算法、作用域和引用，检查合法性（§6.5） |
| 官方校验 | 每份导出跑 Ossie 官方 schema 和语义校验，不通过不交付（§6.8） |
| 原生格式导出 | 单文件形式（§4.6） |

验收：README 矩阵的可导出示例文件通过官方校验；09 空模型稳定 error，不交付文件；导出报告列出损失和逐指标执行约定；
核心模型 → Ossie → 核心模型：单个数据集上的指标按本数据集列与算法一一转换；ratio 若没有可复用的已登记分量则回读为一条 expression，不制造额外指标。未能确定统计数据集时留待用户选择；快照、时间字段及其他不支持的内容按报告与 RT 说明，不承诺完整模型无损。

### 以后的扩展（不在三部分之内）

设计已经写清楚，等有需求再做：

| 项目 | 设计位置 | 什么时候做 |
|---|---|---|
| 数据集引用计数与引用者展开列表 | §8A | 后续功能，原型阶段确认；分开显示“被 N 个对象、K 个关系、M 个指标引用”，三类可分别展开。N 从主来源、附表、成员扩展来源按对象 type_id 去重，K 从映射表数据集（含继承关系的本地绑定）按关系 id 去重，M 从指标 dataset_id（ratio 从分量解析）按指标 id 去重；实时推导，不新增字段，不在上述三部分交付内 |
| 原生格式完整包（打包材料、跨环境搬迁） | §4.6 | 出现跨环境搬迁需求时；之前备份靠数据库备份 |
| 完整往返 diff 分类器 | §7.2 | 全自动分类可后补；每个已支持 RT 的最小定向往返回归与适配器同时交付 |
| 导入后的 AI 补全 | §13.4 | 第二部分跑通、看到真实导入会丢什么之后 |
| 适配器注册表、格式自动识别 | §4.1、§4.3 | 有了第二个适配器时 |

---

## 10. 已确认的决定

下表是已确认决定的汇总，包含数据集、快照、继承与界面结构；执行细节交给 agent。

| 编号 | 事项 | 一句话结论与章节 |
|---|---|---|
| 1 | 指标形式 | 指标独立寻址，常见口径用 simple（含 median）或 ratio，复杂口径用 expression，固定形式之外的 Ossie 指标原文保留（§3.6、§5.6） |
| 2 | 关系标识、角色与读法 | 2026-10-19：name 为唯一关系标识，保留 source_role_name / target_role_name 及完整 verbalizes，删除关系 name/inverse_name 的重复职责；2026-10-20：旧本体内容清理，不保留数据库读取兼容，旧外部文件在导入边界转换 |
| 3 | 复合键 | 支持有序复合来源键、关系列组及由属性构成的复合标识（§3.4、§3.7、§5.5、§6.5） |
| 4 | 导出名称 | Ossie 文档名称取工作空间名称（§6.1） |
| 5 | 存量数据 | 清空测试本体数据，不迁移旧模型，保留工作空间、成员、材料和连接配置（§8） |
| 6 | 材料实例 | 保留材料对象与二元材料链接，用于文档事实和后续实例图谱（§3.1、§14.2） |
| 7 | 工作空间约束 | 删除 ontology_requires，规则必须归属具体元素，外部文档级约束按 RT-04 报损失（§3.5、§5.4） |
| 8 | 文件导入 | 生成提案并复用建模会话、草稿和发布流程，空工作空间同样如此（§4.5） |
| 9 | 关系基数 | 只保留一对一、多对一、多对多，一对多用反向读法表达（§3.4） |
| 10 | 属性唯一性 | 属性基数改为 unique，时点业务唯一性不冒充历史整表唯一性（§3.3、§3.7） |
| 11 | 值概念 | 删除 value_concept，只留七类型；自身及祖先可改写 requires 按变量绑定实例化到每个使用属性，含多元值角色；不恢复独立域或自动联动，不能改写者原文待补全（§5.2） |
| 12 | 平台信息与备份 | Ossie 独立扩展文件只放显示名、同义词、标签、必填、标题、两端角色名及生成读法标记；完整保留用含材料的原生包（§4.6、§6.6） |
| 13 | 文件对比 | 不做原文件对比界面，差异由转换报告和 RT 规则说明，自动对比只用于测试（§7.2） |
| 14 | 规则 | 规则采用受限 SQL 表达式与本体路径，保存 id 依赖并在改名时同步更新（§3.5） |
| 15 | 同义词 | 对象、属性、关系、指标均有 synonyms（§3.2–§3.6） |
| 16 | 数据集 | 新增轻量扁平 datasets 登记，主附表、关系映射表、数据集指标统一引用 dataset id，Ossie 数据集一一对应，不恢复语义模型树（§3.7、§5.5、§6.5） |
| 17 | MCP 路由与版本 | MCP 从授权数据集给出方言和 database/schema，各层无 connection_alias，四工具无 version_id 入参，建模固定服务端 pinned_version_id，问数取当前发布版本（§14） |
| 18 | 实施顺序 | 先核心模型、编辑和 MCP，再导入、导出，完整包等后续扩展按需交付，最低 RT 回归随适配器交付（§9） |
| 19 | 定义分离 | 对象、属性、标识、关系分开定义，外键列可建属性，关系不参与标识（§3.1、§3.9） |
| 20 | 内置名冲突 | 对象与 Ossie 内置概念同名时本期导出报错，不自动改名（§6.2） |
| 21 | 上下文说明 | 上下文说明并入 description，导入按 RT-59 转换，不新增 instructions 或前端独立入口（§3.2、§5.1、§11） |
| 22 | 已计算比率列 | 覆盖率等逐行比率作为属性，总体比率须有分子分母，不能直接求和或平均（§3.6） |
| 23 | 反向一对一路径 | **已被第 17 轮取代**。 指标允许正向多对一、一对一及反向一对一，按声明基数提示风险而不执行基数检查（§3.6） |
| 24 | 关系引用唯一属性 | 关系可连单个 unique 属性或完整标识，无须限定为物理主键（§3.4） |
| 25 | 实例标题 | 删除 MaterialObject.name，文档事实按标题属性、完整标识、可见 quote 开头、UUID 推导只读 display_text；0 和 false 有值，搜索覆盖显示与属性值；数据库仍可回退物理键（§3.2） |
| 26 | 权限裁剪 | 元数据、数据集、SQL、表达式和嵌套提示统一按映射读取权限裁剪，事实及证据按实例权限裁剪（§14.3） |
| 27 | 界面结构 | 全局采用无连线的立体分层概览；语义工作台列对象、关系、指标、数据集，关系图不画指标；数据映射页改用数据集登记与全部绑定总览，原型确认项见 §8A |
| 28 | 指标统计对象 | **指标关联部分已被第 17 轮取代**。 simple、expression 显式二选一保存 base；ratio 仅从同统计对象的 simple 分量推导，避免重复状态；缺分量或不一致拒绝，不能反查对象（§3.6） |
| 29 | Ossie 指标导入 | **已被第 17 轮取代**。 一律挂数据集，按列结构化或保留 expression；改挂对象由用户/AI 提案并确认（§5.6） |
| 30 | 指标依赖变化 | **已被第 17 轮取代**。 改名按 id 重建显示；删引用、改基数及数据集删除按依赖组处理；区分语义和范围保持的物理换绑与可能改含义、成员或时间范围的变更，后者沿继承、派生、ratio 列出影响指标；不扫描证明等价（§3.6） |
| 31 | 指标交互 | **指标关联部分已被第 17 轮取代**。 对象弹窗无指标入口，指标只在语义视图筛选；新建表单使用“统计对象”，simple、expression 可选时间字段，ratio 展示两个分量的时间口径；维度由对象路径或数据集列决定，平台编译参考 SQL 并只读执行数值预览，不经过 DataAgent，标原型阶段确认（§8A） |
| 32 | 删除预聚合提示 | 第 10 轮删除 Metric.pre_aggregations 与 PreAggregationHint（含 dimensions 的 path / column_reference 形式）。它属于执行优化而非语义，Ossie 没有此概念，原设计源自 Cube 的 pre_aggregations，首版删除。汇总表登记成数据集，直接在其上建数据集指标；查询时用不用汇总表由 agent 决定（§3.6） |
| 33 | 删除导入替换模式 | 第 10 轮删除“以文件为准”模式及 source_inventory 源身份清单、保留集合、权威删除范围、删除依赖组和 total_rows 防误删验收。判断“文件确实缺席”不可靠且复杂，首版删除。平台导入只新增和修改，从不生成 delete 提案；要删除就在会话里手动操作，或让 agent 提删除提案并走正常审阅。转换失败条目仍保留原文，等待 AI 补全或用户选择（§4.5） |
| D1 | 主附表 | 同连接主表决定实例集合，附表按声明唯一键横向补属性，每属性明示来源，普通纵向映射与联邦延期（§3.7） |
| D2a | 可排序快照日期列 | 来源：用户 2026-10-23 确认。沿用已有快照语义，允许日期类或可按日期排序的文本/整数列，未知类型仍可登记；不新增字段或模式。原值 `MAX` 支持虚构的组件每日全量表以 `2026-10-23` 或 `20261023` 分区，避免实例与指标总值读取全部历史。格式转换属于执行细节，平台不推断；非日期类快照列不能直接作为月趋势时间字段。取消此支持会使这类全量表无法声明快照（§3.7） |
| D2 | 快照与期末 | 第 9 轮推翻原“指标可覆盖”的决定，删除 non_additive_over_time；快照只在数据集上声明，simple、expression 可选 time_field，ratio 不存该字段而使用两分量各自时间字段。快照数据集（声明了 snapshot_date_column）每个周期取最后一个有数据的日期，其他数据集取周期内全部行；然后按指标自身算法在整个范围上重新计算，去重、均值、比率等不把每日结果相加。各数据集独立选日，同一数据集所有行用同一天，普通主表与快照附表各按自身声明处理；事件列拆到每日增量表，实例浏览默认取最新一天（§3.6、§3.7） |
| D3 | 继承三种建法 | 选择覆盖全部子实例的父绑定、无绑定虚拟父对象的实例并集，或两个独立对象，禁止父表之外另存独立子实例（§3.2） |
| D3b | 继承定义与绑定 | 继承全部属性、普通关系和规则，成员定义放 ObjectType.derived_by，分支取并集，每层限定父范围；同时有扩展表还须取交集；有绑定父对象的子类用派生条件或扩展表，虚拟父的具体子类可绑定继承定义，不重复创建父关系（§3.2、§3.7） |
| D4 | 派生属性 | 派生属性是本对象来源上的同行计算列，平台只校验引用，MCP 将表达式交给 agent（§3.7） |
| D5 | 类型 | 仅用七种内置语义类型，不新增单位、精度、时区或复杂值，不支持类型须报告而非默转字符串（§3.3） |
| D6 | 指标导出 | **指标关联部分已被第 17 轮取代**。 能表达的指标照常导出，连接、空值和比率分量风险逐指标报告；expression 同样检查角色、方向及范围，不能保留时报本项 error，避免算法未变而统计含义已变（§6.5） |
| 34 | Ossie 语义基准 | 尽量无损保留 Ossie 语义，未承载能力集中列 §7；派生定义、元组标识、值类型约束仅成功完整转换的具体条目按 converted，其余原文待补全，避免夸大能力 |
| 35 | 单父与属性标识 | 保留文件首父，其他父类及影响逐项报告；派生条件或关系仅是需审阅的业务改写建议，不等价、不自动生成关系；含关系的 identify_by 整组待补全，避免改变身份（§5.2） |
| 36 | 多元关系标识 | 按基数确定构键角色，复合标识逐项生成 required 编号属性；角色 direct 使用同组编号，不另加一致性规则；仅有对应证据才绑外键，否则保留原角色映射并待补编号绑定，缺决定角色标识不裁剪键（§5.3） |
| 37 | 删除业务动作 | 首版删除 actions、Action、参数、效果、precondition_rule_ids 及 owner_kind=action 规则。只有定义没有执行器，本期先做建模问数；原参考是 Palantir Action Type，Ossie 与本次核对的 Fabric 本体定义协议没有对应构造，待做执行时完整设计。沿第 5 项清空，不做 v2 迁移或迁移报告 |
| 38 | 派生成员定义 | 删除 row_filter，改为 ObjectType.derived_by；simple 条件与 expression 互斥，空数组无本层条件，多项为并集，多层逐级限定并与成员扩展来源同时限定。按 id 保留角色方向和 EXISTS，普通 Rule 不参与成员定义（§3.2、§5.5） |
| 39 | 精简重复字段与限制 | 删除 DataMapping.primary_source_id，independent 固定 main、shared_parent 沿父；simple、ratio.value_kind 只读推导、输入不收，expression 仍声明类型；删除固定 DECIMAL(38,10) 和 SQL 保留字禁用，精度和引号交给 agent（§3.6–3.9） |
| 40 | 报告与补全 | 删除 placeholder outcome 及占位串机制，仅 converted、dropped、error；删持久化 blocked，按实际依赖实时算阻断，保留原文与历史报告；通用解析、版本和原生证据错误 rule_id 可空，避免假编号（§4.2–4.5） |
| 41 | 导出角色与匹配 | **指标关联部分已被第 17 轮取代**。 expression 也检查角色、方向、统计范围，买卖角色被合并时报本项 error；映射在对象 id 重写后按 type_id 一对一匹配，事实、链接、证据仅 UUID；补 Dataset、生成编号及约束 UUID5 键，避免身份漂移（§4.5、§5.8、§6.5） |
| 42 | 阅读顺序 | 指标概念页先给三行输入数据再给计算结果，便于核对，业务口径不变 |
| 43 | 第 15 轮：完整指标范围 | **指标关联部分已被第 17 轮取代**。 所有对象指标先检查主来源、全部派生成员条件、成员扩展及路径子类范围；按实际绑定判断主来源锚点，等价写入聚合才导出，不能时 RT-61 结构化 dropped、expression error；示例 11 金额 dropped（§6.5、§14.6） |
| 44 | 第 15 轮：继承标识 | 父已有标识则子沿用；子类自有首选编号保留普通 unique 属性，原首选标识损失及不能转换的映射逐项报告、原文留存，列 RT-68（§5.2、§7） |
| 45 | 第 15 轮：多元与非法输入 | 建模指引采用 §5.3 的完整角色构键规则，含值角色和实体完整标识，事件按实际身份建键；多元 OneToOne、实体继承值类型均输入 error，不设计转换或补全（§5.2–5.3、§13.3） |
| 46 | 第 15 轮：CASE 与示例精简 | CASE 结构化只限 SUM、AVG、MEDIAN、MIN、MAX，COUNT DISTINCT 独立处理，COUNT 可空列保留 expression；示例 08 客户等级仅留计算绑定，删除重复 Rule；标识页删除旧调用载荷，概念图删除残边，映射说明更新锚点（§5.6） |
| 47 | 第 15 轮：文档事实审阅与读取 | 不同文档各提新建；同类型同完整业务标识只提示重复，由人选择都接受、只接受一条或改更新追加证据；读取按已接受 UUID，继承展开只对同 UUID 去重，业务实体数另按业务标识统计（§4.5、§14.2–14.3） |
| 48 | 第 17 轮：指标只挂数据集 | 推翻原“统计对象可选业务对象”、对象路径与附带依赖及导出检查。simple、expression 只存 dataset_id，ratio 分量须同数据集。**第 17、18 轮允许跨数据集 expression、由本体绑定推出连接、同一数据集多角色显式连接及保留导入子查询的部分，均被第 19 轮第 49 项取代**。对象详情是否按绑定推导展示相关指标仍由工程和原型决定（§3.6、§8A、§12） |
| 49 | 第 19 轮：指标只引用单个数据集 | simple、ratio、expression 一律只引用自己的 dataset_id 所指数据集的列；expression 不允许子查询或显式连接。模型没有数据集之间的关系，指标与本体及本体关系完全无关，从本体推连接会重新耦合。跨数据集条件不建指标，例如仅定义订单金额，华东地区由 agent 查询时沿本体关系筛选。Ossie 单数据集指标一一导入导出，跨数据集或额外查询作用域首版不承载，按 RT-69 原文留报告待补全，可由用户改写为单个数据集上的指标。对照 dbt 在一个语义模型上定义指标、Snowflake 指标聚合同一逻辑表的列、Fabric 按定义所在表在实体下展示；不引入数据集级关系，不让指标引用本体（§3.6、§3.9、§5.6、§6.5、§7、§8A、§14）。2026-10-20 补充：跨表口径通过基于表达式的数据集承载，指标仍只引用单个数据集，见 [数据集两种来源](2026-10-20-dataset-sources.md) |
| 50 | 第 20 轮：指标措辞统一为单个数据集 | 数据集是登记单位，背后可以是表或视图，指标只引用单个数据集的列，不关心其物理形态。主设计、概念页、示例说明及第 49 项统一采用单数据集边界措辞；表达式与导入导出边界不变，确指物理表的映射说明保留（§3.6、§3.7、§5.6、§6.5） |
| 51 | 第 20 轮：数据集引用计数（第 22 轮修正口径） | 后续功能，原型阶段确认。数据集页分开显示“被 N 个对象、K 个关系、M 个指标引用”，三类可分别展开。N 从对象绑定的主来源、附表、成员扩展来源按对象 type_id 去重，K 从关系绑定的映射表数据集（含继承关系的本地绑定）按关系 id 去重，M 从指标 dataset_id 按指标 id 去重；ratio 从分量解析数据集，自身也计一个指标。实时推导，不新增模型字段，列为后续交付项（§8A、§9） |
| 边界 | 只给语义 | SQL、日期不齐的关联、空周期展示和物理类型转换交给 agent，核心不做完整查询编译或运行时基数校验（§2、§3.6、§14） |

指标采用“结构化 + 表达式”的理由是常见口径需要可编辑字段，复杂口径需要保留原算法；MetricFlow、Cube、LookML 都有类型与表达式结合的做法，Fabric 的 [explicit Metric 定义](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/ontology-definition)也有自己的 expression，支持 SQL 等方言（§3.6、§12）。这只作为设计依据，不承诺各产品执行能力或字段完全相同。

## 11. 删除清单

后端：

- `domain/models_v3.py`、`domain/legacy_v1.py`，`domain/snapshot.py` 中的版本转换
- `ossie/native.py`、`ossie/extensions.py`
- `ossie/importer.py`、`ossie/compiler.py`：第一部分随旧模型删除，第二、三部分在 `adapters/ossie/` 重写
- `services/element_save.py`、`api/proposals.py`、`contracts/proposals.py`、`api/mcp.py`、`api/modeling.py`、`services/publish_preview.py` 中的 `schema_version` 分支
- `services/dataagent.py` 中关于 owner_ref、roles、verbalizes、endpoint_direction 的 prompt
- `ossie/compiler.py` 中的 `_resolve_readings` 及别名逻辑；导入器中读取旧版本扩展块（1–4）的代码
- `scripts/ossie_coverage_matrix.py`，由 §7 总表对应的支持矩阵测试取代
- `integrations/dataagent/skills/md2ossie`：改名改写为 `ontofoundry-modeling`（§13.3），删除 `validate_ossie.py` 及其测试；agent 系统提示词中的旧合同 B
- 权限投影、分页、版本、参数化 SQL、标识、引用等仍有效的行为验收要保留或改写，不按文件前缀批量删除；时间验收按已确认 D2 更新，按数据集保留同日选行语义，增加独立末日、趋势、日期不齐与空周期由 agent 处理的案例，删除父主来源决定日期和强制同日连接的旧断言。
- 只针对 v1 / v2 / v3 兼容的测试（`test_p0_v3_contract.py`、`test_p1_*`、`test_t2_postgres_migration.py` 等），逐个确认后删除或改写

前端（已按 main `334bc10` 核对，2026-10-15）：

- `AdvancedMappingDialog`、`MappingStructure`、`NativeMappingEditor`、`MappingForm`、`ObjectEditorPage` 已在 main 删除，不列为本 PR 待删除项，不恢复旧编辑入口。
- 保留当前 `ElementInspector` 对象弹窗和 `InspectorDialog`；`ElementPanels` 概览统一展示和编辑 description，不再单独展示“上下文说明”，规则表展示归属、表达式及“继承”只读标签。属性表 `PropertyMappingTable` 改读 core-1 列、计算表达式及来源；关系表 `RelationMappingTable` 保留“关联方式”（映射表、连接条件），接入判别绑定和唯一属性选择。无需新建高级入口。
- 当前仍存在的 `semantic/MappingTreeEditor`、`SemanticObjectForm` 及语义树数据访问，随 core-1 扁平数据集与来源引用改写或移除；`lib/objectMapping*` 和 `MappingsPage` 按新来源结构改写，不能只删 UI 留类型依赖。

- `components/VerbalizationEditor.tsx`、`lib/verbalization.ts`，换成“反向名称”输入框
- `components/OssieImportDialog.tsx` 中直接发布和跳转三方合并的逻辑，改为“看报告 → 生成提案 → 进入会话”
- `api/types.ts` 中 roles、owner_ref、native_presence、position、endpoint_direction、value_types、旧 semantic_models 与字段/映射树等类型及相关编辑界面；datasets 改为轻量登记，保留其新类型与编辑能力

文档：

- 10-08 方案、P1–P4 进度文档和覆盖矩阵文档顶部标注“已被本文取代”

---

## 12. 未来适配器（参考）

以下均为官方文档核查，日期 **2026-10-15**；Fabric 指新预览体验，未实测租户，不能由参考表推导完全等价。

| 核心模型 | Palantir Foundry（官方） | Microsoft Fabric IQ（官方） |
|---|---|---|
| 对象、属性 | [Object type](https://www.palantir.com/docs/foundry/object-link-types/type-reference)、Property，类型比七标量丰富 | [Entity type](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-create-entity-types)，属性类型、未知类型有其独立规则 |
| 单父继承 | [Interfaces](https://www.palantir.com/docs/foundry/interfaces/interface-overview) 为抽象接口，对象实现接口；不是具体对象继承 | [Inheritance](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-inheritance)：单父、属性继承、普通关系和绑定不继承；父查询仅含直接子类。本平台完整继承关系、规则为有意差异 |
| 关系与绑定 | [Link type](https://www.palantir.com/docs/foundry/object-link-types/create-link-type)：外键、join dataset；1:1 声明不强制执行 | [Relationship](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-create-relationship-types)：Origin/Target 属性或 Use mapping table；基数强制、自关联限制未核实，不引用第三方结论 |
| 多来源 | [MDO](https://www.palantir.com/docs/foundry/object-permissioning/multi-datasource-objects)：column-wise，非 row-wise；每属性一个来源（主键例外） | [绑定](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-bind-data) 有 primary/secondary 操作，但同页仍写单 static 限制，官方内部矛盾，不能据此承诺全部组合可用 |
| 计算属性 | [Derived properties](https://www.palantir.com/docs/foundry/object-link-types/derived-properties) 与本平台范围不直接等同 | [新体验概览](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview#alignment-with-power-bi-semantic-models) 承接源 calculated columns；本体独立定义协议未核实，详见 §3.7 |
| Rule | [Submission criteria](https://www.palantir.com/docs/foundry/action-types/submission-criteria) 有执行语义，不能等同不执行规则 | [Business rule](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-rules)：自然语言业务规则、可关联概念，本体不执行；与 core 受限 SQL 路径不同 |
| Metric | [对象集合聚合 API](https://www.palantir.com/docs/foundry/api/ontology-resources/objects/aggregate)是查询调用，本体没有同构的可复用指标定义 | [操作页](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-metrics)按 measure 所在表对应的实体展示；[定义协议](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/ontology-definition)为顶层 model.metrics[]，展示位置不表示对象归属 |
| 实例标题 | [Title key](https://www.palantir.com/docs/foundry/object-link-types/property-metadata)，与主键分开 | [旧绑定体验](https://learn.microsoft.com/en-us/fabric/iq/ontology/old-experience/how-to-bind-data#add-static-data) 可选 display-name property；不把旧步骤当新体验完整保证 |

二元关系和对象、属性、链接分离是参考方向。本平台选择主表决定实例集合、完整继承普通关系与规则、支持复合标识；有绑定父对象从父表完整读取，虚拟父对象按具体子对象实例并集查询。

核查日期：2026-10-16。指标放在数据集上，与以下分层一致；产品能力和字段不因此完全相同。

| 产品 | 定义与展示 |
|---|---|
| [Ossie / OSI](https://github.com/apache/ossie/blob/main/core-spec/spec.yaml) | 指标在 semantic_model.metrics 中引用数据集字段，没有指向本体概念的关系；core-1 只承载符合单数据集边界的部分，例外见 §7 |
| [Fabric IQ 操作页](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-metrics)与[定义协议](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/ontology-definition) | 定义为顶层 model.metrics[]。操作页说明 measure 按其定义所在表对应的实体展示；“显示在实体下”不能视为模型上的对象归属。explicit 有自身表达式，其他类型可引用源 measure |
| [Palantir 对象集合聚合](https://www.palantir.com/docs/foundry/api/ontology-resources/objects/aggregate) | 提供对象集合聚合和分组；本体没有与这里 Metric 对应的可复用指标定义，不能把一次聚合调用当作独立指标资源 |
| [dbt 语义模型](https://docs.getdbt.com/docs/build/semantic-models) | simple 指标写在一个表对应的语义模型上，使用该模型的列 |
| [Snowflake 语义视图](https://docs.snowflake.com/en/sql-reference/sql/create-semantic-view) | 可在一个逻辑表上对该表的列定义聚合指标；这里对照在单个数据集上聚合的用法 |
| [Looker measure](https://docs.cloud.google.com/looker/docs/reference/param-measure-types) | measure 写在视图中，聚合类型配合 SQL 表达式 |

core-1 保留 simple、ratio 便于编辑常见口径，expression 保留复杂算法；均只引用自己的 dataset_id 所指数据集的列。用户问题中的其他数据集条件由 agent 查询时沿本体关系筛选，不写入指标。对象详情是否按绑定展示相关指标由原型决定，不是持久化关联。

指标选择结构化与表达式并存，也参考以下官方资料。

| 资料 | 已核实的依据 |
|---|---|
| [MetricFlow 指标类型](https://docs.getdbt.com/docs/build/about-metricflow)和 [derived](https://docs.getdbt.com/docs/build/derived) | 类型化指标可与表达式组合；不是任意 SQL 的通用编译承诺。新版把旧 measures 迁入 simple metrics，不能把旧字段布局当成唯一现行格式 |
| [Cube measure](https://docs.cube.dev/reference/data-modeling/measures) | 类型与 SQL 配合，number 可保存聚合表达式；自定义 number_agg 有引擎限制，没有在这里查到独立 median 类型 |
| [LookML measure](https://docs.cloud.google.com/looker/docs/reference/param-measure-types) | 聚合类型包括 median，number 可组合聚合结果；SQL 与方言仍影响执行 |
| [dbt non-additive dimension](https://docs.getdbt.com/docs/build/measures#non-additive-dimensions) | 可声明时间维度不可加、窗口头尾和分组。本平台各数据集独立确定期末日，同一数据集不按实体分组分别取末值 |
| [Fabric 数据绑定](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-bind-data) | 未查到绑定层业务行筛选字段；不能把查询筛选当作绑定筛选，也不能据此断言产品绝对不支持 |
| [Palantir restricted view](https://www.palantir.com/docs/foundry/object-permissioning/configuring-rv-access-controls) | 支持来源层的逐行权限筛选，但不是本平台 derived_by 的业务成员定义；未查到同构的绑定字段 |

[Fabric 元数据](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-add-metadata)包含 description、synonyms 和自定义属性；[Palantir 对象元数据](https://www.palantir.com/docs/foundry/object-link-types/object-type-metadata)包含 description，[搜索说明](https://www.palantir.com/docs/foundry/aip-analyst/capabilities)确认 aliases 可用于识别对象类型。它们不是本平台新增 instructions 的依据；上下文统一合入 description。

## 13. AI 建模技能与导入补全

### 13.1 现状问题

建模 agent 使用的 `integrations/dataagent/skills/md2ossie` 技能，以及平台每轮发给 agent 的提示词（`services/dataagent.py`），
都是按“产出 Ossie”来写的：

- 技能教的是 Ossie 建模：ValueType 取舍、隐式首角色、`roles`、`verbalizes`、`OneToMany` 不合法等，校验器也是 Ossie 校验器。
- 轮次提示词要求 agent 按 v3 写提案：`owner_ref`、有序 `roles`、`ConceptRef`、`concept_context`、`role_values`、
  `owner_columns / role_columns` 等，光关系部分就有十几行说明。
- 同样的建模规则在技能、agent 系统提示词、轮次提示词三处重复。
- 还保留着旧合同 `ontofoundry.model-result/v1`（agent 直接写完整 Ossie 文档）。

核心模型改完以后，这些内容都要换成面向核心模型。

### 13.2 目标

1. **AI 直接产出核心模型的提案**，不再产出 Ossie。需要 Ossie 文件时，走“AI 建模 → 核心模型 → Ossie 适配器导出”。
2. **AI 负责导入时机械规则做不好、或者直接丢掉的部分**（§13.4）。适配器只做确定性转换、不推断（P4），需要理解业务含义的工作交给 AI，
   并且一律以**提案**形式交给用户确认。
3. 建模规则只写在技能里一处；系统提示词只定工作方式，轮次提示词只给本轮的合同、文件路径和材料清单。

### 13.3 技能改造：`md2ossie` → `ontofoundry-modeling`

技能改名，因为它的产出不再是 Ossie。目录结构：

```text
integrations/dataagent/skills/ontofoundry-modeling/
  SKILL.md                         工作流程、提案合同要点、交付要求
  references/
    core-model.md                  核心模型元素与字段（与本文 §3 同步）
    modeling-patterns.md           建模模式与例子，见下表
    import-completion.md           导入补全的处理方法，见 §13.4
    reading-ossie.md               材料是 Ossie 文件时怎么读懂它（角色、读法、值概念的含义）
  assets/vendor/apache-ossie/      保留 ontology.md 作参考；删除校验器和 schema 校验依赖
  scripts/check_result.py          用轮次给出的 JSON Schema 校验结果文件，并检查 client_ref 唯一、引用存在
  tests/
```

`modeling-patterns.md` 覆盖的建模模式：

| 模式 | 写法 |
|---|---|
| 多方参与的事实（n 元关系） | 按 §5.3 建中间对象：角色顺序为 owner 后接 roles；ManyToOne 取除最后角色外全部角色表示为键，无基数取全部，均含值角色；实体角色展开有效完整标识，到各实体角色建多对一关系。不能把日期、数量一律排除在键外；事件对象另按实际业务身份建键 |
| 是 / 否型事实（一元关系） | 布尔属性，例如“是否VIP” |
| 一对多 | 从“多”的一端建多对一关系，name 写稳定关系标识，verbalizes 写完整正反句式 |
| 多对多（无附加信息） | 建 many_to_many 关系，data_join.kind=mapping_table，dataset_id 引用登记的中间表 |
| 多对多（配对本身有信息） | 先判定业务身份再建中间对象；关系元组按 §5.3 构键，业务事件按实际身份（如事件编号，或含日期、尝试次数的组合）建键，不机械复用参与方编号 |
| 复合标识 | 多个属性同时设为标识（关系不参与标识），映射的 `key_columns` 按顺序列出 |
| 自关联 | 源和目标是同一对象，例如“员工 汇报给 员工” |
| 继承、多分类 | 单父 is-a 表达实例包含，子对象可用派生条件或扩展数据定义；只写本地定义，继承定义只读。既是学生又是男生等分类用属性筛选，或人＋学生＋员工角色对象及一对一关系；不为分类堆继承，不重复创建父关系 |
| 受约束的值（Ossie 的 ValueType） | 属性的 `value_kind` + 规则，例如“币种代码是 3 位大写字母”写成该属性上的约束规则 |
| 指标 | 只选一个数据集，simple、expression 的全部列和时间字段限本数据集，ratio 分量必须同数据集；不存本体归属或路径，其他数据集的条件在 agent 查询时处理 |
| 已计算的比率列 | 覆盖率、密度、百分比列建成属性。需要指标时找到原分子与分母做比率；缺分量时先说明不能据此推导总体比率 |
| 快照与趋势 | 在 Dataset 登记快照日期列（仅每日全量快照表），simple 和 expression 按需选时间字段，ratio 使用两分量各自时间字段；各数据集独立选日期且所有行使用同一天，日期不齐的关联与空周期展示交给 agent |
| 汇总表与窗口 | 汇总表登记成数据集，直接在其上建数据集指标；查询时用不用汇总表由 agent 决定。已计算的不同窗口作为不同属性或来源，解释窗口含义，不能相加 |
| 数据集登记 | 先登记方言、schema、表名、说明和可选快照日期列，主附表、关系表只写 dataset_id，不创建字段节点或 semantic_models |
| 有绑定父对象 | 父绑定必须覆盖全部子实例，子对象以 ObjectType.derived_by 或 membership_source_id 扩展表定义成员，继承属性和关系从父绑定取，查父对象只用父表 |
| 虚拟父对象 | 父对象没有映射，具体子对象各自绑定并补配继承属性与关系，实例只属于一个具体子类，查询父对象列出具体子类实例并集 |
| 独立对象与禁止组合 | 不存在实例包含关系时建两个独立对象；禁止已有父绑定却让子实例独立存于父表之外，应改虚拟父或取消继承 |
| 同义词 | 业务别名写进 `synonyms`（对象、属性、关系、指标都有），不写进名称或描述 |
| 规则 | 挂在具体元素上，表达式用路径写法（`sales_order.customer.region`），不用 Ossie 角色写法 |

技能里**不再出现**：`roles`、`owner_ref`、`ValueType`、`ConceptRef`、`concept_context`、`role_values`、
`owner_columns / role_columns`、`OneToMany` 相关的坑。

提示词同步改造：

- 轮次提示词（`services/dataagent.py`）只保留：结果合同（头部值、Schema 文件、create/update/delete 的写法、证据规则）、
  材料清单、MCP 连接、结果文件路径。所有建模规则移到技能。
- agent 系统提示词（`agents/agent_ontofoundry.md`）删除旧合同 B（`ontofoundry.model-result/v1`），技能名改为 `ontofoundry-modeling`。
- 提案合同 `ontofoundry.proposals/v1` 的 `target_kind` 改为：`object_type / property / link_type / rule / metric /
  dataset / mapping / material_object / material_link`（去掉 `value_type`，新增 `metric`、`dataset`）。

部署注意：技能目录改名后，DataAgent 管理员要重新安装技能、更新 agent 的技能配置并重启 DataAgent（见 `integrations/dataagent/README.md`）。

### 13.4 导入补全

导入时适配器按规则做了机械转换或丢弃，其中不少内容需要理解业务含义才能处理好。导入完成后，平台提供“**AI 补全**”，
把这些条目交给建模 agent，由它产出提案。

**流程**：

1. 导入时，原文件按确定的格式化方式（缩进 2 空格、键序不变）保存为工作空间的一份**材料**。
   导入报告中每个条目记下它在这份材料里的行号范围。这样 AI 的提案可以照常用材料证据（行号 + 原文）引用它。
2. 导入生成的会话（§4.5）里显示“用 AI 补全 N 项”。用户点击后，平台在同一会话里发起一次建模运行，材料是导入原文件，
   附带一份“补全清单”（报告中可补全的条目：规则编号、原文路径、行号、导入后对应的核心元素 id）。
3. agent 按技能 `import-completion.md` 逐条处理，产出提案；不能处理的条目在回答里说明原因。
4. 用户在提案面板逐条审阅接受，和普通建模运行完全一样。

AI 补全只发生在用户点击之后，导入本身始终是确定性的。

**各类条目的处理**：

| 导入时发生了什么 | 规则 | AI 补全做什么 | 提案 |
|---|---|---|---|
| 多元关系机械转成中间对象，名字是 `supplier_supplies` 这类拼接名 | RT-27 / RT-28 | 起业务名称（如“供货记录”）、写描述；给中间对象的各条关系起名和反向名；检查搬过来的规则表达式，按核心模型写法改写 | update 中间对象、关系、规则 |
| 一元关系转成布尔属性 | RT-26 | 起业务名称（如“是否VIP”）、写描述 | update 属性 |
| 属性读法未独立保存 | RT-20 | 按原文理解属性含义并补充描述或同义词；二元实体关系读法完整保留，不补猜正反动词 | update 属性、对象 |
| 独立角色名未保存 | RT-21 | 自关联或中间对象的关系名不清楚时，参考角色名改名（如“汇报给”→“上级”） | update 关系 |
| 值类型独立域未保留，部分约束无法改写 | RT-23 / RT-24 | 参考原文补充说明；只补尚未完整转换的属性约束，已实例化的约束不重复创建 | update 属性；create 规则 |
| 无法解析的规则未生成核心提案 | RT-31 | 按路径写法改写表达式，挂到对应元素上 | create 规则 |
| 中间对象决定角色缺标识，整组键待补全；含关系成员的标识整组未导入 | RT-27 / RT-32 | 为对象补全标识：按参与方完整业务标识补建编号属性，仅有逐项对应证据才绑定外键列、映射到对应列，与原标识中的属性一起设为标识（如座位：账户编号 + 座位号） | create / update 属性；update 映射 |
| 值概念上的关系、引用 Any 的关系等合法但未承载的构造 | RT-29 | 判断业务含义，能用核心模型表达的就提出对应元素 | create，或在回答中说明无法表达 |
| 文档级上下文没有明确对象归属 | RT-02 | 参考原文分配同义词到 synonyms，说明并入对应对象 description；能够确定归属的说明已由 RT-59 机械合并 | update 对象 |
| 文档级 `requires` 被丢弃 | RT-04 | 表达式只涉及某一个对象或关系时，改写成该元素上的规则；其余在回答中说明 | create 规则 |
| 指标列引用、统计数据集或表达式边界待补全 | RT-47 / RT-49 / RT-61 / RT-69 | 引用不明时补登记数据集和列；超出单数据集边界的原文保留报告，由用户改写为单个数据集上的指标，不建立本体关联 | create / update 指标与数据集；RT-69 改写不是等价转换 |
| 不支持的表达式、嵌套 referent 等映射被丢弃 | RT-43 | 可确认是同行运算时提出 expression 绑定；其余说明边界 | update 映射，或说明 |
| 字段的 `label`、`dimension` 等被丢弃 | RT-46 | `label` 可作为属性显示名或同义词 | update 属性 |

多元 OneToOne、实体继承值类型是非法输入，直接 error，不在上表中安排转换或 AI 补全。

不交给 AI 的条目：纯格式规范化（RT-10 至 RT-13）、文档名称和描述（RT-01）、旧扩展块（RT-03）、方言丢弃（RT-45）。
这些不交给 AI 自动补全，差异仍在报告说明，不能一概视为不影响业务含义。

**原文件的用途**：作为 AI 补全的材料和证据来源，也是导入报告行号的依据；不提供“与原文件对比”的界面（§7.2）。

### 13.5 实施

- 第一部分：技能改名改写、提示词精简、提案合同的 `target_kind` 调整、删除旧合同 B。
- 以后的扩展：导入补全（依赖第二部分的导入报告和原文件材料）。
- 第一部分验收：技能和提示词不出现 §13.3 列出的旧模型合同；API schema 仍含类型及边界，不依赖技能才能理解。AI 补全交付时才验收 A/B 导入后的补全提案可校验。

---

## 14. 问数：MCP 提供语义，agent 拼 SQL 查数据

### 14.1 分工

| 谁 | 负责 |
|---|---|
| OntoFoundry MCP | 提供对象、属性、关系、规则和指标，以及按权限读取的来源、列类型、关联条件和元数据。结构化指标可附基础 SQL 参考，表达式指标保留原文 |
| DataAgent | 理解问题，根据语义选择来源、时间点和分组，拼 SQL，调用自己的查询工具，再用业务语言回答。类型、方言、精度等执行细节由 agent 调整 |

本节是 agent 答题的分工。§8A 的新建指标数值预览由平台在已登记连接上编译并只读执行当前表单定义，不经过 DataAgent；MCP 仍只有语义读取工具，两个流程互不替代。

表位置和方言由扁平 Dataset 登记提供，列信息来自可选列清单及数据资产元数据快照；DataMapping 和关系只引用数据集及列。主表、附表和快照来源分别按各自语义提供，汇总表可作为独立数据集用于指标，不能把所有来源都横拼成一个宽表。

这与 [Fabric Data Agent 使用来源结构和业务说明生成查询](https://learn.microsoft.com/fabric/data-science/data-agent-add-datasources)的方向相近；不表示两边工具合同或执行能力相同。

### 14.2 四个 MCP 工具

按现有工具职责整合为四个，不增加数据库执行工具。工具参数均不暴露 `version_id`。

| 工具 | 参数 | 行为及结果 |
|---|---|---|
| `search_ontology` | `query, kinds?, cursor?, limit?` | 按名称和同义词检索对象、属性、关系、规则或指标。返回 id、种类、摘要和命中的同义词；本体元素按定义带归属，指标只带数据集，不带对象归属；候选分页 |
| `get_ontology` | `ids?, kinds?, include?, cursor?, limit?` | 省略 ids 时返回轻量目录及数量；ids 非空时批量读取定义和授权绑定。ids=[] 报 invalid_arguments。include 默认 semantic，可选择 physical、rules、adjacency，服务端仍裁剪权限 |
| `search_objects` | `type_id?, q?, cursor?, limit?` | 只检索已接受且获授权的文档事实的推导显示文本和属性值，不访问数据库。按事实 UUID 返回并保留实际 type_id；父类型按继承范围展开，只对同一 UUID 去重，不按业务标识合并；分页及数量按事实条目计算 |
| `get_object` | `id, include?, cursor?, limit?` | 按事实 UUID 读取该条已接受事实的只读 display_text、属性及授权证据；直接邻接保留该事实的端点，按关系和方向分页，不递归展开邻居全文，不合并同业务标识的其他事实 |

limit 默认 20、最大 100，批量 ids 最多 100。嵌套属性、规则和邻接也支持分页，返回总数、当前段及 next_cursor。响应预算为 256 KiB，超出时在元素边界分页；单项过大时提供可分段字段及说明，不能无标识截断。目录和缓存采用相同授权视图。

版本由服务端解析：建模令牌使用已存在的 `pinned_version_id` 固定版本，问数令牌使用当前发布版本。结果可以带 `version_id` 便于追溯，调用方不能传版本参数。cursor 签名绑定工作空间、服务端解析的版本、工具、筛选条件、投影和权限上下文。问数期间若发布版本发生变化，旧 cursor 报 cursor_invalid，agent 从新版本重新读取；建模固定版本不随发布变化。版本被清理时报 version_unavailable。这里固定的是本体和绑定版本，不是业务数据的历史快照。

删除旧数据库 source 搜索、query_metric、独立导出及专用 dataset 工具；数据集通过 get_ontology 的授权 physical 投影按需读取。文档事实用上述两个实例工具，agent 答题所需的数据库统计由 DataAgent 查询工具完成；平台表单预览使用 §8A 的内部流程。

### 14.3 `get_ontology(ids)` 返回内容

结果带 workspace_id 和服务端解析的 version_id。对象定义包含 description、synonyms、title_property_id、extends、derived_by 和直接子对象列表；继承项带 inherited_from 和 binding_status。有绑定父对象说明父范围已包含所有子实例；虚拟父对象返回“无自己的表，实例来自以下子对象”及实例来源类型列表；普通无绑定对象仍标为 unbound，不能与虚拟父混淆。

下面是授权后的物理投影示意。MCP 从 Dataset 的 dialect、schema_name 及服务端来源配置解析方言及 database/schema，不返回 connection_alias；嵌套关系和 SQL 参考也遵守这一规则。

```json
{
  "workspace_id": "…",
  "version_id": "…",
  "elements": [
    {
      "kind": "object_type",
      "id": "…",
      "name": "sales_order",
      "description": "订单统计采用已定义的指标口径。",
      "title_property_id": "…",
      "extends": null,
      "child_types": [
        {
          "id": "…",
          "name": "线上订单"
        }
      ],
      "data": {
        "status": "bound",
        "dialect": "mysql",
        "database": "sales_demo",
        "sources": [
          {
            "id": "main",
            "dataset_id": "…",
            "key_columns": [
              "order_id"
            ],
            "dataset": {
              "id": "…",
              "name": "orders",
              "dialect": "mysql",
              "database": "sales_demo",
              "schema": "sales_demo",
              "table": "orders",
              "snapshot_date_column": null
            }
          }
        ],
        "metadata_snapshot_id": "…"
      },
      "properties": [
        {
          "id": "…",
          "name": "amount",
          "value_kind": "decimal",
          "binding": {
            "kind": "column",
            "source_id": "main",
            "column": "amount"
          },
          "physical_type": "decimal(12,2)",
          "binding_status": "bound"
        }
      ],
      "links": [
        {
          "id": "…",
          "source_type_id": "…",
          "target_type_id": "…",
          "direction": "forward",
          "multiplicity": "many_to_one",
          "binding_status": "bound",
          "data_join": {
            "kind": "mapping_table",
            "dataset_id": "…",
            "source_columns": [
              "order_id"
            ],
            "target_columns": [
              "customer_id"
            ],
            "source_key": {
              "kind": "mapping_key"
            },
            "target_key": {
              "kind": "mapping_key"
            }
          },
          "note": "按声明的多对一关系导航；重复键或映射行仍可能造成重复计算。"
        }
      ]
    }
  ]
}
```

虚拟父对象的物理投影示意为 `{"status":"virtual", "instance_source_type_ids":["<设备>","<车辆>"], "note":"无自己的表，实例来自以下子对象"}`。这是从继承结构推导的查询说明，不是新增持久化字段；物理来源仍按权限裁剪。文档事实查询按已接受的事实 UUID 返回，保留实际 type_id；继承展开只对同一 UUID 去重。不同 UUID 即使业务标识相同，也分别保留其属性、证据与邻接，分页及数量按事实条目计算。需要“有几个业务实体”时，由明确的统计按完整业务标识去重，并说明缺标识事实的处理，不把这一步隐含在检索中。

| 内容 | 返回规则 |
|---|---|
| 权限 | 沿用 `can_read_mappings` 和 `can_read_instances`。无映射读取权限时不返回 Dataset 登记（含名称、说明、列清单和数量）、表、列、JOIN、物理类型、元数据快照或 SQL 参考，物理部分标为 forbidden。表达式内含来源 SQL 时同样按映射权限裁剪，不能从原文旁路泄露物理信息。无实例权限时不能检索事实或证据。摘要、数量、嵌套项和缓存使用相同投影 |
| 路由 | 每个授权 Dataset 给出 dialect、database/schema 和 table；schema 未填写时由服务端来源配置解析默认值，无法确定则未完成。mysql 使用 mysql.query，doris 使用 doris.query，postgresql 等只在 agent 有对应工具时执行，不能伪装成已有工具 |
| 来源 | 返回主附表 dataset 引用、键、成员条件或扩展来源及 Dataset 快照日期列；虚拟父对象明示具体实例来源。计算属性返回其表达式。未绑定为 unbound，缺键为 missing_key，跨连接为 cross_connection，元数据过期为 metadata_stale；权限不足为 forbidden |
| 关系 | 返回端点、方向、绑定和声明基数提示。两端是快照数据集时提示各自日期语义和多日期交叉配对风险，不强加同日连接。同连接且绑定可用时才提供 JOIN 参考；内部连接身份只用于判断能否连接，不传给 agent |
| 指标 | 返回 simple、ratio、expression 及数据集列依赖，不返回对象归属；simple、ratio 可附只读结果类型，ratio 的 dataset_id 从同数据集分量解析，原生输入不保存。simple、expression 返回可选 time_field，ratio 返回分量时间；各来源附快照声明。授权来源就绪的结构化指标可附 sql_reference（SQL、字面量参数、dialect、database、说明）；expression 保留算法与引用作用域交给 agent，来源未定条目不形成已接受指标 |
| 元数据 | 物理类型与注释来自可定位的元数据快照，明示快照 id 及采集时间；业务说明来自本体。这里的元数据快照与业务日快照是不同概念 |

DataAgent 的 `core/tool_runtime.py` 已核对（2026-10-15）：内置查询工具是 `mysql.query(database, sql)` 和 `doris.query(database, sql)`，另有各自可选参数；没有 connection_alias 参数。若多条连接解析到相同的方言和 database，现有 resolver 报多集群歧义，须由来源配置收敛唯一来源；不向 MCP 增加连接别名。

### 14.4 问数 agent 的流程

1. 搜索语义定义，按需读取对象、关系、指标和授权绑定。结果记录 version_id；多次读取若返回了不同版本，或发生 cursor_invalid，就从当前版本重新获取依赖定义，不能混用新旧定义，也不能自行指定旧版本。
2. 有已定义指标时采用它的口径。simple 保留聚合和固定条件，ratio 分别保留分子分母的时间字段和过滤，expression 保留算法；无指标时才组合已有语义。已计算百分比列只当属性，不能凭它编造总体比率。
3. 有绑定父对象只查完整父表；子对象逐级按派生条件筛选，同时有成员扩展来源时还须存在扩展记录，继承项仍用父绑定。虚拟父对象展开具体子对象的实例并集，保留类型和实例键，具体查询编排交给 agent。
4. 按 §3.6 的计算规则处理来源：快照数据集每周期独立选最后有数据的日期，同一数据集所有行使用同一天，不按实例或分组各取最近值；其他数据集取周期内全部行，再按指标算法整体重算，不能把每日去重数、均值或比率相加。ratio 两个分量各按自己的时间字段归周期；日期不齐的关联和空周期展示由 agent 根据问题处理并说明，已有窗口不能跨窗口相加；查询时用不用汇总表由 agent 决定，须保留粒度与口径。
5. 指标只使用自己的数据集列。用户问“华东区订单金额”时，读取 orders 上的订单金额，再沿订单到客户的本体关系筛选客户地区；这是 agent 查询时的行为，不是指标定义的一部分。对象查询按关系方向组织连接，有歧义时处理或澄清，并避免连接重复行放大聚合；跨连接不能伪装成一条 SQL 联邦查询。
6. 根据 dialect 选择 mysql.query 或 doris.query，传入 database 和 sql，按引擎调整物理类型和方言。聚合由数据库完成，不拉回全部明细自己统计。
7. 用业务语言说明口径、来源和快照日期。文档事实从 search_objects、get_object 取得，并注明证据。

### 14.5 实施

第一部分应同时更新四工具 schema、服务端参数校验、权限投影、cursor 和两类 agent 提示词。四工具拒绝传入 version_id，服务端解析版本后才签发 cursor。建模固定版本与问数当前发布版本须分别验收。

问数验收使用通用销售场景，其中“销售额最高的客户”应由数据库聚合后返回，不通过文档实例翻页完成。快照和趋势另按示例 12 验收；本设计未修改当前实现。

### 14.6 最低回归验收矩阵

| 范围 | 必须检查的分支 |
|---|---|
| 来源绑定 | 主附表、关系表、数据集指标统一引用 Dataset，位置只登记一次，列清单可空；一个对象挂二十多张汇总和快照表；逻辑键不依赖数据库主键；附表缺键有明确状态；主表缺附表行仍保留；唯一非主键关联及复合键顺序 |
| 继承 | 父表覆盖全部子实例，语义派生条件与成员扩展表两种限定并可同时使用；虚拟父无映射并按具体子对象实例并集查询，事实同步展开；两个独立对象不继承；拒绝父表之外的独立子实例；继承关系 id 不复制 |
| 计算列 | 数量乘单价、CASE、未知列与跨对象引用；MCP 返回计算表达式 |
| 指标 | simple、expression 全部列及时间字段限 dataset_id，ratio 两分量同数据集；拒绝其他数据集列、SELECT、FROM、JOIN 和额外查询作用域；数据集/列删除与快照变化的依赖组，不受本体删除、改名、基数或成员变化影响；ratio 时间、零分母、NULL、空集、median、复杂本数据集表达式与拼接去重 |
| 平台预览 | 示例 13 无对象绑定时提交数为 10；使用未保存的新表单定义和所选时间范围，总值与按月趋势分别只读执行；ratio 保留分量时间；表达式白名单失败、引擎不支持、缺绑定或权限时显示“无法预览”及原因，不伪造数值 |
| 时间 | 各 Dataset 独立取最新日或周期末日，普通主表和快照附表各按所在表声明选行；事件表按范围整体重算，有提交仓库数两日为 1、2，全周期为 2，不能相加成 3；同一数据集末日排除停在旧日的实例；成员条件不改变数据集日期；日期不齐与空周期交给 agent；不强加日期相等；窗口与汇总表保持原口径 |
| MCP | 同类型同完整业务标识的文档事实只提示重复，由人选择接受或改更新追加证据；只返回已接受事实，UUID 寻址、分页，继承展开仅同 UUID 去重，业务实体数另按业务标识统计；所有层级都不返回连接别名；四工具无版本入参；建模固定版本，问数当前发布版本；发布或权限变化使旧 cursor 失效；物理与实例权限裁剪；分页边界 |
| 导入 | 只新增和修改，文件中没有的已有元素保持不动，平台导入从不生成 delete 提案；转换失败保留原文和待补全状态，等待用户选择或点击 AI 补全；删除由用户在会话里手动操作，或让 agent 提出删除提案并走正常审阅；原子英文标识交换、依赖闭包、多父 RT-34、七类型 RT-35、规则引用重写、平行边唯一匹配；RT-49 和 RT-56 保留 expression，RT-59 合并说明 |
| 本轮语义边界 | 多分支并集、多层派生加成员表交集及 EXISTS 仍属对象语义，与指标独立；决定角色缺标识不裁剪键，最后角色单独报告；编号 direct 逐项对齐，值约束传播；ratio 输入 dataset_id/time_field、simple/ratio 输入 value_kind 拒绝；映射 UUID 锁定、事实及证据仅 UUID；Dataset UUID5；非 Ossie 错误 rule_id 可空；补齐依赖实时解除阻断 |
| 往返 | 单个数据集上的指标与 OSI 一一对应，数据集列与算法保持，ratio 无已登记分量时保留单条 expression；条件行计数规范形式、可空列 COUNT 不转行计数、CASE、CAST/NULLIF；同一作用域同时含 orders、customers，裸 COUNT(*) 待用户选定 orders 后转 simple count，导出带 orders 列的行计数规范式，再导入来源仍唯一为 orders（改选 customers 时同理）；原生无列引用 expression 保留已声明来源，含 COUNT(*) 的表达式可等价规范化行计数，无法表达来源时 RT-61 error；超出单数据集边界的 OSI 指标 RT-69 error，原文留报告待补全，不生成核心指标；RT-60 时间声明、RT-61 非法核心指标导出、RT-62 数据集复用、RT-63 来源、RT-64 键与快照、RT-65 继承、RT-66 元数据、RT-67 成员定义、RT-68 子类标识；多元 OneToOne 与实体继承值类型 error；09 空模型及 13 仅数据集指标的完整 Ossie 导出 error |

此表是后续实施的验收要求，不代表 core-1 schema、适配器、产品 UI 或数据库查询已经通过测试。本轮示例只做静态核查，边界见 README。
