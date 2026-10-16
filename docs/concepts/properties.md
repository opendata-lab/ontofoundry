# 属性

[概念概览](README.md) · [主设计文档 §3.3、§3.7](../design/2026-10-14-core-model-and-format-adapters.md)

本文说明 core-1 的目标模型与行为，状态为设计定稿、待实施。JSON 示例中的业务和数据来源均为虚构；片段不是完整导入包，完整包形式见[格式与转换](formats.md)。字段表逐项说明何时填写、空值与默认行为。

## 1. 概述

一张订单数量为 2、单价为 30，它的金额可以计算为 60。数量、单价和这张订单的金额都是属性：它们各自描述一个实例上的一个值。属性的类型说明值怎样理解，绑定说明值来自哪一列或同行计算，两者分别保存。

需要展示、过滤或计算单个实例的值时使用属性。需要把多张订单金额加起来时，定义指标。每行已有的覆盖率和近三月统计值仍可作为属性；不要把跨行的 SUM 塞进属性绑定。

## 2. 字段

| 字段 | 类型 | 填写要求 | 说明 |
|---|---|---|---|
| `id` | UUID | 必须提供。 | 此字段保存定义的稳定身份，改名不会改变它。 |
| `owner_type_id` | UUID | 必须提供。 | 此字段引用定义该属性的对象，继承时保持原归属。 |
| `name` | 字符串 | 必须提供。 | 这是向用户显示的业务名称。 |
| `technical_name` | 字符串 | 必须提供。 | 这是所属对象内用于引用的技术名。 |
| `description` | 字符串 | 可以省略。 | 此字段解释业务含义、范围和必要上下文。 |
| `value_kind` | 枚举 | 必须提供。 | 此字段选择 string、integer、decimal、float、boolean、date 或 datetime，说明值的业务类型。 |
| `required` | 布尔值 | 可省略，默认 false。 | 此字段声明业务上是否必须有值，默认 false，平台不扫描数据库验证。 |
| `identifier` | 布尔值 | 可省略，默认 false。 | 此字段声明属性是否参与业务标识元组，默认 false。 |
| `unique` | 布尔值 | 可省略，默认 false。 | 此字段声明单个属性是否足以唯一识别实例，默认 false。 |
| `synonyms` | 字符串数组 | 可省略，默认空数组。 | 这些业务别名用于搜索和问答理解。 |
| `evidence` | Evidence 数组 | 可省略，默认空数组。 | 这些证据说明该定义的业务依据。 |


## 3. 例子

下面给出订单金额的完整属性定义与绑定片段。`owner_type_id` 是[订单对象](object-types.md)的 id；其他映射字段见[完整销售样例](../design/core-1-examples/01-basic-sales.json)。

```json
{
  "properties": [
    {
      "id": "00000000-0000-4000-8000-000000002012",
      "owner_type_id": "00000000-0000-4000-8000-000000001002",
      "name": "金额",
      "technical_name": "amount",
      "description": "含税金额，单位元",
      "value_kind": "decimal",
      "required": true,
      "identifier": false,
      "unique": false,
      "synonyms": [
        "销售额",
        "订单金额"
      ],
      "evidence": []
    }
  ],
  "fields": {
    "amount": {
      "kind": "column",
      "source_id": "main",
      "column": "amount"
    }
  }
}
```

读取金额列的参考 SQL：

```sql
SELECT o.order_id, o.amount
FROM dw.orders AS o;
```

若订单金额由数量乘单价得到，FieldBinding 可改为下列形式；前提是来源元数据中这两列存在，属性的语义类型仍为 decimal。

```json
{
  "kind": "expression",
  "expression": "main.quantity * main.unit_price"
}
```

界面在订单属性行展示名称、类型和绑定；agent 查询时按物理类型调整乘法，平台不执行计算。

## 4. 建模建议

| 订单号 | 数量 | 单价 |
|---|---|---|
| O-1 | 2 | 30 |
| O-2 | 1 | 40 |

正例：同行计算金额得到 O-1=60、O-2=40，再按同样的数据集列公式定义 expression 求和得到 100。

反例：在每张订单的属性中写 SUM，会混淆单张订单值与全体金额 100。

正例：把订单数量与单价相乘建成同行计算属性，再在数据集上用 expression `SUM(orders.quantity * orders.unit_price)` 定义订单金额指标。反例：把 `SUM(main.amount)` 放入属性绑定，它跨行聚合，应为指标。

外键也可以建属性。例如订单的客户编码用于显示和过滤；订单到客户的关系另行定义。不要因为已有关系就删除仍有业务用途的编码属性。

百分比列需要先解释每行分母是什么。正例：组件覆盖率作为属性，整体覆盖率另用覆盖数量与应覆盖数量定义 ratio。反例：直接平均各组件覆盖率，并称其为整体覆盖率。

金额>=0 被订单金额和退款金额使用时生成两条属性约束；退款若使用另有>0约束的正金额，还须增加退款金额>0，祖先>=0也保留。值类型约束不自动把属性设为 required。多元值角色的例子见[示例 03](../design/core-1-examples/03-n-ary-reified.json)，多使用点与祖先约束见[示例 08](../design/core-1-examples/08-rules.json)。

## 5. 校验与限制

属性与本对象关系共享技术名空间，本地属性不能遮蔽继承项。核心只有七种标量，不新增单位、精度、时区、数组或结构体字段；有必要的业务解释写入 description，执行适配交给 agent。

单属性标识必须 unique；复合标识成员可分别不唯一。快照的 unique 声明作用于业务实例，不代表同一实例在多日历史表中只出现一次。required 或 identifier 不自动拒绝缺值的文档事实。

同行计算只引用本对象有效来源的物理列，允许算术、CASE 和受限标量函数；不允许聚合、窗口、子查询、其他对象或另一个计算属性。平台只解析引用和边界，不检查实际物理转换是否可执行。

## 6. 与 Palantir Foundry、Microsoft Fabric IQ、Apache Ossie 的对照

核查日期：2026-10-15。以下依据官方公开文档；Fabric IQ 的本体功能处于预览阶段。概念对应不表示字段、执行能力或往返行为相同，未实测外部租户。

Palantir 的 [Property](https://www.palantir.com/docs/foundry/object-link-types/properties-overview)描述对象特征，其支持的类型比本平台七种标量丰富；不能按同名直接导入所有类型。

Fabric 的 [Entity properties](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-create-entity-types)是接近概念。[新体验概览](https://learn.microsoft.com/en-us/fabric/iq/ontology/overview#alignment-with-power-bi-semantic-models)支持承接源计算列；本体内独立编写计算属性的同构入口未核实。其[元数据页](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-add-metadata)未为属性提供与实体相同的 synonyms 编辑能力，不能据此承诺与 core-1 一致。

Ossie 用[实体到值概念的关系](https://github.com/apache/ossie/blob/main/ontology/ontology.md#relationships)表示此类属性。适配器折叠到 value_kind；自身及祖先可完整改写的 requires 复制到所有使用属性（含多元值角色）作为 constraint Rule，按变量绑定改写，description 注明来源，原属性规则保留；不能改写的整条约束原文待补全。独立名称、说明和共享域等仍未承载，见 RT-23、RT-24。
