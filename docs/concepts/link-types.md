# 关系类型

[概念概览](README.md) · [主设计文档 §3.4](../design/2026-10-14-core-model-and-format-adapters.md)

本文说明 core-1 的目标模型与行为，状态为当前实现。JSON 示例中的业务和数据来源均为虚构；片段不是完整导入包，完整包形式见[格式与转换](formats.md)。字段表逐项说明何时填写、空值与默认行为。

2026-10-19 已确认并实施标识、角色及完整读法分离，当前以[关系读法设计](../design/2026-10-19-link-verbalizations.md)为准。

## 1. 概述

客户 C-1 下了订单 O-1 和 O-2。“订单属于客户”就是关系类型，O-1 属于 C-1 则是一条具体关系。定义一次关系，就可以从订单找客户，也可以用反向读法从客户看订单。

需要连接两个业务实例时使用关系；只记录客户名称这样的标量时使用属性。core-1 只保存二元关系，包含数量、成绩或日期的配对事实应建中间对象，例如选课记录。关系定义说明端点、名称与基数，物理 JOIN 另在绑定中描述；没有数据绑定时仍可先定义业务联系。关系图只画对象及其关系。

## 2. 字段

| 字段 | 类型 | 填写要求 | 说明 |
|---|---|---|---|
| `id` | UUID | 必须提供。 | 此字段保存定义的稳定身份，改名不会改变它。 |
| `name` | ASCII 标识符 | 必须提供。 | 对应 Ossie relationship.name，是所属对象内用于引用的唯一标识，例如 reports_to。 |
| `description` | 字符串 | 可以省略。 | 此字段解释业务含义、范围和必要上下文。 |
| `verbalizes` | 字符串数组 | 可省略，默认空数组。 | 完整业务句式，使用 {source}/{target} 引用两端；保留文字、尾部和顺序，最多 50 条，每条 4000 字符。 |
| `synonyms` | 字符串数组 | 可省略，默认空数组。 | 这些业务别名用于搜索和问答理解。 |
| `tags` | 字符串数组 | 可省略，默认空数组。 | 这些标签用于管理和整理定义。 |
| `source_type_id` | UUID | 必须提供。 | 此字段引用关系的源对象类型。 |
| `target_type_id` | UUID | 必须提供。 | 此字段引用关系的目标对象类型，可以与源对象相同。 |
| `source_role_name` | 字符串 或 null | 可省略。 | 来源对象在本关系中的角色，例如下属。 |
| `target_role_name` | 字符串 或 null | 可省略。 | 目标对象在本关系中的角色，例如主管。 |
| `multiplicity` | 枚举 | 必须提供。 | 此字段选择 one_to_one、many_to_one 或 many_to_many，说明关系的声明基数。 |
| `data_join` | DataJoin 或 null | 可以为空或省略。 | 此字段保存物理关联方式，没有可用绑定时为空。 |
| `evidence` | Evidence 数组 | 可省略，默认空数组。 | 这些证据说明该定义的业务依据。 |

### 绑定字段

| 字段 | 类型 | 填写要求 | 说明 |
|---|---|---|---|
| `kind` | 枚举 | 必须提供。 | direct 使用两端属性列逐对相等，mapping_table 使用登记表的列组关联两端。 |
| `source_property_ids` | 有序 UUID 数组 | direct 绑定必须提供。 | 这些源端属性与目标端属性按顺序逐对相等。 |
| `target_property_ids` | 有序 UUID 数组 | direct 绑定必须提供。 | 这些目标端属性必须组成声明的唯一键，并与源端按顺序对齐。 |
| `dataset_id` | UUID | mapping_table 绑定必须填写。 | 此字段引用已登记的关系映射数据集。 |
| `source_columns` | 有序字符串数组 | mapping_table 绑定必须提供。 | 这些映射表列按顺序对应源端所选键。 |
| `target_columns` | 有序字符串数组 | mapping_table 绑定必须提供。 | 这些映射表列按顺序对应目标端所选键。 |
| `source_key` | 对象 | mapping_table 绑定必须提供。 | 此字段选择源端的 mapping_key，或用 properties 指定唯一属性组。 |
| `target_key` | 对象 | mapping_table 绑定必须提供。 | 此字段选择目标端的 mapping_key，或用 properties 指定唯一属性组。 |


