# 核心模型与格式适配器设计

日期：2026-10-14 · 状态：草案，待评审

本文**取代** `docs/plans/2026-10-08-ossie-native-lossless-plan.md` 及其 P1–P4 进度文档、
`docs/design/2026-10-08-ossie-coverage-matrix.md` 中“Ossie 是模型规范层、必须无损承载”的原则。
为避免与已有的草稿 schema v2 / v3 混淆，本文的模型称为**核心模型（Core Model）**，
存储标识 `schema_version: "core-1"`，不再沿用数字版本号。

---

## 1. 背景与结论

10-08 方案把 Apache Ossie 定为模型的规范层，要求平台原生、无损地承载 Ossie 的全部构造。落地结果是草稿 schema v3
（`domain/models_v3.py`）实质上成了 Ossie 文档的语法树：每个节点记录字段是否出现（`native_presence`）、数组位置（`position`）；
关系是 `owner_ref + roles[]` 的 n 元结构；值类型是独立概念；语义层照搬 OSI 的 dataset / field / mapping 递归树；
平台扩展还要记录“导出时改了哪些 JSON 位置”以便撤销（`export_edits`）。
发布时所有草稿都会先转成 v3（`services/workspaces.py`），编辑、提案、合并、前端、agent prompt 都被迫围绕这套结构工作。

本设计的结论：

1. **核心模型是平台唯一的真相**。建模、编辑、提案、合并、发布、查询、MCP 都只面向核心模型。
2. **外部格式只通过适配器进出**。Ossie 是第一个适配器，以后可以加 Palantir Foundry、Microsoft Fabric IQ、OWL 等。
3. **转换允许有损，但每一处有损都必须写进转换报告**，不静默丢弃，也不静默猜测。
4. 核心模型的形状参考 Palantir Foundry 和 Microsoft Fabric IQ 的共同做法：**关系只有二元**；
   多元事实建成中间对象；关系的数据绑定统一为“一张关系源表 + 源键列 + 目标键列”。

---

## 2. 原则

| # | 原则 | 含义 |
|---|---|---|
| P1 | 核心模型优先 | 核心模型只包含平台自己需要编辑、校验、查询的结构。外部格式有、平台用不到的构造不进入核心模型。 |
| P2 | 适配器隔离 | `domain/` 不得 import 任何适配器；适配器只依赖核心模型的公开类型。外部格式的概念（角色、presence、方言……）不出现在适配器之外。 |
| P3 | 有损可见 | 导入、导出都产出转换报告，逐项列出“结构改写 / 丢弃 / 占位 / 错误”。 |
| P4 | 不猜测 | 无法确定含义的构造（例如任意 SQL 里的列）一律报告并跳过，不半读、不推断。 |
| P5 | 无损只靠原生格式 | 平台自己的完整备份和搬迁用 OntoFoundry 原生格式的**完整包**（§4.6，含材料），无损；不含材料的单文件形式会丢失证据，导入报告逐项说明。外部格式只保证业务结构和命名：核心模型 → 外部格式 → 核心模型时，规则名、动作、实例、证据等可能丢失。外部格式 → 核心模型 → 外部格式**不保证**还原原文，但每处差异都必须能归到一条编号规则（§7.1），并在导入报告里逐项列出。 |
| P6 | 导出必须合法 | 导出的文档必须通过目标格式的官方校验。缺的信息优先省略或由模型推导，不往受校验的字段里塞占位字符串（见 §4.4）。 |

---

## 3. 核心模型 core-1

以现有 v2（`domain/models.py` 中的 `*Definition` 类）为基础做减法和少量加法。所有元素都有稳定 UUID，集合扁平、按 id 寻址，
所属关系用引用表达，这些都沿用 v2。

### 3.1 元素一览

| 集合 | 元素 | 说明 |
|---|---|---|
| `object_types` | 业务对象 | |
| `properties` | 属性 | 对象 → 一个值 |
| `link_types` | 关系 | **只有二元**：源对象 → 目标对象 |
| `rules` | 规则 | 约束或派生，SQL 表达式，属于某个具体元素 |
| `actions` | 动作 | 平台自有，沿用 v2 |
| `metrics` | 指标 | **新增**，结构化（粒度 + 聚合 + 属性路径 + 条件），见 §3.6 |
| `mappings` | 数据映射 | 对象 → 表、主键列、属性 → 列 |
| `material_objects` / `material_links` | 材料实例 | 沿用 v2；`material_links` 只有 source / target。保留用于后续的实例图谱（Palantir 的对象和链接实例也是同样用途） |

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
| `name` | str | 业务名称（显示名） |
| `technical_name` | str | `^[A-Za-z_][A-Za-z0-9_]*$`，工作空间内唯一（忽略大小写） |
| `description` | str | |
| `synonyms` | list[str] | **新增**（取代 v3 `extension_v4.concept_context.synonyms`），供问答和 MCP 检索 |
| `tags` | list[str] | |
| `extends` | list[UUID] | 父对象，只能是业务对象；子对象只持有自己新增的属性和关系 |
| `evidence` | list[Evidence] | 沿用 v2 |

### 3.3 属性 `Property`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id`、`owner_type_id`、`name`、`technical_name`、`description` | | 同 v2 |
| `value_kind` | enum | `string / integer / decimal / float / boolean / date / datetime` |
| `required` | bool | |
| `identifier` | bool | 是否参与对象标识 |
| `unique` | bool | 值在所有对象中是否唯一（如身份证号）。对象的标识只由这一个属性构成时，它必须是 `unique`；参与复合标识时可以不唯一 |
| `synonyms` | list[str] | **新增**，业务别名，如“金额”的“销售额” |
| `evidence` | | |

**删除**：`verbalizes`、`target_role_name`、`multiplicity`（由 `unique` 取代）、`value_concept`。

### 3.4 关系 `LinkType`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id`、`name`、`technical_name`、`description` | | `name` 就是正向读法里的动词，例如“属于” |
| `inverse_name` | str / null | **新增**，反向读法里的动词，例如“拥有”；可空 |
| `synonyms` | list[str] | **新增** |
| `source_type_id`、`target_type_id` | UUID | 允许相同（自关联，例如 员工 汇报给 员工） |
| `multiplicity` | enum | `one_to_one / many_to_one / many_to_many`。没有一对多：一对多关系一律从“多”的一端建成多对一，例如“订单 → 客户，多对一，名称‘属于’，反向名称‘拥有’”；界面上从客户一侧也能看到“拥有 订单” |
| `tags` | list[str] | |
| `data_join` | DataJoin / null | 关系的数据绑定，见下 |
| `evidence` | | |

**删除**：`verbalizes`、`source_role_name`、`target_role_name`，以及 v3 的 `owner_ref`、`roles`、`endpoint_direction`、
`owner_role_name`、`legacy_multiplicity`。

**`DataJoin`**（参照 Fabric IQ 的关系绑定方式）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `table_name` | str / null | 关系源表。null 表示使用**源对象**映射的那张表 |
| `schema_name` | str / null | 关系源表的 schema；同源对象映射所在的 `connection_alias` |
| `source_columns` | list[str] | 关系源表中，与源对象主键列（`key_columns`）按位置一一相等的列 |
| `target_columns` | list[str] | 关系源表中，与目标对象主键列按位置一一相等的列 |

列表长度必须分别等于两端对象的主键列数，复合主键因此自然支持。

例子：

- 订单 属于 客户（多对一，外键在订单表）：`table_name=null`（即订单表），`source_columns=[order_id]`，`target_columns=[customer_id]`。
- 员工 汇报给 员工（自关联，多对一，外键在员工表）：`table_name=null`，`source_columns=[employee_id]`，`target_columns=[manager_id]`。
- 学生 选修 课程（多对多）：`table_name=enrollments`，`source_columns=[student_id]`，`target_columns=[course_id]`。
- 发货 对应 订单明细（订单明细主键为 `order_id + line_no`）：`table_name=null`（发货表），`source_columns=[shipment_id]`，
  `target_columns=[order_id, line_no]`。

连接条件统一为：关系源表与源对象表按“源列 = 源主键”连接，与目标对象表按“目标列 = 目标主键”连接（多列时逐列 AND）；
关系源表与某一端是同一张表时省掉那次连接。**连接方式按用途决定**：

| 用途 | 连接方式 | 原因 |
|---|---|---|
| 指标、问数（从粒度对象出发沿路径走） | **LEFT JOIN** | 必须保留每一个粒度对象，再按条件过滤或聚合。用内连接会先删掉“没有关联对象”的粒度对象：例如“没有上级的员工数”（条件 `manager.employee_no is_null`），内连接结果永远是 0 |
| 浏览某个实例的关联实例（如“这张订单的客户”） | 内连接 | 只列确实存在的关联 |

指标里沿路径的条件写在 `WHERE` 或聚合内的 `CASE WHEN` 中，不写进连接条件。

### 3.5 规则 `Rule`

同 v2：`id, name, technical_name, description, owner_kind, owner_id, rule_kind (constraint | derivation), expression, evidence`。
`owner_kind` 为 `object_type / property / link_type / action`。**删除** `verbalizes`，自然语言说明写在 `description`。
v3 中概念上重复存储的 `requires: list[UUID]`、`derived_by: list[UUID]` 不再存在，规则只存在 `rules` 集合。

**表达式写法**：ANSI SQL，用文字路径引用：`对象.属性`、`对象.关系.属性`，第一段是规则所属的对象
（属性、关系上的规则，第一段是其所属对象），每一段的含义与指标的路径（§3.6）相同。平台不执行规则，只检查路径中的对象、关系、属性都存在。
规则保留 SQL 文本，因为约束和派生的形式比指标多得多，结构化成本太高。例：

```sql
-- 属性 sales_order.amount 上的约束
sales_order.amount > 0
-- 对象 sales_order 上的约束：华东客户的订单必须有销售员
sales_order.customer.region <> '华东' OR sales_order.salesperson.employee_no IS NOT NULL
```

不使用 Ossie 的角色写法（如 `Person.parent_of(descendant)`）。

### 3.6 指标 `Metric`（新增，结构化）

