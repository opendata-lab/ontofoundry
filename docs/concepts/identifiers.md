# 标识

[概念概览](README.md) · [主设计文档 §3.2–3.4、§3.9](../design/2026-10-14-core-model-and-format-adapters.md)

本文说明 core-1 的目标模型与行为，状态为设计定稿、待实施。JSON 示例中的业务和数据来源均为虚构；片段不是完整导入包，完整包形式见[格式与转换](formats.md)。字段表逐项说明何时填写、空值与默认行为。

## 2026-10-20 命名与交换约定

对象、属性、关系、规则和指标统一使用必填 `name`（英文标识，`^[A-Za-z_][A-Za-z0-9_]*$`）和可选 `display_name`（中文名称）。名称为空时界面显示 name，名称可重复；英文标识沿用原命名空间与引用规则。Dataset 不变。关系的完整含义及角色名不变。旧数据库内容清理，不转换；旧外部文件由导入适配器转换并报告。

Ossie 导出为 ZIP：纯 Ossie 文件与 `ontofoundry-extension.json`。显示名仅在扩展 `display_names`；同义词在支持的位置用 `ai_context.synonyms`，概念和本体关系使用扩展 synonyms。单个 Ossie 文件导入显示名为空；旧版扩展块仅导入兼容。详见[命名统一设计](../design/2026-10-20-display-name-unification.md)。

## 1. 概述

订单 O-1 的第 1 行与订单 O-2 的第 1 行是两条不同明细。因此识别明细要同时使用订单号和行号，不能只看行号。业务标识就是回答“是不是同一个实例”的一组属性，由本对象及继承属性中全部 identifier=true 的项组成。

需要跨来源识别同一业务实例时定义标识；只为界面显示一个名字时使用标题属性。定义的 UUID、业务标识、来源记录键和文档事实 UUID 分别识别不同东西，不必取相同值。关系用于导航，不参与核心业务标识，也不把多个值拼成字符串冒充有类型的键。

## 2. 字段

| 字段 | 类型 | 填写要求 | 说明 |
|---|---|---|---|
| `Property.identifier` | 布尔值 | 可省略，默认 false；参与业务标识时设为 true。 | 此字段为 true 时，该属性参与业务标识。 |
| `Property.unique` | 布尔值 | 可省略，默认 false；单属性标识必须设为 true。 | 单属性标识必须声明 true，复合标识成员可以为 false。 |
| `Property.required` | 布尔值 | 可省略，默认 false。 | 此字段声明业务必填性，与唯一性分别表达，默认 false。 |
| `MappingSource.key_columns` | 有序字符串数组 | 绑定就绪时必须提供非空键列表；空列表表示绑定未完成。 | 这些列按顺序构成来源的逻辑键，与业务标识顺序分别维护。 |
| `MaterialObject.id` | UUID | 必须提供。 | 此字段保存文档对象事实身份，不用业务编号拼接生成。 |


## 3. 例子

以下是订单明细的复合标识属性，所属对象与完整映射见[复合键样例](../design/core-1-examples/04-composite-key.json)。

```json
{
  "properties": [
    {
      "id": "00000000-0000-4000-8000-000000002314",
      "owner_type_id": "00000000-0000-4000-8000-000000001302",
      "display_name": "订单号",
      "name": "order_no",
      "description": "",
      "value_kind": "string",
      "required": true,
      "identifier": true,
      "unique": false,
      "synonyms": [],
      "evidence": []
    },
    {
      "id": "00000000-0000-4000-8000-000000002311",
      "owner_type_id": "00000000-0000-4000-8000-000000001302",
      "display_name": "行号",
      "name": "line_no",
      "description": "",
      "value_kind": "integer",
      "required": true,
      "identifier": true,
      "unique": false,
      "synonyms": [],
      "evidence": []
    }
  ]
}
```

订单 O-1001 的第 1 行与订单 O-1002 的第 1 行是两个实例，行号本身不唯一。按明细键定位的参考查询：

```sql
SELECT l.*
FROM dw.order_lines AS l
WHERE l.order_id = :order_id AND l.line_no = :line_no;
```

这里假定示例表的位置和主来源键为 dw.order_lines、[order_id, line_no]，参数分别为 O-1001 和整数 1；物理键顺序由映射声明，业务标识顺序另按属性 UUID 字节序确定。

## 4. 建模建议

| 订单号 | 行号 | 商品 |
|---|---|---|
| O-1 | 1 | 纸 |
| O-2 | 1 | 笔 |

正例：用（订单号，行号）作为复合标识，得到两个不同实例。

反例：只用行号会把两条“1”合并为一个实例。

正例：订单明细把订单号和行号都设为 identifier，两个属性分别允许 unique=false。反例：只保留行号并设 unique=true，会把不同订单的第 1 行当成同一实例。

