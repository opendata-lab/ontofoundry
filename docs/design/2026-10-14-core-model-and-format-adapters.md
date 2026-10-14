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
| P5 | 自身往返稳定 | 核心模型 → 外部格式 → 核心模型，对核心模型里有落点的内容应当稳定（靠技术名匹配和平台扩展块）。外部格式 → 核心模型 → 外部格式**不保证**还原原文，但每处差异都必须能归到一条编号规则（§7.1），并能对具体文件列出（§7.2）。 |
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
| `metrics` | 指标 | **新增**，扁平结构，见 §3.6 |
| `mappings` | 数据映射 | 对象 → 表、主键列、属性 → 列 |
| `material_objects` / `material_links` | 材料实例 | 沿用 v2；`material_links` 只有 source / target。保留用于后续的实例图谱（Palantir 的对象和链接实例也是同样用途） |

**删除**：v2 的 `ontology_requires`（工作空间级约束）。规则必须归属具体元素，不再有不属于任何元素的约束。

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
| `multiplicity` | `one_to_one` / `many_to_one` / null | null 表示交给导出时推导 |
| `value_concept` | str / null | 仅用于导出时沿用外部文件里的值概念名，平台内部不使用 |
| `evidence` | | |

**删除**：`verbalizes`、`target_role_name`。

### 3.4 关系 `LinkType`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id`、`name`、`technical_name`、`description` | | `name` 就是正向读法里的动词，例如“下单” |
| `inverse_name` | str / null | **新增**，反向读法里的动词，例如“属于”；可空 |
| `source_type_id`、`target_type_id` | UUID | 允许相同（自关联，例如 员工 汇报给 员工） |
| `multiplicity` | enum | `one_to_one / many_to_one / one_to_many / many_to_many` |
| `identifier` | bool | 源对象是否通过本关系被标识，要求多对一或一对一 |
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
- 客户 拥有 订单（一对多，外键在订单表）：`table_name=orders`，`source_columns=[customer_id]`，`target_columns=[order_id]`。
- 学生 选修 课程（多对多）：`table_name=enrollments`，`source_columns=[student_id]`，`target_columns=[course_id]`。
- 发货 对应 订单明细（订单明细主键为 `order_id + line_no`）：`table_name=null`（发货表），`source_columns=[shipment_id]`，
  `target_columns=[order_id, line_no]`。

查询统一为：关系源表 JOIN 源对象表 ON 源列 = 源主键 JOIN 目标对象表 ON 目标列 = 目标主键（多列时逐列 AND）；
关系源表与某一端是同一张表时省掉那次 JOIN。

### 3.5 规则 `Rule`

同 v2：`id, name, technical_name, description, owner_kind, owner_id, rule_kind (constraint | derivation), expression, evidence`。
`owner_kind` 为 `object_type / property / link_type / action`。**删除** `verbalizes`，自然语言说明写在 `description`。
v3 中概念上重复存储的 `requires: list[UUID]`、`derived_by: list[UUID]` 不再存在，规则只存在 `rules` 集合。

### 3.6 指标 `Metric`（新增）