指标是独立的顶层元素，不挂在某个对象下面，因为一个指标经常要跨多个对象（例如“华东区客户的订单金额”同时用到订单和客户）。
指标**不写 SQL**，而是用结构化字段描述：聚合方式、聚合哪个属性、过滤条件。这和 dbt MetricFlow、Cube、LookML 等语义层的做法一致。

#### 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id`、`name`、`technical_name`、`description`、`synonyms`、`evidence` | | |
| `kind` | `simple` / `ratio` | 简单指标或比率指标 |
| `value_kind` | enum | 结果类型，**由平台推导**，不由用户决定：`count / count_distinct` → `integer`；`sum / min / max` → 被聚合属性的类型；`avg` → `decimal`；`ratio` → `decimal`。文件里写的值必须与推导结果一致 |
| **简单指标** | | |
| `base_type_id` | UUID | 粒度对象，即“按什么来数”。例如订单金额的粒度是订单，客户数的粒度是客户 |
| `aggregation` | enum | `sum / avg / min / max / count / count_distinct` |
| `measure` | Path / null | 被聚合的属性。`count` 时为 null，表示数粒度对象本身；其余必填 |
| `filters` | list[Condition] | 过滤条件，全部同时满足（AND）；可为空 |
| **比率指标** | | |
| `numerator_id`、`denominator_id` | UUID | 分子、分母各引用一个简单指标，两者粒度对象必须相同。比率按**小数**相除：两边先转成 `DECIMAL(38, 10)` 再除，分母为 0 时结果为空；`value_kind` 固定为 `decimal`。平台查询、MCP 给出的 SQL、Ossie 导出都用这一条，避免两边都是计数时发生整数除法（1 / 2 得 0） |

**Path（路径）**：从粒度对象出发，沿关系走到某个属性。

```json
{ "links": [<关系 id>, ...], "property_id": <属性 id> }
```

- `links` 为空表示粒度对象自己的属性；每一跳都必须**沿关系正向**（从源到目标）走一条多对一或一对一关系，
  这样连表后仍是一行一个粒度对象，聚合不会重复计算。不允许反向走：反向走一对一的自关联时分不清方向，
  需要时以另一端为粒度，或者把关系建在另一个方向。
- 用 id 引用，对象、关系、属性改名后指标不受影响。界面和导出时显示为 `sales_order.customer.region` 这样的文字路径。

**Condition（条件）**：

```json
{ "path": <Path>, "operator": "eq", "values": ["华东"] }
```

`operator` 为 `eq / ne / gt / ge / lt / le / in / not_in / between / is_null / not_null`；`values` 的个数由运算符决定
（`between` 两个，`in / not_in` 至少一个，`is_null / not_null` 零个），值的类型须与属性的 `value_kind` 一致。
暂不支持“或”（OR），需要时拆成多个指标或以后扩展。

#### 例子

对象 `sales_order`（订单，标识属性 `order_no`，属性 `amount`、`status`），对象 `customer`（客户，标识属性 `customer_no`，属性 `region`），
关系 `sales_order.customer`（订单 → 客户，多对一）。路径按文字形式书写，实际存的是 id。

| 指标 | kind | 粒度 | aggregation | measure | filters |
|---|---|---|---|---|---|
| 订单金额 | simple | 订单 | sum | `sales_order.amount` | |
| 订单数 | simple | 订单 | count | — | |
| 已完成订单数 | simple | 订单 | count | — | `sales_order.status eq 已完成` |
| 华东区订单金额 | simple | 订单 | sum | `sales_order.amount` | `sales_order.customer.region eq 华东` |
| 下单客户数 | simple | 订单 | count_distinct | `sales_order.customer.customer_no` | |
| 客户数 | simple | 客户 | count | — | |
| 客单价 | ratio | 订单 | — | 分子：订单金额，分母：下单客户数 | |

存储形式（华东区订单金额）：

```json
{
  "kind": "simple",
  "name": "华东区订单金额", "technical_name": "east_order_amount",
  "base_type_id": "<sales_order>",
  "aggregation": "sum",
  "measure": { "links": [], "property_id": "<sales_order.amount>" },
  "filters": [
    { "path": { "links": ["<sales_order.customer>"], "property_id": "<customer.region>" },
      "operator": "eq", "values": ["华东"] }
  ]
}
```

#### 不放进指标定义的东西

- **按什么分组**（按月、按地区）和**时间范围**属于查询，不属于指标定义：查询时传入分组路径和条件，路径规则与上面相同，从粒度对象出发。
- 比率以外的四则运算组合（如“金额 × 汇率 − 退款”）暂不支持；真需要时再加 `derived` 类型。

#### 为什么结构化，而不是 SQL 或函数

| | 结构化 | SQL 表达式 | 函数（Palantir Function） |
|---|---|---|---|
| 平台校验 | 每个字段都能校验：路径是否只走“一”的方向、类型是否匹配 | 要解析 SQL 才能校验 | 很难 |
| 改名 | 用 id 引用，不受影响 | 表达式里的名字要跟着改 | 代码要改 |
| 生成查询 | 直接拼 SQL，可按不同数据库生成 | 要解析后改写 | 要运行环境 |
| 编辑界面 | 表单：选粒度、选聚合、选属性、加条件 | 写 SQL | 写代码 |
| AI 生成 | 填字段，出错能被校验指出 | 容易写出解析不了的 SQL | 难 |
| 导出到 Ossie | 编译成 ANSI SQL | 改写名字 | 无法导出 |

代价是表达能力有限（没有 OR、没有任意运算），但覆盖了绝大多数业务指标；不够用时再扩展类型，而不是退回 SQL。

### 3.7 数据映射 `DataMapping`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id`、`type_id`、`connection_alias`、`table_name`、`schema_name` | | 同 v2 |
| `key_columns` | list[str] | 主键列，至少一列；复合主键按顺序列出（取代 v2 的单列 `key_column`） |
| `fields` | {属性技术名: 列名} | 同 v2 |

`concept_mappings`、`mapping_nodes` 递归树取消。

### 3.8 草稿顶层

```text
schema_version: "core-1"
workspace_id
object_types, properties, link_types, rules, actions,
metrics, mappings, material_objects, material_links
```

**删除**的 v3 顶层字段：`hash_algorithm`、`ossie_version`、`ossie_name`、`ossie_description`、`ai_context`、
`native_presence`、`document_origin`、`core_version`、`core_presence`、`extension_v4`、`value_types`、`semantic_models`、
`datasets`、`dataset_fields`、`dataset_relationships`、`concept_mappings`、`mapping_nodes`。

### 3.9 校验

沿用 v2 `OntologyDraft.validate_graph` 的全部规则（同名、技术名冲突、继承环、属性与关系共享命名空间、规则归属、Action 引用、实例类型、映射引用），
新增：

- `data_join` 引用的表：`table_name` 为 null 时源对象必须已映射；目标对象必须已映射。
- `data_join` 的 `source_columns` / `target_columns` 长度分别等于两端对象 `key_columns` 的长度。
- 指标：`simple` 的 `measure` 与 `aggregation` 匹配（`count` 时为空，`sum / avg` 时属性须为数值类型）；
  `measure` 和 `filters` 中每条路径都从 `base_type_id` 出发，每一跳都沿关系正向走多对一或一对一关系，落在存在的属性上；
  条件的 `values` 个数和类型符合运算符与属性类型；`value_kind` 等于按聚合方式和属性类型推导出的结果类型；
  `ratio` 的分子、分母都是 `simple`、粒度对象相同，且推导出的结果类型都是数值（`integer / decimal / float`）。
  例：`MIN(customer.signed_on)` 的结果类型是 `date`，不能做比率的分子或分母。
- `inverse_name` 非空时不得与 `name` 相同。
- `rules.expression` 中的路径必须从规则所属对象出发，每段都存在。
- **标识只由属性组成**：对象的标识是它全部 `identifier=true` 的属性（含从父对象继承的），组合起来唯一。关系不参与标识，只负责连接对象。
  标识只有一个属性时，该属性必须 `unique=true`；多个属性组成的复合标识不要求各自唯一。
  例：订单明细的标识是“订单号”+“行号”两个属性，行号在不同订单里会重复，`unique=false` 合法；
  “所属订单”关系另外存在，用于从明细走到订单。这与 Palantir、Fabric 一致：主键是属性，关系另行定义。
- 技术名不能是 ANSI SQL 保留字（大小写不敏感），因为规则和指标的路径不加引号写进 SQL。

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

**合并不归适配器管**。适配器只负责把外部文档翻译成一个独立的核心模型；怎么进入草稿由平台统一处理，见 §4.5。
这样每个适配器都不需要重复实现合并和 id 保持。

### 4.2 转换报告

```python
class TranslationIssue(BaseModel):
    outcome: Literal["converted", "dropped", "placeholder", "error"]
    construct: str               # 外部格式里的构造名，例如 "Relationship(n-ary)"
    source_path: str             # 导入时为外部文档路径；导出时为核心元素路径
    target_path: str | None
    message: str                 # 中文说明

class TranslationReport(BaseModel):
    direction: Literal["import", "export"]
    adapter: str
    counts: dict[str, int]       # 各类元素的翻译数量
    issues: list[TranslationIssue]
```

| outcome | 含义 | 例子 |
|---|---|---|
| `converted` | 结构被改写，信息基本保留 | 三元关系 → 中间对象；一元关系 → 布尔属性 |
| `dropped` | 丢弃 | 读法里的同义说法、字段的 `dimension.is_time` |
| `placeholder` | 目标格式必填、平台没有对应值，写了占位串 | Ossie 适配器不会出现，见 §4.4 |
| `error` | 阻止导入或导出 | 文档不是 JSON、版本不支持、导出时模型为空 |

前端导入、导出对话框按 outcome 分组展示；报告随导入记录保存。

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
      extension.py         ai_context.ontofoundry 扩展块读写
      validator.py         官方 schema + 语义校验（沿用现有 ossie/validator.py）
      assets/vendor/       固定版本的 Ossie schema（沿用）
    native/                OntoFoundry 原生格式（§4.6）
