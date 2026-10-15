# 规则

[概念概览](README.md) · [主设计文档 §3.5、§5.4、§6.4](../design/2026-10-14-core-model-and-format-adapters.md)

本文说明 core-1 的目标模型与行为，状态为设计定稿、待实施。JSON 示例中的业务和数据来源均为虚构；片段不是完整导入包，完整包形式见[格式与转换](formats.md)。字段表逐项说明何时填写、空值与默认行为。

## 1. 概述

“订单金额必须大于零”是一条关于金额的约束；“大额订单须有经办人”说明订单与经办人的业务要求。规则把这些业务要求归到具体对象、属性或关系，帮助人和 agent 理解定义的边界。

需要表达约束或派生含义时使用规则，以受限 SQL 和本体路径引用已有定义。平台保存并校验引用，不执行规则。要让属性实际读出计算值，应另写属性计算绑定；要筛出 VIP 客户，应另写成员条件。只保存规则不会自动改变查询、数据库约束或业务数据。

## 2. 字段

| 字段 | 类型 | 填写要求 | 说明 |
|---|---|---|---|
| `id` | UUID | 必须提供。 | 此字段保存定义的稳定身份，改名不会改变它。 |
| `name` | 字符串 | 必须提供。 | 这是向用户显示的业务名称。 |
| `technical_name` | 字符串 | 必须提供。 | 这是归属元素内用于引用的技术名。 |
| `description` | 字符串 | 可以省略。 | 此字段解释业务含义、范围和必要上下文。 |
| `owner_kind` | 枚举 | 必须提供。 | 此字段选择规则归属为 object_type、property 或 link_type。 |
| `owner_id` | UUID | 必须提供。 | 此字段引用规则所属的具体元素，必须与 owner_kind 一致。 |
| `rule_kind` | 枚举 | 必须提供。 | 此字段用 constraint 表达约束，用 derivation 表达派生说明。 |
| `expression` | 字符串 | 必须提供。 | 此字段保存受限 SQL 表达式，本体引用按 id 解析，文字路径用于阅读。 |
| `evidence` | Evidence 数组 | 可省略，默认空数组。 | 这些证据说明该定义的业务依据。 |


## 3. 例子

以下给出对象约束的完整规则定义，依赖对象、属性和关系见[规则完整样例](../design/core-1-examples/08-rules.json)。

```json
{
  "rules": [
    {
      "id": "00000000-0000-4000-8000-000000004702",
      "name": "大额订单须有经办人",
      "technical_name": "big_order_handler",
      "description": "",
      "owner_kind": "object_type",
      "owner_id": "00000000-0000-4000-8000-000000001701",
      "rule_kind": "constraint",
      "expression": "sales_order.amount < 100000 OR sales_order.handler.employee_no IS NOT NULL",
      "evidence": []
    }
  ]
}
```

“大额订单须有经办人”从订单出发引用经办人员工号。界面将规则显示在相应对象或关系弹窗中，规则不是资源管理器的第五类；此处查看方式标为“原型阶段确认”。属性规则在属性上下文查看。

示例 08 的客户等级只保存下面的同行计算绑定及属性业务说明，不再重复保存同一算法的 derivation Rule；实际值由绑定读取：

```json
{
  "kind": "expression",
  "expression": "CASE WHEN main.total_spent >= 100000 THEN '金牌' WHEN main.total_spent >= 10000 THEN '银牌' ELSE '普通' END"
}
```

## 4. 建模建议

| 订单号 | 金额 |
|---|---|
| O-1 | 100 |
| O-2 | -5 |

正例：把“金额 > 0”挂到金额属性，可说明 O-2 不满足业务约束。

反例：以为保存规则会删掉 O-2 或阻止库中出现负数；本期平台没有执行这条规则。

正例：把“金额必须为正”挂到金额属性，表达式写 `sales_order.amount > 0`。反例：保存一条工作空间级规则，既不声明归属，也不说明哪个金额。

用 description 解释业务理由，用 expression 表达可解析条件。把业务同义词写到对应元素 synonyms，不写进规则表达式或另开 instructions 字段。

FieldBinding 决定计算属性实际读出的值；ObjectType.derived_by 与成员扩展来源共同决定子对象范围。仅在业务需要独立寻址、证据或独立说明用途时保存 derivation Rule，不要求每个计算属性重复保存公式。示例 08 的客户等级只用计算绑定；普通 Rule 不决定成员范围，也不让子对象自动变为可查询。

## 5. 校验与限制

表达式允许常量、比较、布尔组合、算术、CASE、受限标量函数和本体路径；不允许 SELECT、子查询、聚合和窗口。首段从规则上下文对象出发：对象 owner 用自身，属性用所属对象，关系用源对象；继承规则继续使用父上下文。

平台解析用于识别表达式结构的抽象语法树 AST（Abstract Syntax Tree）与 id 依赖，路径各段必须存在；技术名变化在同一提案组按依赖更新，不做全局字符串替换。规则的关系导航不直接套用 simple 指标的“只走向一”限制，但集合不能冒充标量，须有后续语法明确支持的量化形式。

Ossie 规则无法完整解析时按 RT-31 报本项 error，原文、归属和定位保留待补全，不生成非法 Rule，不覆盖已有定义；独立提案继续。派生子概念成员定义转 ObjectType.derived_by，不重复存 Rule。规则名、技术名和说明不能靠 Ossie 完整往返，应使用原生格式。

值类型自身及祖先的有效 requires 按来源去重，按变量绑定实例化到每个使用属性，含多元值角色；字符串字面量不替换，原属性规则不覆盖，继承属性不重复生成。规则 owner_kind=property、rule_kind=constraint，description 记录来源。导出作为各属性关系的 requires，不恢复 ValueType。不能改写的整条约束保留原文并待补全，来源说明不表示以后自动联动。

## 6. 与 Palantir Foundry、Microsoft Fabric IQ、Apache Ossie 的对照

核查日期：2026-10-15。以下依据官方公开文档；Fabric IQ 的本体功能处于预览阶段。概念对应不表示字段、执行能力或往返行为相同，未实测外部租户。

Palantir [Submission criteria](https://www.palantir.com/docs/foundry/action-types/submission-criteria)控制动作能否提交，有实际执行含义；与 core-1 仅保存的规则不等同。

Fabric [Business rules](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-use-rules)用自然语言并关联业务概念，供消费者理解，表达式结构与本平台不同。不能把“关联规则”理解为数据库自动执行。

Ossie [requires / derived_by](https://github.com/apache/ossie/blob/main/ontology/ontology.md#derivation-expressions)挂在概念和关系上；适配器将可解析项转换成规则，派生子概念优先按 RT-67 判定，不能同时作为普通规则和成员绑定重复导入。