## 3. 例子

订单属于客户的完整关系定义如下。端点及数据集依赖见[基础销售样例](../design/core-1-examples/01-basic-sales.json)；映射表直接使用订单数据集，无须新建一张中间表。

```json
{
  "id": "00000000-0000-4000-8000-000000003001",
  "name": "customer",
  "description": "",
  "verbalizes": ["{source}属于{target}", "{target}拥有{source}"],
  "synonyms": [
    "下单客户"
  ],
  "source_type_id": "00000000-0000-4000-8000-000000001002",
  "target_type_id": "00000000-0000-4000-8000-000000001001",
  "multiplicity": "many_to_one",
  "tags": [],
  "data_join": {
    "source_columns": [
      "order_id"
    ],
    "target_columns": [
      "customer_id"
    ],
    "kind": "mapping_table",
    "source_key": {
      "kind": "mapping_key"
    },
    "target_key": {
      "kind": "mapping_key"
    },
    "dataset_id": "b7cc4307-1928-522c-a58b-921b2b697d75"
  },
  "evidence": []
}
```

绑定就绪、来源同连接且无需快照选日时，agent 可以组织如下参考查询：

```sql
SELECT o.order_id, c.customer_id, c.name
FROM dw.orders AS o
LEFT JOIN dw.customers AS c ON o.customer_id = c.customer_id;
```

从客户侧浏览时读作“客户拥有订单”；浏览关联实例只列匹配关系。上面的 LEFT JOIN 用于从订单出发保留未匹配订单，两种使用场景不能机械共用筛选方式。

## 4. 建模建议

| 订单号 | 客户编号 |
|---|---|
| O-1 | C-1 |
| O-2 | C-1 |

正例：定义订单到客户为多对一，从 C-1 反向浏览得到 O-1、O-2，无须再建反向关系。

反例：把它声明为一对一，与两张订单属于同一客户的事实冲突；声明不等于数据库已验证约束。

正例：订单指向客户设为 many_to_one，关系标识 customer，正向含义“{source}属于{target}”，反向含义“{target}拥有{source}”。反例：为了从客户浏览订单，再建一条意义相同的反向关系，会产生两个独立定义。core-1 不存 one_to_many 枚举，统一从多的一端定义。

没有附加信息的学生选课可以用 many_to_many 和映射表。选课若还有成绩、选课日期或重修次数，应把“选课记录”建为中间对象；三方供货事实也使用中间对象和多条二元关系。

direct 适合两端已有有用业务属性且目标唯一的关联；只有物理外键、没有业务属性时，可以把该端表作为 mapping_table。不要为每个辅助 JOIN 列强造属性。

多元关系导入为中间对象。按每个实体角色的有效完整标识逐项生成同类型编号属性，值角色也生成属性；生成角色属性 required=true。ManyToOne 的键为除最后角色外的全部角色表示，含非最后值角色；无基数时全部角色构键。复合标识展开，同类型不同角色不合并。编号属性就是角色 direct 连接的 source_property_ids，target_property_ids 是参与对象的完整标识组，按项对应，关系由这组编号定义，不另加一致性 Rule。

只有映射证明外键逐项对应业务标识才绑定编号列；外键指物理键或其他候选键时，编号绑定待补全，角色关系按原映射保留。不能猜值或伪装为跨表计算列。参与对象无完整标识时不生成该角色编号属性：缺决定角色标识使中间标识整组待补全，已有其他属性也不设 identifier；ManyToOne 最后角色缺标识只使该角色编号待补全，前面完整键仍可生成。其他约束须先确认现有 Rule 语法可表达，不能表达的整项原文待补全，不夸大能力。