```

API：`POST /workspaces/{id}/imports/{adapter_id}`、`GET /workspaces/{id}/exports/{adapter_id}`，
现有的 `/imports/ossie` 保留为 `adapter_id=ossie-0.2` 的别名。用一个测试保证 `domain/` 不 import `adapters/`。

### 4.4 缺失信息与占位的通用规则

导出时目标格式要求、核心模型里没有的信息，按以下顺序处理：

1. **可选字段**：直接不写。
2. **必填字段，能从核心模型推导**：推导生成（例如 Ossie 的 `verbalizes` 由名称生成）。
3. **必填字段，推导不出，且目标字段是自由文本、不受语义校验**：写占位串 `"不支持"`，报告 `placeholder`。
4. **必填字段，推导不出，且目标字段受校验**（枚举、表达式、引用、类型）：不导出该元素，报告 `dropped`。不得写占位串，否则导出文件过不了官方校验。

导入时外部文档有、核心模型没有落点的信息，一律**不读**，报告 `dropped`。

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
   选择导入方式：
   - **补充**（默认）：只新增和修改，文件里没有的已有元素保持不动。
   - **以文件为准**：额外为文件里没有的已有元素生成删除提案。
2. 用户确认后，平台：
   - 把原文件保存为一份材料（§13.4）；
   - 新建一个建模会话，标题“导入 <文件名>”，基于当前已发布版本；
   - 把适配器产出的核心模型和会话草稿逐元素对比，找出每个导入元素对应草稿里的哪个元素，生成一批提案：
     对应不上的 → create；内容不同的 → update（含改名）；“以文件为准”时草稿有、文件没有的 → delete。匹配方式按格式区分：

     | 格式 | 匹配方式 |
     |---|---|
     | **原生格式** | 文件带着稳定 UUID，**分两轮匹配，结果必须一对一**：<br>① 先对**全部**导入元素按 UUID + 元素类型匹配，对上的双方都锁定；技术名不同算改名（update）。<br>② 再在**两边都未锁定**的元素之间按技术名匹配（规则见下行）；匹配上就沿用草稿里的 id，并把文件里对这个元素的引用改成该 id。<br>③ 仍对不上的保留文件里的 UUID 新建。<br>例：文件有 `alpha(id1)`、`beta(id2)`，草稿只有已改名为 `beta` 的 `id1`。第①轮 `alpha` 锁定 `id1`（改名回 `alpha`）；第②轮 `beta(id2)` 找不到未锁定的 `beta`，按③新建，但它的技术名与 `id1` 当前的名字 `beta` 冲突，按下面的冲突规则报告，不会把两个导入元素都对应到 `id1` |
     | **Ossie 等外部格式** | 文件里没有我们的 UUID（适配器生成的 id 只在本次有效），**按技术名匹配**：对象按 `technical_name`，属性和关系按 `所属对象.technical_name`，规则按 `归属.technical_name`，指标按 `technical_name` |

     冲突不硬套，逐条报告、不生成该元素的提案，由用户处理：
     - UUID 在本工作空间登记过、但类型不同（元素身份表规定 id 不跨类型复用）；
     - 按 UUID 对应后改出来的技术名，或新建元素的技术名，与草稿里另一个元素冲突。
     元素身份按工作空间登记，同一个原生文件导入到别的工作空间时 UUID 可以原样使用。
   - 每条提案附材料证据，指向原文件里对应的行；
   - 提案批次的 `producer_json` 记为 `{"kind": "import", "adapter": "ossie-0.2", "report_id": ...}`，和 agent 产出的批次区分。
3. 跳转到该会话。用户在提案面板审阅：可以逐条接受，也可以用已有的“全部接受”；然后照常在发布面板发布。
4. 会话里显示“用 AI 补全 N 项”（§13.4），在同一个会话里发起一次建模运行，补全提案和导入提案放在一起审阅。

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
  "format": "ontofoundry", "schema_version": "core-1", "exported_at": "2026-10-14T08:00:00Z",
  "materials": [
    { "material_id": "mat_returns_jan", "name": "1月退货登记.md", "sha256": "3f1c…", "byte_size": 2048,
      "path": "materials/3f1c….md" }
  ]
}
```

单文件形式就是 `{ "format", "schema_version", "exported_at", "draft" }` 四个字段。

**导出**：核心模型原样写入 `draft.json`，包括规则名、动作、指标、映射、实例、证据。完整包把**被任何证据引用**的材料（含导入时保存的原 Ossie 文件）
按原字节打进 `materials/`，文件名用 sha256，manifest 记录材料 id、名称、哈希和大小。没被引用的材料不打包。

**导入**（同样走提案，§4.5）：

1. 校验 `schema_version`；完整包逐个校验材料文件的 sha256 与 manifest 一致，不一致整包拒绝。
2. **重建材料**：按 sha256 在目标工作空间查找同内容的材料（材料表对 `workspace_id + sha256` 唯一），有就复用；没有就用包里的原文件新建，
   照常切分。得到“包内材料 id → 目标材料 id”的对照表。
3. **重写证据引用**：所有材料证据的 `material_id` 按对照表改成目标 id；`material_sha256` 不变，行号和原文不变（内容相同，行号仍然有效）。
4. 人工证据原样保留；`created_by` 是导出环境的用户 id，目标环境不一定有这个用户，界面按原值显示，不做映射。
5. 单文件形式没有材料：证据引用的材料在目标工作空间按 sha256 找得到就重写引用，找不到就丢弃该证据并报 `dropped`。

各种场景和边界情况的完整示例见 [`core-1-examples/`](core-1-examples/README.md)（示例是 `draft.json` 部分的写法）。

---

## 5. Ossie 适配器：导入

适用版本：`ontology/ontology.json` 的 `version = "0.2.0.dev0"`。其他版本报 `error`。
只包含 `semantic_model`、没有 `ontology` 的 OSI core-spec 独立文档：报 `error`（没有可导入的业务对象）。

### 5.1 文档层

| Ossie | 导入 | 说明 |
|---|---|---|
| `version` | 校验 | 不是 `0.2.0.dev0` 报 `error` |
| `name`、`description` | 不读，记入报告 | 模型名称取工作空间自身 |
| `requires` | `dropped` | 核心模型没有工作空间级约束；原文留在报告里，可由 AI 补全改写成具体元素上的规则（§13.4） |
| `ai_context`（字符串） | `dropped` | |
| `ai_context.ontofoundry` | 读取，见 §5.7 | 平台自己导出的扩展块 |
| `ai_context` 其他键（`synonyms`、`instructions`、其他厂商键） | `dropped` | |
| `ontology` | 见 §5.2–5.4 | |
| `ontology_mappings` | 见 §5.5–5.6 | |

### 5.2 概念

| Ossie | 导入 | 说明 |
|---|---|---|
| `EntityType` | → `ObjectType` | `concept` → `technical_name`（不合规的字符替换为 `_`，冲突加后缀，报 `converted`）；`name` 取扩展块显示名，没有则用 `concept` |
| `description` | → `description` | |
| `extends`（实体） | → `extends` | |
| `extends`（值概念或内置类型） | `dropped` | 实体不能继承值 |
| `identify_by` | 全部成员都是属性时：这些属性 `identifier=true` | 标识**整组翻译或整组放弃**，不裁剪：只要有一个成员是关系（Ossie 允许用关系做标识）或引用不存在，整组标识都不导入，所有成员属性都不设 `identifier`、`unique` 保持原样，关系照常作为普通关系导入，报告“标识待补全”（RT-32）。否则裁剪后剩下的单个属性会被当成唯一标识，与它 `unique=false` 冲突。<br>只有一个属性成员时，该属性设 `unique=true`：Ossie 的 `identify_by` 本身就表示能用它唯一找到对象；原文的 `multiplicity` 不是 `OneToOne` 时报 `converted`（RT-33） |
| `requires` / `derived_by` | → `rules`（`owner_kind=object_type`，constraint / derivation） | 规则名取扩展块，没有则生成 `{对象名}·约束1` |
| `ValueType` | **不建元素**，折叠进属性 | 见下 |

**值概念折叠**：属性的 `value_kind` 沿值概念的 `extends` 链找到第一个内置类型
（`String / Integer / Decimal / Float / Boolean / Date / DateTime`）；找不到则用 `string` 并报 `converted`。
值概念本身不保留：名字、`description`、`extends` 链、`requires`、`derived_by`、`identify_by`、`relationships` 全部 `dropped`（RT-23、RT-24）。

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
| `name` | → `technical_name`；显示名取扩展块，没有则见下方读法 |
| `description` | → `description` |
| `requires` / `derived_by` | → `rules`（owner 为对应的属性 / 关系 / 中间对象） |
| `roles[].name` | `dropped`（只在读法里有用） |
| `verbalizes` | 提取动词，见下；其余 `dropped` |

**读法提取**（仅 b 和 d）：

- b：第一条形如 `{源…}文字{目标…}` 的读法，若扩展块没有显示名，则“文字”作为 `name`；
  第一条形如 `{目标…}文字{源…}` 的读法，“文字”作为 `inverse_name`。其他读法 `dropped`。
- d：第一条形如 `{owner}文字` 的读法，若扩展块没有显示名，则“文字”作为属性 `name`。
- a：读法全部 `dropped`，导出时重新生成。

**multiplicity**：

| 情况 | `ManyToOne` | `OneToOne` | 缺省 |
|---|---|---|---|
| a. 属性 | `unique=false` | `unique=true` | `unique=false` |
| b. 二元关系 | `many_to_one` | `one_to_one` | `many_to_many` |
| c. 多元关系 | `dropped`（Ossie 对多元基数的含义不明确） | 同左 | — |

**c. 多元关系 → 中间对象**。例：

```json
{ "concept": "supplier", "type": "EntityType",
  "relationships": [{
    "name": "supplies",
    "roles": [{ "concept": "part" }, { "concept": "project" }, { "concept": "Integer", "name": "quantity" }],
    "verbalizes": ["{supplier}向{project}供应{part}，数量{Integer:quantity}"]
  }] }
```

导入为：

| 核心元素 | 技术名 | 说明 |
|---|---|---|
| 业务对象 | `supplier_supplies` | 命名 `{owner}_{关系名}`，冲突加后缀；显示名取扩展块，没有则用关系名；描述注明“由多元关系 supplier.supplies 转换” |
| 关系 | `supplier_supplies.supplier` → `supplier` | 多对一 |
| 关系 | `supplier_supplies.part` → `part` | 多对一 |
| 关系 | `supplier_supplies.project` → `project` | 多对一 |
| 属性 | `supplier_supplies.quantity` | `integer`；值概念 / 内置类型角色变成中间对象的属性 |