指标是独立的顶层元素，不挂在某个对象下面，因为一个指标经常要跨多个对象（例如“华东区客户的订单金额”同时用到订单和客户）。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id`、`name`、`technical_name`、`description` | | |
| `base_type_id` | UUID | 指标的粒度对象，即“按什么来数”。例如订单金额的粒度是订单，客户数的粒度是客户 |
| `expression` | str | ANSI SQL 聚合表达式，引用**从粒度对象出发的路径**，见下 |
| `value_kind` | enum / null | |
| `evidence` | | |

**路径写法**：`粒度对象.属性`，或经由关系跳到其他对象：`粒度对象.关系.属性`、`粒度对象.关系.关系.属性`。例：

```sql
-- 粒度：订单
SUM(order.amount)
SUM(CASE WHEN order.customer.region = '华东' THEN order.amount END)
COUNT(DISTINCT order.customer.id)
```

- 路径中每一跳都必须是**指向“一”的一侧**（从源走多对一 / 一对一关系，或从目标反向走一对多关系），
  这样 JOIN 不会让粒度对象的行变多，聚合结果不会重复计算。
- 走关系名而不是对象名，所以同一个对象有两条关系时不会有歧义（例如 `order.buyer.level` 和 `order.seller.level`）。
- 需要“对多”方向的指标，换一个粒度对象来写。例如“每个客户的平均订单数”用订单做粒度：
  `COUNT(order.id) / COUNT(DISTINCT order.customer.id)`。

指标面向业务对象和属性，不面向表和列。查询时通过 `mappings` 和关系的 `data_join` 翻译到物理表列。
取代 v3 的 `semantic_models / datasets / dataset_fields / dataset_relationships / metrics` 五个集合。

**为什么不做成函数（Function）**：Palantir 的 Function 是 TypeScript / Python 代码，能力更强，但平台要提供代码运行环境，
agent 也难以理解和生成。指标是声明式 SQL，平台能校验、能翻译成查询，agent 也能直接读懂。
以后真需要带参数的计算，可以另加 Function 元素，指标保持不变。

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
- `metrics.expression` 中的路径必须从 `base_type_id` 出发，每一跳都指向“一”的一侧，最后落在一个存在的属性上。
- `inverse_name` 非空时不得与 `name` 相同。

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
    def diff_roundtrip(self, original: bytes, exported: bytes) -> list[RoundTripDiff]: ...  # 每处差异带规则编号，见 §7.2

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
   - 把适配器产出的核心模型和会话草稿逐元素对比，按技术名匹配（对象按 `technical_name`，属性和关系按
     `所属对象.technical_name`，规则按 `归属.technical_name`，指标按 `technical_name`），生成一批提案：
     草稿里没有的 → create；内容不同的 → update；“以文件为准”时草稿有、文件没有的 → delete；
   - 每条提案附材料证据，指向原文件里对应的行；
   - 提案批次的 `producer_json` 记为 `{"kind": "import", "adapter": "ossie-0.2", "report_id": ...}`，和 agent 产出的批次区分。
3. 跳转到该会话。用户在提案面板审阅：可以逐条接受，也可以用已有的“全部接受”；然后照常在发布面板发布。
4. 会话里显示“用 AI 补全 N 项”（§13.4），在同一个会话里发起一次建模运行，补全提案和导入提案放在一起审阅。

空工作空间也走同一流程，此时全部是 create 提案，“全部接受”后发布即可。
这样导入不需要自己的合并、冲突处理和发布逻辑，全部复用提案机制；现有导入弹窗里的“直接发布 / 跳转发布页三方合并”逻辑删除。

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
| `identify_by` | 被引用的属性 `identifier=true`；被引用的二元关系 `identifier=true` | 引用不存在或被引用的是多元关系（见 §5.3 c）时 `dropped` |
| `requires` / `derived_by` | → `rules`（`owner_kind=object_type`，constraint / derivation） | 规则名取扩展块，没有则生成 `{对象名}·约束1` |
| `ValueType` | **不建元素**，折叠进属性 | 见下 |

**值概念折叠**：属性的 `value_kind` 沿值概念的 `extends` 链找到第一个内置类型
（`String / Integer / Decimal / Float / Boolean / Date / DateTime`）；找不到则用 `string` 并报 `converted`。
属性角色引用的概念名（值概念名或内置类型名）只要与导出时会自动生成的名字不同，就写入属性的 `value_concept`
（导出规则：标识属性生成 `{对象}_{属性}_value`，普通属性直接用内置类型名），从而再导出时角色引用的名字不变。
值概念自身只保留名字和最终的内置类型，`extends` 链被拉平：`A extends B extends Integer` 再导出为 `A extends Integer`。
值概念自己的 `description`、`requires`、`derived_by`、`identify_by`、`relationships` 全部 `dropped`。

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
| a. 属性 | `many_to_one` | `one_to_one` | null（导出时推导） |
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
| 关系 | `supplier_supplies.supplier` → `supplier` | 多对一，`identifier=true` |
| 关系 | `supplier_supplies.part` → `part` | 多对一，`identifier=true` |
| 关系 | `supplier_supplies.project` → `project` | 多对一，`identifier=true` |
| 属性 | `supplier_supplies.quantity` | `integer`；值概念 / 内置类型角色变成中间对象的属性 |

- 指向实体的角色变成中间对象到该实体的多对一关系，技术名取角色名，没有则取角色概念名。
- 指向实体的角色全部 `identifier=true`，即中间对象由这些参与方共同标识。
- 原关系上的 `requires` / `derived_by` 挂到中间对象上，表达式原文保留，并报 `converted`：表达式里对原关系名的引用可能不再成立。
- 原关系的读法 `dropped`。
- 导出时**不还原**成多元关系，中间对象按普通实体导出。

**d. 一元关系 → 布尔属性**。例：`customer` 上的 `{ "name": "is_vip", "verbalizes": ["{customer}是VIP"] }`
导入为属性 `customer.is_vip`，`value_kind=boolean`，名称“是VIP”。导出时按普通布尔属性导出，不还原成一元关系。

### 5.4 工作空间级约束和规则

- 文档 `requires`：`dropped`（RT-04）。
- 各元素的 `requires` / `derived_by` → `rules`，规则名、技术名、描述优先取扩展块（§5.7），表达式原文不改。
- 归属元素被 `dropped` 时，其规则一并 `dropped`。

### 5.5 数据映射

每个 `OntologyMap` 的 `name`（没有则用 `semantic_model.name`）作为 `connection_alias`。只识别下列模式，其余 `dropped`：

| 模式 | Ossie 形状 | 导入为 |
|---|---|---|
| 对象映射（单列主键） | `concept_mappings[]` 中实体概念恰好 1 个 `object_mappings`，`expression` 为 `dataset.字段`（或单列），与该 dataset 的 `primary_key` 对应 | `DataMapping`：`source` 按最后一个 `.` 拆成 `schema_name` / `table_name`，`key_columns = [主键列]` |
| 对象映射（复合主键） | 恰好 1 个 `object_mappings`，没有 `expression`，`referent_mappings` 为一层平铺列表，每项 `relationship` 是该概念 `identify_by` 中的一项、`expression` 为 `dataset.字段` | `key_columns` 按 `identify_by` 顺序列出这些列；`relationship` 是属性时同时写入 `fields`；是标识关系时，该列同时作为这条关系 `data_join` 的目标列 |
| 属性列 | `link_mappings` 根节点的 `object_mapping` 指向主键，`children[].relationship` 为属性名，`object_mapping.expression` 为 `dataset.字段` | `fields[属性] = 列`；也接受旧平台扩展 v1 写出的扁平形式 |
| 外键关系 | `children[].relationship` 为二元关系名，`object_mapping.concept` 为另一端；或 `semantic_model.relationships` 中 `from` / `to` 分别是两端的 dataset | `data_join`：`table_name` 为外键所在 dataset 的表，源列 / 目标列按两端主键对应 |
| 多对多 join 表 | 不映射到任何概念的 dataset，带两条 `relationships` 分别指向两端 | 第 4 阶段支持（§9）；之前报 `dropped` |

`dataset.字段` 中的“字段”是 dataset field 名，物理列名取该 field 的 `ANSI_SQL` 表达式；表达式必须是单个列名（可带引号）。

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

**不做任何推断**，只导入一眼就能确定含义的指标：

| 情况 | 导入 |
|---|---|
| `ANSI_SQL` 表达式只引用**一个** dataset，且该 dataset 和所引用的字段都已映射到对象和属性 | ✅ `base_type_id` = 该 dataset 对应的对象，`dataset.字段` 改写为 `对象.属性`；`description` 照写；`datatype` 能对应 `value_kind` 就写入 |
| 引用多个 dataset | ❌ `dropped` |
| 引用未映射的 dataset 或字段 | ❌ `dropped` |
| 只有非 ANSI 方言 | ❌ `dropped` |

丢弃的指标在导入报告里**保留原文**（名称、描述、各方言表达式）。以后可以把这些原文当作材料，
由平台的自动构建按核心模型的指标写法（粒度对象 + 路径）重新生成，经提案确认后再加入模型。

### 5.7 平台扩展块 `ai_context.ontofoundry`

平台导出时写入（§6.6），导入时读取，用来让“平台 → Ossie → 平台”尽量稳定。其他工具可以忽略它。

| 扩展版本 | 读取的内容 |
|---|---|
| `core-1`（本设计） | 全部，见 §6.6 |
| `1`–`3`（v2 编译器写出） | `display_names`、`tags`、`required_attributes`、`rules`（名称 / 技术名 / 描述）、`actions` |
| `4`（v3 写出） | `display_names`、`tags`、`required_properties`、`concept_context.synonyms`、`actions`；按路径或 id 能对上的才读，`ids`、`export_edits`、`legacy_mapping_ids` 忽略 |

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
| `identifier=true` 的属性和关系 | 所属组件的 `identify_by` |
| 对象上的规则 | 组件的 `requires` / `derived_by` |
| `Property` | 所属组件下的关系：`name = technical_name`，`roles = [{concept: 值概念}]` |
| 值概念 | `value_concept` 有值就用它；否则标识属性生成 `{对象}_{属性}_value`（`ValueType`，`extends` 内置类型）；普通属性直接用内置类型名。沿用现有编译器行为 |
| 属性 `multiplicity` | 有值照写；null 时，唯一的标识属性写 `OneToOne`，其余写 `ManyToOne` |
| 属性读法 | 生成 `{对象}的{属性名}是{值概念}` |
| `required`、`name`（显示名）、`synonyms`、`tags` | 只写入扩展块 |

### 6.3 关系

| `multiplicity` | 写在谁下面 | `roles` | Ossie `multiplicity` |
|---|---|---|---|
| `many_to_one` | 源对象 | `[{concept: 目标}]` | `ManyToOne` |
| `one_to_one` | 源对象 | `[{concept: 目标}]` | `OneToOne` |
| `one_to_many` | **目标对象**（从“多”的一端写） | `[{concept: 源}]` | `ManyToOne` |
| `many_to_many` | 源对象 | `[{concept: 目标}]` | 不写（Ossie 中缺省即无唯一性约束） |

- 自关联：角色名固定写 `related`，以便读法区分两个占位符。
- 读法：`[{源}name{目标}]`，有 `inverse_name` 时再加 `{目标}inverse_name{源}`；`one_to_many` 按实际所属方向书写。
  至少一条，满足 Ossie 必填。
- 关系上的规则 → 关系的 `requires` / `derived_by`。

### 6.4 规则和动作

- `object_type / property / link_type` 规则 → 对应 Ossie 元素的 `requires` / `derived_by`；名称、技术名、描述写入扩展块。
- `action` 规则、`actions`：Ossie 没有对应构造，只写入扩展块。

### 6.5 数据映射和指标

- 每个 `connection_alias` 生成一个 `OntologyMap`，`name` 和 `semantic_model.name` 都是该别名。
- 每个已映射对象生成一个 dataset：`name` = 对象技术名，`source` = `schema.table`，`primary_key = key_columns`，
  `fields` = 每个已映射属性一个字段（字段名 = 属性技术名，表达式为 `ANSI_SQL` 方言下的列名）。
- `concept_mappings`：
  - 单列主键：`object_mappings` 为 `[{"expression": "dataset.主键列"}]`。
  - 复合主键：`object_mappings` 为 `[{"referent_mappings": [...]}]`，每个主键列一项，`relationship` 为映射到该列的标识属性，
    或 `data_join` 目标列包含该列的标识关系。有主键列对不上任何标识属性或标识关系时，该对象的映射报 `dropped`。
  - `link_mappings` 根节点指向主键，`children` 列出属性列。
- 外键关系（`data_join.table_name` 为某一端的表）→ `semantic_model.relationships` 一条（`from_columns` / `to_columns` 为多列时照列），
  外加所属对象 `link_mappings` 中的一个子节点。
- 多对多 join 表 → 第 4 阶段；之前报 `dropped`。
- 指标 → `semantic_model.metrics`。dataset 名 = 对象技术名、字段名 = 属性技术名，所以路径的最后两段直接对应 `dataset.字段`：
  `order.amount` → `order.amount`，`order.customer.region` → `customer.region`，再包上
  `{"dialects": [{"dialect": "ANSI_SQL", "expression": ...}]}`。
  两条不同路径落到同一个 dataset（例如 `order.buyer.level` 和 `order.seller.level`）时，OSI 表达式无法区分，该指标报 `dropped`；
  引用未映射对象的指标也报 `dropped`。

### 6.6 平台扩展块

```json
"ai_context": {
  "ontofoundry": {
    "version": "core-1",
    "display_names": { "order": "订单", "order.amount": "金额", "order.customer": "属于" },
    "inverse_names": { "order.customer": "拥有" },
    "synonyms": { "order": ["订单", "销售单"] },
    "tags": { "order": ["核心"] },
    "required": ["order.amount"],
    "rules": { "order.amount": [{ "technical_name": "positive", "name": "金额为正", "description": "", "rule_kind": "constraint", "expression": "..." }] },
    "actions": [ ... ],
    "unsupported": [ { "path": "material_objects", "message": "Ossie 没有实例数据" } ]
  }
}
```

键一律用技术名路径（`对象`、`对象.属性`、`对象.关系`），不用 UUID：文件可读，重新导入时靠技术名匹配就能沿用 id。

### 6.7 不导出

| 核心内容 | 原因 | 报告 |
|---|---|---|
| `evidence` | Ossie 无对应构造，且引用平台内部材料 | 不逐项报告，文档级说明一次 |
| `material_objects` / `material_links` | Ossie 没有实例数据 | `dropped` |
| 多对多 join 表映射（第 4 阶段之前） | | `dropped` |
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
| ValueType | 折叠进属性 `value_kind` | 只为标识属性或 `value_concept` 生成 |
| `extends`（实体 → 实体） | ✅ | ✅ |
| `extends`（实体 → 值） | ❌ dropped | — |
| `identify_by` | ✅（属性、二元关系） | ✅ |
| 概念 / 关系的 `requires`、`derived_by` | ✅ → rules | ✅ |
| 属性型关系（实体 → 值） | ✅ | ✅ |
| 二元关系（实体 → 实体） | ✅ | ✅（四种基数） |
| 自关联 | ✅ | ✅（角色名 `related`） |
| 一元关系 | 🔁 布尔属性 | 不还原 |
| 多元关系 | 🔁 中间对象 | 不还原 |
| 值概念上的关系 | ❌ dropped | — |
| `roles[].name` | ❌ dropped | 只在自关联时生成 |
| `verbalizes` | 提取动词，其余 dropped | 由名称生成 |
| `multiplicity` | ✅（多元关系 dropped） | ✅ |
| OntologyMap / SemanticModel | ✅ → `connection_alias` | ✅ |
| Dataset（单列主键） | ✅ | ✅ |
| Dataset 复合主键 | ✅（经一层 `referent_mappings`） | ✅ |
| Dataset `unique_keys` | ❌ dropped | — |
| Field（单列 ANSI 表达式） | ✅ | ✅ |
| Field 计算表达式、其他方言、`dimension`、`label`、`datatype` | ❌ dropped | — |
| OSI Relationship（外键） | ✅ → `data_join` | ✅ |
| 多对多 join 表 | 第 4 阶段 | 第 4 阶段 |
| `object_mappings`（单个、单列） | ✅ | ✅ |
| `link_mappings`（一层 children） | ✅ | ✅ |
| 一层 `referent_mappings`（对应 `identify_by`） | ✅ → 复合主键 | ✅ |
| 嵌套 `referent_mappings`、多层 children、多个 object_mappings | ❌ dropped | — |
| Metric（ANSI，只引用一个已映射 dataset） | ✅ | ✅ |
| Metric（引用多个 dataset） | ❌ dropped（原文留在导入报告） | ✅（路径无歧义时） |
| 各处 `ai_context`、`custom_extensions` | ❌ dropped | — |
| （平台）显示名、同义词、标签、必填、规则名、动作 | 从扩展块读 | 写入扩展块 |
| （平台）证据、实例数据 | — | ❌ 不导出 |

✅ 支持　🔁 结构改写（报 `converted`）　❌ 不支持（报 `dropped`）

### 7.1 导入再导出的差异

Ossie 文件导入后再导出，**允许和原文件不同，但每一处不同都必须能归到下表的某条规则**。
规则编号 `RT-xx` 是固定的：转换报告和往返差异报告（§7.2）都引用这些编号。

**文档层**

| 编号 | 差异 | 原文件 | 再导出 |
|---|---|---|---|
| RT-01 | 文档名称、描述换成工作空间的 | `"name": "library", "description": "图书馆"` | `"name": "<工作空间名称>", "description": "<工作空间描述>"` |
| RT-02 | 文档 `ai_context` 只剩平台扩展块 | `{"synonyms": [...], "instructions": "...", "acme": {...}}` | `{"ontofoundry": {"version": "core-1", ...}}` |
| RT-03 | 旧版本平台扩展块升级为 core-1 格式 | `"ontofoundry": {"version": "3", ...}` | `"ontofoundry": {"version": "core-1", ...}` |
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
| RT-22 | 没写基数的属性补上推导出的基数 | 属性关系无 `multiplicity` | `"multiplicity": "ManyToOne"`（唯一标识属性为 `OneToOne`） |
| RT-23 | 值概念的 `extends` 链被拉平 | `A extends B`，`B extends Integer` | `A extends Integer`；`B` 若没有属性引用则消失 |
| RT-24 | 值概念的描述、规则、`identify_by`、关系丢失 | `{"concept": "money", "type": "ValueType", "requires": [...]}` | `{"concept": "money", "type": "ValueType", "extends": ["Decimal"]}` |
| RT-25 | 没有属性引用的值概念消失 | 孤立的 ValueType | 不出现 |
| RT-26 | 一元关系变成布尔属性 | `{"name": "is_vip", "verbalizes": ["{customer}是VIP"]}` | `{"name": "is_vip", "roles": [{"concept": "Boolean"}], "multiplicity": "ManyToOne", "verbalizes": ["{customer}的是VIP是{Boolean}"]}` |
| RT-27 | 多元关系变成中间实体 | `supplier` 下的 `supplies`（3 个角色） | `supplier` 下不再有 `supplies`；新增实体 `supplier_supplies`，带 3 条关系和 `identify_by` |
| RT-28 | 多元关系的基数、读法丢失，规则移到中间实体 | `supplies` 上的 `requires` | 同一表达式出现在 `supplier_supplies` 组件上 |
| RT-29 | 不支持的构造消失：值概念上的关系、实体继承值概念、引用 `Any` 的关系 | | 不出现 |
| RT-30 | `identify_by` 中引用了已消失元素的项被删除 | `"identify_by": ["supplies", "code"]` | `"identify_by": ["code"]` |

**数据映射和指标**

| 编号 | 差异 | 原文件 | 再导出 |
|---|---|---|---|
| RT-40 | dataset 改名为对象技术名，field 改名为属性技术名 | `"datasets": [{"name": "ORD_T", "fields": [{"name": "AMT", ...}]}]` | `"datasets": [{"name": "order", "fields": [{"name": "amount", ...}]}]`，`source` 和物理列不变 |
| RT-41 | OntologyMap 按 `connection_alias` 重组，描述换成生成文字 | 原 `name` / `description` | `name` 不变，`"description": "<别名> 的数据映射"` |
| RT-42 | dataset 描述换成对象描述 | dataset 自己的 `description` | 对象的 `description` |
| RT-43 | 不支持的映射消失（§5.5 不支持清单） | 嵌套 `referent_mappings`、计算表达式等 | 不出现 |
| RT-44 | 没有映射到任何概念的 dataset 消失（第 4 阶段前 join 表也在此列） | | 不出现 |
| RT-45 | 字段和指标只保留 ANSI_SQL 方言 | `"dialects": [{"dialect": "ANSI_SQL", ...}, {"dialect": "SNOWFLAKE", ...}]` | 只有 `ANSI_SQL` |
| RT-46 | 字段的 `dimension`、`label`、`datatype`，dataset 的 `unique_keys` 丢失 | | 不出现 |
| RT-47 | 指标表达式随 RT-40 改写 dataset / field 名 | `SUM(ORD_T.AMT)` | `SUM(order.amount)` |
| RT-48 | 语义层各处的 `ai_context`、`custom_extensions` 丢失 | | 不出现 |
| RT-49 | 跨多个 dataset 的指标（§5.6）、导出时路径有歧义的指标（§6.5）消失 | `SUM(CASE WHEN customers.region = '华东' THEN orders.amount END)` | 不出现 |

**保持不变的部分**：实体概念名（RT-12 除外）、实体继承、实体描述、属性和二元关系的名字与指向、二元关系的基数、
`identify_by`（RT-30 除外）、概念和关系上的 `requires` / `derived_by` 表达式原文（RT-28 只移动位置）、
dataset 的 `source` 和主键、物理列名。

### 7.2 往返差异报告

光有规则表不够，用户还需要知道**自己这份文件**具体哪里变了。为此：

1. **保存原文件**：每次导入把原始文件和导入报告一起存进导入记录。
2. **差异报告**：对一个从 Ossie 导入过的工作空间，导出对话框提供“与导入原文件对比”。
   适配器把原文件和本次导出做结构对比（RT-10 的排序差异不计），每一处差异标注对应的 `RT-xx` 编号，按编号分组展示，例如：

   ```text
   RT-20 读法重新生成      12 处   order.customer, order.items, …
   RT-27 多元关系→中间实体  1 处   supplier.supplies → supplier_supplies
   RT-40 dataset 改名      3 处   ORD_T → order, CUST_T → customer, …
   ```

   导入后被用户修改过的元素，差异标注为“导入后已修改”，与 RT 规则区分开。
3. **测试兜底**：对每份样例文件（含 A/B），测试执行“导入 → 导出 → 差异报告”，断言**每一处差异都有 RT 编号**。
   出现无法归类的差异就是适配器 bug，测试失败。新增 RT 规则必须同时更新本节表格。

---

## 8. 存量数据：清空，不迁移

平台尚未正式就绪，现有的工作空间本体数据都是测试和演示数据，**不做迁移**：

- 上线 core-1 时用一个数据库迁移清空本体相关数据：草稿、已发布版本、提案、导入记录、元素身份表、建模会话中引用旧草稿的部分。
  工作空间、成员、材料、连接配置保留。
- 只读 core-1，不保留 v1 / v2 / v3 的任何读取或转换代码。
- 演示需要的数据，用新的 Ossie 适配器从样例文件重新导入。

这样第 1 阶段不需要写任何兼容代码，`domain/legacy_v1.py`、`domain/snapshot.py` 中的版本转换、`models_v3.py` 可以直接删除。

---

## 9. 分阶段实施

| 阶段 | 内容 | 完成标准 |
|---|---|---|
| 1 | 核心模型 core-1（含复合主键、新 `data_join`、指标）；清空数据的迁移；适配器框架；Ossie 导出（以现有 v2 编译器为基础改造）；删除 v1 / v2 / v3 模型与转换代码 | 每份导出都通过官方校验；`domain/` 不 import `adapters/` 的测试通过 |
| 2 | Ossie 导入重写：概念、属性、二元关系、值概念折叠、一元 / 多元转换、外键和复合主键映射、指标、扩展块、转换报告；导入时保存原文件；往返差异报告（§7.2）；前端导入、导出对话框展示报告 | 样例 A/B 的导入报告做成快照测试；Ossie → core-1 → Ossie 的每处差异都有 RT 编号；core-1 → Ossie → core-1 在技术名匹配下无差异 |
| 3 | 提案 / 编辑 / MCP / agent prompt / 前端全部切到 core-1；删除剩余 v3 分支（见 §11） | agent prompt 中不再出现 owner_ref / roles / verbalizes；前端没有角色、读法编辑器 |
| 3+ | AI 建模技能 `ontofoundry-modeling`、提示词精简、导入补全（§13） | 样例 A/B 导入后 AI 补全的提案全部通过平台校验 |
| 4 | 多对多 join 表的映射、查询、导入导出；指标查询改为按路径翻译（改写 `metric_query.py`） | 多对多关系能查到实例；跨对象指标能查询 |

---

## 10. 已确认的决定

| # | 问题 | 决定 |
|---|---|---|
| 1 | 指标 | **保留，作为独立顶层元素**，带粒度对象，可跨对象（§3.6）。Palantir 用 Function（代码）计算指标，Fabric 的指标（DAX 度量值）放在 Power BI 语义模型里而非本体中；两家都把指标放在对象之外，我们选声明式 SQL，不做 Function |
| 2 | `inverse_name` | 保留（§3.4） |
| 3 | 复合主键 | **支持**：`key_columns`、`source_columns`、`target_columns` 都是列表（§3.4、§3.7）；Ossie 中经一层 `referent_mappings` 导入导出（§5.5、§6.5） |
| 4 | 导出文档 `name` | 工作空间名称（§6.1） |
| 5 | 存量数据 | 清空，不迁移（§8） |
| 6 | 材料实例 | 保留，用于后续实例图谱 |
| 7 | 工作空间级约束 `ontology_requires` | 删除；Ossie 文档级 `requires` 导入时丢弃（RT-04） |
| 8 | 导入到工作空间 | 生成提案，复用本体构建的会话、提案面板、草稿和发布面板；空工作空间同样走提案（§4.5） |

---

## 11. 删除清单

后端：

- `domain/models_v3.py`、`domain/legacy_v1.py`，`domain/snapshot.py` 中的版本转换
- `ossie/native.py`、`ossie/extensions.py`
- `ossie/importer.py` 中 v3 路径（第 2 阶段整体重写）
- `services/element_save.py`、`api/proposals.py`、`contracts/proposals.py`（含 `_carry_placeholders`）、`api/mcp.py`、`api/modeling.py`、`services/publish_preview.py` 中的 `schema_version` 分支
- `services/dataagent.py` 中关于 owner_ref、roles、verbalizes、endpoint_direction 的 prompt
- `ossie/compiler.py` 中的 `_resolve_readings` 及别名逻辑
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
| `multiplicity` | 一对一 / 多对一 / 多对多 | 第三方资料提到有基数提示，未在官方文档核实 |
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
| 多方参与的事实（n 元关系） | 建中间对象，例如“供货记录”，到各参与方各一条多对一关系，参与方关系都设为标识；事实上的数量、日期等作为中间对象的属性 |
| 是 / 否型事实（一元关系） | 布尔属性，例如“是否VIP” |
| 一对多 | 从“多”的一端建多对一关系，`name` 写正向动词、`inverse_name` 写反向动词 |
| 多对多（无附加信息） | `many_to_many` 关系，`data_join.table_name` 填中间表 |
| 多对多（配对本身有信息） | 建中间对象，同 n 元关系 |
| 复合标识 | 多个属性或关系同时设为标识，映射的 `key_columns` 按顺序列出 |
| 自关联 | 源和目标是同一对象，例如“员工 汇报给 员工” |
| 继承 | 子对象 `extends` 父对象，只写自己新增的属性和关系 |
| 受约束的值（Ossie 的 ValueType） | 属性的 `value_kind` + 规则，例如“币种代码是 3 位大写字母”写成该属性上的约束规则 |
| 指标 | 指定粒度对象，表达式用从粒度对象出发的路径，只沿“指向一”的方向走 |
| 同义词 | 业务别名写进 `synonyms`，不写进名称或描述 |

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
| 值概念的描述、约束被丢弃 | RT-24 | 描述并入属性描述；约束改写成属性上的规则 | update 属性；create 规则 |
| 值概念上的关系、实体继承值概念等不支持的构造 | RT-29 | 判断业务含义，能用核心模型表达的就提出对应元素 | create，或在回答中说明无法表达 |
| 文档 `ai_context` 里的同义词和说明被丢弃 | RT-02 | 分配到对应对象的 `synonyms` 和描述 | update 对象 |
| 文档级 `requires` 被丢弃 | RT-04 | 表达式只涉及某一个对象或关系时，改写成该元素上的规则；其余在回答中说明 | create 规则 |
| 跨多个 dataset 的指标被丢弃（原文在报告里） | RT-49 | 按核心模型写法重写：选粒度对象、写路径表达式 | create 指标 |
| 计算表达式、嵌套 referent 等映射被丢弃 | RT-43 | 只在能确定对应列时提出映射修改；其余在回答中列出，交给人工 | update 映射，或说明 |
| 字段的 `label`、`dimension` 等被丢弃 | RT-46 | `label` 可作为属性显示名或同义词 | update 属性 |

不交给 AI 的条目：纯格式规范化（RT-10 至 RT-13）、文档名称和描述（RT-01）、扩展块升级（RT-03）、方言丢弃（RT-45）。
这些不影响业务含义，报告里说明即可。

**和 §7.2 的关系**：保存原文件现在有了明确用途（AI 补全的材料和证据来源），所以第 2 阶段保留“导入时保存原文件”；
导入后“与原文件对比”的用户界面仍按需再做。

### 13.5 实施

- 第 3 阶段：技能改名改写、提示词精简、提案合同的 `target_kind` 调整、删除旧合同 B。
- 第 3 阶段之后：导入补全（依赖第 2 阶段的导入报告和原文件材料）。
- 验收：用样例 A/B 导入后跑一次 AI 补全，提案全部能通过平台校验；技能和提示词里不出现 §13.3 列出的旧概念。