仓库.运往(终点仓库, 天数) ManyToOne 的键是起点仓库编码加终点仓库编码；排班(医生, 日期, 科室) ManyToOne 的键是医生编号加日期。无基数时天数或科室也参与完整元组键。导出保留中间对象，不恢复原多元结构；同元组不能靠随机 UUID 变成多次事件。

## 5. 校验与限制

direct 保存有效属性间的等值语义；SQL JOIN 就绪还要求两端有列绑定，缺绑定时可保留属性引用并标明待补全，不给出伪 SQL。首版不接受计算属性作关联键。目标必须是单个 unique 属性或完整标识；one_to_one 的源端也须声明唯一。mapping_table 的列数、顺序须与两端引用键一致；many_to_many 使用映射表。

关系可以跨连接保留语义，MCP 明示 cross_connection；不能提供伪可执行的单 SQL JOIN。任一端未映射时可保留未就绪 direct 的有效属性引用，或保存 data_join=null，不提供具体 SQL JOIN。原角色映射已经成立但编号列不对应业务标识时，保留原映射，不被未就绪 direct 覆盖。任意 SQL JOIN 和范围 JOIN 不在首版范围。

Ossie 的 OneToOne 只允许二元关系。多元关系声明 OneToOne 是输入错误，报告原文与定位，不转换成元组约束，也不设计 AI 补全分支。

基数是建模声明，不是运行时约束执行。脏键、重复映射行仍可能增行，agent 必须考虑重复计算风险。指标只引用自己的数据集列，与本体关系无关。其他数据集的筛选由 agent 在查询阶段沿这些关系组织，不写入指标定义。

## 6. 与 Palantir Foundry、Microsoft Fabric IQ、Apache Ossie 的对照

核查日期：2026-10-15。以下依据官方公开文档；Fabric IQ 的本体功能处于预览阶段。概念对应不表示字段、执行能力或往返行为相同，未实测外部租户。

Palantir 的 [Link type](https://www.palantir.com/docs/foundry/object-link-types/create-link-type)有外键和 join dataset 关联；官方说明 one-to-one 声明不强制执行。本平台可引用 unique 非主键属性，不照搬其外键必须指 primary-key property 的要求。

Fabric 的 [Relationship type](https://learn.microsoft.com/en-us/fabric/iq/ontology/how-to-create-relationship-types)支持来源/目标属性和 mapping table。自关联及基数强制的全部限制未核实，不能由概念相似推导一致。

Ossie 的 [Relationships 与 roles](https://github.com/apache/ossie/blob/main/ontology/ontology.md#relationships)表达面更宽；二元实体关系可直接翻译，一元转布尔属性，多元重化为对象，实体角色名已保留，二元实体关系完整读法保留，属性/值角色名及属性读法仍按报告说明损失。

## 角色名称与关系读法

对象类型说明参与者是什么，角色名说明它在这段关系中是什么，verbalizes 说明参与者如何联系。员工到员工的自关联可设置 name=reports_to、来源角色“下属”、目标角色“主管”，读法为 `{source}汇报给{target}`、`{target}管理{source}`。正向实例分组显示主管，反向显示下属；同一关系不会产生两个独立定义。

角色名是可选业务语义，不猜测回填，也不是权限角色。未配置时回退到对象或关系标识。Ossie 目标角色写入原生 roles[0].name，隐式源角色经平台扩展保存；完整读法按端点机械转换占位符，不截取动词。

界面在标题显示关系标识，编辑时提供输入，查看正文不重复。在两端对象下方同行显示角色名，再分别显示基数句和正反向关系含义。编辑使用 `{来源}`、`{目标}`，一行一条句式，并预览当前对象/角色名称。正反分组按首个端点占位符判定，编辑后按正向组、反向组排列；组内原顺序保留。读法未填时显示“未填写关系含义”。Ossie 要求至少一条读法，导出生成最小关联句并记录 generated_link_readings 交换元数据，重新导入原样的生成句恢复空列表；这不是核心业务字段。

旧 JSON 的 technical_name 读取为新 name，旧中文 name/inverse_name 读取为正反完整模板。历史发布快照与原哈希不覆写，新写入只输出新结构。