- 指向实体的角色变成中间对象到该实体的多对一关系，技术名取角色名，没有则取角色概念名。
- 中间对象导入时**没有标识**：原文只说明了参与方，没有可作为标识的属性，不编造。导入报告提示“中间对象缺少标识”，
  由用户或 AI 补全为它加上参与方编号等属性并设为标识（如供应商编码 + 零件号 + 项目编码）。
- 原关系上的 `requires` / `derived_by` 挂到中间对象上，表达式原文保留，并报 `converted`：表达式里对原关系名的引用可能不再成立。
- 原关系的读法 `dropped`。
- 导出时**不还原**成多元关系，中间对象按普通实体导出。

**d. 一元关系 → 布尔属性**。例：`customer` 上的 `{ "name": "is_vip", "verbalizes": ["{customer}是VIP"] }`
导入为属性 `customer.is_vip`，`value_kind=boolean`，名称“是VIP”。导出时按普通布尔属性导出，不还原成一元关系。

### 5.4 工作空间级约束和规则

- 文档 `requires`：`dropped`（RT-04）。
- 各元素的 `requires` / `derived_by` → `rules`，规则名按 `{元素名}·约束1` / `{元素名}·派生1` 生成，技术名按 `constraint_1` 等生成。
- 表达式里的引用能按 §3.5 的路径写法解析的，原文导入；解析不了的（如 Ossie 角色写法 `Person.parent_of(descendant)`），规则 `dropped`，原文留在报告里，交给 AI 补全改写（RT-31）。
- 归属元素被 `dropped` 时，其规则一并 `dropped`。

### 5.5 数据映射

每个 `OntologyMap` 的 `name`（没有则用 `semantic_model.name`）作为 `connection_alias`。只识别下列模式，其余 `dropped`：

| 模式 | Ossie 形状 | 导入为 |
|---|---|---|
| 对象映射（单列主键） | `concept_mappings[]` 中实体概念恰好 1 个 `object_mappings`，`expression` 为 `dataset.字段`（或单列），与该 dataset 的 `primary_key` 对应 | `DataMapping`：`source` 按最后一个 `.` 拆成 `schema_name` / `table_name`，`key_columns = [主键列]` |
| 对象映射（复合主键） | 恰好 1 个 `object_mappings`，没有 `expression`，`referent_mappings` 为一层平铺列表，每项 `relationship` 是该概念 `identify_by` 中的一项、`expression` 为 `dataset.字段` | `key_columns` 按 `identify_by` 顺序列出这些列；`relationship` 是属性时同时写入 `fields`；是关系时（Ossie 允许用关系做标识），该列只作为主键列和这条关系 `data_join` 的目标列，不产生标识属性 |
| 属性列 | `link_mappings` 根节点的 `object_mapping` 指向主键，`children[].relationship` 为属性名，`object_mapping.expression` 为 `dataset.字段` | `fields[属性] = 列`；也接受旧平台扩展 v1 写出的扁平形式 |
| 外键关系 | `children[].relationship` 为二元关系名，`object_mapping.concept` 为另一端；或 `semantic_model.relationships` 中 `from` / `to` 分别是两端的 dataset | `data_join`：`table_name` 为外键所在 dataset 的表，源列 / 目标列按两端主键对应 |
| 多对多 join 表 | 不映射到任何概念的 dataset，带两条 `relationships` 分别从它指向两端 dataset | 两端对象之间若恰有一条多对多关系，`data_join.table_name` 为该 dataset 的表，`source_columns` / `target_columns` 取两条 relationships 的 `from_columns`；对不上则 `dropped` |

`dataset.字段` 中的“字段”是 dataset field 名，物理列名取该 field 的 `ANSI_SQL` 表达式；表达式必须是单个列名（可带引号）。
没有被属性映射引用的字段只用于解析主键和 JOIN（平台导出的辅助字段就是这种），不导入为属性。

明确不支持（`dropped`）：

- 嵌套的 `referent_mappings`（`referent_mappings` 里再套 `referent_mappings`），以及不对应 `identify_by` 的 `referent_mappings`
- 一个概念多个 `object_mappings`
- 嵌套超过一层的 `children`
- 计算表达式（函数、运算、CASE 等）
- 只有非 ANSI 方言的字段表达式
- 值概念的 `concept_mappings`
- `unique_keys`
- `Field.dimension` / `label` / `datatype`
- 所有 dataset / field / relationship / metric 上的 `ai_context` 和 `custom_extensions`

### 5.6 指标

**不做任何推断**，只识别下列固定形式（`ANSI_SQL` 方言、只引用**一个** dataset、所引用的字段都已映射到属性）：

| Ossie 表达式 | 导入为 |
|---|---|
| `SUM(ds.f)`、`AVG(ds.f)`、`MIN(ds.f)`、`MAX(ds.f)` | `simple`，粒度 = ds 对应的对象，`aggregation` 对应，`measure` = f 对应的属性 |
| `COUNT(*)` | ❌ `dropped`：没有引用任何 dataset，确定不了粒度 |
| `COUNT(DISTINCT ds.f)` | `simple`，`aggregation = count_distinct`（平台导出的计数指标就是这种形式，见 RT-50） |

`description` 照写；`datatype` 能对应 `value_kind` 就写入。其余一律 `dropped`（RT-49）：引用多个 dataset、带 `CASE WHEN` 等条件、
四则运算、其他函数、引用未映射的 dataset 或字段、只有非 ANSI 方言。

丢弃的指标在导入报告里**保留原文**（名称、描述、各方言表达式），交给 AI 补全按结构化写法重建（§13.4）。

### 5.7 平台扩展块 `ai_context.ontofoundry`

平台导出时写入（§6.6），导入时读取，只承载**命名类信息**：显示名、反向名称、同义词、标签、必填，以及外部名到技术名的对照（`technical_names`）。其他工具可以忽略它。
只读 `version = "core-1"`；旧版本（`1`–`4`）及其他内容一律不读，整块报 `dropped`（RT-03）。

### 5.8 id

适配器按 `uuid5(workspace_id, "ossie:" + 键)` 生成确定性 id，键为 `object:{concept}`、`property:{concept}.{name}`、
`link:{concept}.{name}`、`reified:{concept}.{name}`、`reified-link:{concept}.{name}.{role}`、`rule:{归属键}:{kind}:{序号}`、
`mapping:{concept}`、`metric:{map}.{name}`。合并到已有草稿时，平台按 §4.1 的技术名匹配沿用已有 id。

---

## 6. Ossie 适配器：导出

### 6.1 文档层

| Ossie 字段 | 来源 |
|---|---|
| `version` | 固定 `0.2.0.dev0` |
| `name` | 工作空间名称 |
| `description` | 工作空间描述，空则不写 |
| `ai_context` | 只写 `{ "ontofoundry": {...} }`，见 §6.6 |
| `ontology` | 见 §6.2–6.4；模型没有任何业务对象时报 `error`（Ossie 要求至少 1 个组件） |
| `ontology_mappings` | 见 §6.5；没有映射则不写 |

### 6.2 业务对象和属性

| 核心 | Ossie |
|---|---|
| `ObjectType` | `EntityType` 组件：`concept = technical_name`，`description`，`extends` = 父对象技术名 |
| `identifier=true` 的属性 | 所属组件的 `identify_by` |
| 对象上的规则 | 组件的 `requires` / `derived_by` |
| `Property` | 所属组件下的关系：`name = technical_name`，`roles = [{concept: 值概念}]` |
| 值概念 | 标识属性生成一个 `ValueType`（`extends` 内置类型），名字按下方“生成名”规则分配；普通属性直接用内置类型名 |
| 属性 `unique` | true 写 `OneToOne`，false 写 `ManyToOne` |
| 属性读法 | 生成 `{对象}的{属性名}是{值概念}` |

**外部名**：Ossie 的所有概念（业务对象、值概念、内置概念）共用一个名字空间。核心模型不为此加命名限制，由适配器给每个概念分配**外部名**：

1. 预留 Ossie 内置概念名：`Any`、`String`、`Integer`、`Decimal`、`Float`、`Boolean`、`Date`、`DateTime`。所有比较忽略大小写。
2. **业务对象**：按技术名排序，外部名默认等于技术名；与已预留的名字冲突时（如对象技术名是 `String`）依次试 `{技术名}_entity`、`{技术名}_entity_2`……，取到即预留，并在导出报告里列出改名。核心模型保证对象技术名之间不冲突，所以只会和内置名冲突。
3. **值概念**：再按“对象技术名、属性技术名”排序，依次为每个标识属性取候选名 `{对象外部名}_{属性}_value`；已被占用就依次试 `_value_2`、`_value_3`……
4. 概念定义、`extends`、关系的 `roles`、读法里的占位符、dataset 名、`concept_mappings.concept`、扩展块的键，一律使用外部名。
5. 外部名与技术名不同的对象，记在扩展块的 `technical_names` 里（`{外部名: 技术名}`），平台再导入时据此恢复原技术名。

例：对象 `customer_code_value` 已存在时，`customer.code` 的值概念名是 `customer_code_value_2`；`a_b.c` 与 `a.b_c` 都想用 `a_b_c_value`，
按排序 `a.b_c` 先取到，`a_b.c` 得到 `a_b_c_value_2`。顺序固定，同一模型每次导出的名字相同。
| `required`、`name`（显示名）、`synonyms`、`tags` | 只写入扩展块 |
| 属性上的规则 | 关系的 `requires` / `derived_by` |

### 6.3 关系

| `multiplicity` | 写在谁下面 | `roles` | Ossie `multiplicity` |
|---|---|---|---|
| `many_to_one` | 源对象 | `[{concept: 目标}]` | `ManyToOne` |
| `one_to_one` | 源对象 | `[{concept: 目标}]` | `OneToOne` |
| `many_to_many` | 源对象 | `[{concept: 目标}]` | 不写（Ossie 中缺省即无唯一性约束） |

- 自关联：角色名固定写 `related`，以便读法区分两个占位符。
- 读法：`[{源}name{目标}]`，有 `inverse_name` 时再加 `{目标}inverse_name{源}`。
  至少一条，满足 Ossie 必填。
- 关系上的规则 → 关系的 `requires` / `derived_by`。