关系不参与核心标识。“所属订单”关系支持导航；订单号属性支持标识与过滤，两者可以同时存在。Ossie 导入的 identify_by 如果包含关系成员，整组标识保留为待补全，不截掉关系只留剩余属性。

数据库实例身份由实际具体 type_id 与带类型的有序键元组共同确定；物理键按主来源 key_columns 顺序解释，业务标识按属性 UUID 顺序解释。这里说明身份含义，不另定义调用载荷。反例：用 `a + '::' + b` 拼成身份，既可能发生分隔符冲突，又会丢失类型与 NULL 语义。虚拟父查询保留具体 type_id，不把设备和车辆中相同的局部键合并。

多元关系导入为中间对象。按每个实体角色的有效完整标识逐项生成同类型编号属性，值角色也生成属性；生成角色属性 required=true。ManyToOne 的键为除最后角色外的全部角色表示，含非最后值角色；无基数时全部角色构键。复合标识展开，同类型不同角色不合并。编号属性就是角色 direct 连接的 source_property_ids，target_property_ids 是参与对象的完整标识组，按项对应，关系由这组编号定义，不另加一致性 Rule。

只有映射证明外键逐项对应业务标识才绑定编号列；外键指物理键或其他候选键时，编号绑定待补全，角色关系按原映射保留。不能猜值或伪装为跨表计算列。参与对象无完整标识时不生成该角色编号属性：缺决定角色标识使中间标识整组待补全，已有其他属性也不设 identifier；ManyToOne 最后角色缺标识只使该角色编号待补全，前面完整键仍可生成。其他约束须先确认现有 Rule 语法可表达，不能表达的整项原文待补全，不夸大能力。

仓库.运往(终点仓库, 天数) ManyToOne 的键是起点仓库编码加终点仓库编码；排班(医生, 日期, 科室) ManyToOne 的键是医生编号加日期。无基数时天数或科室也参与完整元组键。导出保留中间对象，不恢复原多元结构；同元组不能靠随机 UUID 变成多次事件。

文档事实读取时依次用有效标题属性值、完整业务标识元组、可见非空材料 quote 的前 80 个字符、事实 UUID 推导 display_text。null 和空字符串无显示值，0 和 false 有值；标识按属性 UUID 顺序，缺任一项就跳过整组；多个 quote 按证据 UUID 顺序取首项，截断只影响显示。只有人工 note 或无可见引文时继续回退 UUID。UI 与 MCP 的 display_text 只读，不写入核心；搜索覆盖推导显示文本和属性值。数据库实例仍按标题、完整标识、物理键回退。

## 5. 校验与限制

标识只有一个属性时 unique 必须为 true；多个属性的唯一性是组合声明，平台不扫描真实数据证明它。父对象已有标识时，子对象沿用完整元组，不能另加 identifier 改变身份；父对象没有标识时，子对象可以定义自己的标识。

Ossie 子类若有不同的自有属性标识，而父对象已有标识，核心仍沿用父标识（RT-68）。如 Person 以 person_no 标识、Employee 另以 employee_no 标识：employee_no 保留为普通 unique 属性，不能设 identifier，也不能与 person_no 拼成组合键；原首选标识的损失逐项报告并保留原文。依赖该身份且不能等价改写的映射待补全，不能报完整转换。

业务标识按属性 UUID 字节序确定顺序，原生引用与 Ossie identify_by 使用该顺序。key_columns 则保留明确声明的列顺序，不能按字母排序。快照实体键可以跨日期重复；历史完整行键通常还含快照日期。

文档事实缺少标识也可保存并提示补全，不能把自动生成的事实 UUID 当作已经补齐的业务编号。

## 6. 与 Palantir Foundry、Microsoft Fabric IQ、Apache Ossie 的对照

核查日期：2026-10-15。以下依据官方公开文档；Fabric IQ 的本体功能处于预览阶段。概念对应不表示字段、执行能力或往返行为相同，未实测外部租户。

Palantir 的 [Primary key 与 title key](https://www.palantir.com/docs/foundry/object-link-types/property-metadata)分开；当前创建链接文档按单 primary-key property 处理。本平台的多属性复合标识是明确差异，不把它说成同构能力。

Fabric 的 [Entity type 定义](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-create-entity-types)与[定义协议](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/ontology-definition)包含标识相关配置；本次核对的 Fabric 本体定义协议以属性或列声明标识；Palantir 也以属性声明主键。它们不等于本平台复合键排序合同。

Ossie 的 [identify_by](https://github.com/apache/ossie/blob/main/ontology/ontology.md#identifying-relationships)列出标识关系，可含实体引用。本平台仅在全部成员均可折叠为属性且不改变已有父标识时整组转换；含关系成员按 RT-32 待补全，子类自有首选标识受 RT-68 继承边界限制。