### 6.4 规则和动作

- `object_type / property / link_type` 规则 → 对应 Ossie 元素的 `requires` / `derived_by`，表达式原文写出。规则名、技术名、描述不导出。
- 导出后用 Ossie 官方 lint 检查表达式，不通过的规则从文件中去掉，导出报告 `dropped`。
- `action` 规则、`actions`：Ossie 没有对应构造，不导出，报 `dropped`。

### 6.5 数据映射和指标

**字段**：Ossie 的映射表达式和关系引用的是 dataset 的**逻辑字段名**，不是物理列名
（[Ossie 规范 · Object mappings](https://github.com/apache/ossie/blob/main/ontology/ontology.md#object-mappings)）。因此：

- 每个已映射属性一个字段：字段名 = 属性技术名，表达式为 `ANSI_SQL` 方言下的物理列名。
- 主键列、外键列等**被键或 JOIN 用到、但没有属性映射到它的物理列**，声明为**辅助字段**：字段名 = 列名；
  与某个属性技术名冲突时加后缀 `_col`（仍冲突再加序号）。辅助字段只为键和 JOIN 服务。
- 下文所有 `dataset.字段` 都指逻辑字段名。一个物理列由哪个字段代表，按“有属性映射用属性字段，否则用辅助字段”确定。

例：示例 01 的客户映射 `{"customer_no": "customer_id", ...}`，主键列 `customer_id` 由属性 `customer_no` 映射，
所以对象映射写 `customer.customer_no`；订单表的外键列 `customer_id` 没有属性映射，声明辅助字段 `customer_id`，
关系写 `from_columns: ["customer_id"]`。

**生成规则**：

- 每个 `connection_alias` 生成一个 `OntologyMap`，`name` 和 `semantic_model.name` 都是该别名。
- 每个已映射对象生成一个 dataset：`name` = 对象技术名，`source` = `schema.table`，`primary_key` = 各主键列对应的字段名，
  `fields` = 属性字段 + 辅助字段。
- `concept_mappings`：
  - 单列主键：`object_mappings` 为 `[{"expression": "dataset.主键字段"}]`。
  - 复合主键：`object_mappings` 为 `[{"referent_mappings": [...]}]`，每个主键列一项，`relationship` 为映射到该列的标识属性，
    `expression` 为该列对应的字段。有主键列没有标识属性映射到它时，该对象的映射报 `dropped`。
  - `link_mappings` 根节点指向主键字段，`children` 每项 `relationship` 为属性技术名、`expression` 为 `dataset.属性技术名`。
- 外键关系（`data_join.table_name` 为某一端的表）→ `semantic_model.relationships` 一条，`from_columns` / `to_columns` 为对应字段名
  （多列时照列），外加所属对象 `link_mappings` 中的一个子节点。
- 多对多 join 表 → 为 join 表声明一个不映射到概念的 dataset（字段全是辅助字段），加两条 `relationships` 从它分别指向两端 dataset；源对象的 `link_mappings` 增加一个根节点，指向 join dataset 的源键字段，子节点为该关系，`object_mapping` 的 `concept` 为目标对象、`expression` 为 join dataset 的目标键字段。

**指标** → `semantic_model.metrics`，结构编译成 `ANSI_SQL` 表达式。导出必须让消费者**不经推断**就能确定粒度和每条路径，所以有三条前提，
任一条不满足，该指标报 `dropped`（RT-49），不导出：

1. **表达式必须引用粒度对象的 dataset**，以此表明粒度。
   - `count` 编译为 `COUNT(DISTINCT 粒度.主键字段)`，带条件时为 `COUNT(DISTINCT CASE WHEN … THEN 粒度.主键字段 END)`。
     沿正向多对一 / 一对一连接不会让粒度行变多，所以与 `COUNT(*)` 等价，同时写明了粒度。粒度对象是复合主键时无法这样写，`dropped`。
   - 其他聚合：`measure` 或某个条件直接落在粒度对象上，表达式自然引用了粒度 dataset；`measure` 和所有条件都经过关系落在别的对象上时
     （例如以订单为粒度的“下单客户数” `COUNT(DISTINCT customer.customer_no)`），表达式里没有粒度 dataset，`dropped`。
2. **每条路径在语义模型里必须唯一**：路径改写为“落脚对象的 dataset.字段”，消费者只能靠 `relationships` 从粒度 dataset 找到落脚 dataset。
   因此在**整个语义模型的关系图**里（不只是本指标用到的关系），从粒度 dataset 沿 `from → to` 方向到落脚 dataset 必须恰好只有一条路径。
   - 示例 05 的交易同时有“买方”“卖方”两条关系指向公司：哪怕指标只用了买方，`company.region` 也分不清经过哪条，`dropped`。
   - 自关联落回粒度自己的 dataset（如 `employee.manager.name` → `employee.name`），与粒度自身的字段无法区分，`dropped`。
   - 还存在另一条多跳路径能到同一 dataset（如订单 → 客户，以及订单 → 门店 → 客户），`dropped`。
3. 路径上每个对象都已映射。

另外，Ossie 的指标表达式不带连接方式，消费方可能用内连接。指标里有**经过关系的 `is_null` 条件**时（如“没有上级的员工数”），内连接会算错，导出照常进行，但在导出报告里对该指标给出警告。

  | 指标 | 编译结果 |
  |---|---|
  | sum / avg / min / max，无条件 | `SUM(sales_order.amount)` |
  | 带条件 | `SUM(CASE WHEN customer.region = '华东' THEN sales_order.amount END)` |
  | count，无条件 / 带条件 | `COUNT(DISTINCT sales_order.order_no)` / `COUNT(DISTINCT CASE WHEN sales_order.status = '已完成' THEN sales_order.order_no END)` |
  | count_distinct（`measure` 在粒度对象上） | `COUNT(DISTINCT sales_order.status)` |
  | ratio | `CAST(<分子> AS DECIMAL(38, 10)) / NULLIF(CAST(<分母> AS DECIMAL(38, 10)), 0)`；分子、分母都满足上面的前提才导出 |

再导入时（§5.6），单 dataset 的 `COUNT(DISTINCT 粒度.主键字段)` 会读成 `count_distinct` 主键属性，口径与原来的 `count` 相同（RT-50）。

### 6.6 平台扩展块

```json
"ai_context": {
  "ontofoundry": {
    "version": "core-1",
    "display_names": { "sales_order": "订单", "sales_order.amount": "金额", "sales_order.customer": "属于" },
    "inverse_names": { "sales_order.customer": "拥有" },
    "synonyms": { "sales_order": ["订单", "销售单"] },
    "tags": { "sales_order": ["核心"] },
    "required": ["sales_order.amount"],
    "technical_names": { "String_entity": "String" },
    "unsupported": [ { "path": "material_objects", "message": "Ossie 没有实例数据" } ]
  }
}
```

键一律用文件里的名字路径（`对象外部名`、`对象外部名.属性`、`对象外部名.关系`、`metric:指标`），不用 UUID：文件可读，重新导入时先用 `technical_names` 还原对象技术名，再靠技术名匹配沿用 id。
规则名、动作、实例、证据不放进扩展块，需要完整保留时用原生格式（§4.6）。

### 6.7 不导出

| 核心内容 | 原因 | 报告 |
|---|---|---|
| `evidence` | Ossie 无对应构造，且引用平台内部材料 | 不逐项报告，文档级说明一次 |
| `material_objects` / `material_links` | Ossie 没有实例数据 | `dropped` |
| `actions`、动作上的规则 | Ossie 没有动作 | `dropped` |
| 规则名、技术名、描述 | Ossie 规则只有表达式 | 不逐项报告，文档级说明一次 |
| 过不了官方 lint 的规则表达式 | | `dropped` |
| 引用未映射对象的指标 | | `dropped` |

**Ossie 导出不需要任何占位字符串**：Ossie 的必填字段（`version`、`name`、`ontology`、`concept`、`type`、关系 `name` 和 `verbalizes`、
dataset `name` 和 `source`、field `name` 和 `expression` 等）都能从核心模型推导出来。

### 6.8 校验

每次导出都跑官方 schema 校验和现有的语义校验（`ossie/validator.py`）。失败视为适配器 bug，导出报 `error`，不交付文件。

---

## 7. 总表：Ossie 构造的支持情况

| Ossie 构造 | 导入 | 导出 |
|---|---|---|
| 文档 `version` / `name` / `description` | 校验 / 不读 / 不读 | 固定值 / 工作空间名称 / 工作空间描述 |
| 文档 `requires` | ❌ dropped | — |
| 文档 `ai_context` | 只读 `ontofoundry` 键 | 只写 `ontofoundry` 键 |
| EntityType | ✅ | ✅ |
| ValueType | 折叠进属性 `value_kind`，值概念本身丢弃 | 只为标识属性生成 |
| `extends`（实体 → 实体） | ✅ | ✅ |
| `extends`（实体 → 值） | ❌ dropped | — |
| `identify_by`（全部成员是属性） | ✅ | ✅（只列标识属性） |
| 概念 / 关系的 `requires`、`derived_by` | ✅ → rules（引用解析不了的 dropped） | ✅（过不了 lint 的 dropped） |
| 属性型关系（实体 → 值） | ✅ | ✅ |
| 二元关系（实体 → 实体） | ✅ | ✅（三种基数） |
| 自关联 | ✅ | ✅（角色名 `related`） |
| 一元关系 | 🔁 布尔属性 | 不还原 |
| 多元关系 | 🔁 中间对象 | 不还原 |
| `identify_by` 含关系成员 | ❌ 整组标识不导入，报“标识待补全” | — |
| 值概念上的关系 | ❌ dropped | — |
| `roles[].name` | ❌ dropped | 只在自关联时生成 |
| `verbalizes` | 提取动词，其余 dropped | 由名称生成 |
| `multiplicity` | ✅（属性 → `unique`；多元关系 dropped） | ✅ |
| OntologyMap / SemanticModel | ✅ → `connection_alias` | ✅ |
| Dataset（单列主键） | ✅ | ✅ |
| Dataset 复合主键 | ✅（经一层 `referent_mappings`） | ✅ |
| Dataset `unique_keys` | ❌ dropped | — |
| Field（单列 ANSI 表达式） | ✅ | ✅ |
| Field 计算表达式、其他方言、`dimension`、`label`、`datatype` | ❌ dropped | — |
| OSI Relationship（外键） | ✅ → `data_join` | ✅ |
| 多对多 join 表 | ✅ | ✅ |
| `object_mappings`（单个、单列） | ✅ | ✅ |
| `link_mappings`（一层 children） | ✅ | ✅ |
| 一层 `referent_mappings`（对应 `identify_by`） | ✅ → 复合主键 | ✅ |
| 嵌套 `referent_mappings`、多层 children、多个 object_mappings | ❌ dropped | — |
| Metric（单个 dataset 上的 SUM / AVG / MIN / MAX / COUNT DISTINCT） | ✅ → 结构化指标 | ✅ |
| Metric（多个 dataset、条件、运算、`COUNT(*)` 等其他形式） | ❌ dropped（原文留在导入报告） | ✅ 结构化指标编译成 SQL（满足 §6.5 三条前提时） |
| 各处 `ai_context`、`custom_extensions` | ❌ dropped | — |
| （平台）显示名、反向名称、同义词、标签、必填 | 从扩展块读 | 写入扩展块 |
| （平台）规则名、动作 | — | ❌ 不导出（用原生格式） |
| （平台）证据、实例数据 | — | ❌ 不导出 |

✅ 支持　🔁 结构改写（报 `converted`）　❌ 不支持（报 `dropped`）

### 7.1 导入再导出的差异

Ossie 文件导入后再导出，**允许和原文件不同，但每一处不同都必须能归到下表的某条规则**。
规则编号 `RT-xx` 是固定的：导入报告的每个条目都引用这些编号，测试也按编号检查（§7.2）。

**文档层**

| 编号 | 差异 | 原文件 | 再导出 |
|---|---|---|---|
| RT-01 | 文档名称、描述换成工作空间的 | `"name": "library", "description": "图书馆"` | `"name": "<工作空间名称>", "description": "<工作空间描述>"` |
| RT-02 | 文档 `ai_context` 只剩平台扩展块 | `{"synonyms": [...], "instructions": "...", "acme": {...}}` | `{"ontofoundry": {"version": "core-1", ...}}` |
| RT-03 | 旧版本平台扩展块不读；规则名、动作等非命名信息不再写入扩展块 | `"ontofoundry": {"version": "3", "rules": ..., "actions": ...}` | `"ontofoundry": {"version": "core-1", "display_names": ...}` |
| RT-04 | 文档级 `requires` 消失 | `"requires": ["COUNT(Customer) > 0"]` | 不出现 |

**格式规范化**（不改变含义）

| 编号 | 差异 | 原文件 | 再导出 |
|---|---|---|---|
| RT-10 | 数组按名称排序：`ontology` 组件、`relationships`、`identify_by`、`extends`、dataset、field | 原文顺序 | 值概念在前、实体在后，各自按名称排序 |
| RT-11 | 空值字段省略 | `"description": ""`、`"extends": []` | 不出现该字段 |
| RT-12 | 不合规的概念名、关系名被替换 | `"concept": "order-line"` | `"concept": "order_line"` |
| RT-13 | 列名的 SQL 引号规范化 | `orders."Amount"` 与 `orders.amount` 混用 | 只在需要时加引号 |

**概念和关系**

| 编号 | 差异 | 原文件 | 再导出 |
|---|---|---|---|
| RT-20 | 读法重新生成 | `["{order}由{customer}下单", "{order}属于{customer}", "{customer}拥有{order}"]` | `["{order}属于{customer}", "{customer}拥有{order}"]`（取自 `name` / `inverse_name`，见 §5.3 读法提取） |
| RT-21 | 角色名丢失；自关联统一为 `related` | `"roles": [{"concept": "employee", "name": "manager"}]` | `"roles": [{"concept": "employee", "name": "related"}]` |
| RT-22 | 没写基数的属性补上基数 | 属性关系无 `multiplicity` | `"multiplicity": "ManyToOne"` |
| RT-23 | 值概念被替换：属性改为引用内置类型，标识属性改为引用适配器生成的值概念（§6.2 生成名） | `"roles": [{"concept": "money"}]`，`money extends Decimal` | `"roles": [{"concept": "Decimal"}]`，`money` 不再出现 |
| RT-24 | 值概念上的描述、规则、`identify_by`、关系随值概念一起丢失 | `{"concept": "money", "type": "ValueType", "requires": [...]}` | 不出现 |
| RT-25 | （已并入 RT-23，编号保留不用） | | |
| RT-26 | 一元关系变成布尔属性 | `{"name": "is_vip", "verbalizes": ["{customer}是VIP"]}` | `{"name": "is_vip", "roles": [{"concept": "Boolean"}], "multiplicity": "ManyToOne", "verbalizes": ["{customer}的是VIP是{Boolean}"]}` |
| RT-27 | 多元关系变成中间实体 | `supplier` 下的 `supplies`（3 个角色） | `supplier` 下不再有 `supplies`；新增实体 `supplier_supplies`，带 3 条关系和 `identify_by` |
| RT-28 | 多元关系的基数、读法丢失，规则移到中间实体 | `supplies` 上的 `requires` | 同一表达式出现在 `supplier_supplies` 组件上 |
| RT-29 | 不支持的构造消失：值概念上的关系、实体继承值概念、引用 `Any` 的关系 | | 不出现 |
| RT-30 | `identify_by` 中引用了已消失元素的项被删除 | `"identify_by": ["supplies", "code"]` | `"identify_by": ["code"]` |
| RT-31 | 引用无法按路径写法解析的规则消失 | `"derived_by": ["Person.parent_of(descendant)"]` | 不出现 |
| RT-32 | 含关系成员的标识整组不导入 | 座位：`"identify_by": ["acct", "seat_nr"]`（`acct` 是关系） | 座位没有 `identify_by`；`seat_nr` 是普通属性，`acct` 是普通关系 |
| RT-33 | 单属性标识补上唯一性 | `identify_by: ["nr"]`，`nr` 的 `multiplicity` 为 `ManyToOne` 或未写 | `nr` 写成 `OneToOne` |

**数据映射和指标**

| 编号 | 差异 | 原文件 | 再导出 |
|---|---|---|---|
| RT-40 | dataset 改名为对象技术名，field 改名为属性技术名 | `"datasets": [{"name": "ORD_T", "fields": [{"name": "AMT", ...}]}]` | `"datasets": [{"name": "sales_order", "fields": [{"name": "amount", ...}]}]`，`source` 和物理列不变 |
| RT-41 | OntologyMap 按 `connection_alias` 重组，描述换成生成文字 | 原 `name` / `description` | `name` 不变，`"description": "<别名> 的数据映射"` |
| RT-42 | dataset 描述换成对象描述 | dataset 自己的 `description` | 对象的 `description` |
| RT-43 | 不支持的映射消失（§5.5 不支持清单） | 嵌套 `referent_mappings`、计算表达式等 | 不出现 |
| RT-44 | 没有映射到任何概念、也不是可识别的 join 表的 dataset 消失 | | 不出现 |
| RT-45 | 字段和指标只保留 ANSI_SQL 方言 | `"dialects": [{"dialect": "ANSI_SQL", ...}, {"dialect": "SNOWFLAKE", ...}]` | 只有 `ANSI_SQL` |
| RT-46 | 字段的 `dimension`、`label`、`datatype`，dataset 的 `unique_keys` 丢失 | | 不出现 |
| RT-47 | 指标表达式随 RT-40 改写 dataset / field 名 | `SUM(ORD_T.AMT)` | `SUM(sales_order.amount)` |
| RT-48 | 语义层各处的 `ai_context`、`custom_extensions` 丢失 | | 不出现 |
| RT-49 | 不是固定形式的指标（§5.6）、导出时不满足三条前提的指标（粒度不明、路径不唯一、对象未映射，§6.5）消失 | `SUM(CASE WHEN customers.region = '华东' THEN orders.amount END)` | 不出现 |
| RT-50 | 计数指标以去重计数形式往返 | 平台导出的 `COUNT(DISTINCT sales_order.order_no)` | 再导入为 `count_distinct` 主键属性（口径不变） |
| RT-51 | 没有属性映射的键列、外键列以辅助字段出现，字段名 = 列名 | dataset 原有的字段名 | `{"name": "customer_id", "expression": …}` |

**保持不变的部分**：实体概念名（RT-12 除外）、实体继承、实体描述、属性和二元关系的名字与指向、二元关系的基数、
`identify_by`（RT-30 除外）、概念和关系上的 `requires` / `derived_by` 表达式原文（RT-28 只移动位置）、
dataset 的 `source` 和主键、物理列名。

### 7.2 让用户知道自己的文件哪里变了

不做“与原文件对比”的界面。用户看到的是：

1. **导入报告**：按文件逐项列出每个被改写、被丢弃的条目，标注 `RT-xx` 编号、原文路径和行号，原文件作为材料保存（§13.4）。
2. **规则表**（§7.1）：说明格式规范化这类全局差异（排序、空字段、读法重新生成等），不逐项列出。

**测试兜底**：适配器提供 `diff_roundtrip`，只在测试里使用。对每份样例文件（含 A/B）执行“导入 → 导出 → 对比”，
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

## 9. 实施：分三部分

### 第一部分：核心模型、增删改查、MCP

目标：平台内部全部切到核心模型，建模、编辑、发布、问数都能用。

| 内容 | 说明 |
|---|---|
| 核心模型 core-1 | §3 的全部元素和校验：二元关系、`unique`、`synonyms`、`inverse_name`、复合主键、新 `data_join`、结构化指标、路径规则、保留字检查 |
| 清空数据 | 数据库迁移清空本体相关数据（§8） |
| 增删改查 | 提案、草稿、合并、发布、元素编辑全部基于核心模型；前端删除角色、读法编辑器，增加反向名称、同义词、指标表单 |
| 查询 | 实例浏览按新 `data_join` 生成 JOIN（含多对多 join 表、复合主键）；结构化指标生成 SQL（改写 `metric_query.py`） |
| MCP | 精简为 4 个工具；`get_ontology` 返回物理绑定和指标 SQL（§14） |
| AI 建模 | 技能 `md2ossie` 改写为 `ontofoundry-modeling`；轮次提示词精简；提案合同 `target_kind` 调整（§13.3） |
| 问数 agent | 系统提示词按 §14.4 重写 |
| 删除旧代码 | v1 / v2 / v3 模型与转换、`ossie/native.py`、`ossie/extensions.py` 等（§11） |

现有的 Ossie 导入、导出依赖旧模型，第一部分期间在界面上**暂时下线**，由第二、三部分重新提供。

验收：在界面和 AI 建模里建出示例 01–08 的模型并发布；演示空间的问数示例全部答对，聚合在一次 SQL 内完成；
`domain/` 不 import 任何适配器。

### 第二部分：导入

| 内容 | 说明 |
|---|---|
| 适配器接口 | 只需导入函数：文件 → 核心模型 + 转换报告（§4.1、§4.2） |
| Ossie 导入 | 概念、属性、二元关系、值概念折叠、一元 / 多元转换、规则、扩展块（§5.1–5.4、§5.7）；映射：对象、属性列、外键、多对多 join 表、复合主键（§5.5）；单表指标（§5.6） |
| 导入走提案 | 新建会话、按技术名对比生成提案、复用提案面板和发布（§4.5）；原文件保存为材料，提案证据指向原文行号 |
| 导入报告 | 按条目列出改写和丢弃，标注 RT 编号、原文路径、行号 |
| 原生格式导入 | 单文件形式（§4.6） |

验收：样例 A/B 和示例 01–10 都能导入；导入报告做成快照测试。

### 第三部分：导出

| 内容 | 说明 |
|---|---|
| 适配器接口 | 导出函数：核心模型 → 文件 + 转换报告 |
| Ossie 导出 | 概念、属性、关系、规则、扩展块（§6.1–6.4、§6.6）；映射：逻辑字段与辅助字段、对象映射、复合主键、外键、多对多 join 表；指标：三条前提检查后编译成 SQL（§6.5） |
| 官方校验 | 每份导出跑 Ossie 官方 schema 和语义校验，不通过不交付（§6.8） |
| 原生格式导出 | 单文件形式（§4.6） |

验收：示例 01–10 导出的 Ossie 文件全部通过官方校验；导出报告列出未导出的内容；
核心模型 → Ossie → 核心模型：支持转换的内容在技术名匹配下保持约定的语义；不支持的内容按导出报告和差异规则丢失，不要求无损。

### 以后的扩展（不在三部分之内）

设计已经写清楚，等有需求再做：

| 项目 | 设计位置 | 什么时候做 |
|---|---|---|
| 原生格式完整包（打包材料、跨环境搬迁） | §4.6 | 出现跨环境搬迁需求时；之前备份靠数据库备份 |
| 往返差异对比（`diff_roundtrip` 和“每处差异都有编号”的测试） | §7.2 | 导入导出稳定后，作为回归测试补上；差异编号表现在只作为说明 |
| 导入后的 AI 补全 | §13.4 | 第二部分跑通、看到真实导入会丢什么之后 |
| 适配器注册表、格式自动识别 | §4.1、§4.3 | 有了第二个适配器时 |

---

## 10. 已确认的决定

| # | 问题 | 决定 |
|---|---|---|
| 1 | 指标 | **保留，作为独立顶层元素，结构化表达**：粒度对象 + 聚合方式 + 属性路径 + 过滤条件，另有比率指标（§3.6）。Palantir 用 Function（代码）计算指标，Fabric 的指标（DAX 度量值）放在 Power BI 语义模型里而非本体中；两家都把指标放在对象之外。我们不用 SQL 也不做 Function |
| 2 | `inverse_name` | 保留（§3.4） |
| 3 | 复合主键 | **支持**：`key_columns`、`source_columns`、`target_columns` 都是列表（§3.4、§3.7）；Ossie 中经一层 `referent_mappings` 导入导出（§5.5、§6.5） |
| 4 | 导出文档 `name` | 工作空间名称（§6.1） |
| 5 | 存量数据 | 清空，不迁移（§8） |
| 6 | 材料实例 | 保留，用于后续实例图谱 |
| 7 | 工作空间级约束 `ontology_requires` | 删除；Ossie 文档级 `requires` 导入时丢弃（RT-04） |
| 8 | 导入到工作空间 | 生成提案，复用本体构建的会话、提案面板、草稿和发布面板；空工作空间同样走提案（§4.5） |
| 9 | 关系基数 | 去掉一对多，只留一对一、多对一、多对多（§3.4） |
| 10 | 属性基数 | 改为 `unique` 开关（§3.3） |
| 11 | `value_concept` | 删除；值概念名的变化见 RT-23 |
| 12 | 平台信息的承载 | Ossie 扩展块只放命名类信息；完整保留用原生格式完整包（含材料，§4.6） |
| 13 | 与原文件对比的界面 | 不做；导入报告逐项说明，对比只用于测试（§7.2） |
| 14 | 规则表达式写法 | SQL 文本，用与指标相同含义的文字路径引用（§3.5） |
| 15 | 同义词 | 对象、属性、关系、指标都有 `synonyms` |
| 16 | 数据集 | 不在核心模型里单独建；`get_ontology` 从映射和元数据快照推导出表、列、JOIN 条件交给 agent（§14） |
| 17 | 问数取数 | MCP 只提供语义和 SQL，agent 用 DataAgent 的数据查询工具按 schema 执行；MCP 工具精简为 4 个（§14） |
| 18 | 实施顺序 | 分三部分：核心模型与增删改查与 MCP、导入、导出；完整包、差异对比、AI 补全、注册表推迟（§9） |
| 19 | 对象、属性、标识、关系 | 各自分开定义：外键列可以建成属性；标识只由属性组成；关系单独定义、不参与标识（§3.1、§3.9） |

---

## 11. 删除清单

后端：

- `domain/models_v3.py`、`domain/legacy_v1.py`，`domain/snapshot.py` 中的版本转换
- `ossie/native.py`、`ossie/extensions.py`
- `ossie/importer.py`、`ossie/compiler.py`：第一部分随旧模型删除，第二、三部分在 `adapters/ossie/` 重写
- `services/element_save.py`、`api/proposals.py`、`contracts/proposals.py`（含 `_carry_placeholders`）、`api/mcp.py`、`api/modeling.py`、`services/publish_preview.py` 中的 `schema_version` 分支
- `services/dataagent.py` 中关于 owner_ref、roles、verbalizes、endpoint_direction 的 prompt
- `ossie/compiler.py` 中的 `_resolve_readings` 及别名逻辑；导入器中读取旧版本扩展块（1–4）的代码
- `scripts/ossie_coverage_matrix.py`，由 §7 总表对应的支持矩阵测试取代
- `integrations/dataagent/skills/md2ossie`：改名改写为 `ontofoundry-modeling`（§13.3），删除 `validate_ossie.py` 及其测试；agent 系统提示词中的旧合同 B
- 只针对 v1 / v2 / v3 兼容的测试（`test_p0_v3_contract.py`、`test_p1_*`、`test_t2_postgres_migration.py` 等），逐个确认后删除或改写

前端：

- `components/VerbalizationEditor.tsx`、`lib/verbalization.ts`，换成“反向名称”输入框
- `components/OssieImportDialog.tsx` 中直接发布和跳转三方合并的逻辑，改为“看报告 → 生成提案 → 进入会话”
- `api/types.ts` 中 roles、owner_ref、native_presence、position、endpoint_direction、value_types、语义层集合等类型及相关编辑界面

文档：

- 10-08 方案、P1–P4 进度文档和覆盖矩阵文档顶部标注“已被本文取代”

---

## 12. 未来适配器（参考）

| 核心模型 | Palantir Foundry | Microsoft Fabric IQ |
|---|---|---|
| ObjectType | Object type | Entity type |
| Property | Property | Property |
| LinkType（二元） | Link type（两个 object type） | Relationship type（source / target） |
| `multiplicity`（三种） | 一对一 / 多对一 / 多对多 | 第三方资料提到有基数提示，未在官方文档核实 |
| `data_join`（`table_name` 为空 = 外键） | 外键 | 关系源表即某一端的表 |
| `data_join`（`table_name` 为 join 表） | join table 数据集 | 单独的关系源表 |
| 中间对象 | object-backed link | 中间实体类型 |
| 自关联 | 支持 | 有第三方资料称不支持（待核实），导出时需报告 |
| Rule、Action、Metric | Action / Function 等，另行设计 | 无直接对应 |

两家都只有二元关系，这也是核心模型只保留二元关系的依据之一。

---

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
| 多方参与的事实（n 元关系） | 建中间对象，例如“供货记录”，到各参与方各一条多对一关系；参与方的编号作为属性并设为复合标识；事实上的数量、日期等作为中间对象的属性 |
| 是 / 否型事实（一元关系） | 布尔属性，例如“是否VIP” |
| 一对多 | 从“多”的一端建多对一关系，`name` 写正向动词、`inverse_name` 写反向动词 |
| 多对多（无附加信息） | `many_to_many` 关系，`data_join.table_name` 填中间表 |
| 多对多（配对本身有信息） | 建中间对象，同 n 元关系 |
| 复合标识 | 多个属性同时设为标识（关系不参与标识），映射的 `key_columns` 按顺序列出 |
| 自关联 | 源和目标是同一对象，例如“员工 汇报给 员工” |
| 继承 | 子对象 `extends` 父对象，只写自己新增的属性和关系 |
| 受约束的值（Ossie 的 ValueType） | 属性的 `value_kind` + 规则，例如“币种代码是 3 位大写字母”写成该属性上的约束规则 |
| 指标 | 结构化：选粒度对象、聚合方式、被聚合的属性路径、过滤条件；比率指标引用两个同粒度的简单指标。路径只沿“指向一”的方向走 |
| 同义词 | 业务别名写进 `synonyms`（对象、属性、关系、指标都有），不写进名称或描述 |
| 规则 | 挂在具体元素上，表达式用路径写法（`sales_order.customer.region`），不用 Ossie 角色写法 |

技能里**不再出现**：`roles`、`owner_ref`、`verbalizes`、`ValueType`、`ConceptRef`、`concept_context`、`role_values`、
`owner_columns / role_columns`、`OneToMany` 相关的坑。

提示词同步改造：

- 轮次提示词（`services/dataagent.py`）只保留：结果合同（头部值、Schema 文件、create/update/delete 的写法、证据规则）、
  材料清单、MCP 连接、结果文件路径。所有建模规则移到技能。
- agent 系统提示词（`agents/agent_ontofoundry.md`）删除旧合同 B（`ontofoundry.model-result/v1`），技能名改为 `ontofoundry-modeling`。
- 提案合同 `ontofoundry.proposals/v1` 的 `target_kind` 改为：`object_type / property / link_type / rule / action / metric /
  mapping / material_object / material_link`（去掉 `value_type`，新增 `metric`）。

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
| 读法里的其他说法被丢弃 | RT-20 | 提取成关系或对象的同义词；正向 / 反向名称不贴切时改写 | update 关系、对象 |
| 角色名被丢弃 | RT-21 | 自关联或中间对象的关系名不清楚时，参考角色名改名（如“汇报给”→“上级”） | update 关系 |
| 值概念及其描述、约束被丢弃 | RT-23 / RT-24 | 描述并入属性描述；约束改写成属性上的规则 | update 属性；create 规则 |
| 引用无法解析的规则被丢弃 | RT-31 | 按路径写法改写表达式，挂到对应元素上 | create 规则 |
| 中间对象缺少标识；含关系成员的标识整组未导入 | RT-27 / RT-32 | 为对象补全标识：把参与方或外键的编号建成属性、映射到对应列，与原标识中的属性一起设为标识（如座位：账户编号 + 座位号） | create / update 属性；update 映射 |
| 值概念上的关系、实体继承值概念等不支持的构造 | RT-29 | 判断业务含义，能用核心模型表达的就提出对应元素 | create，或在回答中说明无法表达 |
| 文档 `ai_context` 里的同义词和说明被丢弃 | RT-02 | 分配到对应对象的 `synonyms` 和描述 | update 对象 |
| 文档级 `requires` 被丢弃 | RT-04 | 表达式只涉及某一个对象或关系时，改写成该元素上的规则；其余在回答中说明 | create 规则 |
| 不是固定形式的指标被丢弃（原文在报告里） | RT-49 | 按结构化写法重建：选粒度对象、聚合方式、属性路径、条件；表达不了的（如 OR、复杂运算）在回答中说明 | create 指标 |
| 计算表达式、嵌套 referent 等映射被丢弃 | RT-43 | 只在能确定对应列时提出映射修改；其余在回答中列出，交给人工 | update 映射，或说明 |
| 字段的 `label`、`dimension` 等被丢弃 | RT-46 | `label` 可作为属性显示名或同义词 | update 属性 |

不交给 AI 的条目：纯格式规范化（RT-10 至 RT-13）、文档名称和描述（RT-01）、旧扩展块（RT-03）、方言丢弃（RT-45）。
这些不影响业务含义，报告里说明即可。

**原文件的用途**：作为 AI 补全的材料和证据来源，也是导入报告行号的依据；不提供“与原文件对比”的界面（§7.2）。

### 13.5 实施

- 第一部分：技能改名改写、提示词精简、提案合同的 `target_kind` 调整、删除旧合同 B。
- 以后的扩展：导入补全（依赖第二部分的导入报告和原文件材料）。
- 验收：用样例 A/B 导入后跑一次 AI 补全，提案全部能通过平台校验；技能和提示词里不出现 §13.3 列出的旧概念。

---

## 14. 问数：MCP 提供语义，agent 拼 SQL 查数据

### 14.1 分工

| 谁 | 负责 |
|---|---|
| OntoFoundry MCP | 提供**语义**：业务对象、属性、关系、指标、规则；以及它们的**物理绑定**：表、列、列类型、JOIN 条件；把结构化指标编译成 SQL |
| 问数 agent（DataAgent） | 理解问题，用 MCP 给的语义拼 SQL，用 DataAgent 自己的**数据查询工具**连数据源执行，再用业务语言回答 |

这和 Fabric Data Agent 接 Lakehouse 的方式相同：先选定可用的表结构，加上业务说明和示例查询，再由 agent 生成 SQL
（[Microsoft Learn – Data agent data sources](https://learn.microsoft.com/fabric/data-science/data-agent-add-datasources)）。
我们的 MCP 就是那份“表结构 + 业务说明”。

**数据集不需要在核心模型里单独建**：MCP 返回的表和列描述是**推导出来的**，来自核心模型的映射（`DataMapping`、`data_join`）
加上数据资产层的元数据快照（列类型、注释），不需要用户另外维护一份。

### 14.2 MCP 工具：从 13 个精简到 4 个

现在 MCP 有 13 个工具（`get_ontology_version`、`search_ontology_types`、`get_ontology_type`、`get_ontology_graph`、`export_ontology`、
`search_objects`、`get_object`、`expand_object_graph`、`list_metrics`、`query_metric`、`get_ontology_manifest`、`list_ontology_elements`、
`get_ontology_elements`），功能重叠，agent 经常选错。精简为 4 个，建模 agent 和问数 agent 共用：

| 工具 | 作用 | 取代 |
|---|---|---|
| `search_ontology(query, kinds?)` | 按名称、同义词搜索对象、属性、关系、指标，返回候选（id、类型、名称、所属对象、一句描述）；有歧义时全部返回 | `search_ontology_types`、`list_metrics` 的搜索 |
| `get_ontology(ids?, cursor?)` | 不给 `ids`：返回版本号、各类元素数量和全部对象、关系、指标的目录（分页）。给 `ids`：返回这些元素的完整定义，**连同拼 SQL 需要的物理绑定**，见 §14.3 | `get_ontology_version`、`get_ontology_manifest`、`get_ontology_type`、`get_ontology_graph`、`list_ontology_elements`、`get_ontology_elements`，以及原计划新增的 `get_sql_context`、`compile_metric_sql` |
| `search_objects(type_id?, q?)` | 搜索**文档实例**（材料中抽取的事实） | `search_objects(source=document)` |
| `get_object(id)` | 读取一个文档实例：属性、原文证据，以及直接关联的实例 | `get_object`、`expand_object_graph` |

去掉的：

- `export_ontology`：导出 Ossie 是界面和 API 的功能，agent 用不到。
- `search_objects(source=database)`、`query_metric`：数据库查询统一由 DataAgent 的数据查询工具执行。
- `list_ontology_elements(kind=dataset / dataset_field)` 等 v3 语义层类型。

每个结果都带 `version_id`。建模运行仍由服务端固定只能读会话基于的版本；问数 agent 第一次调用后沿用返回的 `version_id`。

### 14.3 `get_ontology(ids)` 返回什么

不另设“SQL 上下文”工具，物理绑定直接作为元素定义的一部分返回。agent 读一次就既知道业务含义，也知道怎么拼 SQL。

```json
{
  "version_id": "…",
  "elements": [
    {
      "kind": "object_type", "id": "…", "name": "订单", "technical_name": "sales_order",
      "synonyms": ["销售单"], "description": "…",
      "data": { "dialect": "mysql", "schema": "dw", "table": "dw.orders", "key_columns": ["order_id"] },
      "properties": [
        { "id": "…", "name": "金额", "technical_name": "amount", "value_kind": "decimal", "synonyms": ["销售额"],
          "column": "amount", "column_type": "decimal(12,2)", "description": "含税金额，单位元" }
      ],
      "links": [
        { "id": "…", "name": "属于", "inverse_name": "拥有", "target": "客户", "multiplicity": "many_to_one",
          "join": "dw.orders.customer_id = dw.customers.customer_id",
          "note": "从订单连到客户，订单行数不变；反方向连接会让客户行变多，聚合客户属性前需去重" }
      ],
      "rules": [ { "name": "状态取值", "description": "只能是 待支付 / 已完成 / 已取消", "expression": "…" } ]
    },
    {
      "kind": "metric", "id": "…", "name": "华东区订单金额", "grain": "订单",
      "definition": { "aggregation": "sum", "measure": "sales_order.amount", "filters": ["sales_order.customer.region eq 华东"] },
      "sql": "SELECT SUM(o.amount) FROM dw.orders o LEFT JOIN dw.customers c ON o.customer_id = c.customer_id WHERE c.region = '华东'"
    }
  ]
}
```

- **`data`**：方言来自连接类型；`schema` 取映射的 `schema_name`，没填时取连接默认值（MySQL 为连接配置的 `database`，PostgreSQL 为 `public`）。
  DataAgent 的数据查询工具按 schema 选择查询对象，前提是它能访问同名 schema。对象没有映射时 `data` 为 null，表示“尚未对接数据”。
- **列**：只列已映射的属性；列类型、注释取自元数据快照，业务名称、描述、同义词取自核心模型。
- **`links`**：对象的关系连同 JOIN 条件（由 `data_join` 生成，多对多给出经过关系源表的两段 JOIN）和防重复计算的提示。
- **指标**：结构化定义加编译好的 SQL。需要分组或附加条件时，agent 在这条 SQL 上加 `GROUP BY` / `WHERE`，不改聚合口径。
- **数据集**不单独存在：表、列、JOIN 都由映射和元数据快照推导，不需要用户另外维护。

### 14.4 问数 agent 的工作流程（替换 `agents/agent_ontofoundry_qa.md` 的系统提示词）

1. `search_ontology` 按名称和同义词找到问题涉及的对象、属性、指标；有歧义时请用户澄清。
2. `get_ontology(ids)` 读取这些元素的定义和物理绑定。
3. 有对应指标就用它的 SQL（可加分组和条件）；否则自己拼 SQL：只用返回的表、列和 JOIN 条件，遵守基数提示；从粒度对象出发沿关系连接一律用 LEFT JOIN，条件写在 WHERE 里。
4. 用 DataAgent 的数据查询工具按返回的 `schema` 执行；统计在数据库里完成，不要拉回全部明细再自己算。
5. 用业务名称回答并说明口径；文档里的事实用 `search_objects` / `get_object` 查，并注明出处。

### 14.5 实施

- 第一部分：MCP 工具精简为 4 个；`get_ontology` 返回物理绑定和指标 SQL；更新建模 agent 与问数 agent 的提示词。
- 验收：演示空间“咖啡渠道销售”的示例问题全部通过“MCP 语义 + DataAgent 执行 SQL”答对，其中“销售额最高的客户”一次 SQL 完成，不翻页。
